import math, logging, queuefile, os, json, copy
import stepper
from . import homing

TRINAMIC_DRIVERS = ["tmc2130", "tmc2208", "tmc2209", "tmc2240", "tmc2660",
    "tmc5160"]

HOMING_CALIBRATED_ORIGIN_FILE = "homing_calibrated_origin.json"
CALIBRATION_DATA_VERSION = 2
MIN_SUPPORTED_CALIBRATION_VERSION = 2

class HomingPreciseCorexy:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        if config.getsection('printer').get('kinematics') != 'corexy':
            raise config.error("homing_precise_corexy: kinematics must be corexy!!!")
        self.xy_back_offset = config.getfloat('xy_back_offset', 5., above=0.)
        self.probe_before_delay = config.getfloat('diagonal_probe_before_delay', 0., minval=0)
        self.probe_samples = config.getint('diagonal_probe_samples', 2, minval=2)
        self.probe_tolerance = config.getfloat('diagonal_probe_tolerance', minval=0)
        self.probe_accel = config.getfloat('diagonal_probe_accel', None, above=0.)
        self.probe_speed = config.getfloat('diagonal_probe_speed', above=0.)
        self.probe_retract_speed = config.getfloat('diagonal_probe_retract_speed', above=0.)
        self.probe_tolerance_retries = config.getint('diagonal_probe_tolerance_retries', minval=0)
        # Currently only supports diagonal_move_rail = 1 (B-motor), diagonal_move_rail = 0 (A-motor) not yet adapted
        self.move_rail = config.getint('diagonal_move_rail', 1, minval=0, maxval=1)
        sconfig = config.getsection('stepper_x')
        rotation_dist, steps_per_rotation = stepper.parse_step_distance(sconfig)
        self.x_step_dist = rotation_dist / steps_per_rotation
        self.x_phases = sconfig.getint("microsteps", note_valid=False) * 4
        sconfig = config.getsection('stepper_y')
        rotation_dist, steps_per_rotation = stepper.parse_step_distance(sconfig)
        self.y_step_dist = rotation_dist / steps_per_rotation
        self.y_phases = sconfig.getint("microsteps", note_valid=False) * 4
        self.x_tmc_module = None
        self.y_tmc_module = None
        self.c_a_full_phase = None
        self.c_b_full_phase = None
        debug = config.getint('debug', 0)
        start_args = self.printer.get_start_args()
        factory_mode = start_args.get('factory_mode', False)
        if debug or factory_mode:
            self.debug_mode = True
        else:
            self.debug_mode = False
        self.calibrated_origin_path = os.path.join(self.printer.get_snapmaker_config_dir("persistent"),
                                      HOMING_CALIBRATED_ORIGIN_FILE)
        self.use_calibration_origin = config.getboolean('use_calibration_origin', False) #or os.path.exists('/oem/.factory')
        self.enable_home_validation = config.getboolean('enable_home_validation', False)
        self.use_float_calc = config.getboolean('use_float_calc', False)
        self.validation_retries = config.getint('validation_retries', 3)
        self.calibrated_origin = self.load_calibrated_origin()
        if self.calibrated_origin is not None:
            self.use_calibration_origin = True
        if self.use_calibration_origin == True:
            self.use_float_calc = True
        self.printer.register_event_handler("klippy:connect", self.lookup_tmc)
        self.gcode.register_command('HOMING_PRECISE_COREXY', self.cmd_HOMING_PRECISE_COREXY)
        self.gcode.register_command('HOMING_PRECISE_COREXY_ADVANCED', self.cmd_HOMING_PRECISE_COREXY_ADVANCED)
        self.gcode.register_command("ENTER_HOMING_ORIGIN_CALIBRATION", self.cmd_ENTER_HOMING_ORIGIN_CALIBRATION)
        self.gcode.register_command("EXIT_HOMING_ORIGIN_CALIBRATION", self.cmd_EXIT_HOMING_ORIGIN_CALIBRATION)

    def lookup_tmc(self):
        for driver in TRINAMIC_DRIVERS:
            x_driver_name = "%s stepper_x" % (driver)
            y_driver_name = "%s stepper_y" % (driver)
            module_x = self.printer.lookup_object(x_driver_name, None)
            module_y = self.printer.lookup_object(y_driver_name, None)
            if module_x is not None:
                self.x_tmc_module = module_x
            if module_y is not None:
                self.y_tmc_module = module_y

    def check_xy_is_homing(self):
        toolhead = self.printer.lookup_object('toolhead')
        homed_axes = toolhead.get_kinematics().get_status(0)['homed_axes']
        if 'x' not in homed_axes or 'y' not in homed_axes:
            error = '{"coded": "0002-0528-0000-0010", "msg":"%s", "action": "pause"}' % ("Corexy precise homing aborted: Must home x and y axis first")
            raise self.printer.command_error(error)

    def cal_backoff_position(self, move_offset_x, move_offset_y):
        toolhead = self.printer.lookup_object('toolhead')
        corexy_rails = toolhead.get_kinematics().rails
        x_homing_info = corexy_rails[0].get_homing_info()
        y_homing_info = corexy_rails[1].get_homing_info()
        start_park_position_x = x_homing_info.position_endstop + [1, -1][x_homing_info.positive_dir == True]*move_offset_x
        start_park_position_y = y_homing_info.position_endstop + [1, -1][y_homing_info.positive_dir == True]*move_offset_y
        return start_park_position_x, start_park_position_y

    def calc_position(self, a_dist, b_dist):
        return (a_dist+b_dist)*0.5, (a_dist-b_dist)*0.5

    def phase_backoff_steps(self, corexy_rails):
        if self.x_tmc_module is None or self.y_tmc_module is None:
            raise self.printer.command_error("stepper_x, stepper_y must use the specified tmc devices")
        # Getting an effective direction of travel
        x_away_from_endstop_dir = not corexy_rails[0].get_homing_info().positive_dir
        y_away_from_endstop_dir = not corexy_rails[1].get_homing_info().positive_dir
        x_stepper_dir_inverted = corexy_rails[0].get_steppers()[0].get_dir_inverted()[0]
        y_stepper_dir_inverted = corexy_rails[1].get_steppers()[0].get_dir_inverted()[0]
        x_backoff_dir = [1, -1][x_away_from_endstop_dir == False] * [-1, 1][x_stepper_dir_inverted]
        y_backoff_dir = [1, -1][y_away_from_endstop_dir == False] * [-1, 1][y_stepper_dir_inverted]
        # self.gcode.respond_info("###########x_phase {}, y_phase {}###########".format(self.x_tmc_module.query_phase(), self.y_tmc_module.query_phase()))
        # Calculate the step to be moved for tmc phase alignment
        x_phase_offset = self.x_tmc_module.get_phase_offset()
        x_phases = x_phase_offset[1] if len(x_phase_offset) > 1 else 0
        if x_phases <= 0:
            raise self.printer.command_error(
                "Invalid TMC phase configuration for stepper_x")
        x_scale = 1024.0 / x_phases
        if x_scale == 0:
            raise self.printer.command_error(
                "Invalid TMC phase scale for stepper_x")
        x_backoff_step = (([1, -1][x_backoff_dir == 1]*self.x_tmc_module.query_phase()) % 1024) / x_scale

        y_phase_offset = self.y_tmc_module.get_phase_offset()
        y_phases = y_phase_offset[1] if len(y_phase_offset) > 1 else 0
        if y_phases <= 0:
            raise self.printer.command_error(
                "Invalid TMC phase configuration for stepper_y")
        y_scale = 1024.0 / y_phases
        if y_scale == 0:
            raise self.printer.command_error(
                "Invalid TMC phase scale for stepper_y")
        y_backoff_step = (([1, -1][y_backoff_dir == 1]*self.y_tmc_module.query_phase()) % 1024) / y_scale
        return x_backoff_step, y_backoff_step

    def diagonal_probe(self, endstops, movepos, sim_stall_set_endstops=None):
        toolhead = self.printer.lookup_object('toolhead')
        if self.probe_before_delay:
            toolhead.dwell(self.probe_before_delay)
            toolhead.wait_moves()
        # endstops = rail.get_endstops()
        hmove = homing.HomingMove(self.printer, endstops, sim_stall_set_endstops=sim_stall_set_endstops)
        # hmove = homing.HomingMove(self.printer, endstops, None)
        # start diagonal probe
        epos = hmove.homing_move(movepos, self.probe_speed, True)
        toolhead.flush_step_generation()
        trigger_mcu_pos = {sp.stepper_name: sp.trig_pos
                                for sp in hmove.stepper_positions}
        return epos, trigger_mcu_pos

    def cal_diagonal_dist(self, m_steps):
        d = (abs(m_steps[0][0]) + abs(m_steps[0][1]) + abs(m_steps[1][0]) + abs(m_steps[1][1])) // 2
        c_dist_a = (d + self.x_phases) // (2 * self.x_phases)
        d_y = d - (abs(m_steps[0][0]) + abs(m_steps[0][1]))
        d_y2 = abs(d_y) + self.y_phases
        if d_y < 0:
            d_y2 = -d_y2
        c_dist_b = d_y2 // (2 * self.y_phases)

        f_d1 = ((abs(m_steps[0][0])) + abs(m_steps[0][1]))/(2*self.x_phases)
        f_d2 = ((abs(m_steps[1][0])) + abs(m_steps[1][1]))/(2*self.y_phases)
        c_a_raw = (d) / (2 * self.x_phases)
        c_b_raw = d_y / (2*self.y_phases)
        return c_dist_a, c_dist_b, c_a_raw, c_b_raw

    def round_to_nearest_multiple(self, value, multiple):
        return round(value / multiple) * multiple

    def round_steps_to_multiples(self, m_steps):
        aligned_steps = []
        for i, step_group in enumerate(m_steps):
            aligned_group = []
            for step_value in step_group:
                phase_size = (self.x_phases/4) if self.move_rail == 0 else (self.y_phases/4)
                aligned_value = self.round_to_nearest_multiple(step_value, phase_size)
                aligned_group.append(aligned_value)
            aligned_steps.append(aligned_group)
        return aligned_steps

    def cal_diagonal_dist_float(self, m_steps):
        d1 = (abs(m_steps[1][0]) + abs(m_steps[1][1])) / 2
        d2 = (abs(m_steps[0][0]) + abs(m_steps[0][1])) / 2
        d = d1 + d2
        a = d / 2.
        b = d1 - a
        c_dist_a = a / self.x_phases
        c_dist_b = b / self.y_phases
        return c_dist_a, c_dist_b, c_dist_a, c_dist_b

    def cal_diagonal_move_dist(self, m_dists):
        d1 = (abs(m_dists[1][0]) + abs(m_dists[1][1])) / 2
        d2 = (abs(m_dists[0][0]) + abs(m_dists[0][1])) / 2
        return d1, d2

    def cal_diagonal_dist_selected(self, m_steps, use_float_calc=None):
        use_float = use_float_calc if use_float_calc is not None else self.use_float_calc
        if use_float:
            return self.cal_diagonal_dist_float(m_steps)
        else:
            return self.cal_diagonal_dist(m_steps)

    def is_point_unstable(self, c_dist, origin=None):
        threshold = 1.0 / 4
        if origin is None:
            origin = [0.0, 0.0]
        for i in range(2):
            diff = c_dist[i] - origin[i]
            diff = math.fmod(diff, 1.0)
            if abs(diff - 0.5) < threshold:
                self.gcode.respond_info("Point is unstable, c_dist={}, origin={}".format(c_dist, origin))
                return True
        return False

    def translate_to_ab_grid(self, c_dist, origin=None):
        c_ab = [0, 0]
        if origin is None:
                origin = [0.0, 0.0]
        for i in range(2):
            o_int = int(round(origin[i]))
            c_ab[i] = int(round(c_dist[i] - origin[i])) + o_int
        return c_ab

    def calc_abgrid_offset(self, a_phase_offset, b_phase_offset):
        if self.x_tmc_module is None or self.y_tmc_module is None:
            raise self.printer.command_error("stepper_x, stepper_y must use the specified tmc devices")

        toolhead = self.printer.lookup_object('toolhead')
        corexy_rails = toolhead.get_kinematics().rails
        x_home_dir = 1 if corexy_rails[0].get_homing_info().positive_dir else -1
        y_home_dir = 1 if corexy_rails[1].get_homing_info().positive_dir else -1

        if x_home_dir == y_home_dir:
            a_phase_offset = a_phase_offset * (-y_home_dir)
            b_phase_offset = b_phase_offset * (-x_home_dir)
        else:
            a_phase_offset = a_phase_offset * (-x_home_dir)
            b_phase_offset = b_phase_offset * (-y_home_dir)
        return self.calc_position(a_phase_offset*self.x_phases*self.x_step_dist, b_phase_offset*self.y_phases*self.y_step_dist)

    def perform_diagonal_probing(self, probe_start_x, probe_start_y, xy_back_offset=None):
        toolhead = self.printer.lookup_object('toolhead')
        kin = toolhead.get_kinematics()
        corexy_rails = toolhead.get_kinematics().rails
        if xy_back_offset is None:
            xy_back_offset = self.xy_back_offset
        try:
            toolhead.manual_move([probe_start_x, probe_start_y, None], self.probe_retract_speed)
            toolhead.wait_moves()
            kin.set_ignore_check_move_limit(True)
            probe_cnt, sample, recv_steps, recv_dists = 0, 0, [[], []], [[], []]
            park_step = corexy_rails[1].get_steppers()[0].get_mcu_position()
            probe_success = False
            while probe_cnt <= self.probe_tolerance_retries:
                x_move_position, y_move_position = self.calc_position(0, [-1, 1][sample % 2 == 0]*xy_back_offset*4)
                toolhead.wait_moves()

                pos = toolhead.get_position()
                pos[0] = pos[0] + x_move_position
                pos[1] = pos[1] + y_move_position
                # epos, trigger_mcu_pos = self.diagonal_probe(corexy_rails[1], pos)
                epos, trigger_mcu_pos = self.diagonal_probe(corexy_rails[1].get_endstops(), pos, corexy_rails[0].get_endstops())
                recv_steps[[0, 1][sample % 2 == 1]].append(park_step - trigger_mcu_pos['stepper_y'])
                recv_dists[[0, 1][sample % 2 == 1]].append((round(epos[0]-probe_start_x, 5), round(epos[1]-probe_start_y, 5)))
                toolhead.manual_move([probe_start_x, probe_start_y, None], self.probe_retract_speed)
                toolhead.wait_moves()
                sample += 1
                if len(recv_steps[1]) >= 2:
                    if (((abs(recv_steps[0][0] - recv_steps[0][1])*self.y_step_dist) >= self.probe_tolerance) or
                        (abs((recv_steps[1][0] - recv_steps[1][1])*self.y_step_dist) >= self.probe_tolerance)):
                        sample = 0
                        probe_cnt += 1
                        self.gcode.respond_info("###{}, {}, {}####".format(abs((abs(recv_steps[0][0]) - abs(recv_steps[0][1]))*self.y_step_dist), abs((abs(recv_steps[1][0]) - abs(recv_steps[1][1]))*self.y_step_dist), recv_steps))
                        recv_steps = [[], []]
                        probe_success = False
                    else:
                        probe_success = True
                        recv_steps = self.round_steps_to_multiples(recv_steps)
                        break
            return recv_steps, recv_dists, probe_success
        except Exception as e:
            raise
        finally:
            kin.set_ignore_check_move_limit(False)

    def perform_multi_point_diagonal_probing(self, probe_start_x, probe_start_y):
        point_sequence = [
            [1, 0],
            [-1, 0],
            [0, 1],
            [0, -1],
            [-1, -1],
            [1, 1],
            [1, -1],
            [-1, 1],
            [0, 0],
        ]

        points = []
        for i in range(len(point_sequence)):
            points.append({
                'c_dist': [0.0, 0.0],
                'm_dist': [0.0, 0.0],
                'revalidate': True
            })

        rev_cnt = len(point_sequence)
        for revcount in range(len(point_sequence) // 2):
            c_acc = [0.0, 0.0]
            new_rev_cnt = 0

            for i in range(len(point_sequence)):
                seq = point_sequence[i]
                data = points[i]
                if data['revalidate']:
                    x_off_dist, y_off_dist = self.calc_abgrid_offset(seq[0], seq[1])
                    new_probe_start_x, new_probe_start_y = probe_start_x+x_off_dist, probe_start_y+y_off_dist
                    self.gcode.respond_info("round_{}: ###point_{}###".format(revcount, i))
                    recv_steps, recv_dists, probe_success = self.perform_diagonal_probing(new_probe_start_x, new_probe_start_y)
                    if probe_success == True:
                        data['c_dist'][0], data['c_dist'][1], c_a_raw, c_b_raw = self.cal_diagonal_dist_selected(recv_steps, True)
                        self.gcode.respond_info("c_a_raw: {}, c_b_raw: {}".format(data['c_dist'][0], data['c_dist'][1]))
                    else:
                        error = '{"coded": "0003-0530-0000-0024", "msg":"%s", "action": "cancel"}' % ("Home origin calibration failed, Corexy precise homing failed")
                        raise self.printer.command_error(error)

            c_acc[0] = sum(p['c_dist'][0] for p in points)
            c_acc[1] = sum(p['c_dist'][1] for p in points)
            origin = [c_acc[0] / float(len(point_sequence)), c_acc[1] / float(len(point_sequence))]
            o_int = [int(round(origin[0])), int(round(origin[1]))]
            self.gcode.respond_info("origin: {}, o_int: {}".format(origin, o_int))

            for i in range(len(point_sequence)):
                seq = point_sequence[i]
                data = points[i]
                c_ab = self.translate_to_ab_grid(data['c_dist'], origin)
                c_diff = [c_ab[0] - seq[0] - o_int[0], c_ab[1] - seq[1] - o_int[1]]
                if c_diff[0] != 0 or c_diff[1] != 0:
                    error_msg = "Home calibration point ({},{}) error: dx={} dy={} with origin x={} y={}".format(
                                seq[0], seq[1], c_diff[0], c_diff[1], o_int[0], o_int[1])
                    error = '{"coded": "0003-0530-0000-0025", "msg":"%s", "action": "cancel"}' % (error_msg)
                    raise self.printer.command_error(error)

                data['revalidate'] = self.is_point_unstable(data['c_dist'], origin)
                if data['revalidate']:
                    self.gcode.respond_info("Home calibration point ({},{}) unstable A:{} B:{} with origin A:{} B:{}".format(
                        seq[0], seq[1], data['c_dist'][0], data['c_dist'][1], origin[0], origin[1]))
                    new_rev_cnt += 1

            if new_rev_cnt > rev_cnt:
                error_msg = "Home calibration failed: maximum retries exceeded"
                error = '{"coded": "0003-0530-0000-0026", "msg":"%s", "action": "cancel"}' % (error_msg)
                raise self.printer.command_error(error)

            rev_cnt = new_rev_cnt
            if rev_cnt == 0:
                break

        if rev_cnt > 0:
            error_msg = "Home calibration failed: unstable points remain after retries"
            error = '{"coded": "0003-0530-0000-0026", "msg":"%s", "action": "cancel"}' % (error_msg)
            raise self.printer.command_error(error)

        self.gcode.respond_info("home grid origin A:{} B:{}".format(origin[0], origin[1]))
        return origin

    def save_calibration_data(self, data_line):
        if self.debug_mode:
            logdir = None
            vsd = self.printer.lookup_object('virtual_sdcard', None)
            if vsd is None:
                logging.info("No virtual_sdcard dir to save extruder offset data")
                logdir = '/tmp/calibration_data'
            else:
                logdir = f'{vsd.sdcard_dirname}/calibration_data'

            if logdir is not None:
                if not os.path.exists(logdir):
                    os.makedirs(logdir)
                data_filename = os.path.join(logdir, 'homing_precise_corexy.csv')
                queuefile.async_append_file(data_filename, data_line)

    def generate_and_save_results(self, c_dist_a, c_dist_b, c_dist_raw_a, c_dist_raw_b,
                                probe_start_x, probe_start_y, recv_steps, recv_dists, debug_mode=False):
        x, y = self.calc_position(c_dist_a*self.x_phases*self.x_step_dist,
                                c_dist_b*self.y_phases*self.y_step_dist)
        cal_x_position, cal_y_position = self.cal_backoff_position(x, y)
        results = [
                "%.5f" % probe_start_x, "%.5f" % probe_start_y,
                "%.5f" % cal_x_position, "%.5f" % cal_y_position,
                str(recv_steps),
                ]
        results.extend(["%.5f" % c_dist_raw_a, "%.5f" % c_dist_raw_b])
        results.extend([str(c_dist_a), str(c_dist_b)])
        data_line = ", ".join(results) + "\n"
        self.gcode.respond_info(data_line)
        self.save_calibration_data(data_line)
        return cal_x_position, cal_y_position

    def load_calibrated_origin(self):
        try:
            if not os.path.exists(self.calibrated_origin_path):
                return None
            with open(self.calibrated_origin_path, 'r') as f:
                data = json.load(f)

            if not isinstance(data, dict):
                return None

            version = data.get('version', 0)
            if not isinstance(version, (int, float)):
                logging.warning("Invalid version in calibrated origin file")
                return None

            version = float(version)
            if version < MIN_SUPPORTED_CALIBRATION_VERSION:
                logging.info("Calibrated origin version too old: %s", version)
                return None

            origin = data.get('origin')
            if not isinstance(origin, list) or len(origin) != 2:
                return None

            if not all(isinstance(x, (int, float)) for x in origin):
                return None

            return origin
        except Exception as e:
            logging.exception("Could not load calibrated origin from file: %s", e)
            return None

    def save_calibrated_origin(self, origin):
        if not isinstance(origin, (list, tuple)) or len(origin) != 2:
            logging.error("Invalid origin data format")
            return False

        if not all(isinstance(x, (int, float)) for x in origin):
            logging.error("Origin data contains non-numeric values")
            return False

        try:
            content = json.dumps({
                "origin": list(origin),
                "version": CALIBRATION_DATA_VERSION
            })
            queuefile.async_write_file(self.calibrated_origin_path, content)
            return True
        except Exception as e:
            logging.exception("Could not save calibrated origin to file: %s", e)
            return False

    def precise_corexy_coord(self, gcmd):
        toolhead = self.printer.lookup_object('toolhead')
        homing_xyz_override = self.printer.lookup_object('homing_xyz_override', None)
        kin = toolhead.get_kinematics()
        cur_max_accel = None
        home_unstable = False
        v_home_unstable = False
        try:
            # Ensure that x and y have go home before diagonally moving the probe.
            self.check_xy_is_homing()
            corexy_rails = toolhead.get_kinematics().rails
            # Move to the specified position, manual_move detects if the target position is out of range
            x_position, y_position = self.cal_backoff_position(self.xy_back_offset, self.xy_back_offset)
            toolhead.manual_move([x_position, y_position, None], self.probe_retract_speed)
            toolhead.wait_moves()
            self.c_a_full_phase = None
            self.c_b_full_phase = None
            # full phase alignment
            x_step, y_step = self.phase_backoff_steps(corexy_rails)
            x_dist, y_dist = self.calc_position(x_step*self.x_step_dist, y_step*self.y_step_dist)
            pos = toolhead.get_position()
            probe_start_x, probe_start_y = pos[0]+x_dist, pos[1]+y_dist
            self.gcode.respond_info("probe_start_x: {:.5f}, probe_start_y: {:.5f}".format(probe_start_x, probe_start_y))
            # logging.info("use_cal: {}, f_cal: {}, use_origin: {}".format(self.use_calibration_origin, self.use_float_calc, self.use_calibration_origin))
            self.gcode.respond_info("use_origin: {}, f_cal: {}, origin: {}".format(self.use_calibration_origin, self.use_float_calc, self.calibrated_origin))
            if self.probe_accel is not None:
                cur_max_accel = toolhead.max_accel
                toolhead.set_accel(self.probe_accel)

            force_calibration = gcmd.get_int('FORCE_CALIBRATION', 0, minval=0, maxval=1)
            # get data from calibration file
            if ((self.use_calibration_origin and self.calibrated_origin is None) or force_calibration):
                machine_state_manager = self.printer.lookup_object('machine_state_manager', None)
                in_calibration_mode = machine_state_manager and str(machine_state_manager.get_status()['main_state']) == "HOMING_ORIGIN_CALIBRATION"
                try:
                    if in_calibration_mode:
                        self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=HOMING_ORIGIN_CALIBRATING")
                    calibrated_origin = self.perform_multi_point_diagonal_probing(probe_start_x, probe_start_y)
                    self.save_calibrated_origin(calibrated_origin)
                    self.calibrated_origin = copy.deepcopy(calibrated_origin)
                    self.use_calibration_origin = True
                    self.use_float_calc = True
                finally:
                    if in_calibration_mode:
                        self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=IDLE")
            recv_steps, recv_dists, probe_success = self.perform_diagonal_probing(probe_start_x, probe_start_y)
            if probe_success == True:
                c_dist_a, c_dist_b, c_a_raw, c_b_raw = self.cal_diagonal_dist_selected(recv_steps)
                self.c_a_full_phase = round(c_a_raw, 5)
                self.c_b_full_phase = round(c_b_raw, 5)
                if self.is_point_unstable([c_dist_a, c_dist_b], self.calibrated_origin):
                    home_unstable = True
                    if home_unstable and not self.enable_home_validation:
                        error = '{"coded": "0003-0530-0000-0027", "msg":"%s", "action": "cancel"}' % ("Corexy home is unstable")
                        raise self.printer.command_error(error)
                    else:
                        self.gcode.respond_info("Corexy home point is unstable")
                c_ab = self.translate_to_ab_grid([c_dist_a, c_dist_b], self.calibrated_origin)
                cal_x_position, cal_y_position = self.generate_and_save_results(
                                                c_ab[0], c_ab[1], c_a_raw, c_b_raw,
                                                probe_start_x, probe_start_y, recv_steps, recv_dists, self.debug_mode)

                if self.enable_home_validation:
                    a_phase_offset, b_phase_offset = -1, 3
                    v_x_off_dist, v_y_off_dist = self.calc_abgrid_offset(a_phase_offset, b_phase_offset)
                    probe_start_x, probe_start_y = probe_start_x+v_x_off_dist, probe_start_y+v_y_off_dist
                    self.gcode.respond_info("validation probe_start_x: {:.5f}, probe_start_y: {:.5f}".format(probe_start_x, probe_start_y))
                    toolhead.manual_move([probe_start_x, probe_start_y, None], self.probe_retract_speed)
                    toolhead.wait_moves()
                    self.c_a_full_phase = None
                    self.c_b_full_phase = None
                    recv_steps, recv_dists, probe_success = self.perform_diagonal_probing(probe_start_x, probe_start_y)
                    if probe_success == True:
                        c_dist_a, c_dist_b, c_a_raw, c_b_raw = self.cal_diagonal_dist_selected(recv_steps)
                        self.c_a_full_phase = round(c_a_raw, 5)
                        self.c_b_full_phase = round(c_b_raw, 5)
                        p_ab = c_ab
                        v_p_ab = self.translate_to_ab_grid([c_dist_a, c_dist_b], self.calibrated_origin)
                        self.gcode.respond_info("p_ab: {}, v_p_ab: {}".format(p_ab, v_p_ab))
                        cal_x_position, cal_y_position = self.generate_and_save_results(
                                    v_p_ab[0], v_p_ab[1], c_a_raw, c_b_raw,
                                    probe_start_x, probe_start_y, recv_steps, recv_dists, self.debug_mode)

                        if self.is_point_unstable([c_dist_a, c_dist_b], self.calibrated_origin):
                            v_home_unstable = True
                            self.gcode.respond_info("Corexy validation point is unstable")

                        if home_unstable and v_home_unstable:
                            error = '{"coded": "0003-0530-0000-0027", "msg":"%s", "action": "cancel"}' % ("Corexy home is unstable")
                            raise self.printer.command_error(error)

                        if v_p_ab[0] - p_ab[0] != a_phase_offset or v_p_ab[1] - p_ab[1] != b_phase_offset:
                            error = '{"coded": "0003-0530-0000-0028", "msg":"%s", "action": "cancel"}' % ("Corexy validation point is invalid")
                            raise self.printer.command_error(error)
                    else:
                        error = '{"coded": "0002-0528-0000-0012", "msg":"%s", "action": "pause"}' % ("Corexy precise homing failed")
                        raise self.printer.command_error(error)

                # Check the reasonableness of the calculated data
                if abs(cal_x_position - probe_start_x) > self.x_step_dist*self.x_phases or abs(cal_y_position - probe_start_y) > self.y_step_dist*self.y_phases:
                    error = '{"coded": "0002-0528-0000-0011", "msg":"%s", "action": "pause"}' % ("Corexy precise homing computed coordinate anomaly")
                    logging.info(f"Corexy precise homing: cal_x: {cal_x_position}, cal_y: {cal_y_position}, probe_x: {probe_start_x}, probe_y: {probe_start_y}")
                    raise self.printer.command_error(error)
                toolhead.wait_moves()
                pos = toolhead.get_position()
                pos[0], pos[1] = cal_x_position, cal_y_position
                toolhead.set_position(pos)
            else:
                error = '{"coded": "0002-0528-0000-0012", "msg":"%s", "action": "pause"}' % ("Corexy precise homing failed")
                raise self.printer.command_error(error)

        except Exception as e:
            can_motor_off = True
            if ("z" in kin.get_status(0)['homed_axes']):
                machine_state_manager = self.printer.lookup_object('machine_state_manager', None)
                if machine_state_manager is not None:
                    cur_sta = machine_state_manager.get_status()
                    if str(cur_sta["main_state"]) == "PRINTING":
                        can_motor_off = False

            if can_motor_off:
                self.printer.lookup_object('stepper_enable').motor_off()
            else:
                if hasattr(kin, "note_x_not_homed"):
                    kin.note_x_not_homed()
                if hasattr(kin, "note_y_not_homed"):
                    kin.note_y_not_homed()
            raise
        finally:
            if cur_max_accel is not None:
                toolhead.set_accel(cur_max_accel)

    def cmd_HOMING_PRECISE_COREXY(self, gcmd):
        self.precise_corexy_coord(gcmd)

    def cmd_HOMING_PRECISE_COREXY_ADVANCED(self, gcmd):
        retry_attempts = self.validation_retries
        attempt = 0
        while attempt <= retry_attempts:
            try:
                macro = self.printer.lookup_object('gcode_macro _HOMING_PRECISE_COREXY_ADVANCED', None)
                if macro is not None:
                    force_calibration = gcmd.get_int('FORCE_CALIBRATION', 0, minval=0, maxval=1)
                    self.gcode.run_script_from_command("_HOMING_PRECISE_COREXY_ADVANCED FORCE_CALIBRATION={}".format(force_calibration))
                break
            except Exception as e:
                str_err = self.printer.extract_coded_message_field(str(e))
                if ("Corexy precise homing computed coordinate anomaly" in str_err or
                    "Corexy home is unstable" in str_err or "Corexy validation point is invalid" in str_err) and attempt < retry_attempts:
                    attempt += 1
                    self.gcode.respond_info("Validation failed, retrying... (attempt %d/%d)" % (attempt, retry_attempts))
                    continue
                raise

    def cmd_ENTER_HOMING_ORIGIN_CALIBRATION(self, gcmd):
        self.gcode.run_script_from_command("SET_MAIN_STATE MAIN_STATE=HOMING_ORIGIN_CALIBRATION")
        self.gcode.run_script_from_command("SET_IDLE_TIMEOUT TIMEOUT=9999999999")

    def cmd_EXIT_HOMING_ORIGIN_CALIBRATION(self, gcmd):
        machine_state_manager = self.printer.lookup_object('machine_state_manager', None)
        if machine_state_manager and str(machine_state_manager.get_status()['main_state']) == "HOMING_ORIGIN_CALIBRATION":
            self.gcode.run_script_from_command("EXIT_TO_IDLE REQ_FROM_STATE=HOMING_ORIGIN_CALIBRATION")
            self.gcode.run_script_from_command("SET_IDLE_TIMEOUT TIMEOUT=300")

    def get_status(self, eventtime):
        return {
            'c_a_full_phase': self.c_a_full_phase,
            'c_b_full_phase': self.c_b_full_phase,
            'use_calibration_origin': self.use_calibration_origin,
            'calibrated_origin': self.calibrated_origin
        }

def load_config(config):
    return HomingPreciseCorexy(config)