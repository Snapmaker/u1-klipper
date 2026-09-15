# Tracking of PWM controlled heaters and their temperature control
#
# Copyright (C) 2016-2020  Kevin O'Connor <kevin@koconnor.net>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import os, logging, threading, queuefile
import json


######################################################################
# Heater
######################################################################

KELVIN_TO_CELSIUS = -273.15
MAX_HEAT_TIME = 7.0
AMBIENT_TEMP = 25.
PID_PARAM_BASE = 255.
READ_TIME_TOL = 0.45
MIN_UPDATE_RATIO = 0.15

class Heater:
    def __init__(self, config, sensor):
        self.printer = config.get_printer()
        self.name = config.get_name()
        self.short_name = short_name = self.name.split()[-1]
        # Setup sensor
        self.sensor = sensor
        self.min_temp = config.getfloat('min_temp', minval=KELVIN_TO_CELSIUS)
        self.max_temp = config.getfloat('max_temp', above=self.min_temp)
        min_temp_overshoot = config.getfloat('min_temp_overshoot', 0, minval=0)
        max_temp_overshoot = config.getfloat('max_temp_overshoot', 0, minval=0)
        self.sensor.setup_minmax(self.min_temp - min_temp_overshoot, self.max_temp + max_temp_overshoot)
        self.sensor.setup_callback(self.temperature_callback)
        self.sensor.set_read_tolerance(READ_TIME_TOL, MIN_UPDATE_RATIO)
        self.pwm_delay = self.sensor.get_report_time_delta()
        # Setup temperature checks
        self.min_extrude_temp = config.getfloat(
            'min_extrude_temp', 170.,
            minval=self.min_temp, maxval=self.max_temp)
        is_fileoutput = (self.printer.get_start_args().get('debugoutput')
                         is not None)
        self.can_extrude = self.min_extrude_temp <= 0. or is_fileoutput
        self.max_power = config.getfloat('max_power', 1., above=0., maxval=1.)
        self.smooth_time = config.getfloat('smooth_time', 1., above=0.)
        self.pwm_min_set_diff = config.getfloat('pwm_min_set_diff', 0.05, above=0.)
        self.inv_smooth_time = 1. / self.smooth_time
        self.is_shutdown = False
        self.lock = threading.Lock()
        self.last_temp = self.smoothed_temp = self.target_temp = 0.
        self.last_temp_time = 0.
        # Special variable，extruder hold max power limit
        self.idle_hold_max_power = config.getfloat('idle_hold_max_power', None, above=0., maxval=1.)
        self.active_hold_max_power = config.getfloat('active_hold_max_power', None, above=0., maxval=1.)
        self.dynamic_max_power = self.max_power
        self.pending_power_change = False
        # pwm caching
        self.next_pwm_time = 0.
        self.last_pwm_value = 0.
        # Setup control algorithm sub-class
        algos = {'watermark': ControlBangBang, 'pid': ControlPID}
        algo = config.getchoice('control', algos)
        self.control = algo(self, config)
        self.allow_pid_calibrate = config.getboolean('allow_pid_calibrate', True)
        # Setup output heater pin
        heater_pin = config.get('heater_pin')
        ppins = self.printer.lookup_object('pins')
        self.mcu_pwm = ppins.setup_pin('pwm', heater_pin)
        pwm_cycle_time = config.getfloat('pwm_cycle_time', 0.100, above=0.,
                                         maxval=self.pwm_delay)
        self.mcu_pwm.setup_cycle_time(pwm_cycle_time)
        self.max_heat_time = config.getfloat('max_heat_time', MAX_HEAT_TIME,
                                             above=0.)
        self.mcu_pwm.setup_max_duration(self.max_heat_time)
        # Load additional modules
        self.printer.load_object(config, "verify_heater %s" % (short_name,))
        self.printer.load_object(config, "pid_calibrate")
        gcode = self.printer.lookup_object("gcode")
        gcode.register_mux_command("SET_HEATER_TEMPERATURE", "HEATER",
                                   short_name, self.cmd_SET_HEATER_TEMPERATURE,
                                   desc=self.cmd_SET_HEATER_TEMPERATURE_help)
        gcode.register_mux_command("SET_PID_PROFILE", "HEATER",
                                   short_name, self.cmd_SET_PID_PROFILE,
                                   desc=self.cmd_SET_PID_PROFILE_help)
        self.printer.register_event_handler("klippy:shutdown",
                                            self._handle_shutdown)
    def set_pwm(self, read_time, value):
        if self.target_temp <= 0. or self.is_shutdown:
            value = 0.
        if ((read_time < self.next_pwm_time or not self.last_pwm_value)
            and abs(value - self.last_pwm_value) < self.pwm_min_set_diff):
            # No significant change in value - can suppress update
            return
        pwm_time = read_time + self.pwm_delay
        min_pwm_time = self.mcu_pwm.get_mcu().estimated_print_time(
            self.printer.get_reactor().monotonic()) + 0.5 * self.pwm_delay
        if pwm_time < min_pwm_time:
            pwm_time = min_pwm_time
        pwm_window = min(0.5 * self.max_heat_time,
                         self.max_heat_time - 3. * self.pwm_delay - 0.001)
        self.next_pwm_time = pwm_time + max(0., pwm_window)
        self.last_pwm_value = value
        self.mcu_pwm.set_pwm(pwm_time, value)
    def temperature_callback(self, read_time, temp):
        with self.lock:
            time_diff = read_time - self.last_temp_time
            self.last_temp = temp
            self.last_temp_time = read_time
            self.control.temperature_update(read_time, temp, self.target_temp)
            temp_diff = temp - self.smoothed_temp
            adj_time = min(time_diff * self.inv_smooth_time, 1.)
            self.smoothed_temp += temp_diff * adj_time
            self.can_extrude = (self.smoothed_temp >= self.min_extrude_temp)
        #logging.debug("temp: %.3f %f = %f", read_time, temp)
    def _handle_shutdown(self):
        self.is_shutdown = True
    # External commands
    def get_name(self):
        return self.name
    def get_pwm_delay(self):
        return self.pwm_delay
    def get_max_power(self):
        return self.max_power
    def get_smooth_time(self):
        return self.smooth_time
    def get_dynamic_max_power(self):
        return self.dynamic_max_power
    def set_dynamic_max_power(self, power, delay_increase=True):
        if self.idle_hold_max_power is None and self.active_hold_max_power is None:
            return
        new_power = max(0., min(self.max_power, power))
        if delay_increase:
            if self.dynamic_max_power != new_power:
                if new_power <= self.dynamic_max_power:
                    self.dynamic_max_power = new_power
                    self.pending_power_change = False
                else:
                    if self.pending_power_change:
                        self.dynamic_max_power = new_power
                        self.pending_power_change = False
                    else:
                        self.pending_power_change = True
            else:
                self.pending_power_change = False
        else:
            self.dynamic_max_power = new_power
            self.pending_power_change = False
    def set_temp(self, degrees):
        if degrees and (degrees < self.min_temp or degrees > self.max_temp):
            err_msg = "%s: Requested temperature (%.1f) out of range (%.1f:%.1f)" % (
                self.short_name, degrees, self.min_temp, self.max_temp)
            if self.short_name == 'extruder':
                err_msg = '{"coded": "0003-0523-0000-0036", "oneshot": %d, "msg":"%s"}' % (1, err_msg)
            elif self.short_name.startswith('extruder') and self.short_name[8:].isdigit():
                index = int(self.short_name[8:])
                err_msg = '{"coded": "0003-0523-%04d-0036", "oneshot": %d, "msg":"%s"}' % (index, 1, err_msg)
            elif self.short_name == 'heater_bed':
                err_msg = '{"coded": "0003-0526-0000-0002", "oneshot": %d, "msg":"%s"}' % (1, err_msg)
            raise self.printer.command_error(err_msg)
            # raise self.printer.command_error(
            #     "Requested temperature (%.1f) out of range (%.1f:%.1f)"
            #     % (degrees, self.min_temp, self.max_temp))
        with self.lock:
            self.target_temp = degrees
    def get_temp(self, eventtime):
        print_time = self.mcu_pwm.get_mcu().estimated_print_time(eventtime) - 10.
        with self.lock:
            if self.last_temp_time < print_time:
                return 0., self.target_temp
            return self.smoothed_temp, self.target_temp
    def check_busy(self, eventtime):
        with self.lock:
            return self.control.check_busy(
                eventtime, self.smoothed_temp, self.target_temp)
    def set_control(self, control):
        with self.lock:
            old_control = self.control
            self.control = control
            self.target_temp = 0.
        return old_control
    def alter_target(self, target_temp):
        if target_temp:
            target_temp = max(self.min_temp, min(self.max_temp, target_temp))
        self.target_temp = target_temp
    def stats(self, eventtime):
        with self.lock:
            target_temp = self.target_temp
            last_temp = self.last_temp
            last_pwm_value = self.last_pwm_value
        is_active = target_temp or last_temp > 50.
        return is_active, '%s: target=%.0f temp=%.1f pwm=%.3f' % (
            self.short_name, target_temp, last_temp, last_pwm_value)
    def get_status(self, eventtime):
        with self.lock:
            target_temp = self.target_temp
            smoothed_temp = self.smoothed_temp
            last_pwm_value = self.last_pwm_value
        return {'temperature': round(smoothed_temp, 0), 'target': target_temp,
                'power': last_pwm_value}
    cmd_SET_HEATER_TEMPERATURE_help = "Sets a heater temperature"
    cmd_SET_PID_PROFILE_help = "Sets active PID profile"
    def cmd_SET_PID_PROFILE(self, gcmd):
        profile = gcmd.get('PROFILE', 'default')
        if not isinstance(self.control, ControlPID):
            raise gcmd.error("Heater is not using PID control")
        self.control.set_pid_profile(profile)

    def cmd_SET_HEATER_TEMPERATURE(self, gcmd):
        temp = gcmd.get_float('TARGET', 0.)
        pheaters = self.printer.lookup_object('heaters')
        pheaters.set_temperature(self, temp)


######################################################################
# Bang-bang control algo
######################################################################

class ControlBangBang:
    def __init__(self, heater, config):
        self.heater = heater
        self.heater_max_power = heater.get_max_power()
        self.max_delta = config.getfloat('max_delta', 2.0, above=0.)
        self.heating = False
    def temperature_update(self, read_time, temp, target_temp):
        if self.heating and temp >= target_temp+self.max_delta:
            self.heating = False
        elif not self.heating and temp <= target_temp-self.max_delta:
            self.heating = True
        if self.heating:
            heater_max_power = self.heater_max_power
            if self.heater.idle_hold_max_power is not None or self.heater.active_hold_max_power is not None:
                heater_max_power = min(heater_max_power, self.heater.get_dynamic_max_power())
            self.heater.set_pwm(read_time, heater_max_power)
        else:
            self.heater.set_pwm(read_time, 0.)
    def check_busy(self, eventtime, smoothed_temp, target_temp):
        return smoothed_temp < target_temp-self.max_delta


######################################################################
# Proportional Integral Derivative (PID) control algo
######################################################################

PID_SETTLE_DELTA = 2.
PID_SETTLE_SLOPE = .5

class ControlPID:
    def __init__(self, heater, config):
        self.heater = heater
        self.heater_max_power = heater.get_max_power()

        # Initialize PID profiles from config
        self.pid_profiles = {}
        self.ignore_pid_json = config.getboolean('ignore_pid_json', False)
        config_name = self.heater.get_name()
        config_dir = self.heater.printer.get_snapmaker_config_dir()
        self.json_filename = os.path.join(config_dir, config_name.replace(" ", "_") + "_pid_parameters.json")
        heater_json_profiles = None
        need_save_to_json = False
        if not self.ignore_pid_json:
            heater_json_profiles = self._load_heater_pid_profiles_from_json(self.json_filename)

        for prefix in ['', 'pid2_', 'pid3_']:
            profile = prefix[:-1] if prefix != '' else 'default'
            has_config_profile = config.getfloat(prefix + 'pid_Kp', None) is not None

            # If profile exists in JSON and JSON is enabled, try to use it
            profile_loaded_from_json = False
            if not self.ignore_pid_json and heater_json_profiles and profile in heater_json_profiles:
                validated_profile = self._validate_pid_profile(heater_json_profiles[profile])
                if validated_profile:
                    validated_profile['Kp'] = validated_profile['Kp'] / PID_PARAM_BASE
                    validated_profile['Ki'] = validated_profile['Ki'] / PID_PARAM_BASE
                    validated_profile['Kd'] = validated_profile['Kd'] / PID_PARAM_BASE
                    self.pid_profiles[profile] = validated_profile
                    profile_loaded_from_json = True
                else:
                    if not self.ignore_pid_json:
                        logging.warning("Invalid PID profile '%s' for heater '%s' in JSON file, using config values",
                                      profile, config_name)
                        need_save_to_json = True

            if has_config_profile:
                config_Kp = config.getfloat(prefix + 'pid_Kp')
                config_Ki = config.getfloat(prefix + 'pid_Ki')
                config_Kd = config.getfloat(prefix + 'pid_Kd')
                config_full_power_threshold = config.getfloat(prefix + 'full_power_threshold', None, above=0.)
                config_zero_power_threshold = config.getfloat(prefix + 'zero_power_threshold', None, above=0.)
                config_settle_delta = config.getfloat(prefix + 'settle_delta', PID_SETTLE_DELTA)
                config_settle_slope = config.getfloat(prefix + 'settle_slope', PID_SETTLE_SLOPE)

                profile_data = {
                    'Kp': config_Kp / PID_PARAM_BASE,
                    'Ki': config_Ki / PID_PARAM_BASE,
                    'Kd': config_Kd / PID_PARAM_BASE,
                    'full_power_threshold': config_full_power_threshold,
                    'zero_power_threshold': config_zero_power_threshold,
                    'settle_delta': config_settle_delta,
                    'settle_slope': config_settle_slope,
                }

                json_profile_data = {
                    'Kp': config_Kp,
                    'Ki': config_Ki,
                    'Kd': config_Kd,
                    'full_power_threshold': config_full_power_threshold,
                    'zero_power_threshold': config_zero_power_threshold,
                    'settle_delta': config_settle_delta,
                    'settle_slope': config_settle_slope,
                }

                if not profile_loaded_from_json:
                    self.pid_profiles[profile] = profile_data
                    if not self.ignore_pid_json:
                        need_save_to_json = True

                if not self.ignore_pid_json:
                    if heater_json_profiles is None:
                        heater_json_profiles = {}
                    heater_json_profiles[profile] = json_profile_data

        if not self.pid_profiles:
            raise config.error("No PID profiles configured")

        if not self.ignore_pid_json and need_save_to_json and heater_json_profiles:
            self._save_heater_pid_profiles_to_json(self.json_filename, heater_json_profiles)

        self.current_profile = 'default'
        self.Kp = self.pid_profiles[self.current_profile]['Kp']
        self.Ki = self.pid_profiles[self.current_profile]['Ki']
        self.Kd = self.pid_profiles[self.current_profile]['Kd']
        self.full_power_threshold = self.pid_profiles[self.current_profile]['full_power_threshold']
        self.zero_power_threshold = self.pid_profiles[self.current_profile]['zero_power_threshold']
        self.settle_delta = self.pid_profiles[self.current_profile]['settle_delta']
        self.settle_slope = self.pid_profiles[self.current_profile]['settle_slope']
        self.min_deriv_time = heater.get_smooth_time()
        self.temp_integ_max = 0.
        if self.Ki:
            self.temp_integ_max = self.heater_max_power / self.Ki
        self.prev_temp = AMBIENT_TEMP
        self.prev_temp_time = 0.
        self.prev_temp_deriv = 0.
        self.prev_temp_integ = 0.
        # logging.info("PID profile {} loaded for heater {}".format(self.current_profile, config_name))
        # logging.info("PID parameters: Kp: %0.2f Ki: %0.2f Kd: %0.2f" % (self.Kp*PID_PARAM_BASE,
        #                                                 self.Ki*PID_PARAM_BASE, self.Kd*PID_PARAM_BASE))
    def _validate_pid_profile(self, profile_data):
        if not isinstance(profile_data, dict):
            return None

        required_fields = ['Kp', 'Ki', 'Kd']
        validated_profile = {}

        for field in required_fields:
            if field not in profile_data:
                return None
            try:
                validated_profile[field] = float(profile_data[field])
            except (ValueError, TypeError):
                return None

        optional_fields = ['full_power_threshold', 'zero_power_threshold', 'settle_delta', 'settle_slope']
        for field in optional_fields:
            if field in profile_data and profile_data[field] is not None:
                try:
                    validated_profile[field] = float(profile_data[field])
                except (ValueError, TypeError):
                    pass
            else:
                if field == 'settle_delta':
                    validated_profile[field] = PID_SETTLE_DELTA
                elif field == 'settle_slope':
                    validated_profile[field] = PID_SETTLE_SLOPE
                else:
                    validated_profile[field] = None

        return validated_profile

    def _load_heater_pid_profiles_from_json(self, json_filename):
        try:
            if os.path.exists(json_filename):
                with open(json_filename, 'r') as f:
                    profiles = json.load(f)
                    validated_profiles = {}
                    for profile_name, profile_data in profiles.items():
                        validated_profile = self._validate_pid_profile(profile_data)
                        if validated_profile:
                            validated_profiles[profile_name] = validated_profile
                        else:
                            config_name = self.heater.get_name()
                            logging.warning("Invalid PID profile '%s' in JSON file '%s', skipping",
                                           profile_name, json_filename)
                    return validated_profiles
        except Exception as e:
            logging.warning("Failed to load PID profiles from JSON (%s): %s. Using config values and will recreate JSON.", json_filename, e)
        return None

    def _save_heater_pid_profiles_to_json(self, json_filename, profiles):
        try:
            os.makedirs(os.path.dirname(json_filename), exist_ok=True)
            json_content = json.dumps(profiles, indent=2)
            queuefile.async_write_file(json_filename, json_content, flush=True, safe_write=True)
        except Exception as e:
            logging.warning("Failed to save PID profiles to JSON (%s): %s", json_filename, e)
    def temperature_update(self, read_time, temp, target_temp):
        # Helper method to reset PID state
        def reset_pid_state():
            self.prev_temp = temp
            self.prev_temp_time = read_time
            self.prev_temp_deriv = 0.
            self.prev_temp_integ = 0.

        heater_max_power = self.heater_max_power
        if self.heater.idle_hold_max_power is not None or self.heater.active_hold_max_power is not None:
            heater_max_power = min(heater_max_power, self.heater.get_dynamic_max_power())

        # Check temperature thresholds
        if target_temp > 0:
            # Check if temperature is too high
            if (self.zero_power_threshold is not None and (temp - target_temp > self.zero_power_threshold)):
                self.heater.set_pwm(read_time, 0.)
                # Continue updating PID state variables
                time_diff = read_time - self.prev_temp_time
                temp_diff = temp - self.prev_temp
                if time_diff >= self.min_deriv_time:
                    temp_deriv = temp_diff / time_diff
                else:
                    temp_deriv = (self.prev_temp_deriv * (self.min_deriv_time-time_diff)
                                + temp_diff) / self.min_deriv_time
                temp_err = target_temp - temp
                temp_integ = self.prev_temp_integ + temp_err * time_diff
                temp_integ = max(0., min(self.temp_integ_max, temp_integ))

                # Store state for next measurement
                self.prev_temp = temp
                self.prev_temp_time = read_time
                self.prev_temp_deriv = temp_deriv
                self.prev_temp_integ = temp_integ
                return

            # Check if temperature is too low
            if (self.full_power_threshold is not None and (target_temp - temp > self.full_power_threshold)):
                self.heater.set_pwm(read_time, heater_max_power)
                reset_pid_state()
                return

        # Normal PID control
        time_diff = read_time - self.prev_temp_time
        # Calculate change of temperature
        temp_diff = temp - self.prev_temp
        if time_diff >= self.min_deriv_time:
            temp_deriv = temp_diff / time_diff
        else:
            temp_deriv = (self.prev_temp_deriv * (self.min_deriv_time-time_diff)
                          + temp_diff) / self.min_deriv_time
        # Calculate accumulated temperature "error"
        temp_err = target_temp - temp
        temp_integ = self.prev_temp_integ + temp_err * time_diff
        temp_integ = max(0., min(self.temp_integ_max, temp_integ))
        # Calculate output
        co = self.Kp*temp_err + self.Ki*temp_integ - self.Kd*temp_deriv
        #logging.debug("pid: %f@%.3f -> diff=%f deriv=%f err=%f integ=%f co=%d",
        #    temp, read_time, temp_diff, temp_deriv, temp_err, temp_integ, co)
        bounded_co = max(0., min(heater_max_power, co))
        self.heater.set_pwm(read_time, bounded_co)
        # Store state for next measurement
        self.prev_temp = temp
        self.prev_temp_time = read_time
        self.prev_temp_deriv = temp_deriv
        if co == bounded_co:
            self.prev_temp_integ = temp_integ
    def check_busy(self, eventtime, smoothed_temp, target_temp):
        temp_diff = target_temp - smoothed_temp
        return (abs(temp_diff) > self.settle_delta
                or abs(self.prev_temp_deriv) > self.settle_slope)

    def set_pid_profile(self, profile):
        if profile not in self.pid_profiles:
            raise self.heater.printer.command_error(
                "Unknown PID profile: %s" % (profile,))
        self.current_profile = profile
        gcode = self.heater.printer.lookup_object('gcode', None)
        if gcode is not None:
            gcode.respond_info("set pid profile: {}\n{}".format(profile, self.pid_profiles[profile]))
        self.Kp = self.pid_profiles[profile]['Kp']
        self.Ki = self.pid_profiles[profile]['Ki']
        self.Kd = self.pid_profiles[profile]['Kd']
        self.full_power_threshold = self.pid_profiles[self.current_profile]['full_power_threshold']
        self.zero_power_threshold = self.pid_profiles[self.current_profile]['zero_power_threshold']
        self.settle_delta = self.pid_profiles[self.current_profile]['settle_delta']
        self.settle_slope = self.pid_profiles[self.current_profile]['settle_slope']
        # Reset PID state when switching profiles
        self.prev_temp = AMBIENT_TEMP
        self.prev_temp_time = 0.
        self.prev_temp_deriv = 0.
        self.prev_temp_integ = 0.
        self.temp_integ_max = 0.
        if self.Ki:
            self.temp_integ_max = self.heater_max_power / self.Ki


######################################################################
# Sensor and heater lookup
######################################################################
MAX_HEATING_EXTRUDERS = 2
INACTIVE_EXTRUDER_TEMP_DELTA = 2.0
class PrinterHeaters:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.sensor_factories = {}
        self.heaters = {}
        self.gcode_id_to_sensor = {}
        self.available_heaters = []
        self.available_sensors = []
        self.available_monitors = []
        self.has_started = self.have_load_sensors = False
        self.active_heating_extruders = []
        self.pending_extruders = []
        self.extruder_list = []
        self.reactor = self.printer.get_reactor()
        self.heater_check_timer = None
        self.max_heating_extruders = MAX_HEATING_EXTRUDERS
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        self.printer.register_event_handler("gcode:request_restart",
                                            self.turn_off_all_heaters)
        # Register commands
        gcode = self.printer.lookup_object('gcode')
        gcode.register_command("TURN_OFF_HEATERS", self.cmd_TURN_OFF_HEATERS,
                               desc=self.cmd_TURN_OFF_HEATERS_help)
        gcode.register_command("M105", self.cmd_M105, when_not_ready=True)
        gcode.register_command("TEMPERATURE_WAIT", self.cmd_TEMPERATURE_WAIT,
                               desc=self.cmd_TEMPERATURE_WAIT_help)
    def load_config(self, config):
        self.have_load_sensors = True
        # Load default temperature sensors
        pconfig = self.printer.lookup_object('configfile')
        dir_name = os.path.dirname(__file__)
        filename = os.path.join(dir_name, 'temperature_sensors.cfg')
        try:
            dconfig = pconfig.read_config(filename)
        except Exception:
            raise config.config_error("Cannot load config '%s'" % (filename,))
        for c in dconfig.get_prefix_sections(''):
            self.printer.load_object(dconfig, c.get_name())
    def add_sensor_factory(self, sensor_type, sensor_factory):
        self.sensor_factories[sensor_type] = sensor_factory
    def setup_heater(self, config, gcode_id=None):
        heater_name = config.get_name().split()[-1]
        if heater_name in self.heaters:
            raise config.error("Heater %s already registered" % (heater_name,))
        # Setup sensor
        sensor = self.setup_sensor(config)
        # Create heater
        self.heaters[heater_name] = heater = Heater(config, sensor)
        self.register_sensor(config, heater, gcode_id)
        self.available_heaters.append(config.get_name())
        return heater
    def get_all_heaters(self):
        return self.available_heaters
    def lookup_heater(self, heater_name):
        if heater_name not in self.heaters:
            raise self.printer.config_error(
                "Unknown heater '%s'" % (heater_name,))
        return self.heaters[heater_name]
    def setup_sensor(self, config):
        if not self.have_load_sensors:
            self.load_config(config)
        sensor_type = config.get('sensor_type')
        if sensor_type not in self.sensor_factories:
            raise self.printer.config_error(
                "Unknown temperature sensor '%s'" % (sensor_type,))
        return self.sensor_factories[sensor_type](config)
    def register_sensor(self, config, psensor, gcode_id=None):
        self.available_sensors.append(config.get_name())
        if gcode_id is None:
            gcode_id = config.get('gcode_id', None)
            if gcode_id is None:
                return
        if gcode_id in self.gcode_id_to_sensor:
            raise self.printer.config_error(
                "G-Code sensor id %s already registered" % (gcode_id,))
        self.gcode_id_to_sensor[gcode_id] = psensor
    def register_monitor(self, config):
        self.available_monitors.append(config.get_name())
    def get_status(self, eventtime):
        return {'available_heaters': self.available_heaters,
                'available_sensors': self.available_sensors,
                'available_monitors': self.available_monitors}
    def turn_off_all_heaters(self, print_time=0.):
        # Clear all extruder heating state
        self.active_heating_extruders = []
        self.pending_extruders = []
        # Turn off all heaters
        for heater in self.heaters.values():
            heater.set_temp(0.)
    cmd_TURN_OFF_HEATERS_help = "Turn off all heaters"
    def cmd_TURN_OFF_HEATERS(self, gcmd):
        self.turn_off_all_heaters()
    # G-Code M105 temperature reporting
    def _handle_ready(self):
        self.has_started = True
        if self.heater_check_timer is None:
            self.heater_check_timer = self.reactor.register_timer(
                self._check_heater_queue, self.reactor.NOW)
        self.extruder_list = self.printer.lookup_object('extruder_list', [])
    def _get_temp(self, eventtime):
        # Tn:XXX /YYY B:XXX /YYY
        out = []
        if self.has_started:
            for gcode_id, sensor in sorted(self.gcode_id_to_sensor.items()):
                cur, target = sensor.get_temp(eventtime)
                out.append("%s:%.1f /%.1f" % (gcode_id, cur, target))
        if not out:
            return "T:0"
        return " ".join(out)
    def cmd_M105(self, gcmd):
        # Get Extruder Temperature
        reactor = self.printer.get_reactor()
        msg = self._get_temp(reactor.monotonic())
        did_ack = gcmd.ack(msg)
        if not did_ack:
            gcmd.respond_raw(msg)
    def _wait_for_temperature(self, heater):
        # Helper to wait on heater.check_busy() and report M105 temperatures
        if self.printer.get_start_args().get('debugoutput') is not None:
            return
        toolhead = self.printer.lookup_object("toolhead")
        gcode = self.printer.lookup_object("gcode")
        reactor = self.printer.get_reactor()
        eventtime = reactor.monotonic()
        while not self.printer.is_shutdown() and heater.check_busy(eventtime):
            print_time = toolhead.get_last_move_time()
            gcode.respond_raw(self._get_temp(eventtime))
            eventtime = reactor.pause(eventtime + 1.)
    def _check_heater_queue(self, eventtime):
        # Check active heaters
        self.active_heating_extruders = [
            h for h in self.active_heating_extruders
            if self.heaters[h].last_temp < \
                (self.heaters[h].target_temp - INACTIVE_EXTRUDER_TEMP_DELTA)
        ]

        # Start pending heaters if slots available
        while (self.pending_extruders and
               len(self.active_heating_extruders) < self.max_heating_extruders):
            heater_name, temp = self.pending_extruders.pop(0)
            self.active_heating_extruders.append(heater_name)
            self.heaters[heater_name].set_temp(temp)

        try:
            if self.extruder_list and len(self.extruder_list) > 0:
                toolhead = self.printer.lookup_object('toolhead')
                for i in range(len(self.extruder_list)):
                    name = self.extruder_list[i].get_name()
                    heater = self.heaters[name]
                    if heater.idle_hold_max_power is not None or heater.active_hold_max_power is not None:
                        dynamic_max_power = heater.get_max_power()
                        if not name in self.active_heating_extruders:
                            if toolhead.get_extruder().get_name() == name and heater.active_hold_max_power is not None:
                                dynamic_max_power = heater.active_hold_max_power
                            elif heater.idle_hold_max_power is not None:
                                dynamic_max_power = heater.idle_hold_max_power
                        heater.set_dynamic_max_power(dynamic_max_power)
        except Exception as e:
            logging.info("Error during dynamic power management: %s", str(e))

        return eventtime + 1.0

    def update_pending_extruder(self, heater_name, temp):
        existing_entry_index = None
        for i, (name, t) in enumerate(self.pending_extruders):
            if name == heater_name:
                existing_entry_index = i
                break

        if existing_entry_index is not None:
            self.pending_extruders[existing_entry_index] = (heater_name, temp)
            logging.debug("Updated pending extruder %s with new temp %.1f", heater_name, temp)
        else:
            self.pending_extruders.append((heater_name, temp))
            logging.debug("Added new pending extruder %s with temp %.1f", heater_name, temp)
    def remove_pending_extruder(self, heater_name):
        for i, (name, temp) in enumerate(self.pending_extruders):
            if name == heater_name:
                del self.pending_extruders[i]
                logging.debug("Removed pending extruder %s", heater_name)
                return True
        return False
    def set_temperature(self, heater, temp, wait=False):
        toolhead = self.printer.lookup_object('toolhead')
        toolhead.register_lookahead_callback((lambda pt: None))
        heater_name = heater.get_name()
        virtual_sdcard = self.printer.lookup_object('virtual_sdcard', None)
        if virtual_sdcard is not None:
            virtual_sdcard.record_pl_print_temperature_env({heater.short_name: temp})
        # Only apply limit to extruder heaters
        if not heater_name.startswith('extruder'):
            heater.set_temp(temp)
            if wait and temp:
                self._wait_for_temperature(heater)
            return
        # Handle extruder heating
        if temp > 0:
            if heater_name in self.active_heating_extruders:
                # Already heating - just update target temp
                heater.set_temp(temp)
                if wait:
                    self._wait_for_temperature(heater)
                return

            if len(self.active_heating_extruders) < self.max_heating_extruders:
                # Start heating immediately
                self.active_heating_extruders.append(heater_name)
                heater.set_temp(temp)
                if wait:
                    self._wait_for_temperature(heater)
            else:
                current_temp = self.heaters[heater_name].smoothed_temp
                if current_temp + INACTIVE_EXTRUDER_TEMP_DELTA >= temp:
                    self.remove_pending_extruder(heater_name)
                    heater.set_temp(temp)
                    if wait:
                        self._wait_for_temperature(heater)
                    return

                logging.info("concurrently heating %d extruders, "
                            "waiting for %s to finish",
                            len(self.active_heating_extruders),
                            self.active_heating_extruders[0])
                # Add to pending queue
                if wait:
                    # If waiting, block until heater is active
                    # self.pending_extruders.append((heater_name, temp))
                    self.update_pending_extruder(heater_name, temp)
                    while (heater_name, temp) in self.pending_extruders:
                        self.reactor.pause(self.reactor.monotonic() + 0.2)

                    while heater_name in self.active_heating_extruders:
                        self._wait_for_temperature(self.heaters[heater_name])
                        self.reactor.pause(self.reactor.monotonic() + 0.2)
                else:
                    # Non-blocking - just add to queue
                    self.update_pending_extruder(heater_name, temp)
                    # self.pending_extruders.append((heater_name, temp))
        else:
            # Cooling down
            if heater_name in self.active_heating_extruders:
                logging.info("cancel active heater %s", heater_name)
                self.active_heating_extruders.remove(heater_name)
            self.remove_pending_extruder(heater_name)
            heater.set_temp(temp)
    cmd_TEMPERATURE_WAIT_help = "Wait for a temperature on a sensor"
    def cmd_TEMPERATURE_WAIT(self, gcmd):
        sensor_name = gcmd.get('SENSOR')
        if sensor_name not in self.available_sensors:
            raise gcmd.error("Unknown sensor '%s'" % (sensor_name,))
        min_temp = gcmd.get_float('MINIMUM', float('-inf'))
        max_temp = gcmd.get_float('MAXIMUM', float('inf'), above=min_temp)
        if min_temp == float('-inf') and max_temp == float('inf'):
            raise gcmd.error(
                "Error on 'TEMPERATURE_WAIT': missing MINIMUM or MAXIMUM.")
        if self.printer.get_start_args().get('debugoutput') is not None:
            return
        if sensor_name in self.heaters:
            sensor = self.heaters[sensor_name]
        else:
            sensor = self.printer.lookup_object(sensor_name)
        toolhead = self.printer.lookup_object("toolhead")
        reactor = self.printer.get_reactor()
        eventtime = reactor.monotonic()
        while not self.printer.is_shutdown():
            temp, target = sensor.get_temp(eventtime)
            if temp >= min_temp and temp <= max_temp:
                return
            print_time = toolhead.get_last_move_time()
            gcmd.respond_raw(self._get_temp(eventtime))
            eventtime = reactor.pause(eventtime + 1.)

def load_config(config):
    return PrinterHeaters(config)
