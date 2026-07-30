# Virtual sdcard support (print files directly from a host g-code file)
#
# Copyright (C) 2018-2024  Kevin O'Connor <kevin@koconnor.net>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import os, sys, logging, io
import json, re, copy, tarfile, threading, queuefile
from json_compat import dumps

MAX_TOOL_NUMBER = 32
VALID_GCODE_EXTS = ['gcode', 'g', 'gco']
GENERIC_MOVE_GCODE = {'G0', 'G1', 'G2', 'G3'}
TOOL_CHANGE_COMMANDS = {f'T{i}' for i in range(MAX_TOOL_NUMBER)}
NO_PRE_EXTRUDE_COMMANDS = TOOL_CHANGE_COMMANDS | {
    'BED_MESH_CALIBRATE'
}
USE_REALTIME_TEMP_GCODE = {
    'BED_MESH_CALIBRATE'
}
DEFAULT_ERROR_GCODE = """
{% if 'heaters' in printer %}
   TURN_OFF_HEATERS
{% endif %}
"""

PL_RECORD_FILE_DIR = "/home/lava/printer_data/klippy"
PL_PRINT_FILE_ENV = "pl_print_file_env.json"
PL_PRINT_FILE_MOVE_ENV = "pl_print_file_move_env.json"
PL_PRINT_TEMPERATURE_ENV = "pl_print_temperature_env.json"
PL_PRINT_FLOW_AND_SPEED_FACTOR_ENV = "pl_print_flow_and_speed_factor_env.json"
PL_PRINT_PRESSURE_ADVANCE_ENV = "pl_print_pressure_advance_env.json"
PL_PRINT_LAYER_INFO_ENV = "pl_print_layer_info_env.json"
PL_PRINT_FAN_INFO_ENV = "pl_print_fan_info_env.json"
PL_PRINT_Z_ADJUST_POSITION_ENV = "pl_print_z_adjust_position_env.json"
PL_PRINT_OBJECTS_ENV = "pl_print_objects_env.json"
PL_PRINT_EXCLUDE_OBJECTS_ENV = "pl_print_exclude_objects_env.json"
PL_PRINT_PURIFIER_ENV = "pl_print_purifier_env.json"

class VirtualSD:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.printer.register_event_handler("klippy:shutdown",
                                            self.handle_shutdown)
        self.printer.register_event_handler("power_loss_check:mcu_update_complete",
                                            self.handle_get_mcu_pl_flash_data)
        self.gcode_move = self.printer.load_object(config, 'gcode_move')
        # sdcard state
        sd = config.get('path')
        self.sdcard_dirname = os.path.normpath(os.path.expanduser(sd))
        self.current_file = None
        self.file_position = self.file_size = 0
        self._pl_cache = {}
        # Print Stat Tracking
        self.print_stats = self.printer.load_object(config, 'print_stats')
        # Work timer
        self.reactor = self.printer.get_reactor()
        self.must_pause_work = self.cmd_from_sd = False
        self.next_file_position = 0
        self.work_timer = None
        self.print_task_config = None
        # PL params
        if not os.path.exists(PL_RECORD_FILE_DIR):
            try:
                os.makedirs(PL_RECORD_FILE_DIR)
                config_dir = PL_RECORD_FILE_DIR
            except Exception as e:
                config_dir = self.printer.get_snapmaker_config_dir()
                logging.exception("Failed to create PL_RECORD_FILE_DIR, using default config_dir: %s", str(e))
        else:
            config_dir = PL_RECORD_FILE_DIR

        self.pl_print_file_env_path = os.path.join(config_dir, PL_PRINT_FILE_ENV)
        self.pl_print_file_move_env_path = os.path.join(config_dir, PL_PRINT_FILE_MOVE_ENV)
        self.pl_print_temperature_env_path = os.path.join(config_dir, PL_PRINT_TEMPERATURE_ENV)
        self.pl_print_flow_and_speed_factor_env_path = os.path.join(config_dir, PL_PRINT_FLOW_AND_SPEED_FACTOR_ENV)
        self.pl_print_pressure_advance_env_path = os.path.join(config_dir, PL_PRINT_PRESSURE_ADVANCE_ENV)
        self.pl_print_layer_info_env_path = os.path.join(config_dir, PL_PRINT_LAYER_INFO_ENV)
        self.pl_print_fan_info_env_path = os.path.join(config_dir, PL_PRINT_FAN_INFO_ENV)
        self.pl_print_z_adjust_position_env_path = os.path.join(config_dir, PL_PRINT_Z_ADJUST_POSITION_ENV)
        self.pl_print_objects_env_path = os.path.join(config_dir, PL_PRINT_OBJECTS_ENV)
        self.pl_print_exclude_objects_env_path = os.path.join(config_dir, PL_PRINT_EXCLUDE_OBJECTS_ENV)
        self.pl_print_purifier_env_path = os.path.join(config_dir, PL_PRINT_PURIFIER_ENV)
        self.pl_switch = False
        self.pl_record_file_dir = config_dir
        self.lines = 0
        self.current_line_gcode = ''
        self.current_file_index = 0
        self.max_file_count = 50
        self.pl_mcu_flash_valid_line = 0xFFFFFFFF
        self.pl_mcu_flash_stepper_z_pos = 0xFFFFFFFF
        self.pl_mcu_flash_resume_line = 0xFFFFFFFF
        self.pl_allow_save_env = False
        self.pl_env_valid = False
        self.pl_env_temp_cache = {}
        self.pl_env_fan_info_need_update = False
        self.pl_env_fan_info_allow_min_time = None
        gcode_macro = self.printer.load_object(config, 'gcode_macro')
        try:
            pl_save_variable_macro = self.printer.load_object(config, 'gcode_macro _PL_SAVE_VARIABLE', None)
        except Exception as e:
            pl_save_variable_macro = None
        if pl_save_variable_macro is not None:
            self.pl_start_save_line = pl_save_variable_macro.variables.get('start_save_line', 5)
            self.pl_z_compensation_value = pl_save_variable_macro.variables.get('z_compensation_value', 0)
            self.pl_save_line_interval = pl_save_variable_macro.variables.get('save_line_interval', 1000)
            self.pl_z_hop_temp = pl_save_variable_macro.variables.get('z_hop_temp', 140)
            self.pl_pre_extrude_len = pl_save_variable_macro.variables.get('pre_extrude_len', 20)
            self.pl_speed_pre_extrude = pl_save_variable_macro.variables.get('speed_pre_extrude', 5)
            self.pl_retract = pl_save_variable_macro.variables.get('retract', 2)
            self.pl_unretract = pl_save_variable_macro.variables.get('unretract', 2)
            self.pl_speed_retract = pl_save_variable_macro.variables.get('speed_retract', 30)
            self.pl_speed_unretract = pl_save_variable_macro.variables.get('speed_unretract', 5)
            self.pl_speed_resume_z = pl_save_variable_macro.variables.get('speed_resume_z', 30)
            self.pl_speed_move = pl_save_variable_macro.variables.get('speed_move', 200)
            self.move_extrude_macro = pl_save_variable_macro.variables.get('move_extrude_macro', '')
            self.after_extrude_macro = pl_save_variable_macro.variables.get('after_extrude_macro', '')
            self.z_max_travel = pl_save_variable_macro.variables.get('z_max_travel', 270.5)
        else:
            self.pl_start_save_line = 5
            self.pl_z_compensation_value = -0.2
            self.pl_save_line_interval = 1000
            self.pl_z_hop_temp = 140
            self.pl_pre_extrude_len = 0
            self.pl_speed_pre_extrude = 5
            self.pl_retract = 0
            self.pl_unretract = 0
            self.pl_speed_retract = 30
            self.pl_speed_unretract = 5
            self.pl_speed_resume_z = 30
            self.pl_speed_move = 200
            self.move_extrude_macro = ''
            self.after_extrude_macro = ''
            self.z_max_travel = 270.5
        self.pl_notify_start_line = self.pl_next_save_line = self.pl_start_save_line

        # self.fan_state = {}
        if config.get_prefix_sections("power_loss_check") and config.getboolean("power_loss_check", True):
            self.pl_switch = True
        # Error handling
        gcode_macro = self.printer.load_object(config, 'gcode_macro')
        self.on_error_gcode = gcode_macro.load_template(
            config, 'on_error_gcode', DEFAULT_ERROR_GCODE)
        # Register commands
        self.gcode = self.printer.lookup_object('gcode')
        for cmd in ['M20', 'M21', 'M23', 'M24', 'M25', 'M26', 'M27']:
            self.gcode.register_command(cmd, getattr(self, 'cmd_' + cmd))
        for cmd in ['M28', 'M29', 'M30']:
            self.gcode.register_command(cmd, self.cmd_error)
        self.gcode.register_command(
            "SDCARD_RESET_FILE", self.cmd_SDCARD_RESET_FILE,
            desc=self.cmd_SDCARD_RESET_FILE_help)
        self.gcode.register_command(
            "SDCARD_PRINT_FILE", self.cmd_SDCARD_PRINT_FILE,
            desc=self.cmd_SDCARD_PRINT_FILE_help)
        self.gcode.register_command(
            "SDCARD_PRINT_FILE_WITH_PARAMETERS", self.cmd_SDCARD_PRINT_FILE_WITH_PARAMETERS,
            desc=self.cmd_SDCARD_PRINT_FILE_WITH_PARAMETERS_help)
        self.gcode.register_command(
            "SDCARD_PRINT_TEST", self.cmd_SDCARD_PRINT_TEST)
        self.gcode.register_command(
            "SDCARD_PRINT_PL_RESTORE", self.cmd_SDCARD_PRINT_PL_RESTORE)
        self.gcode.register_command(
            "SDCARD_PRINT_PL_CLEAR_ENV", self.cmd_SDCARD_PRINT_PL_CLEAR_ENV)
    def handle_shutdown(self):
        if self.work_timer is not None:
            self.must_pause_work = True
            try:
                readpos = max(self.file_position - 1024, 0)
                readcount = self.file_position - readpos
                self.current_file.seek(readpos)
                data = self.current_file.read(readcount + 128)
            except:
                logging.exception("virtual_sdcard shutdown read")
                return
            logging.info("Virtual sdcard (%d): %s\nUpcoming (%d): %s",
                         readpos, repr(data[:readcount]),
                         self.file_position, repr(data[readcount:]))
    def handle_get_mcu_pl_flash_data(self):
        try:
            self.parse_power_loss_move_env(validate_only=True)
            self.pl_env_valid = True
            logging.info("Power loss env is valid")
        except Exception as e:
            logging.info("Power loss env is invalid: {}".format(str(e)))
            self.rm_power_loss_info()

    def _update_mcu_flash_valid_line(self):
        self.pl_mcu_flash_valid_line = 0xFFFFFFFF
        self.pl_mcu_flash_stepper_z_pos = 0xFFFFFFFF
        pl_check = self.power_loss_info_check()
        logging.info("pl_check: {}!!!!!!!!!!!".format(pl_check))
        if pl_check[0] and pl_check[1] is not None:
            for key in pl_check[1]:
                line = pl_check[1][key]['line']
                position = pl_check[1][key]['position']
                if line != 0xFFFFFFFF:
                    if key == 'stepper_z':
                        self.pl_mcu_flash_stepper_z_pos = position
                    if self.pl_mcu_flash_valid_line == 0xFFFFFFFF:
                        self.pl_mcu_flash_valid_line = line
                    elif self.pl_mcu_flash_valid_line < line:
                        self.pl_mcu_flash_valid_line = line
        logging.info("pl_mcu_flash_valid_line: {}".format(self.pl_mcu_flash_valid_line))
        return (pl_check[0], self.pl_mcu_flash_valid_line)
    def stats(self, eventtime):
        if self.work_timer is None:
            return False, ""
        return True, "sd_pos=%d" % (self.file_position,)
    def get_file_list(self, check_subdirs=False):
        if check_subdirs:
            flist = []
            for root, dirs, files in os.walk(
                    self.sdcard_dirname, followlinks=True):
                for name in files:
                    ext = name[name.rfind('.')+1:]
                    if ext not in VALID_GCODE_EXTS:
                        continue
                    full_path = os.path.join(root, name)
                    r_path = full_path[len(self.sdcard_dirname) + 1:]
                    size = os.path.getsize(full_path)
                    flist.append((r_path, size))
            return sorted(flist, key=lambda f: f[0].lower())
        else:
            dname = self.sdcard_dirname
            try:
                filenames = os.listdir(self.sdcard_dirname)
                return [(fname, os.path.getsize(os.path.join(dname, fname)))
                        for fname in sorted(filenames, key=str.lower)
                        if not fname.startswith('.')
                        and os.path.isfile((os.path.join(dname, fname)))]
            except:
                logging.exception("virtual_sdcard get_file_list")
                error = '{"coded": "0001-0531-0000-0000", "msg":"%s", "action": "none"}' % ("Unable to get file list")
                raise self.gcode.error(error)
                # raise self.gcode.error("Unable to get file list")
    def get_status(self, eventtime):
        return {
            'file_path': self.file_path(),
            'progress': self.progress(),
            'is_active': self.is_active(),
            'file_position': self.file_position,
            'file_size': self.file_size,
            'pl_env_valid': self.pl_env_valid,
        }
    def file_path(self):
        if self.current_file:
            return self.current_file.name
        return None
    def progress(self):
        if self.file_size:
            return float(self.file_position) / self.file_size
        else:
            return 0.
    def is_active(self):
        return self.work_timer is not None
    def do_pause(self):
        if self.work_timer is not None:
            self.must_pause_work = True
            while self.work_timer is not None and not self.cmd_from_sd:
                self.reactor.pause(self.reactor.monotonic() + .001)
    def do_resume(self):
        if self.work_timer is not None:
            error = '{"coded": "0001-0531-0000-0001", "msg":"%s", "action": "none"}' % ("SD busy")
            raise self.gcode.error(error)
            # raise self.gcode.error("SD busy")
        self.must_pause_work = False
        self.work_timer = self.reactor.register_timer(
            self.work_handler, self.reactor.NOW)
    def do_cancel(self):
        if self.current_file is not None:
            self.do_pause()
            self.current_file.close()
            self.current_file = None
            self.print_stats.note_cancel()
            self.exit_to_idle()
        self.file_position = self.file_size = 0
    def exit_to_idle(self, rm_pl_env_file=True):
        try:
            self.lines = 0
            self.current_line_gcode = ''
            self.current_file_index = 0
            self.pl_notify_start_line = self.pl_next_save_line = self.pl_start_save_line
            self.pl_mcu_flash_resume_line = 0xFFFFFFFF
            self.pl_mcu_flash_valid_line = 0xFFFFFFFF
            self.pl_env_temp_cache = {}
            # self.fan_state = {}
            if rm_pl_env_file:
                self.rm_power_loss_info()
            self.notify_mcu_enable_power_loss(0)
            msm = self.printer.lookup_object('machine_state_manager', None)
            if msm is not None:
                # state_str = str(msm.main_state)
                state_str = str(msm.get_status()['main_state'])
                if state_str == "PRINTING":
                    self.gcode.run_script_from_command("EXIT_TO_IDLE REQ_FROM_STATE=PRINTING")
        except Exception as e:
            logging.exception("{}".format(str(e)))
    # G-Code commands
    def cmd_error(self, gcmd):
        error = '{"coded": "0001-0531-0000-0002", "msg":"%s", "action": "none"}' % ("SD write not supported")
        raise gcmd.error(error)
        # raise gcmd.error("SD write not supported")
    def _pl_recovery_reset_file(self, rm_pl_env_file=True):
        if self.current_file is not None:
            self.do_pause()
            self.current_file.close()
            self.current_file = None
        self.file_position = self.file_size = 0
        self.print_stats.reset(reprint=True)
        self.printer.send_event("virtual_sdcard:reset_file")
    def _reset_file(self, rm_pl_env_file=True):
        if self.current_file is not None:
            self.do_pause()
            self.current_file.close()
            self.current_file = None
        self.file_position = self.file_size = 0
        self.print_stats.reset()
        self.exit_to_idle(rm_pl_env_file)
        self.printer.send_event("virtual_sdcard:reset_file")
    cmd_SDCARD_RESET_FILE_help = "Clears a loaded SD File. Stops the print "\
        "if necessary"
    def cmd_SDCARD_RESET_FILE(self, gcmd):
        if self.cmd_from_sd:
            error = '{"coded": "0001-0531-0000-0003", "msg":"%s", "action": "none"}' % ("SDCARD_RESET_FILE cannot be run from the sdcard")
            raise gcmd.error(error)
            # raise gcmd.error(
            #     "SDCARD_RESET_FILE cannot be run from the sdcard")
        rm_pl_env_file = gcmd.get_int('RM_PL_ENV_FILE', 1)
        self._reset_file(rm_pl_env_file)
    cmd_SDCARD_PRINT_FILE_help = "Loads a SD file and starts the print.  May "\
        "include files in subdirectories."
    def cmd_SDCARD_PRINT_FILE(self, gcmd):
        if self.work_timer is not None:
            error = '{"coded": "0001-0531-0000-0001", "msg":"%s", "action": "none"}' % ("SD busy")
            raise gcmd.error(error)
            # raise gcmd.error("SD busy")
        rm_pl_env_file = gcmd.get_int('RM_PL_ENV_FILE', 1)
        self._reset_file(rm_pl_env_file)
        filename = gcmd.get("FILENAME")
        if filename[0] == '/':
            filename = filename[1:]
        self.rm_power_loss_info()
        self._load_file(gcmd, filename, check_subdirs=True)
        self.gcode.run_script_from_command("TURN_OFF_HEATERS")
        self.do_resume()

    cmd_SDCARD_PRINT_FILE_WITH_PARAMETERS_help = "Loads a SD file and starts the print.  May "\
        "include files in subdirectories."
    def cmd_SDCARD_PRINT_FILE_WITH_PARAMETERS(self, gcmd):
        if self.work_timer is not None:
            error = '{"coded": "0001-0531-0000-0001", "msg":"%s", "action": "none"}' % ("SD busy")
            raise gcmd.error(error)
            # raise gcmd.error("SD busy")
        print_task_config = self.printer.lookup_object('print_task_config', None)
        if print_task_config is None:
            raise gcmd.error("[print_task_config] print_task_config not ready!")
        print_task_config.cmd_SET_PRINT_TASK_PARAMETERS(gcmd)

        rm_pl_env_file = gcmd.get_int('RM_PL_ENV_FILE', 1)
        self._reset_file(rm_pl_env_file)
        filename = gcmd.get("FILENAME")
        if filename[0] == '/':
            filename = filename[1:]
        self.rm_power_loss_info()
        self._load_file(gcmd, filename, check_subdirs=True)
        self.gcode.run_script_from_command("TURN_OFF_HEATERS")
        self.do_resume()

    def cmd_M20(self, gcmd):
        # List SD card
        files = self.get_file_list()
        gcmd.respond_raw("Begin file list")
        for fname, fsize in files:
            gcmd.respond_raw("%s %d" % (fname, fsize))
        gcmd.respond_raw("End file list")
    def cmd_M21(self, gcmd):
        # Initialize SD card
        gcmd.respond_raw("SD card ok")
    def cmd_M23(self, gcmd):
        # Select SD file
        if self.work_timer is not None:
            error = '{"coded": "0001-0531-0000-0001", "msg":"%s", "action": "none"}' % ("SD busy")
            raise gcmd.error(error)
            # raise gcmd.error("SD busy")
        self._reset_file()
        filename = gcmd.get_raw_command_parameters().strip()
        if filename.startswith('/'):
            filename = filename[1:]
        self._load_file(gcmd, filename)
    def cmd_SDCARD_PRINT_TEST(self, gcmd):
        self.gcode.respond_info("self.pl_switch: {}  flag: {} pl_env_valid: {}".format(self.pl_switch, self.get_pl_env_flag(), self.pl_env_valid))
        pl_check = self.power_loss_info_check()
        if pl_check[0] and pl_check[1] is not None:
            for key in pl_check[1]:
                line = pl_check[1][key]['line']
                position = pl_check[1][key]['position']
                self.gcode.respond_info("{}: line {}, position {}".format(key, line, position))
        self.gcode.respond_info("pl_mcu_flash_valid_line: {}".format(self.pl_mcu_flash_valid_line))
        if self.pl_mcu_flash_valid_line != 0xFFFFFFFF:
            find_move_restult = self.pl_find_latest_move_env(self.pl_mcu_flash_valid_line)
            self.gcode.respond_info("find_move_restult index: {}, env_data: {}".format(find_move_restult[0], find_move_restult[1]))
            save_env = self.parse_power_loss_move_env()
            if save_env is None:
                return
            self.gcode.respond_info("file_path: {}".format(save_env['file_path']))
            self.gcode.respond_info("power_loss_run_gcode_info: {}".format(save_env['power_loss_run_gcode_info']))
            self.gcode.respond_info("current_line: {}".format(save_env['current_line']))
            self.gcode.respond_info("cur_file_pos: {}".format(save_env['cur_file_pos']))
            self.gcode.respond_info("last_file_pos: {}".format(save_env['last_file_pos']))
            self.gcode.respond_info("extruder_id: {}".format(save_env['gcode_tracker'].extruder_gcode_id))
            self.gcode.respond_info("homing_stepper_z_info: {}".format(save_env['homing_stepper_z_info']))
            self.gcode.respond_info("last_move_file_index: {}".format(save_env['last_move_file_index']))
            z_info = save_env['homing_stepper_z_info']
            if z_info is not None and self.pl_mcu_flash_stepper_z_pos != 0xFFFFFFFF:
                z_adjust_position = self.get_pl_print_z_adjust_position()
                direction = -1 if z_info['dir_inverted'] else 1
                pl_save_z_pos = (self.pl_mcu_flash_stepper_z_pos - z_info["stepper_z_pos"])*z_info['step_dist']*direction + z_info['z_pos']
                gcode_tracker = save_env['gcode_tracker']
                resum_gcode_position = [
                    last - base
                    for last, base in zip(gcode_tracker.last_position, gcode_tracker.base_position)
                ]
                self.gcode.respond_info("resum_gcode_position: {}".format(resum_gcode_position))
                resume_z =  pl_save_z_pos + z_adjust_position + self.pl_z_compensation_value
                self.gcode.respond_info("pl_save_z_pos: {}, cal z pos: {}, resume z pos: {}!!!!".format(pl_save_z_pos, pl_save_z_pos + z_adjust_position, resume_z))
            else:
                self.gcode.respond_info("Invalid z_info or stepper position data")
    def cmd_SDCARD_PRINT_PL_RESTORE(self, gcmd):
        msm = self.printer.lookup_object('machine_state_manager', None)
        if msm is not None:
            state_str = str(msm.get_status()['main_state'])
            if state_str != "IDLE":
                error_msg = '{"coded": "0001-0531-0000-0005", "msg":"%s", "action": "none"}' % (
                            "Current main state is %s power-loss recovery is not allowed" % (state_str))
                raise gcmd.error(error_msg)
                # raise gcmd.error("Current main state is {} power-loss recovery is not allowed".format(state_str))
        self.restore_print()
    def cmd_SDCARD_PRINT_PL_CLEAR_ENV(self, gcmd):
        msm = self.printer.lookup_object('machine_state_manager', None)
        if msm is not None:
            state_str = str(msm.get_status()['main_state'])
            if state_str == "PRINTING":
                error_msg = '{"coded": "0001-0531-0000-0006", "msg":"%s", "action": "none"}' % (
                            "Do not delete power-loss info during printing")
                raise gcmd.error(error_msg)
                # raise gcmd.error("Do not delete power-loss info during printing")
        self.gcode.run_script_from_command("TIMELAPSE_STOP FORCE=1\r\n")
        self.rm_power_loss_info()
    def _load_file(self, gcmd, filename, check_subdirs=False, reprint=False):
        files = self.get_file_list(check_subdirs)
        flist = [f[0] for f in files]
        files_by_lower = { fname.lower(): fname for fname, fsize in files }
        fname = filename
        try:
            if fname not in flist:
                fname = files_by_lower[fname.lower()]
            fname = os.path.join(self.sdcard_dirname, fname)
            f = io.open(fname, 'r', newline='')
            f.seek(0, os.SEEK_END)
            fsize = f.tell()
            f.seek(0)
        except Exception as e:
            logging.exception(f"virtual_sdcard file open: {str(e)}")
            error_msg = '{"coded": "0001-0531-0000-0004", "msg":"%s", "action": "none"}' % (
                            "Unable to open file")
            raise gcmd.error(error_msg)
            # raise gcmd.error("Unable to open file")
        gcmd.respond_raw("File opened:%s Size:%d" % (filename, fsize))
        gcmd.respond_raw("File selected")
        self.current_file = f
        self.file_position = 0
        self.file_size = fsize
        self.print_stats.set_current_file(filename, reprint)
    def cmd_M24(self, gcmd):
        # Start/resume SD print
        self.do_resume()
    def cmd_M25(self, gcmd):
        # Pause SD print
        self.do_pause()
    def cmd_M26(self, gcmd):
        # Set SD position
        if self.work_timer is not None:
            error = '{"coded": "0001-0531-0000-0001", "msg":"%s", "action": "none"}' % ("SD busy")
            raise gcmd.error(error)
            # raise gcmd.error("SD busy")
        pos = gcmd.get_int('S', minval=0)
        self.file_position = pos
    def cmd_M27(self, gcmd):
        # Report SD print status
        if self.current_file is None:
            gcmd.respond_raw("Not SD printing.")
            return
        gcmd.respond_raw("SD printing byte %d/%d"
                         % (self.file_position, self.file_size))
    def get_file_position(self):
        return self.next_file_position
    def set_file_position(self, pos):
        self.next_file_position = pos
    def is_cmd_from_sd(self):
        return self.cmd_from_sd
    # Background work timer
    def work_handler(self, eventtime):
        logging.info("Starting SD card print, file: %s, position %d",
                     self.current_file.name, self.file_position)
        self.reactor.unregister_timer(self.work_timer)
        exception_manager = self.printer.lookup_object('exception_manager', None)
        print_task_config = self.printer.lookup_object('print_task_config', None)

        if print_task_config is not None:
            print_task_config.set_new_print_info()

        try:
            self.current_file.seek(self.file_position)
        except:
            logging.exception("virtual_sdcard seek")
            self.work_timer = None
            return self.reactor.NEVER
        try:
            self.gcode.run_script_from_command("SET_MAIN_STATE MAIN_STATE=PRINTING")
        except Exception as e:
            logging.exception("{}".format(str(e)))
            self.work_timer = None
            return self.reactor.NEVER
        self.print_stats.note_start()
        gcode_mutex = self.gcode.get_mutex()
        partial_input = ""
        lines = []
        error_message = None
        action = 'cancel'
        is_read_file_error = False
        interval_start_time = self.reactor.monotonic()
        self.pl_env_fan_info_need_update = False
        self.pl_env_fan_info_allow_min_time = None
        self.pl_env_temp_cache = {}

        while not self.must_pause_work:
            if not lines:
                # Read more data
                try:
                    data = self.current_file.read(8192)
                except Exception as e:
                    logging.exception(f"virtual_sdcard read: {str(e)}")
                    error_message = "Unable to read gcode file"
                    exception_id = 531
                    exception_index = 0
                    exception_code = 10
                    exception_level = 3
                    self.printer.send_event("print_stats:update_exception_info",
                                            exception_id,
                                            exception_index,
                                            exception_code,
                                            error_message,
                                            exception_level)
                    if exception_manager is not None:
                        exception_manager.raise_exception_async(
                            id = exception_id,
                            index = exception_index,
                            code = exception_code,
                            message = error_message,
                            oneshot = 1,
                            level = exception_level)
                    is_read_file_error = True
                    break
                if not data:
                    # End of file
                    logging.info(f"Finished SD card print, file: {self.current_file.name}")
                    self.current_file.close()
                    self.current_file = None

                    self.gcode.respond_raw("Done printing file")
                    self.lines = 0
                    self.current_line_gcode = ''
                    break
                lines = data.split('\n')
                lines[0] = partial_input + lines[0]
                partial_input = lines.pop()
                lines.reverse()
                self.reactor.pause(self.reactor.NOW)
                continue
            # Pause if any other request is pending in the gcode class
            if gcode_mutex.test():
                self.reactor.pause(self.reactor.monotonic() + 0.100)
                continue

            if self.must_pause_work:
                continue

            # Dispatch command
            self.cmd_from_sd = True
            line = lines.pop()
            if sys.version_info.major >= 3:
                next_file_position = self.file_position + len(line.encode()) + 1
            else:
                next_file_position = self.file_position + len(line) + 1
            self.next_file_position = next_file_position
            interval_end_time = self.reactor.monotonic()
            self.pl_allow_save_env = True
            self.pl_env_valid = False
            try:
                try:
                    toolhead = self.printer.lookup_object('toolhead')
                    self.lines += 1
                    toolhead.print_file_line = self.lines
                    line = self.process_gcode_line(line)
                    interval_start_time, interval_end_time = \
                        self.record_power_loss_info(interval_start_time, interval_end_time)

                    self.gcode.run_script(line)
                    self.current_line_gcode = line
                    self.record_pl_print_file_move_env(line, self.lines, self.file_position)
                except Exception as e:
                    action = None
                    if hasattr(e, 'action'):
                        action = e.action
                    coded_message = self.printer.extract_encoded_message(str(e))
                    if coded_message is not None:
                        action = coded_message.get("action", action)
                    if action != 'none':
                        logging.info("exit_print: lines=%d, current_line_gcode=%s, file_position=%d" %
                            (self.lines, self.current_line_gcode, self.file_position))
                        raise

            except self.gcode.error as e:
                error_message = str(e)
                action = e.action
                coded_message = self.printer.extract_encoded_message(error_message)
                skip_on_error = False
                try:
                    exception_id = self.gcode.error.default_id
                    exception_index = self.gcode.error.default_index
                    exception_code = self.gcode.error.default_code
                    exception_message = self.printer.extract_coded_message_field(error_message) or self.gcode.error.default_message
                    exception_level = self.gcode.error.default_level

                    structured_code = None
                    if coded_message:
                        structured_code = coded_message.get("coded", None)
                    if exception_manager and structured_code:
                        parsed_structured_code = exception_manager._parse_structured_code(structured_code)
                        if parsed_structured_code is not None:
                            exception_id = parsed_structured_code.get("id", exception_id)
                            exception_index = parsed_structured_code.get("index", exception_index)
                            exception_code = parsed_structured_code.get("code", exception_code)
                            exception_level = parsed_structured_code.get("level", exception_level)
                        else:
                            exception_id = e.id
                            exception_index = e.index
                            exception_code = e.code
                            exception_level = e.level
                    else:
                        exception_id = e.id
                        exception_index = e.index
                        exception_code = e.code
                        exception_level = e.level

                    self.printer.send_event("print_stats:update_exception_info",
                                            exception_id,
                                            exception_index,
                                            exception_code,
                                            exception_message,
                                            exception_level)
                    # Perform special handling for the following exceptions.
                    if exception_id == 532 and exception_index == 0 and exception_code == 4 and exception_level == 2:
                        skip_on_error = True
                except:
                    logging.error("[virtual_sdcard] update exception details failed!")

                if coded_message is not None:
                    action = coded_message.get("action", action)
                if action == 'pause':
                    try:
                        if skip_on_error == True:
                            self.gcode.run_script('PAUSE\n')
                        else:
                            self.gcode.run_script('PAUSE ON_ERROR=1\n')
                    except:
                        logging.exception("PAUSE ON_ERROR cmd")
                        action = 'cancel'
                elif action == 'pause_runout':
                    try:
                        self.gcode.run_script('PAUSE IS_RUNOUT=1\n')
                    except:
                        logging.exception("PAUSE IS_RUNOUT cmd")
                        action = 'cancel'
                else:
                    try:
                        self.gcode.run_script(self.on_error_gcode.render())
                    except:
                        logging.exception("virtual_sdcard on_error")
                break
            except:
                logging.exception("virtual_sdcard dispatch")
                break
            finally:
                toolhead.print_file_line = None
            self.cmd_from_sd = False
            self.file_position = self.next_file_position
            # Do we need to skip around?
            if self.next_file_position != next_file_position:
                try:
                    self.current_file.seek(self.file_position)
                except:
                    logging.exception("virtual_sdcard seek")
                    self.work_timer = None
                    self.exit_to_idle()
                    return self.reactor.NEVER
                lines = []
                partial_input = ""
        logging.info("Exiting SD card print, lines=%d, current_line_gcode=%s, file_position=%d",
                            self.lines, self.current_line_gcode, self.file_position)
        if self.current_file is not None:
            logging.info(f"file: {self.current_file.name}")
        self.pl_allow_save_env = False
        self.work_timer = None
        self.cmd_from_sd = False
        if is_read_file_error == True:
            self.printer.send_event("pause_resume:cancel")
            try:
                self.gcode.run_script(self.on_error_gcode.render())
            except:
                logging.exception("virtual_sdcard on_error")
            self.print_stats.note_cancel()
        elif error_message is not None and action not in ['pause', 'pause_runout']:
            self.print_stats.note_error(error_message)
            self.exit_to_idle()
        elif self.current_file is not None:
            self.print_stats.note_pause(error_message)
        else:
            self.print_stats.note_complete()
            self.exit_to_idle()
        return self.reactor.NEVER

    def get_pl_env_flag(self):
        env_flags = []
        if self.pl_switch:
            for name, obj in self.printer.lookup_objects('power_loss_check'):
                if 'env_flag' in obj.pl_flash_valid:
                    env_flags.append(obj.pl_flash_valid['env_flag'])

        if not env_flags:
            return (1, [])

        max_flag = max(env_flags)
        if max_flag < 4294967294:
            return (max_flag + 1, env_flags)
        return (1, env_flags)

    def notify_mcu_enable_power_loss(self, enable, move_line=0xFFFFFFFF):
        if self.pl_switch:
            env_flag = self.get_pl_env_flag()[0]
            mcu_names = []
            action = "enable" if enable else "disable"
            for name, obj in self.printer.lookup_objects('power_loss_check'):
                obj.enable_power_loss_cmd.send([obj._oid, not not enable, env_flag, move_line])
                mcu_names.append(obj.name)
            # self.gcode.respond_info("Notify the muc: {} to {} power loss, env_flag: {} move_line: {}".format(mcu_names, action, env_flag, move_line))
        else:
            self.gcode.respond_info("Power loss module not detected, Power resume has been disabled")

    def config_pl_allow_save_env(self, allow_save):
        self.pl_allow_save_env = allow_save

    def record_pl_print_file_env(self, file_name, env_flag, sync=False, flush=True, safe_write=True, transfer_pause_time=False):
        data_dict = {
            'env_flag': env_flag,
            'file_path': file_name,
        }
        print_stats = self.printer.lookup_object('print_stats', None)
        if print_stats is not None:
            eventtime = self.reactor.monotonic()
            status = print_stats.get_status(eventtime)
            data_dict['total_duration'] = status['total_duration']
            data_dict['print_duration'] = status['print_duration']
            data_dict['filament_used'] = status['filament_used']
            if transfer_pause_time and print_stats.last_pause_time is not None:
                print_stats.prev_pause_duration += eventtime - print_stats.last_pause_time
                print_stats.last_pause_time = None
            data_dict['prev_pause_duration'] = print_stats.prev_pause_duration
            data_dict['init_duration'] = print_stats.init_duration
            self.save_environment_data(self.pl_print_file_env_path, data_dict, sync, flush, safe_write)

    def force_record_pl_print_file_env(self, transfer_p_t=False):
        print_stats = self.printer.lookup_object('print_stats', None)
        if print_stats is not None and (print_stats.state == 'printing' or print_stats.state == 'paused'):
            self.record_pl_print_file_env(self.current_file.name, self.get_pl_env_flag()[0], transfer_pause_time=transfer_p_t)
            logging.info("Force record power loss print file env")
    def get_pl_print_file_env(self):
        if self.pl_switch:
            try:
                data = self._pl_read_file(self.pl_print_file_env_path)
                return data if data else None
            except Exception as e:
                logging.exception("Failed to read power loss env file")
                return None

    def rm_power_loss_info(self):
        try:
            if not self.printer.is_shutdown():
                rm_paths = [
                    self.pl_print_file_env_path,
                    self.pl_print_file_move_env_path,
                    self.pl_print_temperature_env_path,
                    self.pl_print_flow_and_speed_factor_env_path,
                    self.pl_print_pressure_advance_env_path,
                    self.pl_print_layer_info_env_path,
                    self.pl_print_fan_info_env_path,
                    self.pl_print_z_adjust_position_env_path,
                    self.pl_print_objects_env_path,
                    self.pl_print_exclude_objects_env_path,
                    self.pl_print_purifier_env_path,
                    *[self.pl_print_file_move_env_path.replace('.json', f'_{i}.json')
                        for i in range(self.max_file_count)]
                ]

                for p in rm_paths:
                    try:
                        if os.path.exists(p):
                            queuefile.sync_delete_file(self.printer.get_reactor(), p)
                        if os.path.exists(p + '.tmp'):
                            queuefile.sync_delete_file(self.printer.get_reactor(), p + '.tmp')
                    except Exception as e:
                        logging.warning(f"Failed to delete {p} or {p}.tmp: {e}")
                self.pl_env_valid = False
                self._pl_cache.clear()
                logging.info("rm power_loss info success")
            else:
                logging.info("klippy is shutdown, power_loss info is not allowed to be removed")
        except Exception as err:
            logging.error(f"rm power_loss info fail, err:{err}")

    def backup_print_env_info(self):
        try:
            # output_dir = self.printer.get_snapmaker_config_dir()
            output_dir = self.pl_record_file_dir
            archive_name = "pl_print_env_info.tar.gz"
            archive_path = os.path.join(output_dir, archive_name)

            file_paths = [
                self.pl_print_file_env_path,
                self.pl_print_file_move_env_path,
                self.pl_print_temperature_env_path,
                self.pl_print_flow_and_speed_factor_env_path,
                self.pl_print_pressure_advance_env_path,
                self.pl_print_layer_info_env_path,
                self.pl_print_fan_info_env_path,
                self.pl_print_z_adjust_position_env_path,
                self.pl_print_purifier_env_path,
                *[self.pl_print_file_move_env_path.replace('.json', f'_{i}.json')
                    for i in range(self.max_file_count)]
            ]

            logging.info("Starting environment backup...")
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                logging.info(f"Created output directory: {output_dir}")

            if os.path.exists(archive_path):
                try:
                    os.remove(archive_path)
                    logging.info(f"Removed existing archive: {archive_path}")
                except Exception as e:
                    logging.error(f"Failed to remove existing archive: {e}")
                    return

            valid_files = []
            for fpath in file_paths:
                if os.path.exists(fpath):
                    valid_files.append(fpath)

            if not valid_files:
                logging.warning("No valid files to backup.")
                return

            try:
                with tarfile.open(archive_path, "w:gz") as tar:
                    for fpath in valid_files:
                        arcname = os.path.basename(fpath)
                        tar.add(fpath, arcname=arcname)
                    logging.info(f"Backup created at: {archive_path}")
            except Exception as e:
                logging.error(f"Error creating tar.gz archive: {e}")

        except Exception as e:
            logging.error(f"Unexpected error during backup process: {e}")

    def power_loss_info_check(self):
        if self.pl_switch:
            if not os.path.exists(self.pl_print_file_env_path):
                return (False, None)
            try:
                env_flag = None
                with open(self.pl_print_file_env_path, 'r') as f:
                    data = json.load(f)
                    env_flag = data.get('env_flag')
                save_stepper_info = {}
                for name, obj in self.printer.lookup_objects('power_loss_check'):
                    if 'env_flag' in obj.pl_flash_valid and obj.pl_flash_valid['env_flag'] == env_flag:
                        save_stepper_info.update(obj.pl_flash_save_data)
                return (True, save_stepper_info)
            except Exception as e:
                logging.exception("Failed to read power loss info file")
                return (False, None)

    def process_gcode_line(self, line):
        if not self.pl_switch:
            return line
        fan_state = {}
        current_time = self.reactor.monotonic()
        stripped_line = line.rstrip("\r\n").lstrip()
        if stripped_line.startswith(("M106", "M107")):
            param_list = [" S", " P0", " P1", " P2"]
            is_m107 = stripped_line.startswith("M107")
            cmd_prefix = f"M10{'7' if is_m107 else '6'}"
            for param in param_list:
                target_prefix = f"{cmd_prefix}{param}"
                if stripped_line.startswith(target_prefix):
                    key = f"M106{param}"
                    value = f"M106{param} S0" if is_m107 else stripped_line
                    # self.fan_state[key] = value
                    fan_state[key] = value
                    break
            else:
                if is_m107:
                    fan_state["M106 S"] = "M106 S0"
                    # self.fan_state["M106 S"] = "M106 S0"
            if fan_state:
                self.pl_env_fan_info_need_update = True
                self.pl_env_fan_info_allow_min_time = current_time + 0.5
                # self.record_pl_print_fan_env(fan_state)
        elif stripped_line.startswith(("M600", "PAUSE")):
            self.pl_allow_save_env = False
        elif stripped_line.startswith("PRINT_START"):
            self.record_pl_print_objects_env()
        if stripped_line.startswith("SET_PURIFIER_MODE"):
            data_dict = {"SET_PURIFIER_MODE" : stripped_line}
            self.record_pl_print_purifier_env(data_dict)

        if (self.pl_env_fan_info_need_update and
            self.pl_env_fan_info_allow_min_time is not None and
            current_time > self.pl_env_fan_info_allow_min_time):
            self.pl_env_fan_info_need_update = False
            self.record_pl_print_fan_env(force_update=True)
        return line

    def record_pl_print_fan_env(self, data_dict={}, force_update=False, sync=False, flush=True, safe_write=True):
        if not self._valid_power_loss_condition():
            return
        fan_state = {}
        if force_update:
            fan_info =  {
                            'M106 S':  ['fan', 'M106', 'speed'],
                            "M106 P2": ['fan_generic cavity_fan', 'M106 P2', 'speed'],
                            # "M106 P3": ['purifier', 'M106 P3', 'fan_speed'],
                        }
            for key in fan_info.keys():
                fan_obj = self.printer.lookup_object(fan_info[key][0], None)
                # self.gcode.respond_info("fan key: {}".format(key))
                if fan_obj is not None:
                    curtime = self.reactor.monotonic()
                    fan_sta = fan_obj.get_status(curtime)
                    fan_value = int(fan_sta[fan_info[key][2]] * 255)
                    fan_state[key] = fan_info[key][1] + ' S{}'.format(fan_value)
        fan_state.update(data_dict)
        self.save_environment_data(self.pl_print_fan_info_env_path, fan_state, sync, flush, safe_write)

    def get_pl_print_fan_env(self):
        try:
            data = self._pl_read_file(self.pl_print_fan_info_env_path)
            return data if data else None
        except Exception as e:
            logging.exception("Failed to read print_fan info from file")
            return None

    def wait_until_not_homing(self, timeout_retries=100, log_interval=20):
        retry_count = 0
        homing_xyz_override = self.printer.lookup_object('homing_xyz_override', None)
        if homing_xyz_override is None:
            return False

        while homing_xyz_override.is_homing:
            if retry_count >= timeout_retries:
                self.gcode.respond_info("Timeout waiting for homing to complete!")
                return False

            if retry_count % log_interval == 0:
                self.gcode.respond_info("Waiting for homing to complete...")

            self.reactor.pause(self.reactor.monotonic() + 0.100)
            retry_count += 1

        return True
    def record_pl_print_objects_env(self, sync=False, flush=True, safe_write=True):
        if not self._valid_power_loss_condition_with_pause():
            return
        try:
            exclude_object = self.printer.lookup_object('exclude_object', None)
            if exclude_object is not None:
                objects = {}
                objects["objects"] = exclude_object.get_status(0)['objects']
                self.save_environment_data(self.pl_print_objects_env_path, objects, sync, flush, safe_write)
        except Exception as e:
            logging.exception("Failed to record print objects environment: %s" % str(e))
    def get_pl_print_objects_env(self):
        try:
            data = self._pl_read_file(self.pl_print_objects_env_path)
            return data.get('objects', []) if data else []
        except Exception as e:
            logging.exception("Failed to read print objects environment: %s" % str(e))
            return []
    def record_pl_print_exclude_objects_env(self, sync=False, flush=True, safe_write=True):
        if not self._valid_power_loss_condition_with_pause():
            return
        try:
            exclude_object = self.printer.lookup_object('exclude_object', None)
            if exclude_object is not None:
                exclude_objects = {}
                exclude_objects['excluded_objects'] = exclude_object.get_status(0)['excluded_objects']
                self.save_environment_data(self.pl_print_exclude_objects_env_path, exclude_objects, sync, flush, safe_write)
        except Exception as e:
            logging.exception("Failed to record print exclude objects environment: %s" % str(e))
    def get_pl_print_exclude_objects_env(self):
        try:
            data = self._pl_read_file(self.pl_print_exclude_objects_env_path)
            return data.get('excluded_objects', []) if data else []
        except Exception as e:
            logging.exception("Failed to read print exclude objects environment: %s" % str(e))
            return []
    def record_pl_print_purifier_env(self, data_dict={}, sync=False, flush=True, safe_write=True):
        if not self._valid_power_loss_condition():
            return
        try:
            self.save_environment_data(self.pl_print_purifier_env_path, data_dict, sync, flush, safe_write)
        except Exception as e:
            logging.exception("Failed to record print purifier environment: %s" % str(e))
    def get_pl_print_purifier_env(self):
        if self.pl_switch:
            try:
                data = self._pl_read_file(self.pl_print_purifier_env_path)
                return data if data else None
            except Exception as e:
                logging.exception("Failed to read print purifier environment")
                return None
    def record_pl_print_file_move_env(self, line, line_count, file_pos, sync=False, flush=True, safe_write=True):
        need_save = False
        if self.pl_switch and self.lines >= self.pl_next_save_line:
            need_save = True
            # if self.lines == self.pl_start_save_line or ((self.lines - self.pl_start_save_line) % self.pl_save_line_interval == 0):
            #     need_save = True

        if line.startswith("G28"):
            need_save = True

        curtime = self.reactor.monotonic()
        toolhead = self.printer.lookup_object('toolhead')
        homed_axes_list = str(toolhead.get_kinematics().get_status(curtime)['homed_axes'])
        if (not ('x' in homed_axes_list and 'y' in homed_axes_list and 'z' in homed_axes_list)):
            need_save = False

        extruder_gcode_id = None
        if need_save:
            extruder = toolhead.get_extruder()
            file_path = self.pl_print_file_move_env_path.replace(
                '.json', f'_{self.current_file_index}.json')
            if hasattr(extruder, 'gcode_id'):
                extruder_gcode_id = extruder.gcode_id
            homing_stepper_z_info = None
            homing_xyz_override = self.printer.lookup_object('homing_xyz_override', None)
            if homing_xyz_override is not None:
                homing_stepper_z_info = homing_xyz_override.homing_stepper_z_info
            current_object = None
            exclude_object = self.printer.lookup_object('exclude_object', None)
            if exclude_object is not None:
                current_object = exclude_object.get_status(curtime)['current_object']
            data = {
                'file_pos': file_pos,
                'line_count': line_count,
                'line': line,
                'extruder': extruder_gcode_id,
                'speed': self.gcode_move._get_gcode_speed(),
                'max_accel':toolhead.max_accel,
                'min_cruise_ratio':toolhead.min_cruise_ratio,
                'square_corner_velocity':toolhead.square_corner_velocity,
                'absolute_coord': self.gcode_move.absolute_coord,
                'absolute_extrude': self.gcode_move.absolute_extrude,
                'toolhead_pos': list(toolhead.get_position()),
                'base_position': list(self.gcode_move.base_position),
                'last_position': list(self.gcode_move.last_position),
                'homing_position': list(self.gcode_move.homing_position),
                'homing_stepper_z_info': homing_stepper_z_info,
                'current_object': current_object
            }
            self.pl_next_save_line += self.pl_save_line_interval
            self.save_environment_data(file_path, data, sync, flush, safe_write, replace=True)
            self.current_file_index = (self.current_file_index + 1) % self.max_file_count

    def parse_power_loss_move_env(self, validate_only=False):
        file_path = None
        if not os.path.exists(self.pl_print_file_env_path):
            raise self.printer.command_error("power loss file not found")

        check_result = self._update_mcu_flash_valid_line()
        if self.pl_mcu_flash_valid_line == 0xFFFFFFFF:
            raise self.printer.command_error("mcu_flash_valid_line is 0xFFFFFFFF, no need to recover")

        if self.pl_mcu_flash_stepper_z_pos == 0xFFFFFFFF:
            raise self.printer.command_error("mcu_flash_stepper_z_pos is 0xFFFFFFFF, no need to recover")

        try:
            with open(self.pl_print_file_env_path, 'r') as f:
                env_data = json.load(f)
                file_path = env_data.get('file_path')
                if not file_path:
                    raise self.printer.command_error("No file_path found in power loss env file")
        except Exception as e:
            raise self.printer.command_error(f"Failed to parse power loss env file: {e}")

        last_file_index, pl_save_data = self.pl_find_latest_move_env(self.pl_mcu_flash_valid_line)
        if last_file_index is None:
            raise self.printer.command_error("No valid move_env file was found")

        required_params = [
            'file_pos', 'line_count', 'line','extruder',
            'speed', 'max_accel', 'min_cruise_ratio', 'square_corner_velocity',
            'absolute_extrude', 'toolhead_pos', 'base_position','last_position',
            'homing_position','homing_stepper_z_info','current_object',
        ]

        for param in required_params:
            if param not in pl_save_data:
                raise self.printer.command_error(
                    "Missing required parameter in pl_save_data: {}".format(param))

        if validate_only:
            required_keys = ['stepper_z_pos', 'z_pos', 'dir_inverted', 'step_dist']
            homing_stepper_z_info = pl_save_data.get('homing_stepper_z_info')
            if homing_stepper_z_info is None:
                raise self.printer.command_error("homing_stepper_z_info is None or miss")
            missing_keys = [key for key in required_keys if key not in homing_stepper_z_info]
            if missing_keys:
                raise self.printer.command_error("the saved homing_stepper_z_info data is abnormal")
            return True

        try:
            current_line = None
            first_read = True
            target_line = self.pl_mcu_flash_valid_line
            last_file_pos = cur_file_pos = pl_save_data['file_pos']
            print_objects = self.get_pl_print_objects_env()
            exclude_objects = self.get_pl_print_exclude_objects_env()
            gcode_tracker = GCodeStateTracker(self.printer, pl_save_data)
            factors = self.get_pl_print_flow_and_speed_factor()
            logging.info("factors: {}".format(factors))
            gcode_tracker.set_factors(factors['flow_factor'], factors['speed_factor'], factors['speed_factor_bak'])
            gcode_tracker.set_print_task_config(self.print_task_config)
            gcode_tracker.set_exclude_object(pl_save_data['current_object'], print_objects, exclude_objects)
            with io.open(file_path, 'r', newline='') as f:
                f.seek(pl_save_data['file_pos'])
                current_line = pl_save_data['line_count']
                while current_line <= target_line:
                    line = f.readline()
                    last_file_pos = cur_file_pos
                    cur_file_pos = f.tell()
                    if not line:  # EOF
                        break
                    if first_read == False:
                        gcode_tracker.update_position(line)
                        current_line += 1
                    else:
                        first_read = False
                    if current_line == target_line:
                        power_loss_run_gcode_info = gcode_tracker._parse_gcode_line(line)
                        # self.gcode.respond_info("gcode_tracker target_line: {}".format(parse_gcode))
                        # self.gcode.respond_info("gcode_tracker:\ncurrent_line: {}, cur_file_pos: {} last_file_pos: {}".format(current_line, cur_file_pos, last_file_pos))
                        # self.gcode.respond_info("last_position: {}, base_position: {}".format(gcode_tracker.last_position, gcode_tracker.base_position))
                        return {
                                    'file_path': file_path,
                                    'gcode_tracker': gcode_tracker,
                                    'power_loss_run_gcode_info': power_loss_run_gcode_info,
                                    'current_line': current_line,
                                    'cur_file_pos': cur_file_pos,
                                    'last_file_pos': last_file_pos,
                                    'homing_stepper_z_info': pl_save_data['homing_stepper_z_info'],
                                    'last_move_file_index': last_file_index,
                                    'pl_save_data': pl_save_data,
                               }
        except Exception as e:
            logging.exception("Failed to locate line by number")
            raise self.printer.command_error(f"Line location error: {str(e)}")


    def pl_find_latest_move_env(self, line_cnt):
        last_file_index = None
        pl_save_data = None
        min_diff = float('inf')
        for i in range(self.max_file_count):
            file_path = self.pl_print_file_move_env_path.replace('.json', f'_{i}.json')
            try:
                if os.path.exists(file_path):
                    with open(file_path, 'r') as f:
                        content = json.load(f)
                        file_line_cnt = content.get('line_count', 0)
                        diff = line_cnt - file_line_cnt
                        if diff >= 0 and diff < min_diff:
                            min_diff = diff
                            last_file_index = i
                            pl_save_data = content
            except Exception as e:
                logging.warning(f"Error reading file {file_path}: {e}")
                continue
        return (last_file_index, pl_save_data) if last_file_index is not None else (None, None)

    def force_refresh_move_env_extruder(self, extruder_name, sync=False, flush=True, safe_write=True):
        msm = self.printer.lookup_object('machine_state_manager', None)
        if msm is not None:
            state_str = str(msm.get_status()['main_state'])
            if state_str != "PRINTING":
                raise self.printer.command_error("Cannot refresh move environment while not in printing state")

        if self.print_stats.state != 'paused':
            raise self.printer.command_error("Cannot refresh move environment while not paused")

        extruder = self.printer.lookup_object(extruder_name, None)
        if extruder is None:
            raise self.printer.command_error("Cannot refresh move environment without {}".format(extruder_name))

        mcu_max_line = None
        for name, obj in self.printer.lookup_objects('power_loss_check'):
            params = obj.query_power_loss_stepper_info()
            if params is not None:
                for stepper_info in params.values():
                    line = stepper_info.get("line", 0xFFFFFFFF)
                    if line != 0xFFFFFFFF:
                        if mcu_max_line is None:
                            mcu_max_line = line
                        elif mcu_max_line < line:
                            mcu_max_line = line

        min_line = min(self.lines, mcu_max_line) if mcu_max_line is not None else self.lines
        last_file_index, pl_save_data = self.pl_find_latest_move_env(min_line)
        if last_file_index is None:
            logging.info("No move environment file found")
            return

        state = self.gcode_move.saved_states.get("PAUSE_STATE", None)
        if state is None:
            raise self.printer.command_error("PAUSE_STATE not found")

        state_copy = copy.deepcopy(state)
        toolhead = self.printer.lookup_object('toolhead')
        extruder_switch_gcode = None
        if hasattr(extruder, 'gcode_id'):
            extruder_switch_gcode = extruder.gcode_id

        if pl_save_data.get("line_count", 0xFFFFFFFF) != self.lines:
            _pl_save_data = copy.deepcopy(pl_save_data)
            _pl_save_data['file_pos'] = self.file_position
            _pl_save_data['line_count'] = min_line
            _pl_save_data['line'] = self.current_line_gcode
            if state_copy.get('gcode_id', None) is not None:
                _pl_save_data['extruder'] = state_copy['gcode_id']
            _pl_save_data['speed'] = state_copy['speed'] / state_copy['speed_factor']
            _pl_save_data['max_accel'] = state_copy['accel']
            _pl_save_data['min_cruise_ratio'] = toolhead.min_cruise_ratio
            _pl_save_data['square_corner_velocity'] = toolhead.square_corner_velocity
            _pl_save_data['absolute_coord'] = state_copy['absolute_coord']
            _pl_save_data['absolute_extrude'] = state_copy['absolute_extrude']
            _pl_save_data['homing_position'] = state_copy['homing_position']
            _pl_save_data['base_position'] = state_copy['base_position']
            _pl_save_data['last_position'] = state_copy['last_position']
            data = _pl_save_data
        else:
            data = pl_save_data
        gcode_tracker = GCodeStateTracker(self.printer, data)
        if extruder_switch_gcode is not None:
            gcode_tracker.update_position(extruder_switch_gcode)
            data['extruder'] = extruder_switch_gcode
        data['homing_position'] = gcode_tracker.homing_position
        data['base_position'] = gcode_tracker.base_position
        data['last_position'] = gcode_tracker.last_position
        self.gcode.respond_info("Restored G-Code state: {}".format(data))
        move_env_path = self.pl_print_file_move_env_path.replace('.json', f'_{last_file_index}.json')
        self.rm_power_loss_move_env_file()
        self.save_environment_data(move_env_path, data, sync, flush, safe_write)
        self.current_file_index = (last_file_index + 1) % self.max_file_count

    def rm_power_loss_move_env_file(self, save_file_list=[]):
        failed_files = []
        total_removed = 0
        try:
            for i in range(self.max_file_count):
                file_path = self.pl_print_file_move_env_path.replace('.json', f'_{i}.json')
                if not os.path.exists(file_path):
                    continue

                if not save_file_list or i not in save_file_list:
                    try:
                        queuefile.sync_delete_file(self.printer.get_reactor(), file_path)
                        self._pl_cache.pop(file_path, None)
                        total_removed += 1
                    except Exception as e:
                        failed_files.append(file_path)
                        logging.error(f"Failed to remove move env file {file_path}: {e}")
                        continue
            logging.info(f"rm_power_loss_move_env completed, removed {total_removed} files")

            if failed_files:
                logging.error(f"Failed to remove {len(failed_files)} files: {', '.join(failed_files)}")

        except Exception as e:
            logging.error(f"Unexpected error in rm_power_loss_move_env: {e}")

    def _pl_read_file(self, file_path):
        """Read PL JSON file via direct I/O."""
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                return json.load(f)
        return {}

    def save_environment_data(self, file_path, data_dict={}, sync=False,
                              flush=True, safe_write=True, replace=False):
        if not data_dict:
            return True
        if replace:
            existing_data = dict(data_dict)
        elif file_path in self._pl_cache:
            existing_data = self._pl_cache[file_path]
            existing_data.update(data_dict)
        else:
            try:
                existing_data = self._pl_read_file(file_path)
            except Exception as e:
                logging.exception("Failed to read environment file: %s" % file_path)
                return False
            existing_data.update(data_dict)

        self._pl_cache[file_path] = existing_data

        try:
            json_content = dumps(existing_data, indent=2)
            if sync:
                queuefile.sync_write_file(self.printer.get_reactor(), file_path, json_content,
                                          flush=flush, safe_write=safe_write)
            else:
                queuefile.async_write_file(file_path, json_content,
                                           flush=flush, safe_write=safe_write)
            return True
        except Exception as e:
            logging.exception("Failed to write environment file: %s" % file_path)
            return False

    def _valid_power_loss_condition(self):
        print_stats = self.printer.lookup_object('print_stats', None)
        if not (self.pl_switch and print_stats and print_stats.state == 'printing'):
            return False
        return True

    def _valid_power_loss_condition_with_pause(self):
        print_stats = self.printer.lookup_object('print_stats', None)
        if not (self.pl_switch and print_stats and
                (print_stats.state == 'printing' or print_stats.state == 'paused')):
            return False
        return True

    def record_pl_print_temperature_env(self, data_dict={}, force_update=False, ignore_pl_condition=False, sync=False, flush=True, safe_write=True):
        if not ignore_pl_condition and not self._valid_power_loss_condition():
            return

        temp_data = {}
        rec_extrusion_temp = {}
        if force_update:
            pheaters = self.printer.lookup_object('heaters', None)
            if pheaters is not None:
                for name, heater in pheaters.heaters.items():
                    status = heater.get_status(self.reactor.monotonic())
                    temp_data[name] = status['target']
        temp_data.update(data_dict)
        if sync == False:
            self.pl_env_temp_cache.update(temp_data)
            temp_data = copy.deepcopy(self.pl_env_temp_cache)
        for key in temp_data.keys():
            if key.startswith("extruder"):
                extruder = self.printer.lookup_object(key, None)
                if (extruder is not None and hasattr(extruder, 'heater') and
                    (extruder.heater.min_extrude_temp + 10 <= temp_data[key]) and
                    hasattr(extruder, 'gcode_id')):
                    rec_extrusion_temp[extruder.gcode_id] = temp_data[key]
        temp_data.update(rec_extrusion_temp)
        self.pl_env_temp_cache = copy.deepcopy(temp_data)
        self.save_environment_data(self.pl_print_temperature_env_path, temp_data, sync, flush, safe_write)

    def get_pl_print_temperature_env(self):
        pheaters = self.printer.lookup_object('heaters', None)
        current_heaters = []
        if pheaters is not None:
            current_heaters = [name for name, obj in pheaters.heaters.items()]
        result = {name: 0 for name in current_heaters}
        saved_temps = {}
        try:
            saved_temps = self._pl_read_file(self.pl_print_temperature_env_path)
            if saved_temps:
                for name in current_heaters:
                    if name in saved_temps:
                        result[name] = saved_temps[name]
        except Exception as e:
            saved_temps = {}
            logging.exception("Failed to read temperature info, error: {}".format(str(e)))
        return (result, saved_temps)

    def record_pl_print_flow_and_speed_factor(self, data_dict={}, force_update=False, sync=False, flush=True, safe_write=True):
        if not self._valid_power_loss_condition():
            return
        temp_data = {}
        if force_update:
            temp_data['speed_factor'] = self.gcode_move.speed_factor
            temp_data['flow_factor'] = self.gcode_move.extrude_factor
            temp_data['speed_factor_bak'] = self.gcode_move.speed_factor_bak
        temp_data.update(data_dict)
        self.save_environment_data(self.pl_print_flow_and_speed_factor_env_path, temp_data, sync, flush, safe_write)

    def get_pl_print_flow_and_speed_factor(self):
        try:
            data = self._pl_read_file(self.pl_print_flow_and_speed_factor_env_path)
            if not data:
                return {'speed_factor': None, 'flow_factor': None, 'speed_factor_bak': None}
            speed = data.get('speed_factor') if isinstance(data, dict) else None
            flow = data.get('flow_factor') if isinstance(data, dict) else None
            speed_bak = data.get('speed_factor_bak') if isinstance(data, dict) else None
            return {'speed_factor': speed, 'flow_factor': flow, 'speed_factor_bak': speed_bak}
        except Exception as e:
            logging.exception("Failed to read flow and speed factor info, error: {}".format(str(e)))
            return {'speed_factor': None, 'flow_factor': None, 'speed_factor_bak': None}

    def record_pl_print_pressure_advance(self, data_dict={}, force_update=False, sync=False, flush=True, safe_write=True):
        if not self._valid_power_loss_condition():
            return
        data_dict_load = {}
        if force_update:
            extruder_list = self.printer.lookup_object('extruder_list', [])
            for i in range(len(extruder_list)):
                if hasattr(extruder_list[i], 'extruder_stepper') and extruder_list[i].extruder_stepper is not None:
                    extruder_stepper = extruder_list[i].extruder_stepper
                    key = extruder_stepper.name
                    value = [extruder_stepper.pressure_advance, extruder_stepper.pressure_advance_smooth_time]
                    data_dict_load.update({key: value})
        data_dict_load.update(data_dict)
        self.save_environment_data(self.pl_print_pressure_advance_env_path, data_dict_load, sync, flush, safe_write)

    def get_pl_print_pressure_advance(self):
        try:
            saved_data = self._pl_read_file(self.pl_print_pressure_advance_env_path)
            if not saved_data or not isinstance(saved_data, dict):
                return None
            extruder_steppers = []
            for extruder in self.printer.lookup_object('extruder_list', []):
                if hasattr(extruder, 'extruder_stepper') and extruder.extruder_stepper is not None:
                    extruder_steppers.append(extruder.extruder_stepper.name)
            return {k: v for k, v in saved_data.items() if k in extruder_steppers}
        except json.JSONDecodeError:
            logging.error("Invalid JSON in pressure advance file")
        except Exception as e:
            logging.error("Failed to read pressure advance: %s", str(e))
        return None

    def record_pl_print_layer_info(self, data_dict={}, sync=False, flush=True, safe_write=True):
        if not self._valid_power_loss_condition():
            return
        self.save_environment_data(self.pl_print_layer_info_env_path, data_dict, sync, flush, safe_write)

    def get_pl_print_layer_info(self):
        if self.pl_switch:
            try:
                data = self._pl_read_file(self.pl_print_layer_info_env_path)
                return data if data else None
            except Exception as e:
                logging.exception("Failed to read power loss layer info file")
                return None

    def flush_pl_print_env(self):
        self.record_pl_print_fan_env(force_update=True)
        self.record_pl_print_temperature_env(force_update=True)
        self.record_pl_print_flow_and_speed_factor(force_update=True)
        self.record_pl_print_pressure_advance(force_update=True)

    def record_power_loss_info(self, interval_start_time, interval_end_time):
        if self.pl_switch and self.lines >= self.pl_notify_start_line:
            if self.lines == self.pl_notify_start_line:
                self.notify_mcu_enable_power_loss(1, self.pl_mcu_flash_resume_line)
                self.record_pl_print_file_env(self.current_file.name, self.get_pl_env_flag()[0])
                self.flush_pl_print_env()
                interval_start_time = interval_end_time

            if interval_end_time-interval_start_time > 15:
                interval_start_time = interval_end_time
                self.record_pl_print_file_env(self.current_file.name, self.get_pl_env_flag()[0])
        return interval_start_time, interval_end_time

    def record_pl_print_z_adjust_position(self, adjust_position, sync=False, flush=True, safe_write=True):
        data = {}
        try:
            data = self._pl_read_file(self.pl_print_z_adjust_position_env_path)
        except json.JSONDecodeError:
            self.gcode.respond_info(
                "Warning: Invalid JSON in z_adjust_position file, resetting data")
            data = {}
        except Exception as e:
            self.gcode.respond_info(
                f"Warning: Failed to read z_adjust_position file: {str(e)}")
            data = {}
        if 'z_adjust_position' in data:
            data['z_adjust_position'] += adjust_position
        else:
            data['z_adjust_position'] = adjust_position
        self.save_environment_data(self.pl_print_z_adjust_position_env_path, data, sync, flush, safe_write)

    def get_pl_print_z_adjust_position(self):
        try:
            data = self._pl_read_file(self.pl_print_z_adjust_position_env_path)
            if not data:
                return 0.0
            return float(data.get('z_adjust_position', 0.0))
        except Exception as e:
            return 0.0

    def rm_pl_print_z_adjust_position(self):
        try:
            if os.path.exists(self.pl_print_z_adjust_position_env_path):
                os.remove(self.pl_print_z_adjust_position_env_path)
                logging.info("Removed z_adjust_position file: %s",
                            self.pl_print_z_adjust_position_env_path)
        except Exception as e:
            logging.error("Failed to remove z_adjust_position file: %s", str(e))

    def flush_pl_z_homing_stepper_z_info(self, z_offset=0):
        toolhead = self.printer.lookup_object('toolhead')
        toolhead.wait_moves()
        kin = toolhead.get_kinematics()
        steppers = kin.get_steppers()
        stepper_mcu_pos = [s.get_mcu_position() for s in steppers]
        z_pos = toolhead.get_position()[2]
        homing_xyz_override = self.printer.lookup_object('homing_xyz_override', None)
        if homing_xyz_override is not None:
            homing_xyz_override.homing_stepper_z_info = {
                    'stepper_z_pos': stepper_mcu_pos[2],
                    'z_pos': z_pos - z_offset,
                    'dir_inverted': kin.rails[2].get_steppers()[0].get_dir_inverted()[0],
                    'step_dist':  kin.rails[2].get_steppers()[0].get_step_dist(),
                }
            return homing_xyz_override.homing_stepper_z_info

    def to_relative_path(self, full_path, base_dir):
        if full_path.startswith(base_dir):
            return os.path.relpath(full_path, base_dir)
        return full_path

    def pl_bed_mesh_restore(self):
        homing_xyz_override = self.printer.lookup_object('homing_xyz_override', None)
        if homing_xyz_override is None:
            return
        homing_xyz_override._load_bed_mesh_profile()
    def restore_print(self):
        msm = self.printer.lookup_object('machine_state_manager', None)
        self.print_task_config = self.printer.lookup_object('print_task_config', None)
        try:
            if msm is not None:
                self.gcode.run_script_from_command("SET_MAIN_STATE MAIN_STATE=PRINTING ACTION=PRINT_PL_RESTORE")

            env = self.parse_power_loss_move_env()
            if env is None:
                err_msg = "restore_print failed, environmental prerequisites not met"
                logging.info(err_msg)
                raise self.printer.command_error("restore_print failed: {}".format(err_msg))

            gcode_tracker = env['gcode_tracker']
            power_loss_run_gcode_info = env['power_loss_run_gcode_info']
            current_line = env['current_line']
            cur_file_pos = env['cur_file_pos']
            last_file_pos = env['last_file_pos']
            last_move_file_index = env['last_move_file_index']
            pl_save_data = env['pl_save_data']
            resum_gcode_position = [
                last - base
                for last, base in zip(gcode_tracker.last_position, gcode_tracker.base_position)
            ]

            self.gcode.respond_info("current_line: {}".format(current_line))
            self.gcode.respond_info("cur_file_pos: {}".format(cur_file_pos))
            self.gcode.respond_info("last_file_pos: {}".format(last_file_pos))
            self.gcode.respond_info("extruder_id: {}".format(gcode_tracker.extruder_gcode_id))
            self.gcode.respond_info("gcode_tracker last_position: \n{}".format(gcode_tracker.last_position))
            self.gcode.respond_info("gcode_tracker base_position: {}".format(gcode_tracker.base_position))
            self.gcode.respond_info("gcode_tracker homing_position: {}".format(gcode_tracker.homing_position))
            self.gcode.respond_info("power_loss_run_gcode_info: {}".format(power_loss_run_gcode_info))
            self.gcode.respond_info("last_move_file_index: {}".format(last_move_file_index))
            self.gcode.respond_info("resum_gcode_position: {}".format(resum_gcode_position))
            self.gcode.respond_info("gcode_tracker.extrude_factor {}".format(gcode_tracker.extrude_factor))
            self.gcode.respond_info("gcode_tracker.speed_factor {}".format(gcode_tracker.speed_factor))
            self.gcode.respond_info("gcode_tracker.speed_factor_bak {}".format(gcode_tracker.speed_factor_bak))
            self.gcode.respond_info("gcode_tracker.current_object {}".format(gcode_tracker.current_object))
            # self.gcode.respond_info("gcode_tracker.objects {}".format(gcode_tracker.objects))
            self.gcode.respond_info("gcode_tracker.excluded_objects {}".format(gcode_tracker.excluded_objects))
            self.gcode.respond_info("gcode_tracker.speed {}".format(gcode_tracker.speed))

            self.gcode.respond_info("power_loss start do_resume...")
            self.gcode.respond_info("power_loss start print, filename:%s" % env['file_path'])

            toolhead = self.printer.lookup_object('toolhead')
            pl_temp_env_info, all_temp_env = self.get_pl_print_temperature_env()
            self.gcode.respond_info("pl_temp_env_info : {}\nall_temp_env: {}".format(pl_temp_env_info, all_temp_env))
            bed_temp = pl_temp_env_info.get("heater_bed", 0.0)
            self.gcode.respond_info("power_loss do_resume heater bed: {}".format(bed_temp))
            self.gcode.run_script_from_command("M140 S{}".format(bed_temp))

            purifier_env = self.get_pl_print_purifier_env()
            if purifier_env is not None:
                self.gcode.respond_info("power_loss do_resume purifier: {}".format(purifier_env))
                if "SET_PURIFIER_MODE" in purifier_env:
                    self.gcode.run_script_from_command(purifier_env["SET_PURIFIER_MODE"])

            extruder_list = self.printer.lookup_object('extruder_list', [])
            extruder_temps = {}
            for extruder in extruder_list:
                name = extruder.get_name()
                if not hasattr(extruder, 'gcode_id') or not name:
                    continue
                temp = pl_temp_env_info.get(name, 0.0)
                extruder_temps[name] = {'gcode_id': extruder.gcode_id, 'temp': temp}

            if len(extruder_temps) > 0:
                extruder_gcode_id = gcode_tracker.extruder_gcode_id
                activate_status = toolhead.get_extruder().get_extruder_activate_status()
                retry_extruder_id = toolhead.get_extruder().check_allow_retry_switch_extruder()
                extruder = None
                if activate_status[0][1] == 0:
                    extruder = self.printer.lookup_object(activate_status[0][0], None)
                elif retry_extruder_id is not None and retry_extruder_id < len(extruder_list):
                    extruder = extruder_list[retry_extruder_id]

                if extruder is not None:
                    self.gcode.respond_info("power_loss do_resume activate {}: {}!!!!!!".format(extruder.name, extruder_gcode_id))
                    curtime = self.printer.get_reactor().monotonic()
                    status = extruder.get_status(curtime)
                    if status['temperature'] + 2 < self.pl_z_hop_temp:
                        self.gcode.respond_info("power_loss do_resume preheat {}: {}".format(extruder.name, self.pl_z_hop_temp))
                        self.gcode.run_script_from_command("M109 {} S{} A0".format(extruder.gcode_id, self.pl_z_hop_temp))

            self.gcode.respond_info("power_loss do_resume G28 X Y")
            z_adjust_position = self.get_pl_print_z_adjust_position()
            z_info = env['homing_stepper_z_info']
            homing_xyz_override = self.printer.lookup_object('homing_xyz_override', None)
            z_hop = homing_xyz_override.z_hop if homing_xyz_override is not None else None
            if z_info is not None and self.pl_mcu_flash_stepper_z_pos != 0xFFFFFFFF:
                direction = -1 if z_info['dir_inverted'] else 1
                pl_save_z_pos = (self.pl_mcu_flash_stepper_z_pos - z_info["stepper_z_pos"])*z_info['step_dist']*direction + z_info['z_pos']
                cal_z_postion =  pl_save_z_pos + z_adjust_position

                if homing_xyz_override is not None:
                    homing_z_position = cal_z_postion + (z_hop if z_hop is not None else 0)
                    if homing_z_position > self.z_max_travel:
                        adjusted_z_hop = round(self.z_max_travel - cal_z_postion, 2)
                        z_hop = max(0.0, min(homing_xyz_override.z_hop, adjusted_z_hop))
                        self.gcode.respond_info("Z position would exceed max travel. Adjusting z_hop from {} to {}".format(homing_xyz_override.z_hop, z_hop))
                self.gcode.respond_info("cal_z_postion: {}".format(cal_z_postion))
            else:
                raise self.printer.command_error("Invalid z_info or stepper position data")

            gcode_cmd = "G28 X Y PL_SAVE_Z_HOP 1"
            if z_hop is not None:
                gcode_cmd += " Z_HOP {}".format(z_hop)
            self.gcode.run_script_from_command(gcode_cmd)
            self.gcode.run_script_from_command("{} A0".format(gcode_tracker.extruder_gcode_id))
            toolhead.wait_moves()

            cur_extruder = toolhead.get_extruder()
            activate_status = cur_extruder.get_extruder_activate_status()
            retry_extruder_id = cur_extruder.check_allow_retry_switch_extruder()
            if ((activate_status[0][1] == 0 and cur_extruder.name == activate_status[0][0]) or
                retry_extruder_id == cur_extruder.extruder_num):
                pass
            else:
                raise self.printer.command_error("pre-extrude err, Abnormal activate_status: {}, cur_extruder: {}".format(
                        activate_status[0], cur_extruder.name))
            self.gcode.run_script_from_command("{}".format(self.move_extrude_macro))
            toolhead.wait_moves()
            use_realtime_temp = (power_loss_run_gcode_info.get('cmd', '') in USE_REALTIME_TEMP_GCODE)
            # self.gcode.respond_info("use_realtime_temp: {}".format(use_realtime_temp))
            for key in extruder_temps.keys():
                gcode_id = extruder_temps[key]['gcode_id']
                if gcode_id == gcode_tracker.extruder_gcode_id and gcode_id in all_temp_env and not use_realtime_temp:
                    temp = all_temp_env[gcode_id]
                    self.gcode.respond_info("{}: restore rec extrusion temp: {}".format(gcode_id, temp))
                else:
                    temp = extruder_temps[key]['temp']
                self.gcode.respond_info("power_loss do_resume heat {}: {}".format(gcode_id, temp))
                self.gcode.run_script_from_command("M104 {} S{} A0".format(gcode_id, temp))

            self.gcode.respond_info("Restoring pressure advance parameters...")
            pressure_advance_data = self.get_pl_print_pressure_advance()
            if pressure_advance_data is not None:
                for extruder in self.printer.lookup_object('extruder_list', []):
                    extruder_name = extruder.get_name()
                    if hasattr(extruder, 'extruder_stepper') and extruder.extruder_stepper is not None:
                        stepper_name = extruder.extruder_stepper.name
                        if stepper_name in pressure_advance_data:
                            pa, smooth_time = pressure_advance_data[stepper_name]
                            try:
                                self.gcode.run_script_from_command(
                                    "SET_PRESSURE_ADVANCE EXTRUDER=%s ADVANCE=%.6f SMOOTH_TIME=%.6f" %
                                    (stepper_name, pa, smooth_time))
                                self.gcode.respond_info(
                                    "Restored pressure advance for %s: advance=%.6f, smooth_time=%.6f" %
                                    (stepper_name, pa, smooth_time))
                            except Exception as e:
                                logging.error("Failed to restore pressure advance for %s: %s",
                                            stepper_name, str(e))

            self.gcode.respond_info("Restoring start fan")
            fan_info = self.get_pl_print_fan_env()
            if fan_info is not None:
                for cmd in fan_info.values():
                    self.gcode.run_script_from_command("{}".format(cmd))

            heater_bed = self.printer.lookup_object('heater_bed', None)
            if heater_bed is not None:
                curtime = self.printer.get_reactor().monotonic()
                status = heater_bed.get_status(curtime)
                if status['temperature'] + 2 >= bed_temp:
                    self.gcode.run_script_from_command("M140 S{}".format(bed_temp))
                else:
                    self.gcode.run_script_from_command("M190 S{}".format(bed_temp))
            for key in extruder_temps.keys():
                tmp_extruder = self.printer.lookup_object(key, None)
                curtime = self.printer.get_reactor().monotonic()
                # self.gcode.respond_info("key: {}".format(key))
                # self.gcode.respond_info("tmp_extruder: {}".format(tmp_extruder))
                if tmp_extruder is not None:
                    status = tmp_extruder.get_status(curtime)
                    gcode_id = extruder_temps[key]['gcode_id']
                    temp = extruder_temps[key]['temp']
                    if gcode_id == gcode_tracker.extruder_gcode_id and gcode_id in all_temp_env:
                        if (temp < cur_extruder.heater.min_extrude_temp and
                            all_temp_env[gcode_id] > cur_extruder.heater.min_extrude_temp and
                            not use_realtime_temp):
                            temp = all_temp_env[gcode_id]
                    if status['temperature'] + 2 >= temp:
                        self.gcode.run_script_from_command("M104 {} S{} A0".format(gcode_id, temp))
                    else:
                        self.gcode.run_script_from_command("M109 {} S{} A0".format(gcode_id, temp))

            pos = toolhead.get_position()
            z_adjust_position = self.get_pl_print_z_adjust_position()
            # pl_save_z_pos = gcode_tracker.last_position[2]
            z_info = env['homing_stepper_z_info']
            if z_info is not None and self.pl_mcu_flash_stepper_z_pos != 0xFFFFFFFF:
                direction = -1 if z_info['dir_inverted'] else 1
                pl_save_z_pos = (self.pl_mcu_flash_stepper_z_pos - z_info["stepper_z_pos"])*z_info['step_dist']*direction + z_info['z_pos']
                pos[2] =  pl_save_z_pos + z_adjust_position + self.pl_z_compensation_value
                self.gcode.respond_info("pl_save_z_pos: {}, cal z pos: {}, resume z pos: {}!!!!".format(pl_save_z_pos, pl_save_z_pos + z_adjust_position, pos[2]))
            else:
                raise self.printer.command_error("Invalid z_info or stepper position data")
            toolhead.set_position(pos, homing_axes=[2])
            stepper_z_info = self.flush_pl_z_homing_stepper_z_info(self.pl_z_compensation_value)
            pos = toolhead.get_position()
            self.gcode.respond_info("after set position: {}".format(pos[2]))
            self.pl_bed_mesh_restore()
            self.gcode_move.base_position = gcode_tracker.base_position
            self.gcode_move.homing_position = gcode_tracker.homing_position
            self.rm_pl_print_z_adjust_position()
            self.rm_power_loss_move_env_file()
            move_env_path = self.pl_print_file_move_env_path.replace('.json', f'_{last_move_file_index}.json')
            pl_save_data['homing_stepper_z_info'] = stepper_z_info
            self.save_environment_data(move_env_path, pl_save_data)
            # self.current_file_index = (last_move_file_index + 1) % self.max_file_count
            self.notify_mcu_enable_power_loss(1, current_line)
            file_env = self.get_pl_print_file_env()
            file_env['env_flag'] = self.get_pl_env_flag()[0]
            self.save_environment_data(self.pl_print_file_env_path, file_env)

            self.gcode.respond_info("Restoring start pre-extrude")
            pre_extrude = False
            extra_retract_len = 0
            curtime = self.printer.get_reactor().monotonic()
            cur_extruder = toolhead.get_extruder()
            status = cur_extruder.get_status(curtime)
            can_extrude = (status.get('can_extrude') and cur_extruder.heater.min_extrude_temp < status['target'])
            need_extrude = not (power_loss_run_gcode_info.get('cmd', '') in NO_PRE_EXTRUDE_COMMANDS)
            self.gcode.run_script_from_command("M220 S100")
            self.gcode.run_script_from_command("M221 S100")
            self.gcode.run_script_from_command("M204 S10000")
            if power_loss_run_gcode_info.get('cmd', '') in GENERIC_MOVE_GCODE:
                params = power_loss_run_gcode_info.get('params', {})
                origline = power_loss_run_gcode_info.get('origline', '')
                extruded_length = gcode_tracker.get_float(origline, params, 'E', None)
                if gcode_tracker.absolute_extrude == False and extruded_length is not None and extruded_length < 0:
                    extra_retract_len = abs(extruded_length)
                self.gcode.respond_info("extra_retract_len: {}, extruded_length: {}".format(extra_retract_len, extruded_length))
            if can_extrude and need_extrude:
                self.gcode.run_script_from_command("M83")
                self.gcode.run_script_from_command("G0 E{} F{}".format(self.pl_pre_extrude_len, self.pl_speed_pre_extrude*60))
                self.gcode.run_script_from_command("G0 E{} F{}".format(-1*(self.pl_retract+extra_retract_len), self.pl_speed_retract*60))
                self.gcode.run_script_from_command("{}".format(self.after_extrude_macro))
                pre_extrude = True

            self.gcode.run_script_from_command(
                f"SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY={gcode_tracker.square_corner_velocity} "
                f"MINIMUM_CRUISE_RATIO={gcode_tracker.min_cruise_ratio}"
            )

            self.gcode_move.absolute_coord = True
            self.gcode.respond_info("Restoring x y: {}".format(resum_gcode_position[0], resum_gcode_position[1]))
            self.gcode.run_script_from_command("G0 Y{} F{}".format(resum_gcode_position[1], self.pl_speed_move*60))
            self.gcode.run_script_from_command("G0 X{} F{}".format(resum_gcode_position[0], self.pl_speed_move*60))

            self.gcode.respond_info("Restoring z: {}".format(resum_gcode_position[2]))
            need_restore_z = True
            if power_loss_run_gcode_info.get('cmd', '') == 'G28':
                params = power_loss_run_gcode_info.get('params', {})
                if 'Z' in params or (not {'X', 'Y', 'Z'} & params.keys()):
                    need_restore_z = False
            if need_restore_z:
                self.gcode.run_script_from_command("G0 Z{} F{}".format(resum_gcode_position[2], self.pl_speed_resume_z*60))
            toolhead.wait_moves()
            # self.rm_pl_print_z_adjust_position()
            # May cause the process to power-loss again and not be able to recover!!!
            # self.rm_power_loss_move_env_file()
            # stepper_z_info = self.flush_pl_z_homing_stepper_z_info()

            if pre_extrude:
                self.gcode.run_script_from_command("M83")
                self.gcode.run_script_from_command("G0 E{} F{}".format(self.pl_unretract, self.pl_speed_unretract*60))
            self.gcode.run_script_from_command("G92 E{}".format(resum_gcode_position[3]))

            self.gcode_move.absolute_coord = gcode_tracker.absolute_coord
            self.gcode_move.absolute_extrude = gcode_tracker.absolute_extrude

            self.gcode_move.extrude_factor = gcode_tracker.extrude_factor
            self.gcode_move.speed_factor = gcode_tracker.speed_factor
            self.gcode_move.speed_factor_bak = gcode_tracker.speed_factor_bak
            self.gcode_move.speed = gcode_tracker.speed
            self.gcode.run_script_from_command("M204 S{}".format(gcode_tracker.max_accel))

            if self.print_task_config is not None:
                self.print_task_config.apply_reprint_info()

            if self.work_timer is not None:
                raise self.printer.command_error("SD busy")

            self._pl_recovery_reset_file(False)
            relative_path = self.to_relative_path(env['file_path'], self.sdcard_dirname)
            if relative_path.startswith('/'):
                relative_path = relative_path[1:]
            self._load_file(self.gcode, relative_path, check_subdirs=True, reprint=True)

            skip_line = power_loss_run_gcode_info.get('cmd', '') in GENERIC_MOVE_GCODE
            if skip_line:
                self.file_position = env['cur_file_pos']
                self.lines = env['current_line']
            else:
                self.lines = env['current_line'] - 1
                self.file_position = env['last_file_pos']

            self.pl_notify_start_line = self.lines + 1
            self.pl_next_save_line = self.lines + self.pl_save_line_interval

            exclude_object = self.printer.lookup_object('exclude_object', None)
            if exclude_object is not None:
                exclude_object.objects = gcode_tracker.objects
                exclude_object.excluded_objects = gcode_tracker.excluded_objects
                exclude_object.current_object = gcode_tracker.current_object
                exclude_object._register_transform()

            # self.rm_power_loss_move_env_file()
            # move_env_path = self.pl_print_file_move_env_path.replace('.json', f'_{last_move_file_index}.json')
            # pl_save_data['homing_stepper_z_info'] = stepper_z_info
            # self.save_environment_data(move_env_path, pl_save_data)
            self.current_file_index = (last_move_file_index + 1) % self.max_file_count
            # self.current_file_index = 0
            self.pl_mcu_flash_resume_line = self.lines
            self.gcode.respond_info("pl_mcu_flash_resume_line: {}".format(self.pl_mcu_flash_resume_line))
            self.gcode.run_script_from_command("TIMELAPSE_START TYPE=continue")
            self.gcode.run_script_from_command("DEFECT_DETECTION_START")
            self.do_resume()
        except Exception as e:
            self.gcode.respond_info("Failed to restore pl_print, error: {}".format(str(e)))
            self.backup_print_env_info()
            # self.rm_power_loss_info()
            self.notify_mcu_enable_power_loss(0, 0xFFFFFFFF)
            if self.print_task_config is not None:
                self.print_task_config.reset_print_info()
            if msm is not None:
                state_str = str(msm.get_status()['main_state'])
                if state_str == "PRINTING":
                    self.gcode.run_script_from_command("SET_MAIN_STATE MAIN_STATE=IDLE")
            # raise restore error
            str_err = self.printer.extract_coded_message_field(str(e))
            error_msg = '{"coded": "0001-0531-0000-0005", "msg":"%s", "action": "none"}' % (
                        "Failed to restore pl_print, %s" % (str_err))
            raise self.printer.command_error(error_msg)
            # self.printer.raise_structured_code_exception("0003-0531-0000-0005", error_msg)
            # raise self.printer.command_error("restore_print failed: {}".format(err_msg))
        finally:
            pass

class GCodeStateTracker:
    def __init__(self, printer, initial_state):
        self.state = initial_state
        self.printer = printer
        self.extrude_factor = 1
        self.speed_factor = self.speed_factor_bak = 1. / 60.
        self.print_task_config = None
        self.speed = initial_state['speed'] * self.speed_factor
        self.max_accel = initial_state['max_accel']
        self.min_cruise_ratio = initial_state['min_cruise_ratio']
        self.square_corner_velocity = initial_state['square_corner_velocity']
        self.extruder_gcode_id = initial_state['extruder']
        self.absolute_coord = initial_state['absolute_coord']
        self.absolute_extrude = initial_state['absolute_extrude']
        # self.toolhead_pos = initial_state['toolhead_pos']
        self.base_position = initial_state['base_position']
        self.last_position = initial_state['last_position']
        self.homing_position = initial_state['homing_position']
        self.objects = []
        self.excluded_objects = []
        self.current_object = None

    class sentinel: pass
    def get(self, gcmd, params, name, default=sentinel, parser=str,
            minval=None, maxval=None, above=None, below=None):
        if params is None:
            raise self.printer.command_error("Params dictionary must be provided")
        if name is None:
            raise self.printer.command_error("Parameter name must be specified")

        value = params.get(name.upper())
        if value is None:
            if default is self.sentinel:
                raise self.printer.command_error(
                    f"Error on '{gcmd}': missing {name}")
            return default

        try:
            value = parser(value)
        except:
            raise self.printer.command_error(
                f"Error on '{gcmd}': unable to parse {value}")

        if minval is not None and value < minval:
            raise self.printer.command_error(
                f"Error on '{gcmd}': {name} must have minimum of {minval}")
        if maxval is not None and value > maxval:
            raise self.printer.command_error(
                f"Error on '{gcmd}': {name} must have maximum of {maxval}")
        if above is not None and value <= above:
            raise self.printer.command_error(
                f"Error on '{gcmd}': {name} must be above {above}")
        if below is not None and value >= below:
            raise self.printer.command_error(
                f"Error on '{gcmd}': {name} must be below {below}")
        return value

    def get_int(self, gcmd, params, name, default=sentinel,
               minval=None, maxval=None):
        return self.get(gcmd, params, name, default, int, minval, maxval)

    def get_float(self, gcmd, params, name, default=sentinel,
                 minval=None, maxval=None, above=None, below=None):
        return self.get(gcmd, params, name, default, float,
                       minval, maxval, above, below)

    def _get_gcode_speed(self):
        return self.speed / self.speed_factor

    def _parse_gcode_line(self, line):
        line = origline = line.strip()
        if not line or line.startswith(';'):
            return {}

        if ';' in line:
            line = line.split(';', 1)[0].strip()

        cmd_match = re.match(r'^([A-Z_]+\d*(?:\.\d+)?)', line, re.IGNORECASE)
        if not cmd_match:
            return {}
        cmd = cmd_match.group(1).upper()
        line = line[cmd_match.end():].strip()
        tokens = re.findall(
            r'([A-Z_]+)\s*=\s*([^=\s]*)|([A-Z_]+)([^=\s]*)',
            line,
            re.IGNORECASE
        )

        params = {}
        for key1, value, key2, val2 in tokens:
            key = (key1 or key2).upper()
            val = (value or val2).strip() if (value or val2) else None
            params[key] = val

        return {'cmd': cmd, 'origline': origline, 'params': params}

    def set_gcode_offset(self, line, params):
        move_delta = [0., 0., 0., 0.]
        for pos, axis in enumerate('XYZE'):
            # offset = gcmd.get_float(axis, None)
            offset = self.get_float(line, params, axis, None)
            if offset is None:
                # offset = gcmd.get_float(axis + '_ADJUST', None)
                offset = self.get_float(line, params, axis + '_ADJUST', None)
                if offset is None:
                    continue
                offset += self.homing_position[pos]
            delta = offset - self.homing_position[pos]
            move_delta[pos] = delta
            self.base_position[pos] += delta
            self.homing_position[pos] = offset

    # exclude_object function
    def _add_object_definition(self, definition):
        self.objects = sorted(self.objects + [definition],
                              key=lambda o: o["name"])

    def _exclude_object(self, name):
        if name not in self.excluded_objects:
            self.excluded_objects = sorted(self.excluded_objects + [name])

    def _unexclude_object(self, name):
        if name in self.excluded_objects:
            excluded_objects = list(self.excluded_objects)
            excluded_objects.remove(name)
            self.excluded_objects = sorted(excluded_objects)

    def update_position(self, line):
        parsed = self._parse_gcode_line(line)
        if not parsed:
            return

        cmd = parsed['cmd']
        params = parsed['params']
        line = parsed['origline']
        # self.printer.lookup_object('gcode').respond_info('parsed line: {}'.format(parsed))
        if cmd == 'M82':
            self.absolute_extrude = True
        elif cmd == 'M83':
            self.absolute_extrude = False
        elif cmd == 'G90':
            self.absolute_coord = True
        elif cmd == 'G91':
            self.absolute_coord = False
        elif cmd == 'G92':
            offsets = [ self.get_float(line, params, a, None) for a in 'XYZE' ]
            for i, offset in enumerate(offsets):
                if offset is not None:
                    if i == 3:
                        offset *= self.extrude_factor
                    self.base_position[i] = self.last_position[i] - offset
            if offsets == [None, None, None, None]:
                self.base_position = list(self.last_position)
        elif cmd == 'M220':
            # if 'B' in params:
            #     self.speed_factor_bak = self.speed_factor

            if 'R' in params:
                value = self.speed_factor_bak
                self.speed = self._get_gcode_speed() * value
                self.speed_factor = self.speed_factor_bak

            if 'S' in params:
                value = self.get_float(line, params, 'S', 100., above=0.) / (60. * 100.)
                self.speed = self._get_gcode_speed() * value
                self.speed_factor = value
        elif cmd == 'M221':
            new_extrude_factor = self.get_float(line, params, 'S', 100., above=0.) / 100.
            last_e_pos = self.last_position[3]
            e_value = (last_e_pos - self.base_position[3]) / self.extrude_factor
            self.base_position[3] = last_e_pos - e_value * new_extrude_factor
            self.extrude_factor = new_extrude_factor
        elif cmd == 'M204':
            accel = self.get_float(line, params, 'S', None, above=0.)
            if accel is None:
                # Use minimum of P and T for accel
                p = self.get_float(line, params, 'P', None, above=0.)
                t = self.get_float(line, params, 'T', None, above=0.)
                if p is None or t is None:
                    return
                accel = min(p, t)
            self.max_accel = accel
        elif cmd == 'SET_VELOCITY_LIMIT':
            # max_velocity = self.get_float(cmd, line, 'VELOCITY', None, above=0.)
            max_accel = self.get_float(line, params, 'ACCEL', None, above=0.)
            square_corner_velocity = self.get_float(line, params,
                'SQUARE_CORNER_VELOCITY', None, minval=0.)
            min_cruise_ratio = self.get_float(line, params,
                'MINIMUM_CRUISE_RATIO', None, minval=0., below=1.)
            if min_cruise_ratio is None:
                req_accel_to_decel = self.get_float(line, params, 'ACCEL_TO_DECEL',
                                                    None, above=0.)
                if req_accel_to_decel is not None and max_accel is not None:
                    min_cruise_ratio = 1. - min(1., req_accel_to_decel / max_accel)
                elif req_accel_to_decel is not None and max_accel is None:
                    min_cruise_ratio = 1. - min(1., (req_accel_to_decel
                                                    / self.max_accel))
            # if max_velocity is not None:
            #     self.max_velocity = max_velocity
            if max_accel is not None:
                self.max_accel = max_accel
            if square_corner_velocity is not None:
                self.square_corner_velocity = square_corner_velocity
            if min_cruise_ratio is not None:
                self.min_cruise_ratio = min_cruise_ratio
        elif cmd == 'SET_GCODE_OFFSET':
            self.set_gcode_offset(line, params)
        elif cmd in TOOL_CHANGE_COMMANDS:
            old_gcode_id = self.extruder_gcode_id
            try:
                need_map = self.get_float(line, params, 'A', 1, minval=0)
                if need_map and self.print_task_config is not None:
                    try:
                        extruder_index = int(cmd[1:])
                        print_task_config_info = self.print_task_config.get_print_task_config()
                        extruder_map_table = print_task_config_info["reprint_info"]["extruder_map_table"]
                        if isinstance(extruder_map_table, list) and extruder_index < len(extruder_map_table):
                            mapped_value = extruder_map_table[extruder_index]
                            self.extruder_gcode_id = f"T{mapped_value}"
                        else:
                            logging.exception("Invalid cmd: '%s'" % (cmd,))
                    except Exception as e:
                        logging.exception("Invalid cmd: '%s'" % (cmd,))
                else:
                    self.extruder_gcode_id = cmd
            finally:
                if old_gcode_id != self.extruder_gcode_id:
                    for extruder in self.printer.lookup_object('extruder_list', []):
                        if (extruder.gcode_id == self.extruder_gcode_id and extruder.base_position is not None and
                            extruder.gcode_offset is not None):
                            params['X'] = extruder.gcode_offset[0]
                            params['Y'] = extruder.gcode_offset[1]
                            params['Z'] = extruder.gcode_offset[2]
                            self.set_gcode_offset(line, params)
                            break
        elif cmd in ('G0', 'G1') or (cmd in ('G2', 'G3') and self.absolute_coord):
            try:
                for pos, axis in enumerate('XYZ'):
                    if axis in params and params[axis] is not None:
                        v = float(params[axis])
                        if not self.absolute_coord:
                            # value relative to position of last move
                            self.last_position[pos] += v
                        else:
                            # value relative to base coordinate position
                            self.last_position[pos] = v + self.base_position[pos]
                if 'E' in params and params['E'] is not None:
                    v = float(params['E']) * self.extrude_factor
                    if not self.absolute_coord or not self.absolute_extrude:
                        # value relative to position of last move
                        self.last_position[3] += v
                    else:
                        # value relative to base coordinate position
                        self.last_position[3] = v + self.base_position[3]
                if 'F' in params and params['F'] is not None:
                    gcode_speed = float(params['F'])
                    if gcode_speed <= 0.:
                        raise self.printer.command_error("Invalid speed in '%s'" % (line,))
                    self.speed = gcode_speed * self.speed_factor
            except Exception as e:
                logging.exception("Unable to parse move '%s'" % (line,))
        elif cmd == 'EXCLUDE_OBJECT_START':
            try:
                name = self.get(line, params, 'NAME').upper()
                if not any(obj["name"] == name for obj in self.objects):
                    self._add_object_definition({"name": name})
                self.current_object = name
            except Exception as e:
                logging.exception("Unable to parse '%s'" % (line,))
        elif cmd == 'EXCLUDE_OBJECT_END':
            if self.current_object == None:
                return
            self.current_object = None
        elif cmd == 'EXCLUDE_OBJECT':
            try:
                reset = self.get(line, params, 'RESET', None)
                current = self.get(line, params, 'CURRENT', None)
                name = self.get(line, params, 'NAME').upper()
                if reset:
                    if name:
                        self._unexclude_object(name)

                    else:
                        self.excluded_objects = []

                elif name:
                    if name.upper() not in self.excluded_objects:
                        self._exclude_object(name.upper())

                elif current:
                    if self.current_object:
                        self._exclude_object(self.current_object)
            except Exception as e:
                logging.exception("Unable to parse '%s'" % (line,))
        elif cmd == 'EXCLUDE_OBJECT_DEFINE':
           pass

    def set_factors(self, extrude_factor=None, speed_factor=None, speed_factor_bak=None):
        if extrude_factor is not None:
            self.extrude_factor = extrude_factor

        if speed_factor is not None:
            self.speed = speed_factor * self.speed / self.speed_factor
            self.speed_factor = speed_factor

        if speed_factor_bak is not None:
            self.speed_factor_bak = speed_factor_bak
    def set_print_task_config(self, print_task_config):
        self.print_task_config = print_task_config
    def set_exclude_object(self, current_object=None, objects=[], excluded_objects=[]):
        self.objects = objects
        self.excluded_objects = excluded_objects
        self.current_object = current_object

def load_config(config):
    return VirtualSD(config)
