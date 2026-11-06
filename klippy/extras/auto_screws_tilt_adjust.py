# Helper script to automatically adjust bed screws tilt using Z probe
import math, logging
from . import probe_inductance_coil


class AutoScrewsTiltAdjustError(Exception):
    pass

class AutoScrewsTiltAdjustAbort(Exception):
    pass

class AutoScrewsTiltAdjustPass(Exception):
    pass

class AutoScrewsTiltAdjustLimit(Exception):
    """Exception raised when screw adjustment attempts exceed the limit"""
    pass

class AutoScrewsTiltAdjustStep:
    IDLE = "adjust_idle"
    PROBING_START = "adjust_start"
    PROBING_HOMING = "adjust_homing"
    PROBING_HOMING_DONE = "adjust_homing_done"
    PROBING_HOMING_ERR = "adjust_homing_failed"
    PLATE_DETECTING = 'adjust_plate_detecting'
    PLATE_DETECTED = 'adjust_plate_detected'
    PLATE_DETECTION_ERROR = 'adjust_plate_detection_error'
    RESET_TO_INITIAL = 'adjust_reset_to_initial'
    PROBING_REFPOINT = "adjust_probe_refpoint"
    PROBING_REFPOINT_COMPLETED = "adjust_refpoint_done"
    PROBING_ABORTED = "adjust_aborted"
    PROBING_ABORTING = "adjust_aborting"
    PROBING_BED = "adjust_probing"
    WAIT_MANUAL_ADJUST_SCREWS = "adjust_wait_manual"
    NEXT_POINT_ADJUST = "adjust_next_point_adjust"
    PROBING_ADJUST_VERIFY = "adjust_verify"
    SCREWS_TILT_ADJUST_OK = "adjust_complete"
    SCREWS_TILT_ADJUST_FAIL = "adjust_failed"

class AutoScrewsTiltAdjust:
    def __init__(self, config):
        self.config = config
        self.printer = config.get_printer()
        self.screws = []
        self.max_diff = None
        self.current_point = 0
        self.abort_flag = False
        self.state = AutoScrewsTiltAdjustStep.IDLE
        self.base_points = [None, None, None, None]  # Changed to list
        self.min_z, self.max_z, self.target_z = (None, None, None)
        self.probe_after_delay = 0
        self.need_adjusted_z = None
        self.lock = self.printer.get_reactor().mutex()

        # Read exactly 4 screw positions from config
        for i in range(4):
            prefix = "screw%d" % (i + 1,)
            if config.get(prefix, None) is None:
                raise config.error("auto_screws_tilt_adjust: Must have exactly four screws")
            screw_coord = config.getfloatlist(prefix, count=2)
            screw_name = "screw at %.3f,%.3f" % screw_coord
            screw_name = config.get(prefix + "_name", screw_name)
            self.screws.append((screw_coord, screw_name))

        # Read screw adjustment order (default: 1,2,3,4)
        self.screw_order = config.getintlist('screw_order', [1,2,3,4], count=4)
        # Validate order (must contain 1-4 exactly once each)
        if len(self.screw_order) != 4:
            raise config.error("auto_screws_tilt_adjust: screw_order must have exactly 4 values")
        if any(x < 1 or x > 4 for x in self.screw_order):
            raise config.error("auto_screws_tilt_adjust: screw_order values must be between 1-4")
        if len(set(self.screw_order)) != 4:
            raise config.error("auto_screws_tilt_adjust: screw_order values must be unique")
        if sorted(self.screw_order) != [1,2,3,4]:
            raise config.error("auto_screws_tilt_adjust: screw_order must contain values 1-4 exactly once each")
        self.screw_adjust_threshold = config.getfloat('screw_adjust_threshold', 0.1, above=0.)
        self.adjust_tolerance = config.getfloat('adjust_tolerance', 0.05, maxval=self.screw_adjust_threshold)
        self.probe_interval = config.getfloat('probe_interval', 10, minval=0.)
        self.adjust_probe_samples = config.getint('adjust_probe_samples', 2, minval=1)
        self.adjust_probe_tolerance = config.getfloat('adjust_probe_tolerance', None, minval=0.)
        self.max_adjust_times = config.getint('max_adjust_times', 30, minval=1)
        self.max_verify_attempts = config.getint('max_verify_attempts', 10, minval=1)
        self.samples = config.getint("samples", 3, minval=1)
        self.sample_retract_dist = config.getfloat("sample_retract_dist", 0.3, above=0)

        # Initialize ProbePointsHelper
        self.points = [coord for coord, name in self.screws]
        self.probe_helper = probe_inductance_coil.ProbePointsHelper(
            self.config,
            self.probe_finalize,
            default_points=self.points,
            probe_point_callback=self.probe_point_callback
        )
        self.probe_helper.minimum_points(4)

        # Register commands
        self.gcode = self.printer.lookup_object('gcode')
        self.gcode.register_command(
            "AUTO_SCREWS_TILT_ADJUST",
            self.cmd_AUTO_SCREWS_TILT_ADJUST,
            desc=self.cmd_AUTO_SCREWS_TILT_ADJUST_help
        )
        self.gcode.register_command(
            "AUTO_SCREWS_TILT_ADJUST_ENTRY",
            self.cmd_AUTO_SCREWS_TILT_ADJUST_ENTRY
        )
        self.gcode.register_command(
            "AUTO_SCREWS_TILT_ADJUST_HOMING",
            self.cmd_AUTO_SCREWS_TILT_ADJUST_HOMING
        )
        self.gcode.register_command(
            "AUTO_SCREWS_TILT_ADJUST_DETECT_PLATE",
            self.cmd_AUTO_SCREWS_TILT_ADJUST_DETECT_PLATE
        )
        self.gcode.register_command(
            "AUTO_SCREWS_TILT_ADJUST_RESET_TO_INITIAL",
            self.cmd_AUTO_SCREWS_TILT_ADJUST_RESET_TO_INITIAL
        )
        self.gcode.register_command(
            "AUTO_SCREWS_TILT_ADJUST_PROBE_REFERENCE_POINTS",
            self.cmd_AUTO_SCREWS_TILT_ADJUST_PROBE_REFERENCE_POINTS
        )
        self.gcode.register_command(
            "AUTO_SCREWS_TILT_ADJUST_MANUAL_TUNING",
            self.cmd_AUTO_SCREWS_TILT_ADJUST_MANUAL_TUNING
        )
        self.gcode.register_command(
            "AUTO_SCREWS_TILT_ADJUST_EXIT",
            self.cmd_AUTO_SCREWS_TILT_ADJUST_EXIT
        )

        webhooks = self.printer.lookup_object('webhooks')
        webhooks.register_endpoint(
            "auto_screws_tilt_adjust/abort_screws_adjust", self._handle_abort_screws_adjust)
        webhooks.register_endpoint(
            "auto_screws_tilt_adjust/next_point_adjust", self._handle_next_point_adjust)

    cmd_AUTO_SCREWS_TILT_ADJUST_help = """
    Automatically adjust bed leveling screws by probing until within tolerance.
    """

    def _move(self, coord, speed):
        self.printer.lookup_object('toolhead').manual_move(coord, speed)

    def get_status(self, eventtime):
        return {
            'probe_step': self.state,
            'screw_order': self.screw_order,
            'probe_after_delay': self.probe_after_delay,
            'min_z': round(self.min_z, 5) if self.min_z is not None else None,
            'max_z': round(self.max_z, 5) if self.max_z is not None else None,
            'target_z': round(self.target_z, 5) if self.target_z is not None else None,
            'base_point1': round(self.base_points[0], 5) if self.base_points[0] is not None else None,
            'base_point2': round(self.base_points[1], 5) if self.base_points[1] is not None else None,
            'base_point3': round(self.base_points[2], 5) if self.base_points[2] is not None else None,
            'base_point4': round(self.base_points[3], 5) if self.base_points[3] is not None else None,
            'current_point': self.current_point,
            'need_adjusted_z': round(self.need_adjusted_z, 5) if self.need_adjusted_z is not None else None,
            'adjust_tolerance': self.adjust_tolerance,
            'screw_adjust_threshold': self.screw_adjust_threshold
        }

    def _handle_abort_screws_adjust(self, web_request):
        try:
            with self.lock:
                self.abort_flag = True
            web_request.send({'state': 'success'})
        except Exception as e:
            logging.error(f'failed to abort screws adjust: {str(e)}')
            web_request.send({'state': 'error', 'message': str(e)})

    def _handle_next_point_adjust(self, web_request):
        try:
            if self.state == AutoScrewsTiltAdjustStep.WAIT_MANUAL_ADJUST_SCREWS:
                self._set_state(AutoScrewsTiltAdjustStep.NEXT_POINT_ADJUST)
            else:
                raise self.printer.command_error('Not in wait manual adjust screws state')
            web_request.send({'state': 'success'})
        except Exception as e:
            web_request.send({'state': 'error', 'message': str(e)})
    def _probe_abort_check(self):
        if self.abort_flag or self.printer.is_shutdown():
            with self.lock:
                self.state = AutoScrewsTiltAdjustStep.PROBING_ABORTING
            logging.info("abort_flag set, can't continue")
            raise AutoScrewsTiltAdjustAbort

    def _check_level_diff(self):
        """Check if all reference points height difference is within tolerance"""
        if None in self.base_points:
            return False

        self.max_z = max(self.base_points)
        self.min_z = min(self.base_points)
        level_diff = self.max_z - self.min_z

        self.gcode.respond_info(
            "Current height difference: %.3fmm (max allowed: %.3fmm)" %
            (level_diff, self.screw_adjust_threshold))
        return level_diff < self.screw_adjust_threshold

    def probe_finalize(self, offsets, positions):
        toolhead = self.printer.lookup_object('toolhead')
        self.max_diff_error = False

        # Calculate target Z height (average of all points)
        z_values = [pos[2] for pos in positions]
        self.target_z = sum(z_values) / len(z_values) if z_values else 0.0
        self.min_z = min(z_values) if z_values else 0.0
        self.max_z = max(z_values) if z_values else 0.0

        # Assign base points
        self.base_points = z_values[:4]  # Store as list
        with self.lock:
            self.state = AutoScrewsTiltAdjustStep.PROBING_REFPOINT_COMPLETED

        # Bed level summary
        self.gcode.respond_info("Bed level summary:")
        self.gcode.respond_info("Target height=%.5f (lowest=%.5f, highest=%.5f, difference=%.5f)" %
            (self.target_z, self.min_z, self.max_z, self.max_z-self.min_z))

        if abs(self.max_z - self.min_z) < self.screw_adjust_threshold:
            self.gcode.respond_info("All 4 points meet requirements, no further adjustment needed")
            raise AutoScrewsTiltAdjustPass

    def probe_point_callback(self, points):
        if self.abort_flag:
            with self.lock:
                self.state = AutoScrewsTiltAdjustStep.PROBING_ABORTING
            raise AutoScrewsTiltAdjustAbort
        if not points or len(points) < 2:
            return
        with self.lock:
            self.current_point = min(points[0] + 1, points[1])

    def _verify_level(self, probe_cmd, toolhead, probe_object):
        if probe_object is None:
            raise AutoScrewsTiltAdjustError("Probe object not found")

        with self.lock:
            self.state = AutoScrewsTiltAdjustStep.PROBING_ADJUST_VERIFY

        self.gcode.respond_info("Verifying overall leveling...")
        for i, (coord, name) in enumerate(self.screws):
            self._probe_abort_check()
            self._move([None, None, self.probe_helper.default_horizontal_move_z],
                      self.probe_helper.lift_speed)
            self._move([coord[0], coord[1], None],
                      self.probe_helper.speed)
            toolhead.wait_moves()
            self.gcode.run_script_from_command(probe_cmd)
            toolhead.wait_moves()
            self.base_points[i] = probe_object.get_status(0)['last_z_result']

        return self._check_level_diff()

    def adjust_screws(self, gcmd):
        toolhead = self.printer.lookup_object('toolhead')
        probe_object = self.printer.lookup_object('probe', None)
        if probe_object is None:
            raise gcmd.error("Probe object not found")

        # Initial probing results and adjustment instructions
        self.gcode.respond_info("Initial probing results:")
        for i, (z, screw) in enumerate(zip(self.base_points, self.screws)):
            coord, name = screw
            diff = self.target_z - z
            direction = "CW" if diff > 0 else "CCW"
            self.gcode.respond_info(
                "%s : x=%.5f, y=%.5f, z=%.5f (turn %s %.5fmm)" %
                (name, coord[0], coord[1], z, direction, abs(diff)))

        params = gcmd.get_command_parameters()
        adjust_probe_samples = None
        adjust_probe_tolerance = None
        if 'ADJUST_PROBE_SAMPLES' not in params and self.adjust_probe_samples is not None:
            adjust_probe_samples = self.adjust_probe_samples
        if 'ADJUST_PROBE_TOLERANCE' not in params and self.adjust_probe_tolerance is not None:
            adjust_probe_tolerance = self.adjust_probe_tolerance
        probe_cmd = "PROBE"
        if adjust_probe_samples is not None:
            probe_cmd += " SAMPLES={}".format(adjust_probe_samples)
        if adjust_probe_tolerance is not None:
            probe_cmd += " SAMPLES_TOLERANCE={:.3f}".format(adjust_probe_tolerance)
        probe_interval = gcmd.get_int("ADJUST_PROBE_INTERVAL", self.probe_interval, minval=1)
        max_adjust_times = gcmd.get_int('ADJUST_MAX_TIMES', self.max_adjust_times, minval=1)
        max_verify_attempts = gcmd.get_int('MAX_VERIFY_ATTEMPTS', self.max_verify_attempts, minval=1)

        verify_attempt = 0
        while verify_attempt < max_verify_attempts:
            verify_attempt += 1
            self.gcode.respond_info("Starting adjustment round %d..." % verify_attempt)

            # Adjust screws in specified order
            for screw_num in self.screw_order:
                i = screw_num - 1  # Convert to 0-based index
                screw = self.screws[i]
                coord, name = screw
                adjust_count = 0
                while True:
                    # Check adjustment count limit
                    adjust_count += 1
                    if adjust_count > max_adjust_times:
                        raise AutoScrewsTiltAdjustLimit(
                            "%s adjustment exceeded max limit (%d times)" % (name, max_adjust_times))

                    # Probe current point
                    diff = self.target_z - self.base_points[i]
                    if abs(diff) <= self.adjust_tolerance:
                        self.gcode.respond_info(
                            "%s is within tolerance (deviation: %.3fmm)" % (name, diff))
                        break

                    self._probe_abort_check()
                    self._move([None, None, self.probe_helper.default_horizontal_move_z], self.probe_helper.lift_speed)
                    self._move([coord[0], coord[1], None], self.probe_helper.speed)
                    self.gcode.respond_info("Adjusting %s..., auto probing in %3fs" % (name, self.probe_interval))
                    self.need_adjusted_z = self.target_z - self.base_points[i]
                    direction = "CW" if diff > 0 else "CCW"
                    self.gcode.respond_info("Turn %s %s (%.3fmm)" % (direction, name, diff))

                    with self.lock:
                        self.probe_after_delay = probe_interval
                        self.state = AutoScrewsTiltAdjustStep.WAIT_MANUAL_ADJUST_SCREWS
                        self.current_point = screw_num

                    # Wait for probe interval
                    toolhead.wait_moves()  # Ensure all moves complete
                    remaining = probe_interval
                    while remaining > 0:
                        self._probe_abort_check()
                        dwell_time = min(1.0, remaining)
                        toolhead.dwell(dwell_time)
                        remaining -= dwell_time
                        self.probe_after_delay = remaining

                    with self.lock:
                        self.probe_after_delay = 0
                        self.state = AutoScrewsTiltAdjustStep.PROBING_BED
                    self.gcode.run_script_from_command(probe_cmd)
                    toolhead.wait_moves()
                    self.base_points[i] = probe_object.get_status(0)['last_z_result']

            # Recalculate target height as average of max and min
            self.max_z = max(self.base_points)
            self.min_z = min(self.base_points)
            self.target_z = (self.max_z + self.min_z) / 2
            self.gcode.respond_info("Updated target height: %.5f (max:%.5f min:%.5f)" %
                (self.target_z, self.max_z, self.min_z))

            # Verify overall leveling
            if self._verify_level(probe_cmd, toolhead, probe_object):
                raise AutoScrewsTiltAdjustPass
            elif verify_attempt < max_verify_attempts:
                self.gcode.respond_info("Preparing for adjustment round %d..." % (verify_attempt + 1))
            else:
                raise AutoScrewsTiltAdjustLimit("Adjustment exceeded max verification attempts (%d)" % max_verify_attempts)
    def _set_state(self, state):
        with self.lock:
            self.state = state
    def _verify_screws_tilt_adjust_state(self, operation=None):
        machine_state_manager = self.printer.lookup_object('machine_state_manager', None)
        if (machine_state_manager and
            str(machine_state_manager.get_status()['main_state']) != "SCREWS_TILT_ADJUST"):
            if operation:
                raise self.printer.command_error(f"Operation '{operation}' requires SCREWS_TILT_ADJUST mode")
            else:
                raise self.printer.command_error("Operation requires SCREWS_TILT_ADJUST mode")
    def cmd_AUTO_SCREWS_TILT_ADJUST(self, gcmd):
        with self.lock:
            self.base_points = [None, None, None, None]
            self.min_z, self.max_z, self.target_z = (None, None, None)
            self.current_point = 0
            self.probe_after_delay = 0
            self.need_adjusted_z = None
            self.abort_flag = False
            self.state = AutoScrewsTiltAdjustStep.PROBING_START

        # Allow overriding screw order via GCODE parameter
        if 'SCREW_ORDER' in gcmd.get_command_parameters():
            try:
                new_order = [int(x) for x in gcmd.get('SCREW_ORDER').split(',')]
                if len(new_order) != 4:
                    raise gcmd.error("SCREW_ORDER must have exactly 4 values")
                if any(x < 1 or x > 4 for x in new_order):
                    raise gcmd.error("SCREW_ORDER values must be between 1-4")
                if len(set(new_order)) != 4:
                    raise gcmd.error("SCREW_ORDER values must be unique")
                if sorted(new_order) != [1,2,3,4]:
                    raise gcmd.error("SCREW_ORDER must contain values 1-4 exactly once each")
                self.screw_order = new_order
                self.gcode.respond_info("Using custom screw adjustment order: %s" % self.screw_order)
            except ValueError:
                raise gcmd.error("Invalid SCREW_ORDER format - use comma-separated numbers (e.g. '1,2,3,4')")

        adjust_tolerance = gcmd.get_float('ADJUST_TOLERANCE', self.adjust_tolerance)
        screw_adjust_threshold = gcmd.get_float('SCREW_ADJUST_THRESHOLD', self.screw_adjust_threshold)
        if adjust_tolerance > screw_adjust_threshold:
            raise gcmd.error("ADJUST_TOLERANCE must not exceed SCREW_ADJUST_THRESHOLD")

        self.adjust_tolerance = adjust_tolerance
        self.screw_adjust_threshold = screw_adjust_threshold

        force_homing = gcmd.get_int('FORCE_HOMING', 0)
        curtime = self.printer.get_reactor().monotonic()
        homed_axes_list = self.printer.lookup_object('toolhead').get_status(curtime)['homed_axes']
        if not ('x' in homed_axes_list and 'y' in homed_axes_list and 'z' in homed_axes_list) or force_homing:
            with self.lock:
                self.state = AutoScrewsTiltAdjustStep.PROBING_HOMING
            self.gcode.run_script_from_command("G28")
        try:
            with self.lock:
                self.state = AutoScrewsTiltAdjustStep.PROBING_REFPOINT
            self.probe_helper.start_probe(gcmd)
            self.adjust_screws(gcmd)
        except AutoScrewsTiltAdjustPass as e:
            with self.lock:
                self.state = AutoScrewsTiltAdjustStep.SCREWS_TILT_ADJUST_OK
            self.gcode.run_script_from_command("BED_MESH_CLEAR_MANUAL_LEVELING_REQUIRED")
        except AutoScrewsTiltAdjustAbort as e:
            with self.lock:
                self.state = AutoScrewsTiltAdjustStep.PROBING_ABORTED
        except (AutoScrewsTiltAdjustLimit, AutoScrewsTiltAdjustError, Exception) as e:
            with self.lock:
                self.state = AutoScrewsTiltAdjustStep.SCREWS_TILT_ADJUST_FAIL
            raise gcmd.error(str(e))
        finally:
            self._move([None, None, self.probe_helper.default_horizontal_move_z], self.probe_helper.lift_speed)
    def cmd_AUTO_SCREWS_TILT_ADJUST_ENTRY(self, gcmd):
        try:
            adjust_tolerance = gcmd.get_float('ADJUST_TOLERANCE', self.adjust_tolerance)
            screw_adjust_threshold = gcmd.get_float('SCREW_ADJUST_THRESHOLD', self.screw_adjust_threshold)
            if adjust_tolerance > screw_adjust_threshold:
                raise gcmd.error("ADJUST_TOLERANCE must not exceed SCREW_ADJUST_THRESHOLD")
            self.adjust_tolerance = adjust_tolerance
            self.screw_adjust_threshold = screw_adjust_threshold
            self.gcode.run_script_from_command("SET_MAIN_STATE MAIN_STATE=SCREWS_TILT_ADJUST")
            with self.lock:
                self.base_points = [None, None, None, None]
                self.min_z, self.max_z, self.target_z = (None, None, None)
                self.current_point = 0
                self.probe_after_delay = 0
                self.need_adjusted_z = None
                self.abort_flag = False
            self._set_state(AutoScrewsTiltAdjustStep.PROBING_START)
            timeout = 9999999999
            idle_timeout = self.printer.lookup_object('idle_timeout', None)
            if idle_timeout is not None and hasattr(idle_timeout, 'idle_timeout_on_pause'):
                timeout = idle_timeout.idle_timeout_on_pause
            self.gcode.run_script_from_command("SET_IDLE_TIMEOUT TIMEOUT={}".format(timeout))
        except Exception as e:
            raise gcmd.error(str(e))

    def cmd_AUTO_SCREWS_TILT_ADJUST_HOMING(self, gcmd):
        self._verify_screws_tilt_adjust_state("HOMING")
        try:
            self._set_state(AutoScrewsTiltAdjustStep.PROBING_HOMING)
            self.gcode.run_script_from_command("G28 SAMPLES_TOLERANCE 0.1 ACTION 1")
            toolhead = self.printer.lookup_object('toolhead')
            curtime = self.printer.get_reactor().monotonic()
            homed_axes_list = toolhead.get_status(curtime)['homed_axes']
            pos = toolhead.get_position()
            if ('x' in homed_axes_list and 'y' in homed_axes_list and 'z' in homed_axes_list) and pos[2] < 50:
                self._move([None, None, 50], 20)
            self._set_state(AutoScrewsTiltAdjustStep.PROBING_HOMING_DONE)
        except Exception as e:
            self._set_state(AutoScrewsTiltAdjustStep.PROBING_HOMING_ERR)
            raise gcmd.error(str(e))

    def cmd_AUTO_SCREWS_TILT_ADJUST_DETECT_PLATE(self, gcmd):
        self._verify_screws_tilt_adjust_state("PLATE DETECTION")
        try:
            self._set_state(AutoScrewsTiltAdjustStep.PLATE_DETECTING)
            self.gcode.run_script_from_command("DETECT_BED_PLATE")
            self._set_state(AutoScrewsTiltAdjustStep.PLATE_DETECTED)
        except Exception as e:
            self._set_state(AutoScrewsTiltAdjustStep.PLATE_DETECTION_ERROR)
            raise gcmd.error(str(e))

    def cmd_AUTO_SCREWS_TILT_ADJUST_RESET_TO_INITIAL(self, gcmd):
        self._verify_screws_tilt_adjust_state("RESET TO INITIAL")
        try:
            self._set_state(AutoScrewsTiltAdjustStep.RESET_TO_INITIAL)
            self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=RESET_TO_INITIAL")
            self._move([None, None, self.probe_helper.default_horizontal_move_z], self.probe_helper.lift_speed)
        except Exception as e:
            pass

    def cmd_AUTO_SCREWS_TILT_ADJUST_PROBE_REFERENCE_POINTS(self, gcmd):
        self._verify_screws_tilt_adjust_state("PROBE REFERENCE POINTS")
        try:
            if 'SAMPLES' not in gcmd.get_command_parameters():
                gcmd._params['SAMPLES'] = '{}'.format(self.samples)
            if 'SAMPLE_RETRACT_DIST' not in gcmd.get_command_parameters():
                gcmd._params['SAMPLE_RETRACT_DIST'] = '{}'.format(self.sample_retract_dist)
            self._set_state(AutoScrewsTiltAdjustStep.PROBING_REFPOINT)
            self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=PROBE_REFERENCE_POINTS")
            self.probe_helper.start_probe(gcmd)
        except AutoScrewsTiltAdjustAbort as e:
            self._set_state(AutoScrewsTiltAdjustStep.PROBING_ABORTED)
        except AutoScrewsTiltAdjustPass:
            self._set_state(AutoScrewsTiltAdjustStep.SCREWS_TILT_ADJUST_OK)
            self.gcode.run_script_from_command("BED_MESH_CLEAR_MANUAL_LEVELING_REQUIRED")
        except (AutoScrewsTiltAdjustLimit, AutoScrewsTiltAdjustError, Exception) as e:
            self._set_state(AutoScrewsTiltAdjustStep.SCREWS_TILT_ADJUST_FAIL)
            raise gcmd.error(str(e))
        finally:
            self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=IDLE")
    def cmd_AUTO_SCREWS_TILT_ADJUST_MANUAL_TUNING(self, gcmd):
        self._verify_screws_tilt_adjust_state("MANUAL TUNING")
        if self.state != AutoScrewsTiltAdjustStep.PROBING_REFPOINT_COMPLETED:
            raise gcmd.error("Must complete probing refpoint before manual tuning")

        toolhead = self.printer.lookup_object('toolhead')
        probe_object = self.printer.lookup_object('probe', None)
        if probe_object is None:
            raise gcmd.error("Probe object not found")
        max_verify_attempts = gcmd.get_int('MAX_VERIFY_ATTEMPTS', self.max_verify_attempts, minval=1)
        max_adjust_times = gcmd.get_int('ADJUST_MAX_TIMES', self.max_adjust_times, minval=1)
        try:
            verify_attempt = 0
            while verify_attempt < max_verify_attempts:
                verify_attempt += 1
                self.gcode.respond_info("Starting adjustment round %d..." % verify_attempt)
                self.gcode.respond_info("Initial probing results:")
                for i, (z, screw) in enumerate(zip(self.base_points, self.screws)):
                    coord, name = screw
                    diff = self.target_z - z
                    direction = "CW" if diff > 0 else "CCW"
                    self.gcode.respond_info(
                        "%s : x=%.5f, y=%.5f, z=%.5f (turn %s %.5fmm)" %
                        (name, coord[0], coord[1], z, direction, abs(diff)))
                self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=MANUAL_TUNING")
                # Adjust screws in specified order
                for screw_num in self.screw_order:
                    i = screw_num - 1  # Convert to 0-based index
                    screw = self.screws[i]
                    coord, name = screw
                    self._probe_abort_check()
                    # Probe current point
                    diff = self.target_z - self.base_points[i]
                    self.need_adjusted_z = self.target_z - self.base_points[i]
                    with self.lock:
                        self.state = AutoScrewsTiltAdjustStep.WAIT_MANUAL_ADJUST_SCREWS
                        self.current_point = screw_num

                    # if abs(diff) <= self.adjust_tolerance:
                    #     self.gcode.respond_info(
                    #         "%s is within tolerance (deviation: %.3fmm)" % (name, diff))
                    #     break

                    self._move([None, None, self.probe_helper.default_horizontal_move_z], self.probe_helper.lift_speed)
                    self._move([coord[0], coord[1], None], self.probe_helper.speed)
                    self._move([None, None, self.base_points[i]+self.sample_retract_dist], self.probe_helper.lift_speed)
                    probe_cmd = "PROBE SAMPLES=1 SAMPLE_RETRACT_DIST={}".format(self.sample_retract_dist)
                    adjust_count = 0
                    while True:
                        adjust_count += 1
                        if adjust_count > max_adjust_times:
                            raise AutoScrewsTiltAdjustLimit(
                                "%s adjustment exceeded max limit (%d times)" % (name, max_adjust_times))
                        self.need_adjusted_z = self.target_z - self.base_points[i]
                        diff = self.target_z - self.base_points[i]
                        direction = "CW" if diff > 0 else "CCW"
                        self.gcode.respond_info("Turn %s %s (%.3fmm)" % (direction, name, diff))
                        self._probe_abort_check()
                        toolhead.wait_moves()  # Ensure all moves complete
                        self.gcode.run_script_from_command(probe_cmd)
                        toolhead.wait_moves()
                        self.base_points[i] = probe_object.get_status(0)['last_z_result']
                        self._move([None, None, self.base_points[i]+self.sample_retract_dist], self.probe_helper.lift_speed)
                        # if self.state == AutoScrewsTiltAdjustStep.NEXT_POINT_ADJUST:
                        if self.state != AutoScrewsTiltAdjustStep.WAIT_MANUAL_ADJUST_SCREWS:
                            break

                # Verify overall leveling
                self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=PROBING_ADJUST_VERIFY")
                probe_cmd = "PROBE SAMPLES=3 SAMPLE_RETRACT_DIST={}".format(self.sample_retract_dist)
                if self._verify_level(probe_cmd, toolhead, probe_object):
                    raise AutoScrewsTiltAdjustPass
                elif verify_attempt < max_verify_attempts:
                    self.gcode.respond_info("Preparing for adjustment round %d..." % (verify_attempt + 1))
                else:
                    raise AutoScrewsTiltAdjustLimit("Adjustment exceeded max verification attempts (%d)" % max_verify_attempts)

                # Recalculate target height as average of max and min
                self.max_z = max(self.base_points)
                self.min_z = min(self.base_points)
                self.target_z = (self.max_z + self.min_z) / 2
                self.gcode.respond_info("Updated target height: %.5f (max:%.5f min:%.5f)" %
                    (self.target_z, self.max_z, self.min_z))
        except AutoScrewsTiltAdjustPass as e:
            self._set_state(AutoScrewsTiltAdjustStep.SCREWS_TILT_ADJUST_OK)
            self.gcode.run_script_from_command("BED_MESH_CLEAR_MANUAL_LEVELING_REQUIRED")
        except AutoScrewsTiltAdjustAbort as e:
            self._set_state(AutoScrewsTiltAdjustStep.PROBING_ABORTED)
        except (AutoScrewsTiltAdjustLimit, AutoScrewsTiltAdjustError, Exception) as e:
            self._set_state(AutoScrewsTiltAdjustStep.SCREWS_TILT_ADJUST_FAIL)
            raise gcmd.error(str(e))
        finally:
            self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=IDLE")
            curtime = self.printer.get_reactor().monotonic()
            homed_axes_list = self.printer.lookup_object('toolhead').get_status(curtime)['homed_axes']
            if ('x' in homed_axes_list and 'y' in homed_axes_list and 'z' in homed_axes_list):
                self._move([None, None, self.probe_helper.default_horizontal_move_z], self.probe_helper.lift_speed)
    def cmd_AUTO_SCREWS_TILT_ADJUST_EXIT(self, gcmd):
        self._verify_screws_tilt_adjust_state("EXIT")
        try:
            self.gcode.run_script_from_command("EXIT_TO_IDLE REQ_FROM_STATE=SCREWS_TILT_ADJUST")
            self.gcode.run_script_from_command("SET_IDLE_TIMEOUT TIMEOUT=300")
            self._set_state(AutoScrewsTiltAdjustStep.IDLE)
            toolhead = self.printer.lookup_object('toolhead')
            curtime = self.printer.get_reactor().monotonic()
            homed_axes_list = toolhead.get_status(curtime)['homed_axes']
            pos = toolhead.get_position()
            if ('x' in homed_axes_list and 'y' in homed_axes_list and 'z' in homed_axes_list) and pos[2] < 50:
                self._move([None, None, 50], 20)
        except Exception as e:
            logging.info("Auto Screws Tilt Adjust Exit Failed: %s" % str(e))
def load_config(config):
    return AutoScrewsTiltAdjust(config)
