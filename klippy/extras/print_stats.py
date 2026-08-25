# Virtual SDCard print stat tracking
#
# Copyright (C) 2020  Eric Callahan <arksine.code@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import logging, copy, os

LOGICAL_EXTRUDER_NUM = 32
PHYSICAL_EXTRUDER_NUM = 4
PRINT_STATS_CONFIG_FILE                         = "print_stats.json"

PRINT_STATS_DEFAULT_CONFIG                      = {
    'print_job': {
        'flow_calibrate': [False] * PHYSICAL_EXTRUDER_NUM,
        'preextrude_filament': [False] * LOGICAL_EXTRUDER_NUM,
    }
}

class PrintStats:
    def __init__(self, config):
        printer = config.get_printer()
        self.printer = printer
        self.gcode_move = printer.load_object(config, 'gcode_move')
        self.reactor = printer.get_reactor()

        config_dir = self.printer.get_snapmaker_config_dir()
        config_name = PRINT_STATS_CONFIG_FILE
        self._config_path = os.path.join(config_dir, config_name)
        self._config = self.printer.load_snapmaker_config_file(
            self._config_path,
            PRINT_STATS_DEFAULT_CONFIG,
            create_if_not_exist=True)

        self.print_task_config = None
        self.max_logical_extruder_num = LOGICAL_EXTRUDER_NUM
        self.max_physical_extruder_num = PHYSICAL_EXTRUDER_NUM
        self.exception_details = {}

        self.reset(reprint=True)
        # Register commands
        self.gcode = printer.lookup_object('gcode')
        self.gcode.register_command(
            "SET_PRINT_STATS_INFO", self.cmd_SET_PRINT_STATS_INFO,
            desc=self.cmd_SET_PRINT_STATS_INFO_help)
        self.gcode.register_command(
            "SM_PRINT_PREEXTRUDE_FILAMENT", self.cmd_SM_PRINT_PREEXTRUDE_FILAMENT)
        self.gcode.register_command(
            "SM_PRINT_FLOW_CALIBRATE", self.cmd_SM_PRINT_FLOW_CALIBRATE)
        # event handler
        self.printer.register_event_handler("klippy:ready", self._ready)
        self.printer.register_event_handler("print_stats:update_exception_info",
                                                self._update_exception_info)

    def _ready(self):
        self.toolhead = self.printer.lookup_object("toolhead")
        self.max_logical_extruder_num = self.toolhead.max_logical_extruder_num
        self.max_physical_extruder_num = self.toolhead.max_physical_extruder_num
        self.print_task_config = self.printer.lookup_object("print_task_config", None)
        if len(self._config['print_job']['flow_calibrate']) != self.max_physical_extruder_num or \
                len(self._config['print_job']['preextrude_filament']) != self.max_logical_extruder_num:
            PRINT_STATS_DEFAULT_CONFIG['print_job']['flow_calibrate'] = [False] * self.max_physical_extruder_num
            PRINT_STATS_DEFAULT_CONFIG['print_job']['preextrude_filament'] = [False] * self.max_logical_extruder_num
            self._config = copy.deepcopy(PRINT_STATS_DEFAULT_CONFIG)
            if not self.printer.update_snapmaker_config_file(self._config_path,
                    self._config, PRINT_STATS_DEFAULT_CONFIG):
                logging.error("[print_stats] save config failed\r\n")

    def _update_filament_usage(self, eventtime):
        toolhead = self.printer.lookup_object('toolhead')
        extruder_list = self.printer.lookup_object('extruder_list', [])
        gc_status = self.gcode_move.get_status(eventtime)
        if not extruder_list or len(extruder_list) <= 1:
            cur_epos = gc_status['position'].e
        else:
            cur_epos = sum(extruder.last_position for extruder in extruder_list)
        self.filament_used += (cur_epos - self.last_epos) / gc_status['extrude_factor']
        self.last_epos = cur_epos

    def _update_exception_info(self, id, index, code, message, level):
        if id is None or index is None or code is None or message is None or level is None:
            self.exception_details['id'] = self.gcode.error.default_id
            self.exception_details['index'] = self.gcode.error.default_index
            self.exception_details['code'] = self.gcode.error.default_code
            self.exception_details['message'] = self.gcode.error.default_message
            self.exception_details['level'] = self.gcode.error.default_level
        else:
            self.exception_details['id'] = id
            self.exception_details['index'] = index
            self.exception_details['code'] = code
            self.exception_details['message'] = message
            self.exception_details['level'] = level
    def _reset_last_e_position(self):
        curtime = self.reactor.monotonic()
        gc_status = self.gcode_move.get_status(curtime)
        extruder_list = self.printer.lookup_object('extruder_list', [])
        if not extruder_list or len(extruder_list) <= 1:
            cur_epos = gc_status['position'].e
        else:
            cur_epos = sum(extruder.last_position for extruder in extruder_list)
        self.last_epos = cur_epos
    def set_current_file(self, filename, reprint=False):
        self.reset(reprint)
        self.filename = filename
    def note_start(self):
        curtime = self.reactor.monotonic()
        virtual_sdcard = self.printer.lookup_object('virtual_sdcard', None)
        print_file_env = layer_info = None
        if virtual_sdcard is not None:
            print_file_env = virtual_sdcard.get_pl_print_file_env()
            layer_info = virtual_sdcard.get_pl_print_layer_info()
            if print_file_env is not None and print_file_env.get("filament_used"):
                self.filament_used = print_file_env.get("filament_used")

        if self.print_start_time is None:
            # self.print_start_time = curtime
            if print_file_env is not None and print_file_env.get("total_duration"):
                if layer_info is not None and layer_info.get("current_layer") is not None and layer_info.get("total_layer") is not None:
                    self.info_current_layer = int(layer_info.get("current_layer"))
                    self.info_total_layer = int(layer_info.get("total_layer"))
                prev_pause_duration = print_file_env.get("prev_pause_duration", None)
                init_duration = int(print_file_env.get("init_duration", 0))
                if prev_pause_duration is not None and int(prev_pause_duration) + self.init_duration < int(print_file_env.get("total_duration")):
                    self.prev_pause_duration = int(prev_pause_duration)
                    self.init_duration = init_duration
                self._reset_last_e_position()
                self.print_start_time = curtime - int(print_file_env.get("total_duration"))
            else:
                self.print_start_time = curtime
            self.printer.send_event("print_stats:new_task_start")
        elif self.last_pause_time is not None:
            # Update pause time duration
            pause_duration = curtime - self.last_pause_time
            self.prev_pause_duration += pause_duration
            self.last_pause_time = None
            if virtual_sdcard is not None:
                virtual_sdcard.force_record_pl_print_file_env()
        # Reset last e-position
        self._reset_last_e_position()
        self.state = "printing"
        self.error_message = ""
        self.exception_details = {}
        self.printer.send_event("print_stats:start")
        # Force a full refresh of print_stats to subscribers on print start
        self.printer.lookup_object('webhooks').send_status('print_stats')

    def note_pause(self, message=None):
        if self.last_pause_time is None:
            curtime = self.reactor.monotonic()
            self.last_pause_time = curtime
            # update filament usage
            self._update_filament_usage(curtime)
        if self.state != "error":
            self.state = "paused"
        if message is not None:
            self.error_message = message
        self.printer.send_event("print_stats:paused")
    def note_complete(self):
        self.exception_details = {}
        self._note_finish("complete")
    def note_error(self, message):
        self._note_finish("error", message)
    def note_cancel(self):
        if self.state == "paused":
            self.exception_details = {}
        self._note_finish("cancelled")
    def _note_finish(self, state, error_message = ""):
        print_config = self.printer.lookup_object('print_task_config', None)
        if print_config is not None:
            print_config.reset_print_info(is_finish_print=True)
        if self.print_start_time is None:
            self.printer.send_event("print_stats:stop")
            return
        self.state = state
        self.error_message = error_message
        eventtime = self.reactor.monotonic()
        self.total_duration = eventtime - self.print_start_time
        if self.filament_used < 0.0000001:
            # No positive extusion detected during print
            self.init_duration = self.total_duration - \
                self.prev_pause_duration
        self.print_start_time = None
        self.printer.send_event("print_stats:stop")
    cmd_SET_PRINT_STATS_INFO_help = "Pass slicer info like layer act and " \
                                    "total to klipper"
    def cmd_SET_PRINT_STATS_INFO(self, gcmd):
        total_layer = gcmd.get_int("TOTAL_LAYER", self.info_total_layer, \
                                   minval=0)
        current_layer = gcmd.get_int("CURRENT_LAYER", self.info_current_layer, \
                                     minval=0)
        if total_layer == 0:
            self.info_total_layer = None
            self.info_current_layer = None
        elif total_layer != self.info_total_layer:
            self.info_total_layer = total_layer
            self.info_current_layer = 0

        if self.info_total_layer is not None and \
                current_layer is not None and \
                current_layer != self.info_current_layer:
            self.info_current_layer = min(current_layer, self.info_total_layer)
        virtual_sdcard = self.printer.lookup_object('virtual_sdcard', None)
        if virtual_sdcard is not None:
            info_layer = {'current_layer': self.info_current_layer, 'total_layer': self.info_total_layer}
            virtual_sdcard.record_pl_print_layer_info(info_layer)

    def cmd_SM_PRINT_PREEXTRUDE_FILAMENT(self, gcmd):
        index = gcmd.get_int("INDEX", None)
        force = gcmd.get_int("FORCE", False)
        temp = gcmd.get_float("TEMP", None)
        extruder = None
        print_task_config_status = None
        is_soft = False

        if index == None or index < 0 or index >= self.max_logical_extruder_num:
            raise gcmd.error("[print_stats] invalid extruder index")

        if self.print_task_config == None:
            raise gcmd.error("[print_stats] print_task_config not available")
        else:
            print_task_config_status = self.print_task_config.get_status()
        extruder = print_task_config_status['extruder_map_table'][index]
        is_soft = int(print_task_config_status['filament_soft'][extruder])

        if force == False:
            if self._config['print_job']['preextrude_filament'][index] == True:
                return
            if print_task_config_status['extruders_used'][extruder] == False:
                return

        toolhead = self.printer.lookup_object("toolhead")
        toolhead.wait_moves()
        if toolhead.get_extruder().extruder_index != extruder:
            self.gcode.run_script_from_command(f"T{index}\n")
            toolhead.wait_moves()

        rawparams = gcmd.get_raw_command_parameters()
        if temp is None:
            try:
                temp = toolhead.get_extruder().heater.target_temp
                if temp < toolhead.get_extruder().heater.min_extrude_temp:
                    temp = 220
            except:
                logging.error("[print_stats] get extruder target temp failed")
                temp = 220
            self.gcode.run_script_from_command("INNER_PREEXTRUDE_FILAMENT SOFT=%d TEMP=%f %s\n" % (is_soft, temp, rawparams))
        else:
            self.gcode.run_script_from_command("INNER_PREEXTRUDE_FILAMENT SOFT=%d %s\n" % (is_soft, rawparams))
        toolhead.wait_moves()
        self._config['print_job']['preextrude_filament'][index] = True
        if not self.printer.update_snapmaker_config_file(self._config_path,
                self._config, PRINT_STATS_DEFAULT_CONFIG):
            logging.error("[print_stats] save config failed\r\n")

    def cmd_SM_PRINT_FLOW_CALIBRATE(self, gcmd):
        index = gcmd.get_int("INDEX", None)
        extruder = gcmd.get_int("EXTRUDER", None)

        if self.print_task_config is None:
            raise gcmd.error("[print_stats] print_task_config object not available")
        print_task_config_status = self.print_task_config.get_status()

        if index is not None and extruder is not None:
            raise gcmd.error("[print_stats] extruder and index cannot be specified together!")

        if index is not None:
            if index < 0 or index >= self.max_logical_extruder_num:
                raise gcmd.error("[print_stats] invalid extruder index!")
            extruder = print_task_config_status['extruder_map_table'][index]
        elif extruder is not None:
            if extruder < 0 or extruder >= self.max_physical_extruder_num:
                raise gcmd.error("[print_stats] invalid extruder!")
        else:
            extruder = self.toolhead.get_extruder().extruder_index

        if print_task_config_status['auto_replenish_filament']:
            extruder = print_task_config_status['extruders_replenished'][extruder]

        if print_task_config_status['extruders_used'][extruder] == False:
            return

        if print_task_config_status['flow_calibrate'] == False or \
                print_task_config_status['flow_calib_extruders'][extruder] == False:
            return

        if self._config['print_job']['flow_calibrate'][extruder] == True:
            return

        self.toolhead.wait_moves()
        rawparams = gcmd.get_raw_command_parameters()
        self.gcode.run_script_from_command(f"T{extruder} A0\n")
        self.gcode.run_script_from_command(f"FLOW_CALIBRATE %s\n" % (rawparams))
        self.toolhead.wait_moves()
        self._config['print_job']['flow_calibrate'][extruder] = True
        if not self.printer.update_snapmaker_config_file(self._config_path,
                self._config, PRINT_STATS_DEFAULT_CONFIG):
            logging.error("[print_stats] save config failed\r\n")

    def reset(self, reprint=False):
        self.filename = self.error_message = ""
        self.state = "standby"
        self.prev_pause_duration = self.last_epos = 0.
        self.filament_used = self.total_duration = 0.
        self.print_start_time = self.last_pause_time = None
        self.init_duration = 0.
        self.info_total_layer = None
        self.info_current_layer = None
        if reprint == False:
            self._config['print_job'] = copy.deepcopy(PRINT_STATS_DEFAULT_CONFIG['print_job'])
            if not self.printer.update_snapmaker_config_file(
                    self._config_path,
                    self._config, PRINT_STATS_DEFAULT_CONFIG):
                logging.error("[print_stats] save config failed\r\n")

    def get_status(self, eventtime):
        time_paused = self.prev_pause_duration
        if self.print_start_time is not None:
            if self.last_pause_time is not None:
                # Calculate the total time spent paused during the print
                time_paused += eventtime - self.last_pause_time
            else:
                # Accumulate filament if not paused
                self._update_filament_usage(eventtime)
            self.total_duration = eventtime - self.print_start_time
            if self.filament_used < 0.0000001:
                # Track duration prior to extrusion
                self.init_duration = self.total_duration - time_paused
        print_duration = self.total_duration - self.init_duration - time_paused
        return {
            'filename': self.filename,
            'total_duration': self.total_duration,
            'print_duration': print_duration,
            'filament_used': self.filament_used,
            'state': self.state,
            'exception': copy.deepcopy(self.exception_details),
            'message': self.error_message,
            'info': {'total_layer': self.info_total_layer,
                     'current_layer': self.info_current_layer}
        }

def load_config(config):
    return PrintStats(config)
