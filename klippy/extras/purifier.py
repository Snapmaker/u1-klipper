import logging, os, threading
from . import pulse_counter

FAN_STATE_TURN_ON                                   = 0
FAN_STATE_TURN_OFF                                  = 1
FAN_STATE_TURNING_OFF                               = 2

# Mode definitions
MODE_IDLE                                           = 0 # Idle mode - original functionality
MODE_COOL_CHAMBER                                   = 1 # Cool chamber mode - exhaust fan + temperature detection + dynamic fan control
MODE_PREHEAT_CHAMBER                                = 2 # Preheat mode - inner fan + fan RPM monitoring + temperature waiting
MODE_HOT_CHAMBER                                    = 3 # Hot chamber mode - inner fan + fan RPM monitoring

DEFAULT_POWER_DT_SAMPLE_TIME                        = 0.08
DEFAULT_POWER_DT_SAMPLE_COUNT                       = 4
DEFAULT_POWER_DT_REPORT_TIME                        = 0.350
DEFAULT_POWER_DT_THRESHOLD                          = 0.88

DEFAULT_WORK_TIME_UPDATE_INTERVAL                   = 30
DEFAULT_EXHAUST_FAN_DELAY_TIME                      = 180
DEFAULT_INNER_FAN_DELAY_TIME                        = 180

PERIODIC_STATUS_CHECK_INTERVAL                      = 1.0
FAN_RPM_FAULT_THRESHOLD                             = 20
AVG_TEMP_SAMPLES                                    = 10
DESIRED_CRITICAL_MIN_TEMP_DIFF                      = 1.0
DYNAMIC_FAN_POWER_INCREMENT                         = 0.1
DYNAMIC_FAN_POWER_DECREMENT                         = 0.05
DYNAMIC_FAN_POWER_ADJUST_INTERVAL                   = 50.0
COOL_CHECK_TIMEOUT_INTERVAL                         = 240
COOLING_ACTIVATION_OFFSET                           = 0
COOLING_FAN_POWER_START_INCREMENT                   = 5
PREHEAT_CHECK_TIMEOUT_INTERVAL                      = 180
PREHEAT_MIN_VALID_RISE_TEMP                         = 0.0

VALID_PURIFIER_FAN_TYPE = ['exhaust', 'inner']

PURIFIER_CONFIG_FILE = 'purifier.json'
DEFAULT_PURIFIER_CONFIG = {
    'exhaust_delay_time': DEFAULT_EXHAUST_FAN_DELAY_TIME,
    'inner_delay_time': DEFAULT_INNER_FAN_DELAY_TIME,
    'inner_work_time': 0.0,
}

FAN_MIN_TIME = 0.200

class PurifierFanTachometer:
    def __init__(self, printer, pin, ppr, sample_time, poll_time):
        self._frequence = pulse_counter.FrequencyCounter(printer, pin, sample_time, poll_time)
        self._ppr = ppr

    def get_status(self, eventtime=None):
        rpm = None
        if self._frequence is not None:
            rpm = self._frequence.get_frequency()  * 30. / self._ppr
        return {'rpm': rpm}

class PurifierFan:
    def __init__(self,
                 config,
                 fan_pin,
                 max_power=1.,
                 kick_start_time=0.1,
                 off_below=0.,
                 cycle_time=0.010,
                 hardware_pwm=False,
                 shutdown_speed=0.,
                 tach_pin=None,
                 tach_ppr=2,
                 tach_sample_time=1.,
                 tach_poll_time=0.0015,
                 ):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()

        self.last_fan_value = 0.
        self.last_fan_time = 0.

        self.max_power = max_power
        self.kick_start_time = kick_start_time
        self.off_below = off_below

        # Setup pwm object
        ppins = self.printer.lookup_object('pins')
        self.mcu_fan = ppins.setup_pin('pwm', fan_pin)
        self.mcu_fan.setup_max_duration(0.)
        self.mcu_fan.setup_cycle_time(cycle_time, hardware_pwm)
        self.mcu_fan.setup_start_value(0., max(0., min(self.max_power, shutdown_speed)))

        # Setup tachometer
        self.tachometer = None
        if tach_pin is not None:
            self.tachometer = PurifierFanTachometer(self.printer, tach_pin,
                                        tach_ppr, tach_sample_time, tach_poll_time)

    def get_mcu(self):
        return self.mcu_fan.get_mcu()

    def set_speed(self, print_time, value):
        if value < self.off_below:
            value = 0.
        value = max(0., min(self.max_power, value * self.max_power))

        if value == self.last_fan_value:
            return

        system_time = self.reactor.monotonic()
        system_time += FAN_MIN_TIME
        print_time = self.get_mcu().estimated_print_time(system_time)
        print_time = max(self.last_fan_time + FAN_MIN_TIME, print_time)
        if (value and value < self.max_power and self.kick_start_time
            and (not self.last_fan_value or value - self.last_fan_value > .5)):
            # Run fan at full speed for specified kick_start_time
            self.mcu_fan.set_pwm(print_time, self.max_power)
            print_time += self.kick_start_time
        self.mcu_fan.set_pwm(print_time, value)
        self.last_fan_time = print_time
        self.last_fan_value = value

    def get_speed(self):
        return self.last_fan_value

    def get_max_power(self):
        return self.max_power

    def get_status(self, eventtime):
        status_dict = {
            'speed': self.last_fan_value,
        }
        if self.tachometer is not None:
            status_dict.update(self.tachometer.get_status(eventtime))

        return status_dict

class Purifier:
    def __init__(self, config):
        self.printer = config.get_printer()
        ppins = self.printer.lookup_object('pins')
        self.reactor = self.printer.get_reactor()

        config_dir = self.printer.get_snapmaker_config_dir("persistent")
        self.config_path = os.path.join(config_dir, PURIFIER_CONFIG_FILE)
        self.config_info = self.printer.load_snapmaker_config_file(self.config_path,
                                                              DEFAULT_PURIFIER_CONFIG)
        # check config
        if self.config_info['inner_work_time'] < 0:
            self.config_info['inner_work_time'] = 0.0
            self.printer.update_snapmaker_config_file(self.config_path,
                        self.config_info, DEFAULT_PURIFIER_CONFIG)

        # exhaust_fan
        self._exhaust_fan = None
        if config.get('exhaust_pin', None) is not None:
            fan_pin = config.get('exhaust_pin', None)
            max_power = config.getfloat('exhaust_max_power', 1., above=0., maxval=1.)
            kick_start_time = config.getfloat('exhaust_kick_start_time', 0.1, minval=0.)
            off_below = config.getfloat('exhaust_off_below', 0., minval=0., maxval=1.)
            cycle_time = config.getfloat('exhaust_cycle_time', 0.010, above=0.)
            hardware_pwm = config.getboolean('exhaust_hardware_pwm', False)
            shutdown_speed = config.getfloat('exhaust_shutdown_speed', 0, minval=0., maxval=1.)
            tach_pin = config.get('exhaust_tach_pin', None)
            tach_ppr = config.getint('exhaust_tach_ppr', 2, minval=1)
            tach_sample_time = config.getfloat('exhaust_tach_sample_time', 1., above=0.)
            tach_poll_time = config.getfloat('exhaust_tach_poll_interval', 0.0015, above=0.)
            self._exhaust_fan = PurifierFan(config,
                                            fan_pin,
                                            max_power,
                                            kick_start_time,
                                            off_below,
                                            cycle_time,
                                            hardware_pwm,
                                            shutdown_speed,
                                            tach_pin,
                                            tach_ppr,
                                            tach_sample_time,
                                            tach_poll_time)

        # inner fan
        self._inner_fan = None
        if config.get('inner_pin', None) is not None:
            fan_pin = config.get('inner_pin')
            max_power = config.getfloat('inner_max_power', 1., above=0., maxval=1.)
            kick_start_time = config.getfloat('inner_kick_start_time', 0.1, minval=0.)
            off_below = config.getfloat('inner_off_below', 0., minval=0., maxval=1.)
            cycle_time = config.getfloat('inner_cycle_time', 0.010, above=0.)
            hardware_pwm = config.getboolean('inner_hardware_pwm', False)
            shutdown_speed = config.getfloat('inner_shutdown_speed', 0, minval=0., maxval=1.)
            tach_pin = config.get('inner_tach_pin', None)
            tach_ppr = config.getint('inner_tach_ppr', 2, minval=1)
            tach_sample_time = config.getfloat('inner_tach_sample_time', 1., above=0.)
            tach_poll_time = config.getfloat('inner_tach_poll_interval', 0.0015, above=0.)
            self._inner_fan = PurifierFan(config,
                                            fan_pin,
                                            max_power,
                                            kick_start_time,
                                            off_below,
                                            cycle_time,
                                            hardware_pwm,
                                            shutdown_speed,
                                            tach_pin,
                                            tach_ppr,
                                            tach_sample_time,
                                            tach_poll_time)

        # power enable pin
        self._power_enable_pin = None
        power_enable_pin = config.get('power_enable_pin', None)
        if power_enable_pin is not None:
            self._power_enable_pin = ppins.setup_pin('digital_out', power_enable_pin)
            self._power_enable_pin.setup_max_duration(0.)

        # power detect
        power_det_pin = config.get('power_det_pin', None)
        self._power_det_pin = None
        if power_det_pin is not None:
            self._power_det_pin = ppins.setup_pin('adc', power_det_pin)
            self._power_det_pin.setup_adc_sample(DEFAULT_POWER_DT_SAMPLE_TIME, DEFAULT_POWER_DT_SAMPLE_COUNT)
            self._power_det_pin.setup_adc_callback(DEFAULT_POWER_DT_REPORT_TIME, self._adc_callback)
        self._power_det_threshold = config.getfloat('power_det_threshold', DEFAULT_POWER_DT_THRESHOLD)
        self.power_det_debounce_threshold = config.getint('power_det_debounce_threshold', 3, minval=1)
        self.power_det_debounce_count = 0
        self._power_detected = False
        self._power_det_value = 1
        self.last_print_time = 0

        self._exhaust_fan_state = FAN_STATE_TURN_OFF
        self._inner_fan_state = FAN_STATE_TURN_OFF
        self._exhaust_delay_timer = self.reactor.register_timer(self._exhaust_delay_timer_cb)
        self._inner_delay_timer = self.reactor.register_timer(self._inner_delay_timer_cb)
        self._work_time_monitor_timer = self.reactor.register_timer(self._work_time_monitor_timer_cb)
        self._periodic_check_timer = self.reactor.register_timer(self._periodic_status_check)

        self._inner_last_turn_on_time = None

        # purifier mode
        self.purifier_mode = MODE_IDLE
        self.desired_chamber_temp = 0
        self.critical_chamber_temp = 0
        self.external_temp_sensor = None
        external_temp_sensor = config.get('external_temp_sensor', None)
        if external_temp_sensor is not None:
            full_name = f"temperature_sensor {external_temp_sensor}"
            self.external_temp_sensor = self.printer.load_object(config, full_name)
        self.check_interval = config.getfloat('check_interval', PERIODIC_STATUS_CHECK_INTERVAL, above=0.)
        self.fan_rpm_fault_threshold = config.getint('fan_rpm_fault_threshold', FAN_RPM_FAULT_THRESHOLD, minval=1)
        self.fan_rpm_fault_counter = 0
        self.exhaust_fan_speed_threshold = 0
        self.inner_fan_speed_threshold = 0

        # temperature prediction related variables
        self.avg_temp_samples = config.getint('avg_temp_samples', AVG_TEMP_SAMPLES, minval=1)
        self.dynamic_fan_power_increment = config.getfloat('dynamic_fan_power_increment', DYNAMIC_FAN_POWER_INCREMENT, above=0.0)
        self.dynamic_fan_power_decrement = config.getfloat('dynamic_fan_power_decrement', DYNAMIC_FAN_POWER_DECREMENT, above=0.0)
        self.desired_critical_min_temp_diff = config.getfloat('desired_critical_min_temp_diff',
                                                                DESIRED_CRITICAL_MIN_TEMP_DIFF, minval=0.0)
        self.cooling_activation_offset = config.getfloat('cooling_activation_offset', COOLING_ACTIVATION_OFFSET, minval=0.0)
        self.cooling_fan_power_start_increment = config.getfloat('cooling_fan_power_start_increment', COOLING_FAN_POWER_START_INCREMENT, minval=0.0)
        self.preheat_check_timeout_interval = config.getfloat('preheat_check_timeout_interval', PREHEAT_CHECK_TIMEOUT_INTERVAL, minval=0)
        self.preheat_min_valid_rise_temp  = config.getfloat('preheat_min_valid_rise_temp', PREHEAT_MIN_VALID_RISE_TEMP, minval=0)
        self.dynamic_fan_control = config.getint('dynamic_fan_control', 1, minval=0, maxval=1)
        self.cool_check_timeout_interval = config.getfloat('cool_check_timeout_interval', COOL_CHECK_TIMEOUT_INTERVAL, minval=0)
        self.dynamic_fan_power_adjust_interval = config.getfloat('dynamic_fan_power_adjust_interval', DYNAMIC_FAN_POWER_ADJUST_INTERVAL, minval=0)
        self.temp_readings = []
        self.average_temperature = None
        self.preheat_wait_enabled = False
        self.preheat_check_last_temp = None
        self.preheat_check_timeout_time = None
        self.cool_check_last_temp = None
        self.cool_check_last_adjust_temp = None
        self.cool_check_timeout_time = None
        self.dynamic_fan_power_adjust_time = None
        self.exception_manager = None
        self.preheat_check_timeout_default_interval = self.preheat_check_timeout_interval
        self.dynamic_fan_control_default = self.dynamic_fan_control
        self.timer_execution_counter = 0
        self.v_sd = None
        self.fan_fault_reported = False
        self.critical_temp_reported = False
        self.print_stats = None

        self.is_print_task_delay_turnoffing_inner = False
        self.is_print_task_delay_turnoffing_exhaust = False
        self.last_print_task_purifier_mode = MODE_IDLE

        # gcode
        self.gcode = self.printer.lookup_object("gcode")
        self.gcode.register_command('SET_PURIFIER', self.cmd_SET_PURIFIER)
        self.gcode.register_command('GET_PURIFIER', self.cmd_GET_PURIFIER)
        self.gcode.register_command('SET_PURIFIER_MODE', self.cmd_SET_PURIFIER_MODE)
        self.gcode.register_command('WAIT_CHAMBER_TEMP', self.cmd_WAIT_CHAMBER_TEMP)

        # webhook api
        wh = self.printer.lookup_object('webhooks')
        wh.register_endpoint("control/purifier", self._handle_control_purifier)

        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        self.printer.register_event_handler("klippy:shutdown", self._handle_shutdown)
        self.printer.register_event_handler("gcode:request_restart", self._handle_shutdown)
        self.printer.register_event_handler("pause_resume:pause", self._reset_preheat_state)
        self.printer.register_event_handler("pause_resume:cancel", self._handle_cancel_print_job)
        self.printer.register_event_handler('print_stats:stop', self._handle_stop_print_job)
        self.printer.register_event_handler('print_stats:start', self._handle_start_print_job)

    def _handle_ready(self):
        self.timer_execution_counter = 0
        self.reactor.update_timer(self._periodic_check_timer, self.reactor.NOW)
        self.exception_manager = self.printer.lookup_object('exception_manager', None)
        self.v_sd = self.printer.lookup_object('virtual_sdcard', None)
        self.print_stats = self.printer.lookup_object('print_stats', None)
        self.reactor.update_timer(self._work_time_monitor_timer, self.reactor.monotonic() + 1)

    def _handle_shutdown(self, eventtime=None):
        self.reactor.update_timer(self._work_time_monitor_timer, self.reactor.NEVER)
        self.reactor.update_timer(self._inner_delay_timer, self.reactor.NEVER)
        self.reactor.update_timer(self._exhaust_delay_timer, self.reactor.NEVER)
        self.reactor.update_timer(self._periodic_check_timer, self.reactor.NEVER)
    def _reset_preheat_state(self):
        self.preheat_wait_enabled = False
        self.preheat_check_last_temp = None
        self.preheat_check_timeout_time = None

    def _handle_start_print_job(self):
        self._reset_exception_reporting_state()
        self.last_print_task_purifier_mode = self.purifier_mode

    def _handle_stop_print_job(self):
        self._reset_exception_reporting_state()

    def _handle_cancel_print_job(self):
        self._reset_exception_reporting_state()

    def _reset_exception_reporting_state(self):
        self.fan_fault_reported = False
        self.critical_temp_reported = False
        self.fan_rpm_fault_counter = 0
        self.cool_check_last_temp = None
        self.cool_check_last_adjust_temp = None
        self.cool_check_timeout_time = None
        self.preheat_check_last_temp = None
        self.preheat_check_timeout_time = None
        self.dynamic_fan_power_adjust_time = None
        # Reset preheat wait state
        self.preheat_wait_enabled = False
    def _adc_callback(self, read_time, read_value):
        self._power_det_value = read_value
        _power_detected = False
        if (self._power_det_value < self._power_det_threshold):
            _power_detected = True
        else:
            _power_detected = False

        if _power_detected != self._power_detected:
            if self.power_det_debounce_count <= self.power_det_debounce_threshold:
                self.power_det_debounce_count += 1

            if self.power_det_debounce_count == self.power_det_debounce_threshold:
                self._power_detected = _power_detected
                if not _power_detected:
                    self.set_exhaust_fan_delay_turn_off(0)
                    self.set_inner_fan_delay_turn_off(0)
                    self._reset_chamber_mode()
                    self.purifier_mode = MODE_IDLE
                    logging.info("[purifier] purifier offline!!!")
                else:
                    logging.info("[purifier] purifier online!!!")
        else:
            self.power_det_debounce_count = 0

    def _work_time_monitor_timer_cb(self, eventtime):
        need_save = False
        try:
            update_mode = 0

            if self._inner_fan_state != FAN_STATE_TURN_OFF:
                if self.print_stats is not None:
                    if self.print_stats.state not in ['printing', 'paused']:
                        if self.is_print_task_delay_turnoffing_inner == False:
                            update_mode = 1
                        else:
                            if self.last_print_task_purifier_mode in [MODE_PREHEAT_CHAMBER, MODE_HOT_CHAMBER]:
                                update_mode = 2
                            else:
                                update_mode = 1
                    else:
                        if self.purifier_mode in [MODE_PREHEAT_CHAMBER, MODE_HOT_CHAMBER]:
                            update_mode = 2
                        else:
                            update_mode = 1
                else:
                    if self.purifier_mode in [MODE_PREHEAT_CHAMBER, MODE_HOT_CHAMBER]:
                        update_mode = 2
                    else:
                        update_mode = 1
            else:
                update_mode = 1

            current_time = self.reactor.monotonic()
            if update_mode == 2:
                if self._inner_last_turn_on_time is None:
                    self._inner_last_turn_on_time = current_time
                else:
                    if current_time > self._inner_last_turn_on_time:
                        self.config_info['inner_work_time'] += current_time - self._inner_last_turn_on_time
                        need_save = True
                    self._inner_last_turn_on_time = current_time

            else:
                if self._inner_last_turn_on_time is not None:
                    if current_time > self._inner_last_turn_on_time:
                        self.config_info['inner_work_time'] += current_time - self._inner_last_turn_on_time
                        need_save = True
                    self._inner_last_turn_on_time = None

            return self.reactor.monotonic() + DEFAULT_WORK_TIME_UPDATE_INTERVAL

        finally:
            if need_save:
                if not self.printer.update_snapmaker_config_file(self.config_path,
                            self.config_info, DEFAULT_PURIFIER_CONFIG):
                    logging.error("[purifier] save purifier failed\r\n")

    def _set_power_enable(self, print_time):
        if self._power_enable_pin is None:
            logging.error("[purifier] power enable pin not exist!")
            return

        exhaust_fan_speed = 0
        inner_fan_speed = 0
        if self._exhaust_fan is not None:
            exhaust_fan_speed = self._exhaust_fan.get_speed()
        if self._inner_fan is not None:
            inner_fan_speed = self._inner_fan.get_speed()

        if exhaust_fan_speed > 0 or inner_fan_speed > 0:
            self._power_enable_pin.set_digital(print_time, 1)
        else:
            self._power_enable_pin.set_digital(print_time, 0)

    def set_exhaust_fan_speed(self, speed):
        if not self._power_detected and speed > 0:
            logging.error("[purifier] purifier not exist!")
            return

        if self._exhaust_fan is None:
            logging.error("[purifier] exhaust fan not exist!")
            return

        self.reactor.update_timer(self._exhaust_delay_timer, self.reactor.NEVER)

        if speed > 1.0:
            speed = 1.0
            self._exhaust_fan_state = FAN_STATE_TURN_ON
        elif speed < 0.0001:
            speed = 0
            self._exhaust_fan_state = FAN_STATE_TURN_OFF
        else:
            self._exhaust_fan_state = FAN_STATE_TURN_ON

        system_time = self.reactor.monotonic()
        system_time += FAN_MIN_TIME
        print_time = self._exhaust_fan.get_mcu().estimated_print_time(system_time)
        print_time = max(self.last_print_time + FAN_MIN_TIME, print_time)
        self._exhaust_fan.set_speed(print_time, speed)
        print_time += 0.01
        self._set_power_enable(print_time)
        self.last_print_time = print_time
        self.is_print_task_delay_turnoffing_exhaust = False

    def set_inner_fan_speed(self, speed):
        if not self._power_detected and speed > 0:
            logging.error("[purifier] purifier not exist!")
            return

        if self._inner_fan is None:
            logging.error("[purifier] inner fan not exist!")
            return

        self.reactor.update_timer(self._inner_delay_timer, self.reactor.NEVER)

        if speed > 1.0:
            speed = 1.0
            self._inner_fan_state = FAN_STATE_TURN_ON
        elif speed < 0.0001:
            speed = 0
            self._inner_fan_state = FAN_STATE_TURN_OFF
        else:
            self._inner_fan_state = FAN_STATE_TURN_ON

        system_time = self.reactor.monotonic()
        system_time += FAN_MIN_TIME
        print_time = self._inner_fan.get_mcu().estimated_print_time(system_time)
        print_time = max(self.last_print_time + FAN_MIN_TIME, print_time)
        self._inner_fan.set_speed(print_time, speed)
        print_time += 0.01
        self._set_power_enable(print_time)
        self.last_print_time = print_time
        self.is_print_task_delay_turnoffing_inner = False

        if self._inner_fan_state == FAN_STATE_TURN_ON:
            if self._inner_last_turn_on_time is None:
                if self.purifier_mode in [MODE_PREHEAT_CHAMBER, MODE_HOT_CHAMBER]:
                    if self.print_stats is None or \
                       self.print_stats.state in ['printing', 'paused']:
                        self._inner_last_turn_on_time = system_time
        else:
            if self._inner_last_turn_on_time is not None:
                self.reactor.update_timer(self._work_time_monitor_timer, self.reactor.NOW)

    def _exhaust_delay_timer_cb(self, eventtime):
        self.set_exhaust_fan_speed(0)
        self.is_print_task_delay_turnoffing_exhaust = False
        return self.reactor.NEVER

    def _inner_delay_timer_cb(self, eventtime):
        self.set_inner_fan_speed(0)
        self.is_print_task_delay_turnoffing_inner = False
        return self.reactor.NEVER

    def _periodic_status_check(self, eventtime):
        try:
            self.timer_execution_counter = (self.timer_execution_counter + 1) & 0x7FFFFFFF
            mode_handlers = {
                MODE_IDLE: self._handle_idle_chamber_mode,
                MODE_COOL_CHAMBER: self._handle_cool_chamber_mode,
                MODE_PREHEAT_CHAMBER: self._handle_preheat_chamber_mode,
                MODE_HOT_CHAMBER: self._handle_hot_chamber_mode,
            }
            self._update_temperature_data(eventtime)
            handler = mode_handlers.get(self.purifier_mode)
            if handler:
                handler(eventtime)
        except Exception:
            self._reset_preheat_state()
            logging.exception("[purifier] periodic status check error")

        return eventtime + self.check_interval

    def _pause_print(self):
        self._reset_preheat_state()
        if hasattr(self, 'v_sd') and self.v_sd is not None and self.v_sd.work_timer is not None:
            self.v_sd.pl_allow_save_env = False
        if self.print_stats.state == "printing":
            self.reactor.register_async_callback(lambda pt: self.gcode.run_script("PAUSE"))
        # self.gcode.run_script("PAUSE")

    def _handle_idle_chamber_mode(self, eventtime):
        if self.preheat_wait_enabled:
            self._reset_preheat_state()

    def _check_inner_fan_rpm_fault(self, eventtime):
        fault_detected = False
        if self._inner_fan is not None:
            inner_fan_info = self._inner_fan.get_status(eventtime)
            fan_speed = inner_fan_info.get('speed', 0.0)
            fan_rpm = inner_fan_info.get('rpm')
            if fan_speed > 0 and fan_rpm is not None and fan_rpm == 0:
                if self.fan_rpm_fault_counter <= self.fan_rpm_fault_threshold:
                    if self.fan_rpm_fault_counter == self.fan_rpm_fault_threshold:
                        fault_detected = True
                        logging.error("[purifier] Inner fan fault detected: fan is enabled but RPM is 0!")
                    self.fan_rpm_fault_counter += 1
                else:
                    self.fan_rpm_fault_counter = 0
        return fault_detected
    def _handle_hot_chamber_mode(self, eventtime):
        # Automatically turn off exhaust fan if it's running in current mode
        if self._exhaust_fan is not None and self._exhaust_fan.get_speed() != 0:
            self.set_exhaust_fan_speed(0)

        fault_detected = self._check_inner_fan_rpm_fault(eventtime)
        if fault_detected and not self.fan_fault_reported:
            self.fan_fault_reported = True
            msg = "Inner fan fault detected: fan is enabled but RPM is 0!"
            self.printer.raise_structured_code_exception("0002-0533-0000-0000", msg)
            self.printer.send_event("print_stats:update_exception_info",
                                    533,
                                    0,
                                    0,
                                    msg,
                                    2)
            self._pause_print()
            return

        if self.preheat_wait_enabled:
            if self.preheat_check_timeout_time is None:
                self.preheat_check_timeout_time = eventtime + self.preheat_check_timeout_interval

            # Reset if temperature is above desired or timeout reached
            if ((self.average_temperature is not None and
                 self.desired_chamber_temp > 0 and
                 self.average_temperature >= self.desired_chamber_temp) or
                eventtime > self.preheat_check_timeout_time):
                self._reset_preheat_state()
    def _update_temperature_data(self, eventtime):
        try:
            if self.external_temp_sensor is not None:
                current_temp, target_temp = self.external_temp_sensor.get_temp(eventtime)
                self.temp_readings.append(current_temp)

                while len(self.temp_readings) > self.avg_temp_samples:
                    self.temp_readings.pop(0)

                if len(self.temp_readings) >= self.avg_temp_samples:
                    self.average_temperature = sum(self.temp_readings) / len(self.temp_readings)
        except Exception as e:
            logging.error("[purifier] Failed to update chamber temperature data: %s", str(e))
    def _trigger_cooling_alarm(self):
        current_temp = self.average_temperature if self.average_temperature is not None else "Unknown"
        self.critical_temp_reported = True
        msg = ("Chamber temperature is too high! \n"
            "Current temperature: %s, Critical temperature: %.2f") % (current_temp, self.critical_chamber_temp)
        msg = "Failed to cool chamber temperature: %s" % msg
        self.printer.raise_structured_code_exception("0002-0533-0000-0001", msg)
        self.printer.send_event("print_stats:update_exception_info",
                                533,
                                0,
                                1,
                                msg,
                                2)
        self._pause_print()

    def _handle_cool_chamber_mode(self, eventtime):
        if (self.external_temp_sensor is not None and
            self.average_temperature is not None and
            self._exhaust_fan is not None):
            exhaust_fan_speed = self._exhaust_fan.get_speed()
            target_speed = exhaust_fan_speed
            exhaust_fan_max_power = self._exhaust_fan.get_max_power()
            if self.desired_chamber_temp and self.desired_chamber_temp > 0:
                if not self.critical_temp_reported:
                    # Initialize tracking variables on first run
                    if self.cool_check_last_temp is None:
                        self.cool_check_last_temp = self.average_temperature
                    if self.cool_check_timeout_time is None:
                        self.cool_check_timeout_time = eventtime + self.cool_check_timeout_interval
                    if self.dynamic_fan_power_adjust_time is None:
                        self.dynamic_fan_power_adjust_time = eventtime + self.dynamic_fan_power_adjust_interval
                    if self.cool_check_last_adjust_temp is None:
                        self.cool_check_last_adjust_temp = self.average_temperature

                    # --- Fan speed control ---
                    # Asymmetric strategy, evaluated at power_adjust_interval:
                    #   Above critical: always full speed
                    #   Rising:  linear [desired, critical] → [current, max], 5% resolution
                    #   Falling: decrease by 10%, min at threshold
                    # Uses cool_check_last_adjust_temp for direction detection to avoid
                    # 1-second noise: compares current temp to temp at last adjustment
                    if self.dynamic_fan_control and eventtime > self.dynamic_fan_power_adjust_time:
                        self.dynamic_fan_power_adjust_time = eventtime + self.dynamic_fan_power_adjust_interval
                        min_speed = self.exhaust_fan_speed_threshold
                        max_speed = exhaust_fan_max_power
                        lower_bound = self.desired_chamber_temp
                        upper_bound = self.critical_chamber_temp

                        if self.average_temperature >= self.critical_chamber_temp:
                            # Above critical: always full speed
                            target_speed = max_speed
                        elif self.average_temperature > self.cool_check_last_adjust_temp:
                            # Temperature rising: linear from current to max, 5% resolution
                            # Floor at min_speed so manually lowered speed recovers
                            if upper_bound <= lower_bound:
                                target_speed = max_speed if self.average_temperature >= lower_bound else max(exhaust_fan_speed, min_speed)
                            elif self.average_temperature <= lower_bound:
                                if self.average_temperature < lower_bound - self.cooling_fan_power_start_increment:
                                    target_speed = exhaust_fan_speed
                                else:
                                    target_speed = max(exhaust_fan_speed, min_speed)
                            elif self.average_temperature >= upper_bound:
                                target_speed = max_speed
                            else:
                                ratio = (self.average_temperature - lower_bound) / (upper_bound - lower_bound)
                                target_speed = max(exhaust_fan_speed, min_speed) + ratio * (max_speed - max(exhaust_fan_speed, min_speed))
                            target_speed = round(target_speed / 0.01) * 0.01
                            target_speed = min(target_speed, max_speed)
                        elif self.average_temperature < self.cool_check_last_adjust_temp:
                            # Temperature falling: decrease by 10%, min at threshold
                            if self.average_temperature < lower_bound:
                                if exhaust_fan_speed > min_speed:
                                    target_speed = round(max(min_speed, exhaust_fan_speed - self.dynamic_fan_power_decrement), 2)
                        else:
                            target_speed = exhaust_fan_speed

                        if target_speed == exhaust_fan_speed:
                            if self.average_temperature < lower_bound - self.cooling_fan_power_start_increment:
                                if exhaust_fan_speed > min_speed:
                                    target_speed = round(max(min_speed, exhaust_fan_speed - self.dynamic_fan_power_decrement), 2)


                        if abs(target_speed - exhaust_fan_speed) > 0.01:
                            logging.info(
                                "[purifier] Adjusting exhaust fan speed from %.2f to %.2f, "
                                "temp=%.2f, desired=%.2f, critical=%.2f" %
                                (exhaust_fan_speed, target_speed,
                                 self.average_temperature, self.desired_chamber_temp,
                                 self.critical_chamber_temp))
                            self.set_exhaust_fan_speed(target_speed)

                        self.cool_check_last_adjust_temp = self.average_temperature

                    prev_temp = self.cool_check_last_temp
                    if self.average_temperature < self.cool_check_last_temp:
                        self.cool_check_last_temp = self.average_temperature

                    # --- Critical alarm logic ---
                    if self.average_temperature > self.critical_chamber_temp:
                        if self.preheat_wait_enabled:
                            # WAIT_CHAMBER_TEMP mode: check downward trend
                            if self.average_temperature < prev_temp:
                                # Downward trend: reset timeout, continue waiting
                                self.cool_check_timeout_time = eventtime + self.cool_check_timeout_interval
                            elif eventtime >= self.cool_check_timeout_time:
                                # No downward trend + timeout → alarm
                                self._trigger_cooling_alarm()
                                return
                        else:
                            # Non-WAIT mode: simple timeout check
                            if eventtime >= self.cool_check_timeout_time:
                                self._trigger_cooling_alarm()
                                return
                    else:
                        # Temperature below critical: reset timeout
                        self.cool_check_timeout_time = eventtime + self.cool_check_timeout_interval
                else:
                    self.cool_check_last_temp = None
                    self.cool_check_last_adjust_temp = None
                    self.cool_check_timeout_time = None
                    self.dynamic_fan_power_adjust_time = None


        if self.preheat_wait_enabled:
            if self.external_temp_sensor is not None:
                if self.average_temperature is not None:
                    current_temp = self.average_temperature
                    if (current_temp < self.critical_chamber_temp - self.cooling_activation_offset or
                        current_temp < self.desired_chamber_temp):
                        self._reset_preheat_state()
                        return

                    if self.preheat_check_last_temp is None or self.preheat_check_timeout_time is None:
                        self.preheat_check_timeout_time = eventtime + self.preheat_check_timeout_interval
                        self.preheat_check_last_temp = current_temp
                        return

                    if current_temp < self.preheat_check_last_temp - self.preheat_min_valid_rise_temp:
                        self.preheat_check_last_temp = current_temp
                        self.preheat_check_timeout_time = eventtime + self.preheat_check_timeout_interval

                if self.preheat_check_timeout_time is None:
                    self.preheat_check_timeout_time = eventtime + self.preheat_check_timeout_interval

                if eventtime > self.preheat_check_timeout_time:
                    self._reset_preheat_state()
            else:
                self._reset_preheat_state()
    def _handle_preheat_chamber_mode(self, eventtime):
        # current_temp_str = f"{self.average_temperature:.2f}" if self.average_temperature is not None else "Unknown"
        # inner_fan_speed = self._inner_fan.get_speed() if self._inner_fan else 0
        # exhaust_fan_speed = self._exhaust_fan.get_speed() if self._exhaust_fan else 0
        # self.gcode.respond_info(f"[purifier] handle_preheat_chamber_mode - Current: {current_temp_str}°C, "
        #                        f"\nInner Fan Speed: {inner_fan_speed}, Exhaust Fan Speed: {exhaust_fan_speed}, "
        #                        f"\nDesired Temp: {self.desired_chamber_temp}°C, Preheat Wait: {self.preheat_wait_enabled}, "
        #                        f"\nLast Check Temp: {self.preheat_check_last_temp}, Timeout: {self.preheat_check_timeout_time}")
        if self._exhaust_fan is not None and self._exhaust_fan.get_speed() != 0:
            self.set_exhaust_fan_speed(0)

        fault_detected = self._check_inner_fan_rpm_fault(eventtime)
        if fault_detected and not self.fan_fault_reported:
            msg = "Inner fan fault detected: fan is enabled but RPM is 0!"
            self.printer.raise_structured_code_exception("0002-0533-0000-0000", msg)
            self.printer.send_event("print_stats:update_exception_info",
                                    533,
                                    0,
                                    0,
                                    msg,
                                    2)
            self.fan_fault_reported = True
            self._pause_print()
            return

        if self.preheat_wait_enabled:
            if self.external_temp_sensor is not None:
                if self.average_temperature is not None:
                    current_temp = self.average_temperature
                    if current_temp >= self.desired_chamber_temp:
                        self._reset_preheat_state()
                        return

                    if self.preheat_check_last_temp is None or self.preheat_check_timeout_time is None:
                        self.preheat_check_timeout_time = eventtime + self.preheat_check_timeout_interval
                        self.preheat_check_last_temp = current_temp
                        return

                    if current_temp > self.preheat_check_last_temp + self.preheat_min_valid_rise_temp:
                        self.preheat_check_last_temp = current_temp
                        self.preheat_check_timeout_time = eventtime + self.preheat_check_timeout_interval

            if self.preheat_check_timeout_time is None:
                self.preheat_check_timeout_time = eventtime + self.preheat_check_timeout_interval

            if eventtime > self.preheat_check_timeout_time:
                self._reset_preheat_state()
    def _reset_chamber_mode(self):
        self.preheat_wait_enabled = False
        self.fan_rpm_fault_counter = 0
        self.preheat_check_last_temp = None
        self.preheat_check_timeout_time = None
        self.desired_chamber_temp = 0
        self.critical_chamber_temp = 0
        self.dynamic_fan_control = self.dynamic_fan_control_default
        self.fan_fault_reported = False
        self.critical_temp_reported = False
        self.cool_check_last_temp = None
        self.cool_check_last_adjust_temp = None
        self.cool_check_timeout_time = None
        self.dynamic_fan_power_adjust_time = None
        self.exhaust_fan_speed_threshold = 0
        self.inner_fan_speed_threshold = 0

    def set_exhaust_fan_delay_turn_off(self, delay):
        if self._exhaust_fan_state == FAN_STATE_TURN_OFF:
            self.is_print_task_delay_turnoffing_exhaust = False
            return

        if delay < 1:
            self.set_exhaust_fan_speed(0)
        else:
            self._exhaust_fan_state = FAN_STATE_TURNING_OFF
            self.reactor.update_timer(self._exhaust_delay_timer, self.reactor.monotonic() + delay)
            self.is_print_task_delay_turnoffing_exhaust = True

    def set_inner_fan_delay_turn_off(self, delay):
        if self._inner_fan_state == FAN_STATE_TURN_OFF:
            self.is_print_task_delay_turnoffing_inner = False
            return

        if delay < 1:
            self.set_inner_fan_speed(0)
        else:
            self._inner_fan_state = FAN_STATE_TURNING_OFF
            self.reactor.update_timer(self._inner_delay_timer, self.reactor.monotonic() + delay)
            self.is_print_task_delay_turnoffing_inner = True

    def get_status(self, eventtime):
        exhaust_fan_status = None
        if self._exhaust_fan is not None:
            exhaust_fan_status = self._exhaust_fan.get_status(eventtime)
        inner_fan_status = None
        if self._inner_fan is not None:
            inner_fan_status = self._inner_fan.get_status(eventtime)

        status_dict = {
            'power_detected': self._power_detected,
            'power_det_value': round(self._power_det_value * 3.3, 1),
            'mode': self.purifier_mode,
            'desired_chamber_temp': self.desired_chamber_temp,
            'critical_chamber_temp': self.critical_chamber_temp,
        }
        if self._inner_fan is not None:
            status_dict.update({'inner_fan_work_time': round(self.config_info['inner_work_time'], 1)})
            if 'rpm' in inner_fan_status:
                status_dict.update({'inner_fan_rpm': inner_fan_status['rpm']})

        if exhaust_fan_status is not None:
            status_dict.update({'exhaust_fan': {}})
            status_dict['exhaust_fan'].update({'speed': exhaust_fan_status['speed']})
            status_dict['exhaust_fan'].update({'delay': self.config_info['exhaust_delay_time']})
            status_dict['exhaust_fan'].update({'speed_threshold': self.exhaust_fan_speed_threshold})
        if inner_fan_status is not None:
            status_dict.update({'inner_fan': {}})
            status_dict['inner_fan'].update({'speed': inner_fan_status['speed']})
            status_dict['inner_fan'].update({'delay': self.config_info['inner_delay_time']})
            status_dict['inner_fan'].update({'speed_threshold': self.inner_fan_speed_threshold})

        return status_dict

    def _handle_control_purifier(self, web_request):
        try:
            fan = web_request.get('fan', None)
            speed = web_request.get_int('speed', None)
            delay = web_request.get_int('delay', None)
            work = web_request.get_int('work', None)
            skip_delay = web_request.get_int('skip_delay', 1)
            logging.info(f"[purifier] wb, control_purifier: {web_request.get_raw_parameters()}")

            need_save = False

            if fan not in VALID_PURIFIER_FAN_TYPE:
                raise ValueError("[purifier] fan neme error!")

            if speed is not None:
                if not self._power_detected and speed > 0:
                    raise ValueError("[purifier] purifier not exist!")

            if fan == 'exhaust':
                if delay != None:
                    self.config_info['exhaust_delay_time'] = delay
                    need_save = True
                else:
                    delay = self.config_info['exhaust_delay_time']

                if speed is not None:
                    if speed > 0:
                        self.set_exhaust_fan_speed(speed / 100.0)
                    else:
                        if skip_delay != 0:
                            self.set_exhaust_fan_speed(0)
                        else:
                            self.set_exhaust_fan_delay_turn_off(delay)

            elif fan == 'inner':
                if delay != None:
                    self.config_info['inner_delay_time'] = delay
                    need_save = True
                else:
                    delay = self.config_info['inner_delay_time']

                if work != None:
                    if work < 0:
                        raise ValueError("[purifier] work time must >= 0!")
                    self.config_info['inner_work_time'] = float(work)
                    need_save = True

                if speed is not None:
                    if speed > 0:
                        self.set_inner_fan_speed(speed / 100.0)
                    else:
                        if skip_delay != 0:
                            self.set_inner_fan_speed(0)
                        else:
                            self.set_inner_fan_delay_turn_off(delay)

            else:
                pass

            web_request.send({'state': 'success'})

        except Exception as e:
            web_request.send({'state': 'error', 'message': str(e)})

        finally:
            if need_save:
                if not self.printer.update_snapmaker_config_file(self.config_path,
                            self.config_info, DEFAULT_PURIFIER_CONFIG):
                    logging.error("[purifier] save purifier failed\r\n")

    def cmd_SET_PURIFIER(self, gcmd):
        logging.info("[purifier] SET_PURIFIER %s", gcmd.get_raw_command_parameters())

        fan = gcmd.get('FAN')
        speed = gcmd.get_float('SPEED', None, minval=0)
        delay = gcmd.get_int('DELAY_OFF', None, minval=0)
        work = gcmd.get_int('WORK', None, minval=0)

        need_save = False

        if fan not in VALID_PURIFIER_FAN_TYPE:
            raise gcmd.error(f"[purifier] fan name error!")

        if speed is not None:
            if not self._power_detected and speed > 0:
                raise gcmd.error("[purifier] purifier not exist!")

        if fan == 'exhaust':
            if delay != None:
                self.config_info['exhaust_delay_time'] = delay
                need_save = True
            else:
                delay = self.config_info['exhaust_delay_time']

            if speed is not None:
                if speed > 0:
                    self.set_exhaust_fan_speed(speed)
                else:
                    self.set_exhaust_fan_delay_turn_off(delay)

        elif fan == 'inner':
            if delay != None:
                self.config_info['inner_delay_time'] = delay
                need_save = True
            else:
                delay = self.config_info['inner_delay_time']

            if work != None:
                if work < 0:
                    raise gcmd.error("[purifier] work time must >= 0!")
                self.config_info['inner_work_time'] = float(work)
                need_save = True

            if speed is not None:
                if speed > 0:
                    self.set_inner_fan_speed(speed)
                else:
                    self.set_inner_fan_delay_turn_off(delay)

        else:
            pass

        if need_save:
            if not self.printer.update_snapmaker_config_file(self.config_path,
                        self.config_info, DEFAULT_PURIFIER_CONFIG):
                logging.error("[purifier] save purifier failed\r\n")

    def cmd_GET_PURIFIER(self, gcmd):
        status = self.get_status(self.reactor.monotonic())

        # Add more detailed information
        mode_names = {
            MODE_IDLE: "IDLE",
            MODE_COOL_CHAMBER: "COOL_CHAMBER",
            MODE_PREHEAT_CHAMBER: "PREHEAT_CHAMBER",
            MODE_HOT_CHAMBER: "HOT_CHAMBER"
        }

        detailed_status = {
            'mode': mode_names.get(self.purifier_mode, "UNKNOWN"),
            'preheat_wait_enabled': self.preheat_wait_enabled,
            'desired_chamber_temp': self.desired_chamber_temp,
            'critical_chamber_temp': self.critical_chamber_temp,
            'average_temperature': self.average_temperature,
            'preheat_check_last_temp': self.preheat_check_last_temp,
            'preheat_check_timeout_time': self.preheat_check_timeout_time,
            'fan_rpm_fault_counter': self.fan_rpm_fault_counter,
            'fan_fault_reported': self.fan_fault_reported,
            'dynamic_fan_control': self.dynamic_fan_control,
            'critical_temp_reported': self.critical_temp_reported
        }
        status.update(detailed_status)
        gcmd.respond_info(str(status), log=False)

    def _setup_idle_mode(self, gcmd):
        def safe_get_config_int(key, default_val):
            try:
                val = self.config_info.get(key, default_val)
                return int(val) if val is not None else default_val
            except (ValueError, TypeError) as e:
                logging.warning(f"[purifier] Config value '{key}' invalid ({val}), using default {default_val}")
                return default_val

        exhaust_delay = gcmd.get_int('EXHAUST_FAN_DELAY_OFF', safe_get_config_int('exhaust_delay_time', DEFAULT_EXHAUST_FAN_DELAY_TIME))
        inner_delay = gcmd.get_int('INNER_FAN_DELAY_OFF', safe_get_config_int('inner_delay_time', DEFAULT_INNER_FAN_DELAY_TIME))

        self._reset_chamber_mode()
        self.set_exhaust_fan_delay_turn_off(exhaust_delay)
        self.set_inner_fan_delay_turn_off(inner_delay)
        self.purifier_mode = MODE_IDLE
        gcmd.respond_info(f"Purifier mode set to IDLE\n"
            f"  EXHAUST_FAN_DELAY_OFF={exhaust_delay}\n"
            f"  INNER_FAN_DELAY_OFF={inner_delay}")

    def _setup_cool_chamber_mode(self, gcmd):
        fan_speed = gcmd.get_float('FAN_SPEED', 0.6, minval=0.0, maxval=1.0)
        desired_temp = gcmd.get_float('DESIRE_TEMP', 42)
        alarm_temp = gcmd.get_float('ALARM_TEMP', desired_temp+self.desired_critical_min_temp_diff)
        alarm_temp = max(alarm_temp, desired_temp+self.desired_critical_min_temp_diff)
        delay_off = gcmd.get_int('DELAY_OFF', None, minval=0)
        dynamic_fan_control = gcmd.get_int('DYNAMIC_FAN_CONTROL', self.dynamic_fan_control_default, minval=0, maxval=1)
        self._reset_chamber_mode()
        self.desired_chamber_temp = desired_temp
        self.critical_chamber_temp = alarm_temp
        self.dynamic_fan_control = dynamic_fan_control
        self.set_exhaust_fan_speed(fan_speed)
        self.set_inner_fan_speed(0)
        self.config_info['inner_delay_time'] = 0
        self.exhaust_fan_speed_threshold = fan_speed
        self.purifier_mode = MODE_COOL_CHAMBER
        if delay_off is not None:
            if self.config_info.get('exhaust_delay_time', DEFAULT_EXHAUST_FAN_DELAY_TIME) != delay_off:
                self.config_info['exhaust_delay_time'] = delay_off
                self.printer.update_snapmaker_config_file(self.config_path,
                            self.config_info, DEFAULT_PURIFIER_CONFIG)
        gcmd.respond_info(f"Purifier mode set to COOL CHAMBER\n"
                        f"  FAN_SPEED={fan_speed}\n"
                        f"  DESIRE_TEMP={desired_temp}\n"
                        f"  ALARM_TEMP={alarm_temp}\n"
                        f"  DYNAMIC_FAN_CONTROL={dynamic_fan_control}\n"
                        f"  DELAY_OFF={self.config_info.get('exhaust_delay_time', DEFAULT_EXHAUST_FAN_DELAY_TIME)}")
    def _setup_preheat_chamber_mode(self, gcmd):
        desired_temp = gcmd.get_float('DESIRE_TEMP', 0)
        fan_speed = gcmd.get_float('FAN_SPEED', 0.6, minval=0.0)
        delay_off = gcmd.get_int('DELAY_OFF', None, minval=0)
        self._reset_chamber_mode()
        self.set_inner_fan_speed(fan_speed)
        self.set_exhaust_fan_speed(0)
        self.config_info['exhaust_delay_time'] = 0
        self.desired_chamber_temp = desired_temp
        self.purifier_mode = MODE_PREHEAT_CHAMBER
        self.inner_fan_speed_threshold = fan_speed
        if delay_off is not None:
            if self.config_info.get('inner_delay_time', DEFAULT_INNER_FAN_DELAY_TIME) != delay_off:
                self.config_info['inner_delay_time'] = delay_off
                self.printer.update_snapmaker_config_file(self.config_path,
                            self.config_info, DEFAULT_PURIFIER_CONFIG)
        gcmd.respond_info(f"Purifier mode set to PREHEAT CHAMBER\n"
                        f"  DESIRE_TEMP={desired_temp}\n"
                        f"  FAN_SPEED={fan_speed}\n"
                        f"  DELAY_OFF={self.config_info.get('inner_delay_time', DEFAULT_INNER_FAN_DELAY_TIME)}")

    def _setup_hot_chamber_mode(self, gcmd):
        desired_temp = gcmd.get_float('DESIRE_TEMP', 0)
        fan_speed = gcmd.get_float('FAN_SPEED', 0.6, minval=0.0)
        delay_off = gcmd.get_int('DELAY_OFF', None, minval=0)
        self._reset_chamber_mode()
        self.set_inner_fan_speed(fan_speed)
        self.set_exhaust_fan_speed(0)
        self.config_info['exhaust_delay_time'] = 0
        self.desired_chamber_temp = desired_temp
        self.purifier_mode = MODE_HOT_CHAMBER
        self.inner_fan_speed_threshold = fan_speed
        if delay_off is not None:
            if self.config_info.get('inner_delay_time', DEFAULT_INNER_FAN_DELAY_TIME) != delay_off:
                self.config_info['inner_delay_time'] = delay_off
                self.printer.update_snapmaker_config_file(self.config_path,
                            self.config_info, DEFAULT_PURIFIER_CONFIG)
        gcmd.respond_info(f"Purifier mode set to HOT CHAMBER\n"
                        f"  DESIRE_TEMP={desired_temp}\n"
                        f"  FAN_SPEED={fan_speed}\n"
                        f"  DELAY_OFF={self.config_info.get('inner_delay_time', DEFAULT_INNER_FAN_DELAY_TIME)}")
    def cmd_SET_PURIFIER_MODE(self, gcmd):
        try:
            if not self._power_detected:
                gcmd.respond_info("[purifier] purifier not exist!")
                return
            mode_handlers = {
                MODE_IDLE: self._setup_idle_mode,
                MODE_COOL_CHAMBER: self._setup_cool_chamber_mode,
                MODE_PREHEAT_CHAMBER: self._setup_preheat_chamber_mode,
                MODE_HOT_CHAMBER: self._setup_hot_chamber_mode,
            }
            mode = gcmd.get_int('MODE', None)
            if mode is not None:
                if mode not in mode_handlers:
                    err_msg = f'Invalid purifier mode {mode}'
                    raise gcmd.error(err_msg)
                self.reactor.update_timer(self._periodic_check_timer, self.reactor.NEVER)
                try:
                    mode_handlers[mode](gcmd)
                finally:
                    self.reactor.update_timer(self._periodic_check_timer, self.reactor.NOW)
            if self.print_stats is not None:
                if self.print_stats.state in ['printing', 'paused']:
                    self.last_print_task_purifier_mode = self.purifier_mode
        except Exception as e:
            raise
    def cmd_WAIT_CHAMBER_TEMP(self, gcmd):
        if not self._power_detected:
            gcmd.respond_info("[purifier] Cannot wait for temperature: purifier not detected!")
            return
        timeout = gcmd.get_float('TIMEOUT', self.preheat_check_timeout_default_interval)
        self.reactor.update_timer(self._periodic_check_timer, self.reactor.NEVER)
        cur_time = self.reactor.monotonic()
        self.preheat_check_timeout_time = None
        self.preheat_wait_enabled = True
        if timeout != self.preheat_check_timeout_interval:
            self.preheat_check_timeout_interval = timeout
        self.reactor.update_timer(self._periodic_check_timer, self.reactor.NOW)

        # Calculate wait timeout based on user-specified timeout
        wait_timeout_time = cur_time + timeout + 5  # Adding small buffer
        timer_execution_counter = self.timer_execution_counter
        last_info_time = cur_time

        self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=PREHEAT_CHAMBER")
        while self.preheat_wait_enabled and self.reactor.monotonic() < wait_timeout_time and not self.printer.is_shutdown() and self._power_detected:
            current_time = self.reactor.monotonic()
            if current_time - last_info_time >= 5.0:
                # Show current temperature and target temperature
                current_temp_str = f"{self.average_temperature:.2f}" if self.average_temperature is not None else "Unknown"
                remaining_time = max(0, wait_timeout_time - current_time)

                # Calculate remaining preheat check timeout time if available
                remaining_preheat_timeout = "N/A"
                if self.preheat_check_timeout_time is not None:
                    remaining_preheat_timeout = max(0, self.preheat_check_timeout_time - current_time)
                    remaining_preheat_timeout = f"{remaining_preheat_timeout:.1f}s"
                else:
                    remaining_preheat_timeout = "N/A"

                # Format the last checked temperature
                last_temp_str = f"{self.preheat_check_last_temp:.2f}" if self.preheat_check_last_temp is not None else "None"

                msg = f"[purifier] Waiting for chamber temperature... Current: {current_temp_str}°C, " \
                      f"Target: {self.desired_chamber_temp}°C, Timeout: {timeout}s, " \
                      f"Preheat Timeout: {remaining_preheat_timeout}, Last Temp: {last_temp_str}, Remaining: {remaining_time:.1f}s"
                gcmd.respond_info(msg)
                last_info_time = current_time

            self.reactor.pause(self.reactor.monotonic() + 0.5)
            if timer_execution_counter != self.timer_execution_counter:
                wait_timeout_time = self.reactor.monotonic() + 5*self.check_interval + 2
                timer_execution_counter = self.timer_execution_counter
        self._reset_preheat_state()
        self.reactor.pause(self.reactor.monotonic() + 0.5)
        self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=IDLE")

def load_config(config):
    return Purifier(config)

