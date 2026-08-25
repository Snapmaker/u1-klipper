# Power loss detection handling

import json, logging, os, copy, ctypes
import pins
import stepper

POWER_LOSS_CHECK_CFG_FILE = 'power_loss_check.json'

class PowerLossCheck:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = config.get_printer().lookup_object('gcode')
        self.enable_status_output = False
        self.name = 'master' if config.get_name() == 'power_loss_check' else config.get_name().split()[-1]

        # Configuration parameters
        ppins = self.printer.lookup_object('pins')
        pin = config.get('pin')
        pin_params = ppins.lookup_pin(pin, can_invert=True, can_pullup=True)
        self._mcu = pin_params['chip']
        cfg_trigger_time = config.getfloat('power_loss_trigger_time', 0.0109, above=0.)
        self.power_loss_trigger_time = cfg_trigger_time
        if self.name == 'master':
            self._config_path = os.path.join(self.printer.get_snapmaker_config_dir(),
                                             POWER_LOSS_CHECK_CFG_FILE)
            trigger_source = "default config"
            try:
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    val = json.load(f).get('power_loss_trigger_time')
                if val is not None and val > 0:
                    self.power_loss_trigger_time = float(val)
                    trigger_source = "json config"
            except Exception:
                pass
            logging.info("power_loss_check: power_loss_trigger_time=%.6f (from %s)",
                         self.power_loss_trigger_time, trigger_source)
        self.report_interval_time = config.getint('report_interval', 0, minval=0)
        self.duty_threshold = config.getfloat('duty_threshold', 0.54, minval=0)
        self.debounce_threshold = config.getint('debounce_threshold', 20, minval=0)
        self.type_confirm_threshold = config.getint('type_confirm_threshold', 3, minval=0)
        self._cmd_queue = self._mcu.alloc_command_queue()
        self._mcu.register_config_callback(self._build_config)

        self.high_level_tick = 0xFFFFFFFF
        self.low_level_tick = 0xFFFFFFFF
        self.voltage_type = 0xFF
        self.power_loss_flag = 0
        self.initialized = 0
        self.duty_percent = 0.0
        self.pl_flash_valid = {}
        self.pl_flash_save_data = {}
        self.pl_tmp_flash_data = {}
        self.pl_get_flash_date = False
        self.pl_exception_is_report = False
        # Register GCODE commands
        if self.name == 'master':
            self.last_type = None
            self.timer = self.reactor.register_timer(self._auto_switch_bed_pid_control)
            self.bed_pid_control_mode = config.get('bed_pid_control_mode', 'auto_switch')
            self.gcode.register_command('UPDATE_POWER_LOSS_REPORT_INTERVAL',
                                    self.cmd_UPDATE_POWER_LOSS_REPORT_INTERVAL,
                                    desc=self.cmd_UPDATE_POWER_LOSS_REPORT_INTERVAL_help)
            self.gcode.register_command('QUERY_POWER_LOSS_CHECK_INFO',
                                    self.cmd_QUERY_POWER_LOSS_CHECK_INFO,
                                    desc=self.cmd_QUERY_POWER_LOSS_CHECK_INFO_help)
            self.gcode.register_command('ENABLE_POWER_LOSS_REPORT_LOG',
                                    self.cmd_ENABLE_POWER_LOSS_REPORT_LOG,
                                    desc=self.cmd_ENABLE_POWER_LOSS_REPORT_LOG_help)
            self.gcode.register_command('SET_POWER_LOSS_TRIGGER_TIME',
                                    self.cmd_SET_POWER_LOSS_TRIGGER_TIME,
                                    desc=self.cmd_SET_POWER_LOSS_TRIGGER_TIME_help)

        self.gcode.register_mux_command("ENABLE_POWER_LOSS", "NAME", self.name,
                                        self.cmd_ENABLE_POWER_LOSS)
        self.gcode.register_mux_command("QUERY_POWER_LOSS_FLASH_VALID", "NAME", self.name,
                                        self.cmd_QUERY_POWER_LOSS_FLASH_VALID,
                                        desc=self.cmd_QUERY_POWER_LOSS_FLASH_VALID_help)
        self.gcode.register_mux_command("QUERY_POWER_LOSS_STEPPER_INFO", "NAME", self.name,
                                        self.cmd_QUERY_POWER_LOSS_STEPPER_INFO,
                                        desc=self.cmd_QUERY_POWER_LOSS_STEPPER_INFO_help)
        self.printer.register_event_handler("klippy:ready", self._handle_klipper_ready)

    def _build_config(self):
        self._oid = self._mcu.create_oid()
        clock = self._mcu.get_query_slot(self._oid)
        self._report_clock = self._mcu.seconds_to_clock(self.report_interval_time)
        self._mcu.add_config_cmd(
            "config_power_loss_check oid=%d clock=%u power_loss_trigger_time=%u report_interval=%u duty_threshold=%u"
            " debounce_threshold=%u type_confirm_threshold=%u"
            % (self._oid, clock, self.power_loss_trigger_time*1000000, self._report_clock, self.duty_threshold*1000000,
               self.debounce_threshold, self.type_confirm_threshold))

        self.update_report_interval_cmd = self._mcu.lookup_command(
            "update_report_interval oid=%c report_interval=%u")

        self.enable_power_loss_cmd = self._mcu.lookup_command(
            "enable_power_loss oid=%c enable=%u print_flag=%u move_line=%u")

        self.query_power_loss_stepper_info_cmd = self._mcu.lookup_query_command(
            "query_power_loss_stepper_info oid=%c type=%u index=%u",
            "power_loss_stepper_info_result oid=%c result=%u",
            oid=self._oid, cq=self._cmd_queue)

        self.query_power_loss_flash_valid_cmd = self._mcu.lookup_query_command(
            "query_power_loss_flash_valid oid=%c",
            "power_loss_flash_valid oid=%c last_seq=%u valid_sector_count=%u env_flag=%u save_stepper_num=%u",
            oid=self._oid, cq=self._cmd_queue)

        self.query_power_loss_check_info_cmd = self._mcu.lookup_query_command(
            "query_power_loss_status oid=%c",
            "power_loss_status oid=%c high_level=%u low_level=%u voltage_type=%u power_loss_flag=%u initialized=%u",
            oid=self._oid, cq=self._cmd_queue)

        self._mcu.register_response(self.handle_report_power_loss_status,
                            "report_power_loss_status", self._oid)

        self._mcu.register_response(self.handle_report_stepper_info,
                            "power_loss_stepper_info", self._oid)

    def _handle_klipper_ready(self):
        if self.name == 'master':
            heater_bed = self.printer.lookup_object('heater_bed', None)
            if heater_bed is not None:
                if self.bed_pid_control_mode == 'auto_switch':
                    # need to start a timer to detect the input voltage type
                    self.reactor.update_timer(self.timer, self.reactor.NOW+0.5)
                elif self.bed_pid_control_mode == 'pid2' or self.bed_pid_control_mode == 'default':
                    try:
                        if heater_bed is not None and hasattr(heater_bed.heater.control, 'Kp'):
                            self.gcode.run_script_from_command("SET_PID_PROFILE HEATER=heater_bed PROFILE={}".format(self.bed_pid_control_mode))
                    except Exception as e:
                        logging.error(f"Error while attempting to force {self.bed_pid_control_mode} for heater_bed: {e}")
        # query power-loss valid information
        params = self.query_power_loss_flash_valid_cmd.send([self._oid])
        self.pl_flash_valid = {}
        self.pl_flash_valid['last_seq'] = params['last_seq']
        self.pl_flash_valid['valid_sector_count'] = params['valid_sector_count']
        self.pl_flash_valid['env_flag'] = params['env_flag']
        self.pl_flash_valid['save_stepper_num'] = params['save_stepper_num']

        # query flash saved stepper information
        self.pl_tmp_flash_data = {}
        params = self.query_power_loss_stepper_info_cmd.send([self._oid, 255, 0])
        self.pl_flash_save_data = copy.deepcopy(self.pl_tmp_flash_data)
        self.pl_get_flash_date = True
        power_loss_check_list = self.printer.lookup_object('power_loss_check_list', [])
        if all(getattr(obj, 'pl_get_flash_date', False) for obj in power_loss_check_list):
            self.printer.send_event("power_loss_check:mcu_update_complete")

    def _auto_switch_bed_pid_control(self, eventtime):
        voltage_type = 0xFF
        if self.voltage_type != voltage_type:
            voltage_type = self.voltage_type
            if self.last_type != voltage_type:
                self.last_type = voltage_type
            else:
                switch_success = True
                try:
                    if voltage_type == 0:
                        heater_bed = self.printer.lookup_object('heater_bed', None)
                        if heater_bed is not None and hasattr(heater_bed.heater.control, 'Kp'):
                            self.gcode.run_script_from_command("SET_PID_PROFILE HEATER=heater_bed PROFILE=pid2")
                except Exception as e:
                    switch_success = False
                    logging.error(f"auto_switch_bed_pid_control failed: {e}")
                finally:
                    voltage_str = "220v" if voltage_type == 1 else "110v"
                    self.gcode.respond_info("auto switching bed PID control based on voltage type: {}, switch_success: {}".format(voltage_str, switch_success))
                    return self.reactor.NEVER
        return eventtime + self.report_interval_time + 0.3

    def get_status(self, eventtime):
        return {
            'initialized': self.initialized,
            'high_level_tick': self.high_level_tick,
            'low_level_tick': self.low_level_tick,
            'voltage_type': self.voltage_type,
            'power_loss_flag': self.power_loss_flag,
            'duty_percent': self.duty_percent
        }

    def _update_status_from_params(self, params):
        self.initialized = params['initialized']
        self.high_level_tick = params['high_level']
        self.low_level_tick = params['low_level']
        self.voltage_type = params['voltage_type']
        self.power_loss_flag = params['power_loss_flag']
        if self.initialized and self.high_level_tick != 0xFFFFFFFF and self.low_level_tick != 0xFFFFFFFF:
            self.duty_percent =  self.high_level_tick / (self.high_level_tick + self.low_level_tick)

    def handle_report_power_loss_status(self, params):
        self._update_status_from_params(params)
        if self.enable_status_output:
            voltage_str = "110v" if self.voltage_type == 0 else \
                         "220v" if self.voltage_type == 1 else "detecting"
            self.gcode.respond_info("Assigned variables: initialized=%d, high_level_tick=%d, low_level_tick=%d, voltage_type=%s, power_loss_flag=%d, duty_percent=%.2f%%" % (
                self.initialized, self.high_level_tick, self.low_level_tick,
                voltage_str, self.power_loss_flag, self.duty_percent*100))

        if self.name == 'master' and self.power_loss_flag and self.pl_exception_is_report == False:
            self.pl_exception_is_report = True
            # coded = "0003-0522-0000-0017"
            # self.printer.raise_structured_code_exception(coded, "mcu: Power loss triggered", 0, 0)
            error = '{"coded": "0003-0522-0000-0017", "msg":"%s", "oneshot": 0}' % ("mcu: Power loss triggered",)
            self.printer.invoke_shutdown(error)

    def handle_report_stepper_info(self, params):
        stepper_type = params['type']
        stepper_index = params['index']
        stepper_line = params['line']
        stepper_position = ctypes.c_int32(params['position']).value
        if stepper_type < len(stepper.power_loss_need_save_steppers):
            name = stepper.power_loss_need_save_steppers[stepper_type]
            if stepper_index > 0:
                name += str(stepper_index)
            self.gcode.respond_info(
                "Stepper %s: line=%u position=%d" % (
                    name, stepper_line, stepper_position))
            # Save stepper info to pl_tmp_flash_data with name as key
            self.pl_tmp_flash_data[name] = {
                'line': stepper_line,
                'position': stepper_position
            }
        else:
            self.gcode.respond_info(
                "Unknown stepper type=%d index=%d: line=%u position=%d" % (
                    stepper_type, stepper_index, stepper_line, stepper_position))
    def query_power_loss_stepper_info(self, stepper_type=0, stepper_index=0):
        try:
            self.pl_tmp_flash_data = {}
            params = self.query_power_loss_stepper_info_cmd.send([self._oid, stepper_type, stepper_index])
            return copy.deepcopy(self.pl_tmp_flash_data)
        except Exception as e:
            logging.error(f"Failed to query power loss stepper info: {e}")
            return None

    cmd_UPDATE_POWER_LOSS_REPORT_INTERVAL_help = "Update power loss report interval"
    def cmd_UPDATE_POWER_LOSS_REPORT_INTERVAL(self, gcmd):
        interval = gcmd.get_float('INTERVAL', minval=0)
        clock = self._mcu.seconds_to_clock(interval)
        self.update_report_interval_cmd.send([self._oid, clock])
        self.report_interval_time = interval
        gcmd.respond_info("Power loss report interval updated to %.3f seconds" % interval)

    cmd_QUERY_POWER_LOSS_CHECK_INFO_help = "Query power loss check status"
    def cmd_QUERY_POWER_LOSS_CHECK_INFO(self, gcmd):
        params = self.query_power_loss_check_info_cmd.send([self._oid])
        self._update_status_from_params(params)
        voltage_str = "110v" if self.voltage_type == 0 else \
                     "220v" if self.voltage_type == 1 else "detecting"
        self.gcode.respond_info("QUERY_POWER_LOSS_CHECK_INFO: initialized=%d, high_level_tick=%d, low_level_tick=%d, voltage_type=%s, power_loss_flag=%d, duty_percent=%.2f%%" % (
            self.initialized, self.high_level_tick, self.low_level_tick,
            voltage_str, self.power_loss_flag, self.duty_percent*100))

    cmd_ENABLE_POWER_LOSS_REPORT_LOG_help = "Enable/disable power loss status report output"
    def cmd_ENABLE_POWER_LOSS_REPORT_LOG(self, gcmd):
        enable = gcmd.get_int('ENABLE', 0, minval=0, maxval=1)
        self.enable_status_output = bool(enable)
        gcmd.respond_info("Power loss status report output %s" %
                         ("enabled" if self.enable_status_output else "disabled"))

    cmd_QUERY_POWER_LOSS_FLASH_VALID_help = "Query power loss flash valid status"
    def cmd_QUERY_POWER_LOSS_FLASH_VALID(self, gcmd):
        params = self.query_power_loss_flash_valid_cmd.send([self._oid])
        self.gcode.respond_info(
            "query %s power_loss_flash_valid: last_seq=%u valid_sector_count=%u "
            "env_flag=%u save_stepper_num=%u" % (
                self.name, params['last_seq'], params['valid_sector_count'],
                params['env_flag'], params['save_stepper_num']))

    cmd_QUERY_POWER_LOSS_STEPPER_INFO_help = "Query power loss stepper info"
    def cmd_QUERY_POWER_LOSS_STEPPER_INFO(self, gcmd):
        stepper_type = gcmd.get_int('TYPE', 0, minval=0)
        stepper_index = gcmd.get_int('INDEX', 0, minval=0)
        if stepper_type == 255:
            self.gcode.respond_info("save {} flash steppers info:".format(self.name))
        else:
            self.gcode.respond_info("cur_kin steppers info:")
        params = self.query_power_loss_stepper_info_cmd.send([self._oid, stepper_type, stepper_index])
        self.gcode.respond_info("query {} completed".format(self.name))

    def cmd_ENABLE_POWER_LOSS(self, gcmd):
        enable = gcmd.get_int('ENABLE', 0, minval=0, maxval=1)
        print_flag = gcmd.get_int('PRINT_FLAG', 0xFFFFFFFF)
        move_line = gcmd.get_int('MOVE_LINE', 0xFFFFFFFF)
        self.enable_power_loss_cmd.send([self._oid, enable, print_flag, move_line])
        gcmd.respond_info("%s power loss %s, print_flag %d, move_line %d" %
                         (self.name, "enabled" if enable else "disabled", print_flag, move_line))

    cmd_SET_POWER_LOSS_TRIGGER_TIME_help = "Set power loss trigger time and save to config file"
    def cmd_SET_POWER_LOSS_TRIGGER_TIME(self, gcmd):
        val = gcmd.get_float('TIME', None, minval=0.001, maxval=1.0)
        if val is None:
            gcmd.respond_info("Usage: SET_POWER_LOSS_TRIGGER_TIME TIME=<seconds>")
            return
        self.power_loss_trigger_time = val
        save_ok = False
        try:
            self.printer.update_snapmaker_config_file(
                self._config_path, {'power_loss_trigger_time': val}, {})
            save_ok = True
        except Exception:
            logging.exception("power_loss_check: failed to save config")
        try:
            configfile = self.printer.lookup_object('configfile')
            configfile.set('power_loss_check', 'power_loss_trigger_time', "%.6f" % val)
        except Exception:
            logging.exception("power_loss_check: configfile.set failed")
        if save_ok:
            gcmd.respond_info(
                "power_loss_trigger_time=%.6f\n"
                "The SAVE_CONFIG command will update the printer config file\n"
                "with this parameter and restart the printer." % val)
        else:
            gcmd.respond_info(
                "power_loss_trigger_time=%.6f set (persist failed)" % val)

def load_config(config):
    power_loss_check_list = config.get_printer().lookup_object('power_loss_check_list', None)
    pl_obj = PowerLossCheck(config)
    if power_loss_check_list is None:
        pl_list = []
        pl_list.append(pl_obj)
        config.get_printer().add_object('power_loss_check_list', pl_list)
    else:
        power_loss_check_list.append(pl_obj)
    return pl_obj

def load_config_prefix(config):
    power_loss_check_list = config.get_printer().lookup_object('power_loss_check_list', None)
    pl_obj = PowerLossCheck(config)
    if power_loss_check_list is None:
        pl_list = []
        pl_list.append(pl_obj)
        config.get_printer().add_object('power_loss_check_list', pl_list)
    else:
        power_loss_check_list.append(pl_obj)
    return pl_obj
