# Pause/Resume functionality with position capture/restore
#
# Copyright (C) 2019  Eric Callahan <arksine.code@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import logging

class PauseResume:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.recover_velocity = config.getfloat('recover_velocity', 50.)
        self.v_sd = None
        self.print_stats = None
        self.is_paused = False
        self.sd_paused = False
        self.pause_command_sent = False
        self.printer.register_event_handler("klippy:connect",
                                            self.handle_connect)
        self.gcode.register_command("PAUSE_BASE", self.cmd_PAUSE_BASE,
                                    desc=self.cmd_PAUSE_BASE_help)
        self.gcode.register_command("PAUSE", self.cmd_PAUSE,
                                    desc=self.cmd_PAUSE_help)
        self.gcode.register_command("RESUME_BASE", self.cmd_RESUME_BASE,
                                    desc=self.cmd_RESUME_BASE_help)
        self.gcode.register_command("RESUME", self.cmd_RESUME,
                                    desc=self.cmd_RESUME_help)
        self.gcode.register_command("CLEAR_PAUSE", self.cmd_CLEAR_PAUSE,
                                    desc=self.cmd_CLEAR_PAUSE_help)
        self.gcode.register_command("CANCEL_PRINT", self.cmd_CANCEL_PRINT,
                                    desc=self.cmd_CANCEL_PRINT_help)
        webhooks = self.printer.lookup_object('webhooks')
        webhooks.register_endpoint("pause_resume/cancel",
                                   self._handle_cancel_request)
        webhooks.register_endpoint("pause_resume/pause",
                                   self._handle_pause_request)
        webhooks.register_endpoint("pause_resume/resume",
                                   self._handle_resume_request)
    def handle_connect(self):
        self.v_sd = self.printer.lookup_object('virtual_sdcard', None)
        self.print_stats = self.printer.lookup_object('print_stats', None)
    def _handle_cancel_request(self, web_request):
        logging.info("[pause_resume] request cancel")
        self.printer.send_event("pause_resume:cancel")
        self.gcode.run_script("CANCEL_PRINT")
    def _handle_pause_request(self, web_request):
        logging.info("[pause_resume] request pause")
        if self.v_sd is not None and self.v_sd.work_timer is not None:
            self.v_sd.pl_allow_save_env = False
        self.printer.send_event("pause_resume:pause")
        self.gcode.run_script("PAUSE")
    def _handle_resume_request(self, web_request):
        logging.info("[pause_resume] request resume")
        self.gcode.run_script("RESUME")
    def get_status(self, eventtime):
        return {
            'is_paused': self.is_paused
        }
    def is_sd_active(self):
        return self.v_sd is not None and self.v_sd.is_active()
    def send_pause_command(self):
        # This sends the appropriate pause command from an event.  Note
        # the difference between pause_command_sent and is_paused, the
        # module isn't officially paused until the PAUSE gcode executes.
        if not self.pause_command_sent:
            if self.is_sd_active():
                # Printing from virtual sd, run pause command
                self.sd_paused = True
                self.v_sd.do_pause()
            else:
                self.sd_paused = False
                self.gcode.respond_info("action:paused")
            self.pause_command_sent = True
    cmd_PAUSE_BASE_help = ("Pauses the current print")
    def cmd_PAUSE_BASE(self, gcmd):
        if self.is_paused:
            gcmd.respond_info("Print already paused")
            return
        self.send_pause_command()
        self.gcode.run_script_from_command("SAVE_GCODE_STATE NAME=PAUSE_STATE")
        self.is_paused = True
    cmd_PAUSE_help = ("Pauses the current print")
    def cmd_PAUSE(self, gcmd):
        if self.print_stats is not None:
            if self.print_stats.state not in ['printing', 'paused']:
                gcmd.respond_raw(f"!! Cannot pause while not printing: {self.print_stats.state}")
                return
        if self.is_paused:
            gcmd.respond_raw(f"!! Print already paused")
            return

        exclude_obj = self.printer.lookup_object('exclude_object', None)
        if exclude_obj is not None:
            if exclude_obj.get_status()['in_excluded_region'] == True and self.v_sd.is_cmd_from_sd():
                gcmd.respond_info("Cannot pause while in an excluded region")
                return

        try:
            gcmd.respond_info("Pausing...")
            rawparams = gcmd.get_raw_command_parameters()
            self.gcode.run_script_from_command("INNER_PAUSE %s\n" % (rawparams))
        except Exception as e:
            raise gcmd.error("Unable to pause print: %s" % (str(e)))
        finally:
            self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=IDLE")
    def send_resume_command(self):
        if self.sd_paused:
            # Printing from virtual sd, run pause command
            self.v_sd.do_resume()
            self.sd_paused = False
        else:
            self.gcode.respond_info("action:resumed")
        self.pause_command_sent = False
    cmd_RESUME_BASE_help = ("Resumes the print from a pause")
    def cmd_RESUME_BASE(self, gcmd):
        if not self.is_paused:
            gcmd.respond_info("Print is not paused, resume aborted")
            return
        velocity = gcmd.get_float('VELOCITY', self.recover_velocity)
        move = gcmd.get_int('MOVE', 1 , minval=0, maxval=1)
        accel = gcmd.get_float('MOVE_ACCEL', 5000.)
        extrude = gcmd.get_float('EXTRUDE', 0., minval=0., maxval=20.)
        xy_first = gcmd.get_int('XY_FIRST', 0)
        self.gcode.run_script_from_command(
            "RESTORE_GCODE_STATE NAME=PAUSE_STATE MOVE=%d MOVE_SPEED=%.4f MOVE_ACCEL=%.4f EXTRUDE=%.4f XY_FIRST=%d"
            % (move, velocity, accel, extrude, xy_first))
        self.send_resume_command()
        self.is_paused = False
    cmd_RESUME_help = ("Resumes the print from a pause")
    def cmd_RESUME(self, gcmd):
        if self.print_stats is not None:
            if self.print_stats.state not in ['paused']:
                raise gcmd.error(f"!! Cannot resume while not printing: {self.print_stats.state}")

        machine_state_manager = self.printer.lookup_object('machine_state_manager', None)
        if machine_state_manager is not None:
            machine_sta = machine_state_manager.get_status()
            if str(machine_sta["main_state"]) != "PRINTING" or str(machine_sta["action_code"]) != "IDLE":
                raise gcmd.error(f"!! Cannot resume while machine main_state: {machine_sta['main_state']} or action_code: {machine_sta['action_code']}")

        if self.is_paused == False:
            raise gcmd.error(f"!! Not in paused state and cannot be resumed!\r\n")

        try:
            gcmd.respond_info("Resuming...")
            rawparams = gcmd.get_raw_command_parameters()
            self.gcode.run_script_from_command("INNER_RESUME %s\n" % (rawparams))
        except:
            gcmd.respond_info("!! Resumes error!")
            self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=IDLE")
            try:
                toolhead = self.printer.lookup_object('toolhead')
                macro = self.printer.lookup_object('gcode_macro PAUSE', None)
                temp = 40
                if macro is not None:
                    temp = macro.variables.get('pause_temp', 40)

                for i in range(toolhead.max_physical_extruder_num):
                    obj = None
                    if i == 0:
                        obj = self.printer.lookup_object('extruder', None)
                    else:
                        obj = self.printer.lookup_object(f'extruder{i}', None)

                    if obj is not None and obj.get_status(self.reactor.monotonic())['target'] > 0:
                        self.gcode.run_script_from_command(f"M104 S{temp} T{i} A0\n")
            except Exception as e:
                logging.error(str(e))
                gcmd.respond_info("!! Set pause_temp error!\r\n")

            raise

    cmd_CLEAR_PAUSE_help = (
        "Clears the current paused state without resuming the print")
    def cmd_CLEAR_PAUSE(self, gcmd):
        self.is_paused = self.pause_command_sent = False
    cmd_CANCEL_PRINT_help = ("Cancel the current print")
    def cmd_CANCEL_PRINT(self, gcmd):
        if self.is_sd_active() or self.sd_paused:
            self.v_sd.do_cancel()
        else:
            gcmd.respond_info("action:cancel")
        self.cmd_CLEAR_PAUSE(gcmd)

def load_config(config):
    return PauseResume(config)
