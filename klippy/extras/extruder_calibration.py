# Extruder Park Calibration module for Klipper
# This module provides functionality to calibrate extruder park positions

import logging, os, queuefile, copy
from . import probe, probe_inductance_coil

class ExtruderParkCalibrationStep:
    PROBING_IDLE = "idle"
    PROBING_START = "probing"
    PROBING_COMPLETE = "complete"
    PROBING_ERROR = "error"

class ExtruderParkCalibration:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.name = config.get_name()
        self.extruder_start_positions = {}
        self.extruder_probe_aperture = {}
        self.extruder_probe_direction = {}
        self.extruder_reverse_distance = {}
        self.extruder_probe_dist = {}
        self.extruder_result_offset = {}
        self.calibration_results = {}
        self.extruder_theoretical_position = {}
        self.extruder_tolerance = {}
        self.extruder_y_cal_second_positions = {}
        self.y_calibration_results = {}
        self.err_msg = ""
        self.calibration_index = 0
        self.state = ExtruderParkCalibrationStep.PROBING_IDLE

        self.speed = config.getfloat('speed', 2.0, above=0.)
        self.probe_fast_speed = config.getfloat('probe_fast_speed', 2.0, above=0.)
        self.lift_speed = config.getfloat('lift_speed', self.speed, above=0.)
        self.sample_count = config.getint('samples', 3, minval=1)
        self.accel = config.getfloat('accel', 1000, above=0.)
        self.sample_retract_dist = config.getfloat('sample_retract_dist', 1., above=0.)
        self.samples_retries = config.getint('samples_tolerance_retries', 0, minval=0)
        self.samples_axis = config.getint('samples_axis', 0, minval=0, maxval=1)
        self.travel_speed = config.getfloat('travel_speed', 200, above=0.)
        # self.sample_dist = config.getfloat('sample_dist', self.extruder_probe_aperture['extruder'], above=0.)
        self.samples_tolerance = config.getfloat('samples_tolerance', 0.100, minval=0.)
        self.save_result = config.getboolean('save_result', False)
        self.default_probe_mode = config.getint('probe_mode', 1, minval=0, maxval=1)
        self.default_start_polarity = config.getboolean('polarity_invert', False)
        # Analog output pin
        analog_output_pin = config.get("analog_output_pin")
        amin, amax = config.getfloatlist('analog_range', count=2)
        pullup = config.getfloat('analog_pullup_resistor', 4700., above=0.)
        buttons = self.printer.load_object(config, 'buttons')
        self.adc_button = buttons.register_adc_button(analog_output_pin, amin, amax, pullup, self._button_handler)
        self.y_cal_enable = config.getboolean('y_cal_enable', False)

        self.extruder_probe_mode = {}
        self.extruder_start_polarity = {}

        for i in range(99):
            section = 'extruder'
            if i:
                section = 'extruder%d' % (i,)
            pos = config.getlists(section + '_start_position', None, seps=(',', '\n'), count=2, parser=float)
            if pos is not None:
                self.extruder_start_positions[section] = list(pos[0])
                aperture = config.getfloat(section + '_probe_aperture', 5.3, above=0.0)
                self.extruder_probe_aperture[section] = aperture
                direction = config.getint(section + '_probe_direction', 1, minval=0, maxval=1)
                self.extruder_probe_direction[section] = direction
                reverse_dist = config.getfloat(section + '_reverse_distance', self.extruder_probe_aperture[section]*0.5)
                self.extruder_reverse_distance[section] = reverse_dist
                probe_dist = config.getfloat(section + '_probe_dist', self.extruder_probe_aperture[section])
                self.extruder_probe_dist[section] = probe_dist
                result_offset = config.getfloat(section + '_result_offset', 0.0)
                self.extruder_result_offset[section] = result_offset
                theoretical_position = config.getfloat(section + '_theoretical_position', None)
                self.extruder_theoretical_position[section] = theoretical_position
                tolerance = config.getfloat(section + '_tolerance', None)
                self.extruder_tolerance[section] = tolerance
                probe_mode_choice = config.getint(section + '_probe_mode', self.default_probe_mode, minval=0, maxval=1)
                self.extruder_probe_mode[section] = probe_mode_choice
                start_polarity = config.getboolean(section + '_polarity_invert', self.default_start_polarity)
                self.extruder_start_polarity[section] = start_polarity
                y_cal_second_pos = config.getlists(section + '_y_cal_second_position', None, seps=(',', '\n'), count=2, parser=float)
                if y_cal_second_pos is not None:
                    self.extruder_y_cal_second_positions[section] = list(y_cal_second_pos[0])
            else:
                break

        self.calibration_total_count = len(self.extruder_start_positions)
        if self.calibration_total_count  == 0:
            raise config.error("At least one extruder must be configured with start_position")

        self.mcu_probe = probe.ProbeEndstopWrapper(config)
        self.invert = self.mcu_probe.mcu_endstop._invert
        self.printer.register_event_handler('klippy:mcu_identify',
                                            self._handle_mcu_identify)
        self.gcode = self.printer.lookup_object('gcode')
        self.gcode.register_command('CALIBRATE_EXTRUDER_PARK_POSITION',
                                    self.cmd_CALIBRATE_EXTRUDER_PARK_POSITION,
                                    desc="Calibrate extruder park position")
        self.gcode.register_command('PROBE_SINGLE_POINT', self.cmd_PROBE_SINGLE_POINT, desc="Probe single point")

    def _button_handler(self, eventtime, state):
        pass

    def _handle_mcu_identify(self):
        kin = self.printer.lookup_object('toolhead').get_kinematics()
        for stepper in kin.get_steppers():
            if stepper.is_active_axis('x') or stepper.is_active_axis('y') or stepper.is_active_axis('z'):
                self.mcu_probe.add_stepper(stepper)

    def cmd_CALIBRATE_EXTRUDER_PARK_POSITION(self, gcmd):
        toolhead = self.printer.lookup_object('toolhead')
        try:
            self.state = ExtruderParkCalibrationStep.PROBING_START
            self.calibration_results = {}
            self.err_msg = ""
            self.calibration_index = 0
            curtime = self.printer.get_reactor().monotonic()
            homed_axes = toolhead.get_status(curtime)['homed_axes']
            if 'x' not in homed_axes or 'y' not in homed_axes:
                raise gcmd.error("Must home X and Y axes first")

            probe_obj = self.printer.lookup_object('probe', None)
            if probe_obj is None:
                raise gcmd.error("Probe object not found")
            orig_mcu_probe = getattr(probe_obj, 'mcu_probe', None)

            extruder = toolhead.get_extruder()
            activate_status = extruder.get_extruder_activate_status()
            if activate_status[0][1] != 1:
                raise gcmd.error("All extruders must be parked on the dock")

            logdir = None
            vsd = self.printer.lookup_object('virtual_sdcard', None)
            if vsd is None:
                gcmd.respond_raw("No virtual_sdcard dir to save extruder offset data")
                logdir = '/tmp/calibration_data'
            else:
                logdir = f'{vsd.sdcard_dirname}/calibration_data'

            enable_theoretical_check = gcmd.get_int('ENABLE_THEORETICAL_CHECK', 1)
            for i in range(len(self.extruder_start_positions)):
                section = 'extruder'
                if i:
                    section = 'extruder%d' % (i,)
                self.calibration_index = i
                if section in self.extruder_start_positions:
                    gcmd.respond_raw("Processing extruder: %s" % section)
                    start_position = list(self.extruder_start_positions[section])
                    override_start_x = gcmd.get_float("%s_START_X" % section.upper(), None)
                    override_start_y = gcmd.get_float("%s_START_Y" % section.upper(), None)

                    if override_start_x is not None:
                        start_position[0] = override_start_x
                    if override_start_y is not None:
                        start_position[1] = override_start_y

                    gcmd.respond_raw("Moving to position: %.3f, %.3f" % (start_position[0], start_position[1]))
                    cur_pos = toolhead.get_position()
                    if cur_pos[1] > start_position[1]:
                        toolhead.manual_move([None, start_position[1], None], self.travel_speed)
                    toolhead.manual_move([start_position[0], start_position[1], None], self.travel_speed)

                    # get laser analog output voltage
                    # if self.y_cal_enable:
                    #     toolhead.wait_moves()
                    #     self.reactor.pause(self.reactor.monotonic() + 1)
                    #     point1_voltage = self.get_analog_output()
                    #     gcmd.respond_raw("position: %.3f, %.3f laser voltage: %.3f" % (start_position[0], start_position[1], point1_voltage))

                    probe_dist = self.extruder_probe_dist[section]
                    probe_direction = self.extruder_probe_direction[section]
                    probe_params = {
                        'SAMPLE_DIST': probe_dist,
                        'SAMPLE_DIR': probe_direction,
                        'SAMPLES_AXIS': self.samples_axis,   # 0 for X-axis, 1 for Y-axis
                        'SAFETY_CHECK': 0,
                        'SAMPLES': self.sample_count,
                        'PROBE_FAST_SPEED': self.probe_fast_speed,
                        'PROBE_SPEED': self.speed,
                        'LIFT_SPEED': self.lift_speed,
                        'PROBE_ACCEL': self.accel,
                        'SAMPLE_RETRACT_DIST': self.sample_retract_dist,
                        'SAMPLES_TOLERANCE_RETRIES': self.samples_retries,
                        'TRAVEL_SPEED': self.travel_speed,
                        'SAMPLES_TOLERANCE': self.samples_tolerance,
                        'TRIG_FREQ_CONFIG': 0
                    }
                    gcmd.get_command_parameters().update(probe_params)

                    # Start first probe
                    if self.extruder_start_polarity[section]:
                        self.mcu_probe.mcu_endstop._invert = not self.invert
                    else:
                        self.mcu_probe.mcu_endstop._invert = self.invert
                    probe_obj.set_mcu_probe(self.mcu_probe)
                    pos = probe_inductance_coil.run_single_probe(probe_obj, gcmd)
                    # Get first contact position
                    first_contact_pos = pos[self.samples_axis]
                    if self.extruder_probe_mode[section] == 1:
                        second_probe_start_pos = list(start_position)
                        reverse_distance = self.extruder_reverse_distance[section]
                        self.mcu_probe.mcu_endstop._invert = not self.mcu_probe.mcu_endstop._invert
                        second_probe_start_pos[self.samples_axis] = first_contact_pos + reverse_distance * ([1, -1][probe_direction <= 0])
                        # Move to second probe start position
                        toolhead.manual_move(second_probe_start_pos, self.travel_speed)
                        # update probe_params
                        # probe_params = {
                        #     'SAMPLE_DIST': probe_dist,
                        #     'SAMPLE_DIR': -probe_direction
                        # }
                        # gcmd.get_command_parameters().update(probe_params)
                        pos = probe_inductance_coil.run_single_probe(probe_obj, gcmd)
                        second_contact_pos = pos[self.samples_axis]
                        mid_point = round((first_contact_pos + second_contact_pos) / 2.0, 3)
                        distance = abs(second_contact_pos - first_contact_pos)
                        final_result = mid_point + self.extruder_result_offset[section]
                    else:
                        final_result = first_contact_pos + self.extruder_result_offset[section]
                        distance = 0.0

                    # y calibration second position
                    if self.y_cal_enable and section in self.extruder_y_cal_second_positions:
                        start_position = list(self.extruder_y_cal_second_positions[section])
                        gcmd.respond_raw("Moving to position: %.3f, %.3f" % (start_position[0], start_position[1]))
                        cur_pos = toolhead.get_position()
                        if cur_pos[1] > start_position[1]:
                            toolhead.manual_move([None, start_position[1], None], self.travel_speed)
                        toolhead.manual_move([start_position[0], start_position[1], None], self.travel_speed)
                        # get laser analog output voltage
                        toolhead.wait_moves()
                        self.reactor.pause(self.reactor.monotonic() + 1)
                        point2_voltage = self.get_analog_output()
                        v_str = "%.3f" % point2_voltage if point2_voltage is not None else "None"
                        gcmd.respond_raw("position: %.3f, %.3f laser voltage: %s" % (start_position[0], start_position[1], v_str))
                        # aver_voltage = (point2_voltage+point1_voltage)/2
                        aver_voltage = point2_voltage


                    gcmd.respond_raw("Results for %s:" % section)
                    gcmd.respond_raw("  First contact: %.3f" % first_contact_pos)
                    if self.extruder_probe_mode[section] == 1:
                        gcmd.respond_raw("  Second contact: %.3f" % second_contact_pos)
                        gcmd.respond_raw("  Distance between contacts: %.3f" % distance)
                        gcmd.respond_raw("  Mid point: %.3f" % mid_point)
                    gcmd.respond_raw("  Result offset: %.3f" % self.extruder_result_offset[section])
                    gcmd.respond_raw(">>> FINAL RESULT: %.3f <<<\n" % final_result)
                    if self.y_cal_enable:
                        # gcmd.respond_raw("two point laser average voltage: %.3f" % (aver_voltage))
                        gcmd.respond_raw("one point laser voltage: %.3f" % (aver_voltage))
                        y_calibration_results = copy.deepcopy(self.y_calibration_results)
                        y_calibration_results.update({section: aver_voltage})
                        self.y_calibration_results = y_calibration_results

                    if (enable_theoretical_check and
                        self.extruder_theoretical_position.get(section) is not None and
                        self.extruder_tolerance.get(section) is not None):
                        theoretical_pos = self.extruder_theoretical_position[section]
                        tolerance = self.extruder_tolerance[section]
                        deviation = abs(final_result - theoretical_pos)
                        if deviation > tolerance:
                            raise gcmd.error("Calibration result for %s is out of tolerance. "
                                           "Result: %.3f, Theoretical: %.3f, Tolerance: %.3f, Deviation: %.3f" %
                                           (section, final_result, theoretical_pos, tolerance, deviation))

                    calibration_results = copy.deepcopy(self.calibration_results)
                    calibration_results.update({section: final_result})
                    self.calibration_results = calibration_results
            gcmd.respond_raw("=== CALIBRATION SUMMARY ===")
            results_to_save = []
            for i in range(len(self.extruder_start_positions)):
                section = 'extruder'
                if i:
                    section = 'extruder%d' % (i,)
                if section in self.calibration_results:
                    result = self.calibration_results[section]
                    gcmd.respond_raw("  %s: %.3f" % (section, result))
                    results_to_save.append("%.3f" % result)
                if self.y_cal_enable:
                    if section in self.y_calibration_results:
                        result = self.y_calibration_results[section]
                        gcmd.respond_raw("Y  %s: %.3f" % (section, result))
                        results_to_save.append("%.3f" % result)

            gcmd.respond_raw("=== END SUMMARY ===")

            if self.save_result and logdir is not None and len(results_to_save):
                if not os.path.exists(logdir):
                    os.makedirs(logdir)
                data_line = ",".join(results_to_save) + "\n"
                data_filename = os.path.join(logdir, 'extruder_park_calibration.csv')
                queuefile.async_append_file(data_filename, data_line)
            self.state = ExtruderParkCalibrationStep.PROBING_COMPLETE

        except Exception as e:
            toolhead.dwell(0.5)
            toolhead.wait_moves()
            self.state = ExtruderParkCalibrationStep.PROBING_ERROR
            str_err = self.printer.extract_coded_message_field(str(e))
            self.err_msg = str_err
            raise
        finally:
            if probe_obj is not None and orig_mcu_probe is not None:
                probe_obj.set_mcu_probe(orig_mcu_probe)
            self.mcu_probe.mcu_endstop._invert = self.invert

    def cmd_PROBE_SINGLE_POINT(self, gcmd):
        toolhead = self.printer.lookup_object('toolhead')
        probe_obj = self.printer.lookup_object('probe', None)
        orig_mcu_probe = getattr(probe_obj, 'mcu_probe', None)
        try:
            self.state = ExtruderParkCalibrationStep.PROBING_START
            self.err_msg = ""
            self.calibration_index = 0
            sample_count = gcmd.get_int('SAMPLES', self.sample_count)
            probe_axis = gcmd.get_int('SAMPLES_AXIS', 0, minval=0, maxval=1)  # 0=X, 1=Y
            probe_direction = gcmd.get_int('SAMPLE_DIR', 1)
            theoretical_position = gcmd.get_float('THEORETICAL_POSITION', None)
            diff_tolerance = gcmd.get_float('DIFF_TOLERANCE', 0.1)
            polarity_invert = gcmd.get_int('POLARITY_INVERT', 0)  # 0=normal, 1=inverted
            sample_dist = gcmd.get_float('SAMPLE_DIST', 10.0)
            probe_fast_speed = gcmd.get_float('PROBE_FAST_SPEED', self.probe_fast_speed)
            probe_speed = gcmd.get_float('PROBE_SPEED', self.speed)
            lift_speed = gcmd.get_float('LIFT_SPEED', self.lift_speed)
            accel = gcmd.get_float('PROBE_ACCEL', self.accel)
            sample_retract_dist = gcmd.get_float('SAMPLE_RETRACT_DIST', self.sample_retract_dist)
            travel_speed = gcmd.get_float('TRAVEL_SPEED', self.travel_speed)
            tolerance = gcmd.get_float('SAMPLES_TOLERANCE', self.samples_tolerance)
            result_offset = gcmd.get_float('RESULT_OFFSET', 0.0)
            samples_tolerance_retries = gcmd.get_int('SAMPLES_TOLERANCE_RETRIES', self.samples_retries)

            probe_obj = self.printer.lookup_object('probe', None)
            if probe_obj is None:
                raise gcmd.error("Probe object not found")
            orig_mcu_probe = getattr(probe_obj, 'mcu_probe', None)

            # Configure probe parameters
            probe_params = {
                'SAMPLES': sample_count,
                'SAMPLE_DIST': sample_dist,
                'SAMPLE_DIR': probe_direction,
                'SAMPLES_AXIS': probe_axis,
                'SAFETY_CHECK': 0,
                'PROBE_FAST_SPEED': probe_fast_speed,
                'PROBE_SPEED': probe_speed,
                'LIFT_SPEED': lift_speed,
                'PROBE_ACCEL': accel,
                'SAMPLE_RETRACT_DIST': sample_retract_dist,
                'SAMPLES_TOLERANCE_RETRIES': samples_tolerance_retries,
                'TRAVEL_SPEED': travel_speed,
                'SAMPLES_TOLERANCE': tolerance,
                'TRIG_FREQ_CONFIG': 0
            }
            gcmd.get_command_parameters().update(probe_params)
            if polarity_invert:
                self.mcu_probe.mcu_endstop._invert = not self.invert
            else:
                self.mcu_probe.mcu_endstop._invert = self.invert

            probe_obj.set_mcu_probe(self.mcu_probe)
            pos = probe_inductance_coil.run_single_probe(probe_obj, gcmd)
            probe_result = pos[probe_axis]
            final_result = probe_result + result_offset
            within_tolerance = True

            if theoretical_position is not None:
                deviation = abs(final_result - theoretical_position)
                within_tolerance = deviation <= diff_tolerance

            gcmd.respond_raw("  Position: %.5f" % probe_result)
            gcmd.respond_raw("  Result_offset: %.5f" % result_offset)
            gcmd.respond_raw("  Final_result value: %.5f" % final_result)

            if within_tolerance == False:
                raise gcmd.error("Calibration result is out of tolerance. "
                               "Result: %.5f, Theoretical: %.5f, Tolerance: %.5f, Deviation: %.3f" %
                               (final_result, theoretical_position, diff_tolerance, abs(final_result - theoretical_position)))
            calibration_results = copy.deepcopy(self.calibration_results)
            calibration_results.update({'single_point': final_result})
            self.calibration_results = calibration_results
            self.state = ExtruderParkCalibrationStep.PROBING_COMPLETE

        except Exception as e:
            toolhead = self.printer.lookup_object('toolhead')
            toolhead.dwell(0.5)
            toolhead.wait_moves()
            self.state = ExtruderParkCalibrationStep.PROBING_ERROR
            str_err = self.printer.extract_coded_message_field(str(e))
            self.err_msg = str_err
            raise
        finally:
            if probe_obj is not None and orig_mcu_probe is not None:
                probe_obj.set_mcu_probe(orig_mcu_probe)
            self.mcu_probe.mcu_endstop._invert = self.invert

    def get_status(self, eventtime):
        return {
            'state': self.state,
            'results': self.calibration_results,
            'probe_index': self.calibration_index,
            'probe_total': self.calibration_total_count,
            'err_msg': self.err_msg,
            'y_calibration_results': self.y_calibration_results
        }

    def get_analog_output(self):
        if self.adc_button is None or getattr(self.adc_button, 'last_adc_value', None) is None:
            return None
        # real voltage = (adc value) * (refrence voltage 3.3) * (Resistance attenuation factor 1.5)
        voltage = self.adc_button.last_adc_value * 3.3 * 1.5
        return voltage

def load_config(config):
    return ExtruderParkCalibration(config)