# Z-Probe support
#
# Copyright (C) 2017-2024  Kevin O'Connor <kevin@koconnor.net>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging, copy, time, os
import pins, queuefile
from . import manual_probe
from . import inductance_coil
from decimal import Decimal, getcontext

HINT_TIMEOUT = """
If the probe did not move far enough to trigger, then
consider reducing the Z axis minimum position so the probe
can travel further (the Z minimum position can be negative).
"""

AXIS_X_INDEX  = 0
AXIS_Y_INDEX  = 1
AXIS_Z_INDEX  = 2
AXIS_NAME_STR = ["x", "y", "z"]

RECTANGLE_PROBE_MODE = 0
CIRCLE_PROBE_MODE    = 1

MAX_OFFSET_DELTA_X      = 0.8
MAX_OFFSET_DELTA_Y      = 0.8
MAX_OFFSET_DELTA_Z      = 0.5

class ExtruderOffsetCalAbort(Exception):
    pass

# Calculate the average Z from a set of positions
def calc_probe_z_average(positions, method='average', axis=AXIS_Z_INDEX):
    if method != 'median':
        # Use mean average
        count = float(len(positions))
        return [sum([pos[i] for pos in positions]) / count
                for i in range(3)]
    # Use median
    z_sorted = sorted(positions, key=(lambda p: p[axis]))
    middle = len(positions) // 2
    if (len(positions) & 1) == 1:
        # odd number of samples
        return z_sorted[middle]
    # even number of samples
    return calc_probe_z_average(z_sorted[middle-1:middle+1], 'average', axis)

def find_circle_center(A, B, C):
    getcontext().prec = 50

    x1, y1 = map(Decimal, A)
    x2, y2 = map(Decimal, B)
    x3, y3 = map(Decimal, C)

    xm1 = (x1 + x2) / Decimal(2)
    ym1 = (y1 + y2) / Decimal(2)
    xm2 = (x2 + x3) / Decimal(2)
    ym2 = (y2 + y3) / Decimal(2)


    if x2 - x1 == Decimal(0):
        m1 = Decimal('Infinity')
    else:
        m1 = (y2 - y1) / (x2 - x1)

    if x3 - x2 == Decimal(0):
        m2 = Decimal('Infinity')
    else:
        m2 = (y3 - y2) / (x3 - x2)

    m_perp1 = -1 / m1 if m1 != Decimal(0) else Decimal(0)
    m_perp2 = -1 / m2 if m2 != Decimal(0) else Decimal(0)

    if m_perp1 == Decimal(0) or m_perp2 == Decimal(0):
        if m_perp1 == Decimal(0):
            h = xm1
            k = ym2 - m_perp2 * (xm2 - xm1)
        elif m_perp2 == Decimal(0):
            h = xm2
            k = ym1 - m_perp1 * (xm1 - xm2)
    else:
        h = (ym2 - ym1 + m_perp1*xm1 - m_perp2*xm2) / (m_perp1 - m_perp2)
        k = m_perp1 * (h - xm1) + ym1

    return (float(h), float(k))

######################################################################
# Probe device implementation helpers
######################################################################

# Helper to implement common probing commands
class ProbeCommandHelper:
    def __init__(self, config, probe, query_endstop=None):
        self.printer = config.get_printer()
        self.probe = probe
        self.query_endstop = query_endstop
        self.name = config.get_name()
        self.xyz_offset_abort = False
        self.xyz_offset_probe_status = 'idle'
        self.lock = self.printer.get_reactor().mutex()
        gcode = self.printer.lookup_object('gcode')
        # QUERY_PROBE command
        self.last_state = False
        gcode.register_command('QUERY_PROBE', self.cmd_QUERY_PROBE,
                               desc=self.cmd_QUERY_PROBE_help)
        # PROBE command
        self.last_z_result = 0.
        gcode.register_command('PROBE', self.cmd_PROBE,
                               desc=self.cmd_PROBE_help)
        # PROBE_CALIBRATE command
        self.probe_calibrate_z = 0.
        gcode.register_command('PROBE_CALIBRATE', self.cmd_PROBE_CALIBRATE,
                               desc=self.cmd_PROBE_CALIBRATE_help)
        # Other commands
        gcode.register_command('PROBE_BED_CONTACT', self.cmd_PROBE_BED_CONTACT,
                               desc=self.cmd_PROBE_BED_CONTACT_help)
        gcode.register_command('PROBE_ACCURACY', self.cmd_PROBE_ACCURACY,
                               desc=self.cmd_PROBE_ACCURACY_help)
        gcode.register_command('Z_OFFSET_APPLY_PROBE',
                               self.cmd_Z_OFFSET_APPLY_PROBE,
                               desc=self.cmd_Z_OFFSET_APPLY_PROBE_help)
        gcode.register_command('SET_PROBE_TRIG_FREQ',
                               self.cmd_SET_PROBE_TRIG_FREQ,
                                desc=None)
        gcode.register_command('INDUCTANCE_COIL_PROBE_QUERY',
                               self.cmd_INDUCTANCE_COIL_PROBE_QUERY,
                                desc=None)
        gcode.register_command('PROBE_XYZ_OFFSET_CALIBRATE',
                               self.cmd_PROBE_XYZ_OFFSET_CALIBRATE_ADVANCED,
                               desc=self.cmd_PROBE_XYZ_OFFSET_CALIBRATE_help)
        self.printer.register_event_handler("probe_xyz_offset:abort", self._probe_xyz_offset_abort)
        self.status = 'idle'
    def _move(self, coord, speed):
        self.printer.lookup_object('toolhead').manual_move(coord, speed)
    def _probe_xyz_offset_abort(self):
        if self.xyz_offset_probe_status == 'probing':
            with self.lock:
                self.xyz_offset_abort = True
    def get_status(self, eventtime):
        return {'name': self.name,
                'last_query': self.last_state,
                'last_z_result': self.last_z_result,
                'status': self.status}
    cmd_QUERY_PROBE_help = "Return the status of the z-probe"
    def cmd_QUERY_PROBE(self, gcmd):
        if self.query_endstop is None:
            raise gcmd.error("Probe does not support QUERY_PROBE")
        toolhead = self.printer.lookup_object('toolhead')
        print_time = toolhead.get_last_move_time()
        res = self.query_endstop(print_time)
        self.last_state = res
        gcmd.respond_info("probe: %s" % (["open", "TRIGGERED"][not not res],))
    cmd_PROBE_help = "Probe Z-height at current XY position"
    def cmd_PROBE(self, gcmd):
        try:
            self.printer.send_event("inductance_coil:probe_start")
            pos = run_single_probe(self.probe, gcmd)
            params = self.probe.get_probe_params(gcmd)
            axis = params['samples_axis']
            gcmd.respond_info("Result is %s=%.6f" % (AXIS_NAME_STR[axis], pos[axis],))
            if axis == AXIS_Z_INDEX:
                self.last_z_result = pos[2]
        finally:
            self.printer.send_event("inductance_coil:probe_end")
    def probe_calibrate_finalize(self, kin_pos):
        if kin_pos is None:
            return
        z_offset = self.probe_calibrate_z - kin_pos[2]
        gcode = self.printer.lookup_object('gcode')
        gcode.respond_info(
            "%s: z_offset: %.3f\n"
            "The SAVE_CONFIG command will update the printer config file\n"
            "with the above and restart the printer." % (self.name, z_offset))
        configfile = self.printer.lookup_object('configfile')
        configfile.set(self.name, 'z_offset', "%.3f" % (z_offset,))
    cmd_PROBE_CALIBRATE_help = "Calibrate the probe's z_offset"
    def cmd_PROBE_CALIBRATE(self, gcmd):
        manual_probe.verify_no_manual_probe(self.printer)
        params = self.probe.get_probe_params(gcmd)
        # Only allowed to be set to Z-axis
        if params['samples_axis'] != AXIS_Z_INDEX:
            raise self.printer.command_error(
                "The command samples axis cannot be specified as X/Y.")
        # Perform initial probe
        curpos = run_single_probe(self.probe, gcmd)
        # Move away from the bed
        self.probe_calibrate_z = curpos[2]
        curpos[2] += 5.
        self._move(curpos, params['lift_speed'])
        # Move the nozzle over the probe point
        x_offset, y_offset, z_offset = self.probe.get_offsets()
        curpos[0] += x_offset
        curpos[1] += y_offset
        self._move(curpos, params['probe_speed'])
        # Start manual probe
        manual_probe.ManualProbeHelper(self.printer, gcmd,
                                       self.probe_calibrate_finalize)
    cmd_PROBE_BED_CONTACT_help = "Probe bed by moving nozzle down until it touches the bed"
    def cmd_PROBE_BED_CONTACT(self, gcmd):
        macro = self.printer.lookup_object('gcode_macro _PROBE_BED_CONTACT', None)
        gcode = self.printer.lookup_object('gcode')
        move_speed = 30
        check_fail_lift_z = 150
        has_error = False
        try:
            if macro is not None:
                move_speed = macro.variables.get('move_speed', move_speed)
                check_fail_lift_z = macro.variables.get('check_fail_lift_z', check_fail_lift_z)
                gcode.run_script_from_command("_PROBE_BED_CONTACT")
            else:
                gcode.run_script_from_command("PROBE SAMPLE_TRIG_FREQ=450 SAMPLES=1 PROBE_SPEED=5")
        except Exception as e:
            has_error = True
            coded_message = self.printer.extract_encoded_message(str(e))
            if coded_message is not None:
                message = coded_message.get("msg", None)
                if message == "No trigger on probe after full movement":
                    err_msg = '{"coded": "0003-0530-0000-0017", "msg":"PEI coated plate not positioned correctly"}'
                    raise self.printer.command_error(err_msg)
            raise
        finally:
            if has_error:
                toolhead = self.printer.lookup_object('toolhead')
                curtime = self.printer.get_reactor().monotonic()
                status = toolhead.get_status(curtime)
                if 'z' in status['homed_axes']:
                    pos = toolhead.get_position()
                    if pos[2] < check_fail_lift_z:
                        toolhead.manual_move([None, None, check_fail_lift_z], move_speed)
    cmd_PROBE_ACCURACY_help = "Probe Z-height accuracy at current XY position"
    def cmd_PROBE_ACCURACY(self, gcmd):
        params = self.probe.get_probe_params(gcmd)
        sample_count = gcmd.get_int("SAMPLES", 10, minval=1)
        toolhead = self.printer.lookup_object('toolhead')
        pos = toolhead.get_position()
        gcmd.respond_info("PROBE_ACCURACY at X:%.3f Y:%.3f Z:%.3f"
                          " (samples=%d retract=%.3f"
                          " speed=%.1f lift_speed=%.1f)\n"
                          % (pos[0], pos[1], pos[2],
                             sample_count, params['sample_retract_dist'],
                             params['probe_speed'], params['lift_speed']))
        # Create dummy gcmd with SAMPLES=1
        fo_params = dict(gcmd.get_command_parameters())
        fo_params['SAMPLES'] = '1'
        gcode = self.printer.lookup_object('gcode')
        fo_gcmd = gcode.create_gcode_command("", "", fo_params)
        # Probe bed sample_count times
        probe_session = self.probe.start_probe_session(fo_gcmd)
        probe_num = 0
        while probe_num < sample_count:
            # Probe position
            probe_session.run_probe(fo_gcmd)
            probe_num += 1
            # Retract
            pos = toolhead.get_position()
            if params['samples_axis'] == AXIS_Z_INDEX:
                liftpos = [None, None, pos[2] + params['sample_retract_dist'] * params['samples_retract_dir']]
            elif params['samples_axis'] == AXIS_X_INDEX:
                liftpos = [pos[0] + params['sample_retract_dist'] * params['samples_retract_dir'], None, None]
            elif params['samples_axis'] == AXIS_Y_INDEX:
                liftpos = [None, pos[1] + params['sample_retract_dist'] * params['samples_retract_dir'], None]
            self._move(liftpos, params['lift_speed'])
        positions = probe_session.pull_probed_results()
        probe_session.end_probe_session()
        # Calculate maximum, minimum and average values
        max_value = max([p[params['samples_axis']] for p in positions])
        min_value = min([p[params['samples_axis']] for p in positions])
        range_value = max_value - min_value
        avg_value = calc_probe_z_average(positions, 'average', params['samples_axis'])[params['samples_axis']]
        median = calc_probe_z_average(positions, 'median', params['samples_axis'])[params['samples_axis']]
        # calculate the standard deviation
        deviation_sum = 0
        for i in range(len(positions)):
            deviation_sum += pow(positions[i][params['samples_axis']] - avg_value, 2.)
        sigma = (deviation_sum / len(positions)) ** 0.5
        # Show information
        gcmd.respond_info(
            "probe accuracy results: maximum %.6f, minimum %.6f, range %.6f, "
            "average %.6f, median %.6f, standard deviation %.6f" % (
            max_value, min_value, range_value, avg_value, median, sigma))
    cmd_Z_OFFSET_APPLY_PROBE_help = "Adjust the probe's z_offset"
    def cmd_Z_OFFSET_APPLY_PROBE(self, gcmd):
        gcode_move = self.printer.lookup_object("gcode_move")
        offset = gcode_move.get_status()['homing_origin'].z
        if offset == 0:
            gcmd.respond_info("Nothing to do: Z Offset is 0")
            return
        z_offset = self.probe.get_offsets()[2]
        new_calibrate = z_offset - offset
        gcmd.respond_info(
            "%s: z_offset: %.3f\n"
            "The SAVE_CONFIG command will update the printer config file\n"
            "with the above and restart the printer."
            % (self.name, new_calibrate))
        configfile = self.printer.lookup_object('configfile')
        configfile.set(self.name, 'z_offset', "%.3f" % (new_calibrate,))
    def cmd_SET_PROBE_TRIG_FREQ(self, gcmd):
        self.probe.mcu_probe.sensor.cmd_SET_TRIG_FREQ(gcmd)
    def cmd_INDUCTANCE_COIL_PROBE_QUERY(self, gcmd):
        self.probe.mcu_probe.sensor.cmd_INDUCTANCE_COIL_QUERY(gcmd)
    def cmd_PROBE_XYZ_OFFSET_CALIBRATE_ADVANCED(self, gcmd):
        try:
            with self.lock:
                self.xyz_offset_abort = False
                self.xyz_offset_probe_status = 'probing'
            self.printer.send_event("inductance_coil:probe_start")
            base_position = self.cmd_PROBE_XYZ_OFFSET_CALIBRATE(gcmd)
        finally:
            with self.lock:
                self.xyz_offset_probe_status = 'idle'
                self.xyz_offset_abort = False
            self.printer.send_event("inductance_coil:probe_end")

    cmd_PROBE_XYZ_OFFSET_CALIBRATE_help = "Probe the x y z position of a specified place"
    def find_circle_center_least_squares(self, points):
        import numpy as np
        # Convert points to numpy array
        points = np.array(points)
        x = points[:, 0]
        y = points[:, 1]

        # Setup the linear system for least squares
        A = np.vstack([2*x, 2*y, np.ones(len(x))]).T
        b = x**2 + y**2

        # Solve using least squares
        c_x, c_y, _ = np.linalg.lstsq(A, b, rcond=None)[0]

        return float(c_x), float(c_y)

    def _probe_z(self, gcmd, z_samples):
        if self.xyz_offset_abort:
            raise ExtruderOffsetCalAbort("ExtruderOffsetCalAbort")
        gcmd.get_command_parameters()['SAMPLES_AXIS'] = str(AXIS_Z_INDEX)
        gcmd.get_command_parameters()['SAMPLE_DIR'] = str(-1)
        gcmd.get_command_parameters()['SAMPLES'] = int(z_samples[0])
        gcmd.get_command_parameters()['SAMPLES_DISCARD'] = int(z_samples[1])
        pos = run_single_probe(self.probe, gcmd)
        return pos[2]

    def _probe_xy(self, gcmd, params, points, center):
        if points < 3:
            return []

        if points == 3:
            sample_dir = [
                params['samples_retract_dir'],
                params['samples_dir'],
                params['samples_retract_dir']
            ]
            position_prepare = [
                None,
                None,
                None
            ]
            position_start_probe = [
                [center[0] - 4, center[1], None],
                [center[0],     center[1], None],
                [center[0] + 4, center[1], None]
            ]
        elif points == 6:
            sample_dir = [
                params['samples_retract_dir'],
                params['samples_retract_dir'],
                params['samples_retract_dir'],
                params['samples_dir'],
                params['samples_dir'],
                params['samples_dir']
            ]
            position_prepare = [
                [center[0] + params['p1x'] - 0.7, center[1]],
                None,
                None,
                [center[0] + params['p1x'] - 0.7, center[1]],
                None,
                None
            ]
            position_start_probe = [
                [center[0] + params['p1x'], center[1] + params['p1y'], None],
                [center[0] + params['p2x'], center[1] + params['p2y'], None],
                [center[0] + params['p3x'], center[1] + params['p3y'], None],
                [center[0] + params['p1x'], center[1] - params['p1y'], None],
                [center[0] + params['p2x'], center[1] - params['p2y'], None],
                [center[0] + params['p3x'], center[1] - params['p3y'], None]
            ]
        elif points == 10:
            sample_dir = [
                params['samples_retract_dir'],
                params['samples_retract_dir'],
                params['samples_retract_dir'],
                params['samples_retract_dir'],
                params['samples_retract_dir'],
                params['samples_dir'],
                params['samples_dir'],
                params['samples_dir'],
                params['samples_dir'],
                params['samples_dir']
            ]
            position_prepare = [
                [center[0] + params['p1x'] - 0.7, center[1]],
                None,
                None,
                None,
                None,
                [center[0] + params['p1x'] - 0.7, center[1]],
                None,
                None,
                None,
                None
            ]
            position_start_probe = [
                [center[0] + params['p1x'], center[1] + params['p1y'], None],
                [center[0] + params['p2x'], center[1] + params['p2y'], None],
                [center[0] + params['p3x'], center[1] + params['p3y'], None],
                [center[0] + params['p4x'], center[1] + params['p4y'], None],
                [center[0] + params['p5x'], center[1] + params['p5y'], None],
                [center[0] + params['p1x'], center[1] - params['p1y'], None],
                [center[0] + params['p2x'], center[1] - params['p2y'], None],
                [center[0] + params['p3x'], center[1] - params['p3y'], None],
                [center[0] + params['p4x'], center[1] - params['p4y'], None],
                [center[0] + params['p5x'], center[1] - params['p5y'], None]
            ]
        else:
            return []

        gcmd.get_command_parameters()['SAMPLES_AXIS'] = str(AXIS_Y_INDEX)
        hit_position = []
        for i in range(points):
            if position_prepare[i] != None:
                self._move(position_prepare[i], params['travel_speed'])
            # move to position to start probing
            self._move(position_start_probe[i], params['travel_speed'])
            gcmd.get_command_parameters()['SAMPLE_DIR'] = str(sample_dir[i])
            if self.xyz_offset_abort:
                raise ExtruderOffsetCalAbort("ExtruderOffsetCalAbort")
            pos = run_single_probe(self.probe, gcmd)
            hit_position.append(pos)

        return hit_position

    def cmd_PROBE_XYZ_OFFSET_CALIBRATE(self, gcmd):
        cur_accel = None
        center = [None, None, None]
        # Check the status of inductance_coil
        result, capture_freq = self.probe.mcu_probe.sensor.check_coil_freq()
        if result != True:
            index = {"extruder": 0, "extruder1": 1, "extruder2": 2, "extruder3": 3}.get(self.probe.mcu_probe.sensor._name, 0)
            code = 0 if capture_freq == 0 else 1
            msg = "%s inductance coil status error [freq: %d]" % (self.probe.mcu_probe.sensor._name, capture_freq)
            message = '{"coded": "0003-0530-%4d-%4d", "oneshot": %d, "msg":"%s"}' % (index, code, 1, msg)
            raise gcmd.error(message)
            # raise gcmd.error("%s inductance coil status error, cannot start current calibration" % (self.probe.mcu_probe.sensor._name))
        # Must go home before probing
        toolhead = self.printer.lookup_object('toolhead')
        configfile = self.printer.lookup_object('configfile')
        gcode = self.printer.lookup_object('gcode')
        curtime = self.printer.get_reactor().monotonic()
        if 'z' not in toolhead.get_status(curtime)['homed_axes']:
            raise self.printer.command_error('{"coded": "0003-0530-0000-0002", "msg":"Must home before probe"}')

        params = self.probe.get_probe_params(gcmd)
        if params['points'] != 6 and params['points'] != 10:
            msg = '{"coded": "0003-0530-0000-0003", "msg":"%s"}' % f"invalid points{params['points']} for XY probe"
            raise self.printer.command_error(msg)

        origin_params = dict(gcmd.get_command_parameters())
        if params.get('log_file') != None:
            log_file = '{}_{}.txt'.format(toolhead.get_extruder().get_name(),
                                            params['log_file'])
            origin_params['LOG_FILE'] = log_file
        z_gcmd = gcode.create_gcode_command("", "", origin_params)
        xy_gcmd = gcode.create_gcode_command("", "", origin_params)
        center = [params['horizontal_move_x'], params['horizontal_move_y'], params['horizontal_move_z']]
        try:
            if params['move_accel'] != toolhead.max_accel:
                cur_accel = toolhead.max_accel
                toolhead.set_accel(params['move_accel'])
            # Move to z probe horizontal position
            horizontal_move_z = params['horizontal_move_z']
            self._move([None, None, horizontal_move_z], params['travel_speed'])
            # Move to x y probe horizontal position
            self._move([params['horizontal_move_x']+params['z_probe_x_move_offset'],
                        params['horizontal_move_y']+params['z_probe_y_move_offset'], None], params['travel_speed'])
            # samples and discard samples
            z_samlpes = [(3, 0), (3, 0), (6, 2)]
            # points for xy
            xyz_points = [3, params['points'], 0]
            for zs, xyp in zip(z_samlpes, xyz_points):
                center[2] = self._probe_z(z_gcmd, zs)
                # lift z
                probe_xy_z_hight = center[2] + params['retract_z_hight']
                self._move([None, None, probe_xy_z_hight], params['travel_speed'])
                # probe in xy plane
                points_pos = self._probe_xy(xy_gcmd, params, xyp, center)
                if len(points_pos) >= 3:
                    center[0], center[1] = self.find_circle_center_least_squares(points_pos)
                # move to center of circle
                gcmd.respond_info(f'Got center: {center[0]:.4f}, {center[1]:.4f}, {center[2]:.4f}')
                self._move([center[0]+params['z_probe_x_move_offset'], center[1]+params['z_probe_y_move_offset'], None], params['travel_speed'])

            if params['update_config']:
                extruder_offset_object = self.printer.lookup_object('extruder_offset_calibration', None)
                if extruder_offset_object is not None:
                    extruder_offset_object.last_xyz_result[toolhead.get_extruder().get_name()] = [center[0], center[1], center[2]]
                else:
                    configfile.set(toolhead.get_extruder().get_name(), 'base_position',
                                    "\n%.6f, %.6f, %.6f\n" % (center[0], center[1], center[2]))
                if params['save_info']:
                    vsd = self.printer.lookup_object('virtual_sdcard', None)
                    if vsd is None:
                        gcmd.respond_info("No virtual_sdcard dir to save extruder offset data")
                        logdir = '/tmp/calibration_data'
                    else:
                        logdir = f'{vsd.sdcard_dirname}/calibration_data'
                    ename = toolhead.get_extruder().get_name()
                    if not os.path.exists(logdir):
                        os.makedirs(logdir)

                    content1 = f'{center[0]:.6f}, {center[1]:.6f}, {center[2]:.6f}\n'
                    try:
                        queuefile.async_append_file(f'{logdir}/{ename}_xyz_offset_data.txt', content1)
                    except Exception as e:
                        logging.exception(f"Failed to append to file {ename}_xyz_offset_data.txt: {e}")

                    date = time.strftime("%Y-%m-%d %H:%M:%S")
                    content2 = f'{ename}({date}): {center[0]:.6f}, {center[1]:.6f}, {center[2]:.6f}\n'
                    if ename == 'extruder3':
                        content2 += '\n'
                    try:
                        queuefile.async_append_file(f'{logdir}/xyz_offset_data.txt', content2)
                    except Exception as e:
                        logging.exception(f"Failed to append to xyz_offset_data.txt: {e}")
            return center
        except ExtruderOffsetCalAbort as e:
            gcmd.respond_info("ExtruderOffsetCal Abort Success")
        finally:
            self._move([None, None, params['horizontal_move_z']], params['travel_speed'])
            self._move([center[0], center[1], params['horizontal_move_z']], params['travel_speed'])
            if cur_accel is not None and cur_accel != toolhead.max_accel:
                toolhead.set_accel(cur_accel)

# Homing via probe:z_virtual_endstop
class HomingViaProbeHelper:
    def __init__(self, config, mcu_probe):
        self.printer = config.get_printer()
        self.mcu_probe = mcu_probe
        self.multi_probe_pending = False
        # Register z_virtual_endstop pin
        self.printer.lookup_object('pins').register_chip('probe', self)
        # Register event handlers
        self.printer.register_event_handler('klippy:mcu_identify',
                                            self._handle_mcu_identify)
        self.printer.register_event_handler("homing:homing_move_begin",
                                            self._handle_homing_move_begin)
        self.printer.register_event_handler("homing:homing_move_end",
                                            self._handle_homing_move_end)
        self.printer.register_event_handler("homing:home_rails_begin",
                                            self._handle_home_rails_begin)
        self.printer.register_event_handler("homing:home_rails_end",
                                            self._handle_home_rails_end)
        self.printer.register_event_handler("gcode:command_error",
                                            self._handle_command_error)
    def _handle_mcu_identify(self):
        kin = self.printer.lookup_object('toolhead').get_kinematics()
        for stepper in kin.get_steppers():
            if stepper.is_active_axis('x') or stepper.is_active_axis('y') or stepper.is_active_axis('z'):
                self.mcu_probe.add_stepper(stepper)
    def _handle_homing_move_begin(self, hmove):
        if self.mcu_probe in hmove.get_mcu_endstops():
            self.mcu_probe.probe_prepare(hmove)
    def _handle_homing_move_end(self, hmove):
        if self.mcu_probe in hmove.get_mcu_endstops():
            self.mcu_probe.probe_finish(hmove)
    def _handle_home_rails_begin(self, homing_state, rails):
        endstops = [es for rail in rails for es, name in rail.get_endstops()]
        if self.mcu_probe in endstops:
            self.mcu_probe.multi_probe_begin()
            self.multi_probe_pending = True
    def _handle_home_rails_end(self, homing_state, rails):
        endstops = [es for rail in rails for es, name in rail.get_endstops()]
        if self.multi_probe_pending and self.mcu_probe in endstops:
            self.multi_probe_pending = False
            self.mcu_probe.multi_probe_end()
    def _handle_command_error(self):
        if self.multi_probe_pending:
            self.multi_probe_pending = False
            try:
                self.mcu_probe.multi_probe_end()
            except:
                logging.exception("Homing multi-probe end")
    def setup_pin(self, pin_type, pin_params):
        if pin_type != 'endstop' or pin_params['pin'] != 'z_virtual_endstop':
            raise pins.error("Probe virtual endstop only useful as endstop pin")
        if pin_params['invert'] or pin_params['pullup']:
            raise pins.error("Can not pullup/invert probe virtual endstop")
        return self.mcu_probe

# Helper to track multiple probe attempts in a single command
class ProbeSessionHelper:
    def __init__(self, config, mcu_probe):
        self.printer = config.get_printer()
        self.mcu_probe = mcu_probe
        gcode = self.printer.lookup_object('gcode')
        self.dummy_gcode_cmd = gcode.create_gcode_command("", "", {})
        # Infer Z position to move to during a probe
        if config.has_section('stepper_z'):
            zconfig = config.getsection('stepper_z')
            self.z_position = zconfig.getfloat('position_min', 0.,
                                               note_valid=False)
        else:
            pconfig = config.getsection('printer')
            self.z_position = pconfig.getfloat('minimum_z_position', 0.,
                                               note_valid=False)
        # Get the allowable detection range of the X-axis
        if config.has_section('stepper_x'):
            xconfig = config.getsection('stepper_x')
            self.x_min_position = xconfig.getfloat('position_min', 0., note_valid=False)
            self.x_max_position = xconfig.getfloat('position_max', 0., note_valid=False)
        else:
            self.x_min_position = 0
            self.x_max_position = 0

        if config.has_section('stepper_y'):
            yconfig = config.getsection('stepper_y')
            self.y_min_position = yconfig.getfloat('position_min', 0., note_valid=False)
            self.y_max_position = yconfig.getfloat('position_max', 0., note_valid=False)
        else:
            self.y_min_position = 0
            self.y_max_position = 0
        self.horizontal_move_z = config.getfloat('horizontal_move_z', 20)
        self.horizontal_move_x = config.getfloat('horizontal_move_x', 20, minval=self.x_min_position, maxval=self.x_max_position)
        self.horizontal_move_y = config.getfloat('horizontal_move_y', 20, minval=self.y_min_position, maxval=self.y_max_position)
        self.retract_z_hight = config.getfloat('retract_z_hight', 5, minval=0.)
        self.homing_helper = HomingViaProbeHelper(config, mcu_probe)
        # Configurable probing speeds
        self.speed = config.getfloat('speed', 5.0, above=0.)
        self.accel = config.getfloat('accel', 1000, above=0.)
        self.z_accel = config.getfloat('z_accel', 100, above=0.)
        self.first_fast_speed = config.getfloat('first_fast_speed', self.speed, above=0.)
        self.lift_speed = config.getfloat('lift_speed', self.speed, above=0.)
        self.travel_speed = config.getfloat('travel_speed', 50, above=0.)
        self.relative_trigger_freq = config.getint('relative_trigger_freq', 200, minval=10)
        # Multi-sample support (for improved accuracy)
        self.sample_count = config.getint('samples', 1, minval=1)
        self.sample_retract_dist = config.getfloat('sample_retract_dist', 2.,
                                                   above=0.)
        atypes = ['median', 'average']
        self.samples_result = config.getchoice('samples_result', atypes,
                                               'average')
        self.samples_tolerance = config.getfloat('samples_tolerance', 0.100,
                                                 minval=0.)
        self.samples_retries = config.getint('samples_tolerance_retries', 0,
                                             minval=0)
        # Session state
        self.multi_probe_pending = False
        self.results = []
        # Register event handlers
        self.printer.register_event_handler("gcode:command_error",
                                            self._handle_command_error)
    def _handle_command_error(self):
        if self.multi_probe_pending:
            try:
                self.end_probe_session()
            except:
                logging.exception("Multi-probe end")
    def _probe_state_error(self):
        raise self.printer.command_error(
            "Internal probe error - start/end probe session mismatch")
    def start_probe_session(self, gcmd):
        if self.multi_probe_pending:
            self._probe_state_error()
        self.mcu_probe.multi_probe_begin()
        self.multi_probe_pending = True
        self.results = []
        return self
    def end_probe_session(self):
        if not self.multi_probe_pending:
            self._probe_state_error()
        self.results = []
        self.multi_probe_pending = False
        self.mcu_probe.multi_probe_end()
    def get_probe_params(self, gcmd=None):
        if gcmd is None:
            gcmd = self.dummy_gcode_cmd
        probe_speed = gcmd.get_float("PROBE_SPEED", self.speed, above=0.)
        probe_accel = gcmd.get_float("PROBE_ACCEL", self.accel, above=0.)
        probe_z_accel = gcmd.get_float("PROBE_Z_ACCEL", self.z_accel, above=0.)
        lift_speed = gcmd.get_float("LIFT_SPEED", self.lift_speed, above=0.)
        samples = gcmd.get_int("SAMPLES", self.sample_count, minval=1)
        samples_discard = gcmd.get_int("SAMPLES_DISCARD", 0, minval=0)
        sample_retract_dist = gcmd.get_float("SAMPLE_RETRACT_DIST",
                                             self.sample_retract_dist, above=0.)
        samples_tolerance = gcmd.get_float("SAMPLES_TOLERANCE",
                                           self.samples_tolerance, minval=0.)
        samples_retries = gcmd.get_int("SAMPLES_TOLERANCE_RETRIES",
                                       self.samples_retries, minval=0)
        samples_result = gcmd.get("SAMPLES_RESULT", self.samples_result)
        samples_axis = gcmd.get_int("SAMPLES_AXIS", AXIS_Z_INDEX, minval=AXIS_X_INDEX, maxval=AXIS_Z_INDEX)
        samples_dir = [1, -1][gcmd.get_int("SAMPLE_DIR", 0) <= 0 or samples_axis == AXIS_Z_INDEX]
        samples_retract_dir = -1*samples_dir
        sample_dist = gcmd.get_float("SAMPLE_DIST", 1.5*sample_retract_dist, minval=1.0)
        sample_dist_z = gcmd.get_float("SAMPLE_DIST_Z", None, minval=0.0)

        # inductance_coil param configuration parsing fetch
        sample_trig_freq_config = gcmd.get_int("TRIG_FREQ_CONFIG", 1, minval=0, maxval=1)
        sample_trig_mode = gcmd.get_int("SAMPLE_TRIG_MODE", 1, minval=0, maxval=1)
        sample_trig_freq = gcmd.get_int("SAMPLE_TRIG_FREQ", self.relative_trigger_freq, minval=10)
        sample_trig_freq_y = gcmd.get_int("SAMPLE_TRIG_FREQ_Y", sample_trig_freq, minval=10)
        sample_absolute_trig = gcmd.get_int("SAMPLE_ABSOLUTE_TRIG", 0, minval=0, maxval=1)
        sample_trig_invert = gcmd.get_int("SAMPLE_TRIG_INVERT", 0, minval=0, maxval=1)
        sample_wait_before_setup = gcmd.get_float("WAIT_BEFORE_SETUP", 0.1, minval=0.)
        sample_wait_after_setup = gcmd.get_float("WAIT_AFTER_SETUP", 0.05, minval=0.)

        # xyz calibration parameters
        travel_speed = gcmd.get_float("TRAVEL_SPEED", self.travel_speed, above=0.)
        horizontal_move_x = gcmd.get_float("HORIZONTAL_MOVE_X", self.horizontal_move_x, minval=self.x_min_position, maxval=self.x_max_position)
        horizontal_move_y = gcmd.get_float("HORIZONTAL_MOVE_Y", self.horizontal_move_y, minval=self.y_min_position, maxval=self.y_max_position)
        horizontal_move_z = gcmd.get_float("HORIZONTAL_MOVE_Z", self.horizontal_move_z)
        z_probe_x_move_offset = gcmd.get_float("Z_PROBE_X_MOVE_OFFSET", 0)
        z_probe_y_move_offset = gcmd.get_float("Z_PROBE_Y_MOVE_OFFSET", -4)
        horizontal_move_z = gcmd.get_float("HORIZONTAL_MOVE_Z", self.horizontal_move_z)
        retract_z_hight = gcmd.get_float("RETRACT_Z_HIGHT", self.retract_z_hight)
        probe_fast_speed = gcmd.get_float("PROBE_FAST_SPEED", self.first_fast_speed, above=0.)
        move_accel = gcmd.get_float("MOVE_ACCEL", 1000, above=0.)
        # horizontal_dist = gcmd.get_float("HORIZONTAL_DIST", 2.0, minval=1.0)
        # probe_xyz_mode = gcmd.get_int("PROBE_XYZ_MODE", RECTANGLE_PROBE_MODE, minval=RECTANGLE_PROBE_MODE, maxval=CIRCLE_PROBE_MODE)
        log_file = gcmd.get("LOG_FILE", None)
        xy_start_pos = gcmd.get_float("XY_START_POS", -6)
        save_info = gcmd.get_int("SAVE_INFO", 0)
        points = gcmd.get_int("PROBE_POINTS", 6)
        if points == 6:
            point1_x = gcmd.get_float("P1X", -4.6)
            point1_y = gcmd.get_float("P1Y", -3.86)
            point2_x = gcmd.get_float("P2X", 0)
            point2_y = gcmd.get_float("P2Y", -6)
            point3_x = gcmd.get_float("P3X", 4.6)
            point3_y = gcmd.get_float("P3Y", -3.86)
            point4_x = gcmd.get_float("P4X", 0)
            point4_y = gcmd.get_float("P4Y", 0)
            point5_x = gcmd.get_float("P5X", 0)
            point5_y = gcmd.get_float("P5Y", 0)
        elif points == 10:
            point1_x = gcmd.get_float("P1X", -4.8)
            point1_y = gcmd.get_float("P1Y", -3.6)
            point2_x = gcmd.get_float("P2X", -2.4)
            point2_y = gcmd.get_float("P2Y", -5.5)
            point3_x = gcmd.get_float("P3X", 0)
            point3_y = gcmd.get_float("P3Y", -6)
            point4_x = gcmd.get_float("P4X", 2.4)
            point4_y = gcmd.get_float("P4Y", -5.5)
            point5_x = gcmd.get_float("P5X", 4.8)
            point5_y = gcmd.get_float("P5Y", -3.6)
        else:
            point1_x = gcmd.get_float("P1X", 0)
            point1_y = gcmd.get_float("P1Y", 0)
            point2_x = gcmd.get_float("P2X", 0)
            point2_y = gcmd.get_float("P2Y", 0)
            point3_x = gcmd.get_float("P3X", 0)
            point3_y = gcmd.get_float("P3Y", 0)
            point4_x = gcmd.get_float("P4X", 0)
            point4_y = gcmd.get_float("P4Y", 0)
            point5_x = gcmd.get_float("P5X", 0)
            point5_y = gcmd.get_float("P5Y", 0)
        update_config = gcmd.get_int("UPDATE_CONFIG", 1, minval=0, maxval=1)
        safety_check = gcmd.get_int("SAFETY_CHECK", 1)
        return {'probe_speed': probe_speed,
                'probe_accel': probe_accel,
                'probe_z_accel': probe_z_accel,
                'lift_speed': lift_speed,
                'move_accel': move_accel,
                'probe_fast_speed': probe_fast_speed,
                'samples': samples,
                'samples_discard': samples_discard,
                'travel_speed': travel_speed,
                'sample_dist': sample_dist,
                'sample_dist_z': sample_dist_z,
                'sample_retract_dist': sample_retract_dist,
                'samples_tolerance': samples_tolerance,
                'samples_tolerance_retries': samples_retries,
                'samples_result': samples_result,
                'samples_axis': samples_axis,
                'samples_dir': samples_dir,
                'samples_retract_dir': samples_retract_dir,
                'sample_trig_freq_config': sample_trig_freq_config,
                'sample_trig_mode': sample_trig_mode,
                'sample_trig_freq': sample_trig_freq,
                'sample_trig_freq_y': sample_trig_freq_y,
                'sample_absolute_trig': sample_absolute_trig,
                'sample_trig_invert': sample_trig_invert,
                'sample_wait_before_setup': sample_wait_before_setup,
                'sample_wait_after_setup': sample_wait_after_setup,
                'horizontal_move_x': horizontal_move_x,
                'horizontal_move_y': horizontal_move_y,
                'horizontal_move_z': horizontal_move_z,
                'z_probe_x_move_offset': z_probe_x_move_offset,
                'z_probe_y_move_offset': z_probe_y_move_offset,
                'retract_z_hight': retract_z_hight,
                # 'horizontal_dist' : horizontal_dist,
                # 'probe_xyz_mode' : probe_xyz_mode,
                'xy_start_pos': xy_start_pos,
                'p1x': point1_x,
                'p1y': point1_y,
                'p2x': point2_x,
                'p2y': point2_y,
                'p3x': point3_x,
                'p3y': point3_y,
                'p4x': point4_x,
                'p4y': point4_y,
                'p5x': point5_x,
                'p5y': point5_y,
                'log_file': log_file,
                'save_info': save_info,
                'points': points,
                'update_config' : update_config,
                'safety_check': safety_check}
    def _probe(self, gcmd, speed=None, dist_z=None):
        params = self.get_probe_params(gcmd)
        toolhead = self.printer.lookup_object('toolhead')
        curtime = self.printer.get_reactor().monotonic()
        if params['safety_check']:
            if 'z' not in toolhead.get_status(curtime)['homed_axes']:
                raise self.printer.command_error('{"coded": "0003-0530-0000-0002", "msg":"Must home before probe"}')
            result, capture_freq = self.mcu_probe.sensor.check_coil_freq()
            if result != True:
                index = {"extruder": 0, "extruder1": 1, "extruder2": 2, "extruder3": 3}.get(self.mcu_probe.sensor._name, 0)
                code = 0 if capture_freq == 0 else 1
                msg = "%s inductance coil status error [freq: %d]" % (self.mcu_probe.sensor._name, capture_freq)
                message = '{"coded": "0003-0530-%4d-%4d", "oneshot": %d, "msg":"%s"}' % (index, code, 1, msg)
                raise gcmd.error(message)
            extruder = toolhead.get_extruder()
            activate_status = extruder.get_extruder_activate_status()
            retry_extruder_id = extruder.check_allow_retry_switch_extruder()
            grab_hall_sensor_type = None
            if hasattr(extruder, 'grab_hall_sensor_type') and extruder.grab_hall_sensor_type:
                grab_hall_sensor_type = extruder.grab_hall_sensor_type
            if activate_status[0][1] != 0 and retry_extruder_id is None:
                if grab_hall_sensor_type and activate_status[0][1] == 1:
                    error_msg = f"Probing abort: No extruder is picked up, all extruders are parked."
                    message = '{"coded": "0003-0530-0000-0013", "msg":"%s"}' % (error_msg)
                    raise gcmd.error(message)

                result = extruder.analyze_switch_extruder_error(activate_status)
                if result:
                    error_msg, activated, unknown, grip_states, activated_code, unknown_code = result
                    if grab_hall_sensor_type and "multi-act" not in error_msg:
                        grip_state = grip_states[unknown[0]]
                        message = None
                        if grip_state == 'FFF':
                            info = "Probing abort: detected that extruder%d is detached. %s" % (unknown[0], error_msg)
                            message = '{"coded": "0003-0530-%4d-0014", "oneshot": %d, "msg":"%s"}' % (unknown[0], 1, info)
                        elif grip_state == 'FFT':
                            info = "Probing abort: detected that extruder%d pogopin not connected. %s" % (unknown[0], error_msg)
                            message = '{"coded": "0003-0530-%4d-0015", "oneshot": %d, "msg":"%s"}' % (unknown[0], 1, info)
                        elif (grip_state == 'TTF' or grip_state == 'TTT'):
                            info = "Probing abort: detected conflicting status for extruder%d: both parked and picked states detected. %s" % (unknown[0], error_msg)
                            message = '{"coded": "0003-0530-%4d-0016", "oneshot": %d, "msg":"%s"}' % (unknown[0], 1, info)
                        if message is not None:
                            raise gcmd.error(message)
                else:
                    error_msg = activate_status
                error_msg = f"Probing abort: Extruder parking status error, {error_msg}"
                message = '{"coded": "0003-0530-0000-0004", "msg":"%s"}' % (error_msg)
                raise gcmd.error(message)
            if extruder.name != activate_status[0][0] and retry_extruder_id != extruder.extruder_num:
                error_msg = f"The extruder activation status does not match, current: {extruder.name}, detected: {activate_status[0][0]}"
                message = '{"coded": "0003-0530-0000-0005", "msg":"%s"}' % (error_msg)
                raise gcmd.error(message)
            if extruder.binding_probe is not None and extruder.binding_probe != self.mcu_probe:
                message = '{"coded": "0003-0530-0000-0006", "msg":"%s"}' % ("The extruder binding mcu probe does not match")
                raise gcmd.error(message)
        pos = toolhead.get_position()
        if params['samples_axis'] == AXIS_Z_INDEX:
            # The z-axis can only probe in the direction of the hot bed.
            if dist_z is not None:
                pos[2] += params['samples_dir'] * dist_z
            else:
                pos[2] = self.z_position
        elif params['samples_axis'] == AXIS_X_INDEX:
            # The detection range of the x-axis is not initialized, and x-axis detection is not supported.
            if self.x_min_position == 0 and self.x_max_position == 0:
                raise self.printer.command_error("The detection range of the x-axis is not initialized, and x-axis detection is not supported")
            pos[AXIS_X_INDEX] = max(self.x_min_position, min(self.x_max_position, pos[AXIS_X_INDEX] + params['samples_dir'] * params['sample_dist']))
        elif params['samples_axis'] == AXIS_Y_INDEX:
            # The detection range of the y-axis is not initialized, and y-axis detection is not supported.
            if self.y_min_position == 0 and self.y_max_position == 0:
                raise self.printer.command_error("The detection range of the y-axis is not initialized, and y-axis detection is not supported")
            pos[AXIS_Y_INDEX] = max(self.y_min_position, min(self.y_max_position, pos[AXIS_Y_INDEX] + params['samples_dir'] * params['sample_dist']))
        else:
            message = '{"coded": "0003-0530-0000-0007", "msg":"%s"}' % ("Unsupported probe axis")
            raise self.printer.command_error(message)
            # raise self.printer.command_error("Unsupported probe axis")

        if params['sample_trig_freq_config']:
            if params['samples_axis'] == AXIS_Z_INDEX:
                new_freq = params['sample_trig_freq']
            else:
                new_freq = params['sample_trig_freq_y']
            if params['sample_wait_before_setup'] != 0 or params['sample_wait_after_setup'] != 0:
                toolhead.wait_moves()
                # toolhead = self.printer.lookup_object('toolhead')
                if params['sample_wait_before_setup'] != 0:
                    toolhead.dwell(params['sample_wait_before_setup'])
                    toolhead.wait_moves()
                self.mcu_probe.sensor._cmd_set_trig_freq(abs(new_freq), -abs(new_freq), params['sample_absolute_trig'],
                                                params['sample_trig_mode'], params['sample_trig_invert'])
                if params['sample_wait_after_setup'] != 0:
                    toolhead.dwell(params['sample_wait_after_setup'])
                    toolhead.wait_moves()
            else:
                toolhead.flush_step_generation()
                clock = self.mcu_probe.sensor._mcu.print_time_to_clock(toolhead.print_time)
                self.mcu_probe.sensor._cmd_set_trig_freq_with_timer(
                    abs(new_freq), -abs(new_freq), clock,
                    params['sample_absolute_trig'],
                    params['sample_trig_mode'],
                    params['sample_trig_invert']
                )
        max_accel_bak = toolhead.max_accel
        z_accel = toolhead.kin.max_z_accel
        try:
            if speed is None:
                speed = params['probe_speed']
            if params['probe_accel'] != max_accel_bak:
                toolhead.set_accel(params['probe_accel'])
            toolhead.kin.max_z_accel = params['probe_z_accel']
            epos = self.mcu_probe.probing_move(pos, speed)
        except self.printer.command_error as e:
            reason = str(e)
            if "Timeout during endstop homing" in reason:
                reason += HINT_TIMEOUT
            raise self.printer.command_error(reason)
        finally:
            if toolhead.max_accel != max_accel_bak:
                toolhead.set_accel(max_accel_bak)
            toolhead.kin.max_z_accel = z_accel

        # Allow axis_twist_compensation to update results
        self.printer.send_event("probe:update_results", epos)
        # Report results
        gcode = self.printer.lookup_object('gcode')

        if params['samples_axis'] == AXIS_Z_INDEX:
            gcode.respond_info("probe at x: %.3f, y: %.3f is z=%.6f"
                            % (epos[0], epos[1], epos[2]))
        elif params['samples_axis'] == AXIS_X_INDEX:
            gcode.respond_info("probe at y: %.3f, z: %.3f is x=%.6f"
                            % (epos[1], epos[2], epos[0]))
        else:
            gcode.respond_info("probe at x: %.3f, z: %.3f is y=%.6f"
                % (epos[0], epos[2], epos[1]))
        return epos[:3]
    def run_probe(self, gcmd):
        if not self.multi_probe_pending:
            self._probe_state_error()
        params = self.get_probe_params(gcmd)
        toolhead = self.printer.lookup_object('toolhead')
        probe_positions = toolhead.get_position()[:3]
        retries = 0
        positions = []
        sample_count = params['samples']
        discard = params['samples_discard']
        # First fast probe if probe count is larger than 1
        if sample_count > 2:
            fast_speed = params.get('probe_fast_speed', params['probe_speed'] * 2.0)
            pos = self._probe(gcmd, fast_speed, params['sample_dist_z'])
            # Retract after fast probe
            probe_positions[params['samples_axis']] = pos[params['samples_axis']] + params['sample_retract_dist'] * params['samples_retract_dir']
            toolhead.manual_move(probe_positions, params['lift_speed'])
            sample_count -= 1
        sample_count += discard*2
        gcmd.respond_info(f'sample {sample_count}, discard {discard*2}')
        while len(positions) < sample_count:
            # Probe position
            pos = self._probe(gcmd, params['probe_speed'], params['sample_dist_z'])
            positions.append(pos)
            # Check samples tolerance
            z_positions = [p[params['samples_axis']] for p in positions]
            if max(z_positions)-min(z_positions) > params['samples_tolerance']:
                if retries >= params['samples_tolerance_retries']:
                    message = '{"coded": "0003-0530-%4d-0008", "msg":"%s"}' % (
                                params['samples_axis'], "Probe samples exceed samples_tolerance")
                    raise gcmd.error(message)
                    # raise gcmd.error("Probe samples exceed samples_tolerance")
                gcmd.respond_info("Probe samples exceed tolerance. Retrying...")
                retries += 1
                positions = []
            # Retract
            if len(positions) < sample_count:
                probe_positions[params['samples_axis']] = pos[params['samples_axis']] + params['sample_retract_dist'] * params['samples_retract_dir']
                toolhead.manual_move(probe_positions, params['lift_speed'])
        # check if need discard samples data
        if discard > 0:
            sorted_pos = sorted(positions, key=lambda positions: positions[params['samples_axis']])
            filter_pos = sorted_pos[discard: -discard]
        else:
            filter_pos = positions
        # save result for slow speed
        if params.get('log_file') != None:
            logdir = '/userdata/gcodes/calibration_data'
            if not os.path.exists(logdir):
                os.makedirs(logdir)
            content = ""
            for p in filter_pos:
                content += f'{p[0]:.6f}, {p[1]:.6f}, {p[2]:.6f}\n'
            content += ' , , \n'
            try:
                queuefile.async_append_file(f'{logdir}/{params["log_file"]}', content)
            except Exception as e:
                logging.exception(f"Failed to append to file {params['log_file']}: {e}")
        # Calculate result
        epos = calc_probe_z_average(filter_pos, params['samples_result'], params['samples_axis'])
        self.results.append(epos)
    def pull_probed_results(self):
        res = self.results
        self.results = []
        return res

# Helper to read the xyz probe offsets from the config
class ProbeOffsetsHelper:
    def __init__(self, config):
        self.x_offset = config.getfloat('x_offset', 0.)
        self.y_offset = config.getfloat('y_offset', 0.)
        self.z_offset = config.getfloat('z_offset')
    def get_offsets(self):
        return self.x_offset, self.y_offset, self.z_offset


######################################################################
# Tools for utilizing the probe
######################################################################

# Helper code that can probe a series of points and report the
# position at each point.
class ProbePointsHelper:
    def __init__(self, config, finalize_callback, default_points=None, probe_point_callback=None):
        self.printer = config.get_printer()
        self.finalize_callback = finalize_callback
        self.probe_point_callback = probe_point_callback
        self.probe_points = default_points
        self.name = config.get_name()
        self.gcode = self.printer.lookup_object('gcode')
        # Read config settings
        if default_points is None or config.get('points', None) is not None:
            self.probe_points = config.getlists('points', seps=(',', '\n'),
                                                parser=float, count=2)
        def_move_z = config.getfloat('horizontal_move_z', 5.)
        self.default_horizontal_move_z = def_move_z
        self.fast_horizontal_move_z = config.getfloat('fast_horizontal_move_z', None)
        self.speed = config.getfloat('speed', 50., above=0.)
        self.min_x_grid_size_for_fast_move = config.getint('min_x_grid_size_for_fast_move', 5, minval=1)
        self.min_y_grid_size_for_fast_move = config.getint('min_y_grid_size_for_fast_move', 5, minval=1)
        self.use_offsets = False
        # Internal probing state
        self.lift_speed = self.speed
        self.probe_offsets = (0., 0., 0.)
        self.manual_results = []
        self.allow_fast_horizontal_move = True
        gcode_macro = self.printer.load_object(config, 'gcode_macro')
        self.first_raise_tool_gcode = gcode_macro.load_template(
            config, 'first_raise_tool_gcode', '')
    def minimum_points(self,n):
        if len(self.probe_points) < n:
            raise self.printer.config_error(
                "Need at least %d probe points for %s" % (n, self.name))
    def update_probe_points(self, points, min_points):
        self.probe_points = points
        self.minimum_points(min_points)
        bed_mesh = self.printer.lookup_object('bed_mesh', None)
        if bed_mesh is not None:
            mesh_config = bed_mesh.bmc.mesh_config
            x_count = mesh_config.get('x_count', 0)
            y_count = mesh_config.get('y_count', 0)
            if x_count < self.min_x_grid_size_for_fast_move or y_count < self.min_y_grid_size_for_fast_move:
                self.allow_fast_horizontal_move = False
            else:
                self.allow_fast_horizontal_move = True
    def use_xy_offsets(self, use_offsets):
        self.use_offsets = use_offsets
    def get_lift_speed(self):
        return self.lift_speed
    def _move(self, coord, speed):
        self.printer.lookup_object('toolhead').manual_move(coord, speed)
    def _raise_tool(self, is_first=False, horizontal_move_z=None):
        speed = self.lift_speed
        if is_first:
            # Use full speed to first probe position
            speed = self.speed
        h_move_z = self.horizontal_move_z
        if horizontal_move_z is not None:
            h_move_z = horizontal_move_z
        self._move([None, None, h_move_z], speed)
    def _invoke_callback(self, results):
        # Flush lookahead queue
        toolhead = self.printer.lookup_object('toolhead')
        toolhead.get_last_move_time()
        # Invoke callback
        res = self.finalize_callback(self.probe_offsets, results)
        return res != "retry"
    def _move_next(self, probe_num):
        # Move to next XY probe point
        nextpos = list(self.probe_points[probe_num])
        if self.use_offsets:
            nextpos[0] -= self.probe_offsets[0]
            nextpos[1] -= self.probe_offsets[1]
        self._move(nextpos, self.speed)
    def start_probe(self, gcmd):
        toolhead = self.printer.lookup_object('toolhead')
        manual_probe.verify_no_manual_probe(self.printer)
        # Lookup objects
        probe = self.printer.lookup_object('probe', None)
        method = gcmd.get('METHOD', 'automatic').lower()
        def_move_z = self.default_horizontal_move_z
        self.horizontal_move_z = gcmd.get_float('HORIZONTAL_MOVE_Z',
                                                def_move_z)
        fast_horizontal_move_z = gcmd.get_float('FAST_HORIZONTAL_MOVE_Z', self.fast_horizontal_move_z)
        if probe is None or method == 'manual':
            # Manual probe
            self.lift_speed = self.speed
            self.probe_offsets = (0., 0., 0.)
            self.manual_results = []
            self._manual_probe_start()
            return
        # Perform automatic probing
        self.lift_speed = probe.get_probe_params(gcmd)['lift_speed']
        self.probe_offsets = probe.get_offsets()
        probe_z_offset = gcmd.get_float("Z_OFFSET", None)
        if probe_z_offset is not None:
            self.probe_offsets = (self.probe_offsets[0],
                                  self.probe_offsets[1],
                                  probe_z_offset)
        gcmd.respond_info("z offset: %s" % (self.probe_offsets[2],))
        if self.horizontal_move_z < self.probe_offsets[2]:
            raise gcmd.error("horizontal_move_z can't be less than"
                             " probe's z_offset")
        probe_session = probe.start_probe_session(gcmd)
        probe_num = 0
        try:
            while 1:
                h_move_z = None
                if probe_num and fast_horizontal_move_z is not None and self.allow_fast_horizontal_move:
                    pos = toolhead.get_position()
                    h_move_z  = pos[2] + fast_horizontal_move_z
                    # gcmd.respond_info("pos[2]: %.5f, h_move_z: %.5f" % (pos[2], h_move_z))
                self._raise_tool(not probe_num, h_move_z)
                if probe_num >= len(self.probe_points):
                    results = probe_session.pull_probed_results()
                    done = self._invoke_callback(results)
                    if done:
                        break
                    # Caller wants a "retry" - restart probing
                    probe_num = 0
                self._move_next(probe_num)
                if not probe_num:
                    self.first_raise_tool_gcode.run_gcode_from_command()
                probe_session.run_probe(gcmd)
                probe_num += 1
                if self.probe_point_callback is not None:
                    self.probe_point_callback([probe_num, len(self.probe_points)])
        finally:
            self._raise_tool(True)
            if probe_session.multi_probe_pending:
                probe_session.end_probe_session()
    def _manual_probe_start(self):
        self._raise_tool(not self.manual_results)
        if len(self.manual_results) >= len(self.probe_points):
            done = self._invoke_callback(self.manual_results)
            if done:
                return
            # Caller wants a "retry" - clear results and restart probing
            self.manual_results = []
        self._move_next(len(self.manual_results))
        gcmd = self.gcode.create_gcode_command("", "", {})
        manual_probe.ManualProbeHelper(self.printer, gcmd,
                                       self._manual_probe_finalize)
    def _manual_probe_finalize(self, kin_pos):
        if kin_pos is None:
            return
        self.manual_results.append(kin_pos)
        self._manual_probe_start()

# Helper to obtain a single probe measurement
def run_single_probe(probe, gcmd):
    try:
        probe_session = probe.start_probe_session(gcmd)
        probe_session.run_probe(gcmd)
        pos = probe_session.pull_probed_results()[0]
        return pos
    finally:
        probe_session.end_probe_session()

######################################################################
# Handle [probe] config
######################################################################

# Endstop wrapper that enables probe specific features
class ProbeEndstopWrapper:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.position_endstop = config.getfloat('z_offset')
        self.stow_on_each_sample = config.getboolean(
            'deactivate_on_each_sample', True)
        gcode_macro = self.printer.load_object(config, 'gcode_macro')
        self.activate_gcode = gcode_macro.load_template(
            config, 'activate_gcode', '')
        self.deactivate_gcode = gcode_macro.load_template(
            config, 'deactivate_gcode', '')
        # Create an "endstop" object to handle the probe pin
        ppins = self.printer.lookup_object('pins')
        self.mcu_endstop = ppins.setup_pin('endstop', config.get('pin'))
        # Wrappers
        self.get_mcu = self.mcu_endstop.get_mcu
        self.add_stepper = self.mcu_endstop.add_stepper
        self.get_steppers = self.mcu_endstop.get_steppers
        self.home_start = self.mcu_endstop.home_start
        self.home_wait = self.mcu_endstop.home_wait
        self.query_endstop = self.mcu_endstop.query_endstop
        # multi probes state
        self.multi = 'OFF'
    def _raise_probe(self):
        toolhead = self.printer.lookup_object('toolhead')
        start_pos = toolhead.get_position()
        self.deactivate_gcode.run_gcode_from_command()
        if toolhead.get_position()[:3] != start_pos[:3]:
            raise self.printer.command_error(
                "Toolhead moved during probe deactivate_gcode script")
    def _lower_probe(self):
        toolhead = self.printer.lookup_object('toolhead')
        start_pos = toolhead.get_position()
        self.activate_gcode.run_gcode_from_command()
        if toolhead.get_position()[:3] != start_pos[:3]:
            raise self.printer.command_error(
                "Toolhead moved during probe activate_gcode script")
    def multi_probe_begin(self):
        if self.stow_on_each_sample:
            return
        self.multi = 'FIRST'
    def multi_probe_end(self):
        if self.stow_on_each_sample:
            return
        self._raise_probe()
        self.multi = 'OFF'
    def probing_move(self, pos, speed):
        phoming = self.printer.lookup_object('homing')
        return phoming.probing_coil_move(self, pos, speed)
    def probe_prepare(self, hmove):
        if self.multi == 'OFF' or self.multi == 'FIRST':
            self._lower_probe()
            if self.multi == 'FIRST':
                self.multi = 'ON'
    def probe_finish(self, hmove):
        if self.multi == 'OFF':
            self._raise_probe()
    def get_position_endstop(self):
        return self.position_endstop

class ExtruderOffsetCalibration:
    extruder_mapping = {
        'T0': 'extruder',
        'T1': 'extruder1',
        'T2': 'extruder2',
        'T3': 'extruder3',
    }

    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')
        self.machine_state_manager = self.printer.lookup_object('machine_state_manager', None)
        self.lock = self.printer.get_reactor().mutex()
        start_args = self.printer.get_start_args()
        self.factory_mode = start_args.get('factory_mode', False)
        self.calibration_step = 'idle'
        self.bed_plate_check = False
        self.is_prehoming = False
        self.status = None
        self.manual_clean_nozzle_status = {
            'extruder': False,
            'extruder1': False,
            'extruder2': False,
            'extruder3': False,
        }
        self.last_xyz_result = {
            'extruder':  None,
            'extruder1': None,
            'extruder2': None,
            'extruder3': None,
        }

        # Register G-code commands
        self.gcode.register_command(
            "EXTRUDER_OFFSET_ACTION_PRESTART",
            self.cmd_EXTRUDER_OFFSET_ACTION_PRESTART)
        self.gcode.register_command(
            "EXTRUDER_OFFSET_ACTION_PREHOMING",
            self.cmd_EXTRUDER_OFFSET_ACTION_PREHOMING)
        self.gcode.register_command(
            "EXTRUDER_OFFSET_ACTION_DETECT_PLATE",
            self.cmd_EXTRUDER_OFFSET_ACTION_DETECT_PLATE)
        self.gcode.register_command(
            "EXTRUDER_OFFSET_ACTION_PREHEAT",
            self.cmd_EXTRUDER_OFFSET_ACTION_PREHEAT)
        self.gcode.register_command(
            "EXTRUDER_OFFSET_ACTION_MANUAL_CLEAN",
            self.cmd_EXTRUDER_OFFSET_ACTION_MANUAL_CLEAN)
        self.gcode.register_command(
            "EXTRUDER_OFFSET_ACTION_HEAT",
            self.cmd_EXTRUDER_OFFSET_ACTION_HEAT)
        self.gcode.register_command(
            "EXTRUDER_OFFSET_ACTION_AUTO_CLEAN",
            self.cmd_EXTRUDER_OFFSET_ACTION_AUTO_CLEAN)
        self.gcode.register_command(
            "EXTRUDER_OFFSET_ACTION_WAIT_COOL",
            self.cmd_EXTRUDER_OFFSET_ACTION_WAIT_COOL)
        self.gcode.register_command(
            "EXTRUDER_OFFSET_ACTION_CHECK_TARGET_TEMP",
            self.cmd_EXTRUDER_OFFSET_ACTION_CHECK_TARGET_TEMP)
        self.gcode.register_command(
            "EXTRUDER_OFFSET_ACTION_PROBE_CALIBRATE",
            self.cmd_EXTRUDER_OFFSET_ACTION_PROBE_CALIBRATE)
        self.gcode.register_command(
            "EXTRUDER_OFFSET_ACTION_SAVE_RESULT",
            self.cmd_EXTRUDER_OFFSET_ACTION_SAVE_RESULT)
        self.gcode.register_command(
            "EXTRUDER_OFFSET_ACTION_EXIT",
            self.cmd_EXTRUDER_OFFSET_ACTION_EXIT)
        self.gcode.register_command(
            "EXTRUDER_OFFSET_ACTION_GET_STATUS",
            self.cmd_EXTRUDER_OFFSET_ACTION_GET_STATUS)

        self.gcode.register_command("DETECT_BED_PLATE", self.cmd_DETECT_PLATE)
        self.printer.register_event_handler("stepper_enable:motor_off", self._motor_off)
        self.printer.register_event_handler("klippy:ready", self._handle_ready)

        # Register abork webhooks
        webhooks = self.printer.lookup_object('webhooks')
        webhooks.register_endpoint(
            "extruder_offset_calibration/probe_abort", self._probe_xyz_offset_abort
        )

    def get_status(self, eventtime):
        sts = {
            'calibration_step': self.calibration_step,
            'bed_plate_check': self.bed_plate_check,
            'is_prehoming': self.is_prehoming,
        }
        last_xyz_result = {f"{key}_last_xyz_result": value for key, value in self.last_xyz_result.items()}
        manual_clean_nozzle = {f"{key}_nozzle_clean": value for key, value in self.manual_clean_nozzle_status.items()}
        sts.update(last_xyz_result)
        sts.update(manual_clean_nozzle)
        return sts

    def reset_xyz_probe_positions(self):
        for extruder in self.last_xyz_result.keys():
            self.last_xyz_result[extruder] = None

    def reset_manual_clean_nozzle_status(self):
        for extruder in self.manual_clean_nozzle_status.keys():
            self.manual_clean_nozzle_status[extruder] = False
    def _motor_off(self, print_time):
        with self.lock:
            self._cleanup_resources()

    def _handle_ready(self):
        self.machine_state_manager = self.printer.lookup_object('machine_state_manager', None)

    def _cleanup_resources(self):
        self.bed_plate_check = False
        self.is_prehoming = False
        self.reset_xyz_probe_positions()
        self.reset_manual_clean_nozzle_status()

    def _verify_calibration_state(self, operation=None):
        if (self.machine_state_manager and
            str(self.machine_state_manager.get_status()['main_state']) != "XYZ_OFFSET_CALIBRATE"):
            if operation:
                message = '{"coded": "0003-0530-0000-0009", "msg":"%s"}' % (
                            f"Operation '{operation}' requires XYZ_OFFSET_CALIBRATE main state")
                raise self.printer.command_error(message)
                # raise self.printer.command_error(
                #     f"Operation '{operation}' requires XYZ_OFFSET_CALIBRATE main state")
            else:
                message = '{"coded": "0003-0530-0000-0009", "msg":"%s"}' % (
                            "Current main state is not XYZ_OFFSET_CALIBRATE")
                raise self.printer.command_error(message)
    def _probe_xyz_offset_abort(self, web_request):
        try:
            self.printer.send_event("probe_xyz_offset:abort")
            web_request.send({'state': 'success'})
        except Exception as e:
            logging.error(f'failed to abort probe xyz_offset: {str(e)}')
            web_request.send({'state': 'error', 'message': str(e)})

    def _get_filament_temp(self, extruder):
        print_task_config = self.printer.lookup_object('print_task_config', None)
        filament_parameters = self.printer.lookup_object('filament_parameters', None)
        extruder_obj = self.printer.lookup_object(f'extruder', None)
        if extruder is not None and extruder != 0:
            extruder_obj = self.printer.lookup_object(f'extruder{extruder}', None)
        if print_task_config is None or filament_parameters is None or extruder_obj is None:
            return 200

        status = print_task_config.get_status()
        temp = filament_parameters.get_print_temp(
                status['filament_vendor'][extruder],
                status['filament_type'][extruder],
                status['filament_sub_type'][extruder],
                extruder_obj.nozzle_diameter,
                extruder_obj.nozzle_volume_type)
        return temp - 20

    def _get_filament_soft(self, extruder):
        print_task_config = self.printer.lookup_object('print_task_config', None)
        filament_parameters = self.printer.lookup_object('filament_parameters', None)
        extruder_obj = self.printer.lookup_object(f'extruder', None)
        if extruder != 0:
            extruder_obj = self.printer.lookup_object(f'extruder{extruder}', None)
        if print_task_config is None or filament_parameters is None or extruder_obj is None:
            return False

        status = print_task_config.get_status()
        return filament_parameters.get_is_soft(
                status['filament_vendor'][extruder],
                status['filament_type'][extruder],
                status['filament_sub_type'][extruder],
                extruder_obj.nozzle_diameter,
                extruder_obj.nozzle_volume_type)

    def cmd_EXTRUDER_OFFSET_ACTION_GET_STATUS(self, gcmd):
        gcmd.respond_info("{}".format(self.get_status(0)))

    def cmd_EXTRUDER_OFFSET_ACTION_PRESTART(self, gcmd):
        # State validation
        # TODO：
        # if self.calibration_step != 'idle':
        #     raise gcmd.error(f"Cannot start calibration in {self.calibration_step}")

        try:
            # TODO Hardware readiness check
            # if not self._check_hardware_ready():
            #     raise gcmd.error("Hardware not ready for calibration")
            self.gcode.run_script_from_command("SET_MAIN_STATE MAIN_STATE=XYZ_OFFSET_CALIBRATE")
            with self.lock:
                self.calibration_step = 'ready'
                self._cleanup_resources()

            macro = self.printer.lookup_object('gcode_macro _EXTRUDER_OFFSET_ACTION_PRESTART', None)
            if macro:
                self.gcode.run_script_from_command("_EXTRUDER_OFFSET_ACTION_PRESTART")

        except Exception as e:
            # with self.lock:
            #     self.calibration_step = 'error'
            raise gcmd.error(str(e))
        finally:
            pass

    def cmd_EXTRUDER_OFFSET_ACTION_PREHOMING(self, gcmd):
        # if self.calibration_step != 'ready':
        #     raise gcmd.error("Calibration in progress, cannot perform homing")
        self._verify_calibration_state("EXTRUDER_OFFSET_ACTION_PREHOMING")
        try:
            with self.lock:
                # Set state to prehoming
                self.calibration_step = 'prehoming'
                self.is_prehoming = False

            default_force_homing = True
            macro = self.printer.lookup_object('gcode_macro _EXTRUDER_OFFSET_ACTION_PREHOMING', None)
            if macro is not None:
                default_force_homing = macro.variables.get('force_homing', True)

            self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=HOMING")
            # Get force homing parameter
            force_homing = gcmd.get_int('FORCE_HOMING', default_force_homing)
            curtime = self.printer.get_reactor().monotonic()
            homed_axes_list = self.printer.lookup_object('toolhead').get_status(curtime)['homed_axes']
            if force_homing or homed_axes_list != "xyz":
                self.gcode.run_script_from_command("G28 SAMPLES_TOLERANCE 0.1")
            self.gcode.run_script_from_command("_EXTRUDER_OFFSET_ACTION_PREHOMING")

            # # Update state to prehoming_done
            with self.lock:
                self.calibration_step = 'prehoming_done'
                self.is_prehoming = True

        except Exception as e:
            # Handle error
            with self.lock:
                self.calibration_step = 'prehoming_error'
            raise gcmd.error(str(e))

        finally:
            self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=IDLE")

    def cmd_DETECT_PLATE(self, gcmd):
        HOLE_POSITION = [30, 134, 3]
        SOLID_POSITION = [30, 100, 3]
        MOVE_SPEED = 200
        CHECK_OK_LIFT_Z = 5
        CHECK_FAIL_LIFT_Z = 150
        toolhead = self.printer.lookup_object('toolhead')
        try:
            # with self.lock:
            #     self.calibration_step = 'plate_detecting'
            self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=DETECT_PLATE")
            presence = gcmd.get_int('PRESENCE', 1)
            hole_position =  copy.deepcopy(HOLE_POSITION)
            solid_position =  copy.deepcopy(SOLID_POSITION)
            solid_x, solid_y, solid_z = solid_position
            hole_x, hole_y, hole_z = hole_position
            default_delta_z = 1
            default_move_speed = MOVE_SPEED
            default_check_ok_lift_z = CHECK_OK_LIFT_Z
            default_check_fail_lift_z = CHECK_FAIL_LIFT_Z
            macro = self.printer.lookup_object('gcode_macro _DETECT_PLATE', None)
            if macro is not None:
                hole_position = [
                    macro.variables.get('hole_x', hole_x),
                    macro.variables.get('hole_y', hole_y),
                    macro.variables.get('hole_z', hole_x)
                ]
                solid_position = [
                    macro.variables.get('solid_x', solid_x),
                    macro.variables.get('solid_y', solid_y),
                    macro.variables.get('solid_z', solid_z)
                ]
                default_delta_z = macro.variables.get('delta_z', default_delta_z)
                default_move_speed = macro.variables.get('move_speed', MOVE_SPEED)
                default_check_ok_lift_z = macro.variables.get('check_ok_lift_z', CHECK_OK_LIFT_Z)
                default_check_fail_lift_z = macro.variables.get('check_fail_lift_z', CHECK_FAIL_LIFT_Z)
            gcmd.respond_info("hole_position: {}, solid_position: {}".format(hole_position, solid_position))
            toolhead.wait_moves()
            default_check_ok_lift_z = gcmd.get_int('CHECK_OK_LIFT_Z', default_check_ok_lift_z)
            default_check_fail_lift_z = gcmd.get_int('CHECK_FAIL_LIFT_Z', default_check_fail_lift_z)
            default_delta_z = gcmd.get_int('DELTA_Z', default_delta_z)
            safe_move_y_pos = gcmd.get_float('SAFE_MOVE_Y_POS', 250, minval=0.)
            pos = toolhead.get_position()
            self.printer.send_event("inductance_coil:probe_start")
            toolhead.manual_move([None, None, solid_position[2]], default_move_speed)
            if pos[1] > safe_move_y_pos:
                toolhead.manual_move([None, safe_move_y_pos, None], 200)
            toolhead.manual_move([solid_position[0], solid_position[1], None], default_move_speed)
            if macro is not None:
                self.gcode.run_script_from_command("_DETECT_PLATE")
            else:
                self.gcode.run_script_from_command("PROBE SAMPLES=2 SAMPLES_TOLERANCE=0.1")
            solid_z = self.printer.lookup_object('probe').get_status(0)['last_z_result']
            toolhead.manual_move([None, None, hole_position[2]], default_move_speed)
            toolhead.manual_move([hole_position[0], hole_position[1], None], default_move_speed)
            if macro is not None:
                self.gcode.run_script_from_command("_DETECT_PLATE")
            else:
                self.gcode.run_script_from_command("PROBE SAMPLES=2 SAMPLES_TOLERANCE=0.1")
            hole_z = self.printer.lookup_object('probe').get_status(0)['last_z_result']
            if presence:
                if abs(solid_z - hole_z) >= default_delta_z:
                    message = '{"coded": "0003-0530-0000-0010", "msg":"%s"}' % ("The plate has been removed")
                    raise gcmd.error(message)
                    # raise gcmd.error("The plate has been removed.")
            else:
                if abs(solid_z - hole_z) <= default_delta_z:
                    message = '{"coded": "0003-0530-0000-0011", "msg":"%s"}' % ("The plate has not been removed")
                    raise gcmd.error(message)
                    # raise gcmd.error("The plate has not been removed.")
            toolhead.manual_move([None, None, default_check_ok_lift_z], default_move_speed)
            # with self.lock:
            #     self.calibration_step = 'plate_detected'
            #     self.bed_plate_check = True
        except Exception as e:
            # with self.lock:
            #     self.calibration_step = 'plate_detection_error'
            try:
                toolhead.manual_move([None, None, default_check_fail_lift_z], default_move_speed)
            except:
                pass

            raise gcmd.error(str(e))
        finally:
            self.printer.send_event("inductance_coil:probe_end")
            self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=IDLE")

    def cmd_EXTRUDER_OFFSET_ACTION_DETECT_PLATE(self, gcmd):
        try:
            with self.lock:
                self.calibration_step = 'plate_detecting'
                self.bed_plate_check = False
            self.cmd_DETECT_PLATE(gcmd)
            with self.lock:
                self.calibration_step = 'plate_detected'
                self.bed_plate_check = True
        except Exception as e:
            with self.lock:
                self.calibration_step = 'plate_detection_error'
            raise
        finally:
            pass

    def cmd_EXTRUDER_OFFSET_ACTION_PREHEAT(self, gcmd):
        try:
            # with self.lock:
            #     self.calibration_step = 'preheat'
            #     self.error_message = None
            params = {}
            bed_temp = gcmd.get_int('BED_TEMP', None)
            if bed_temp is not None:
                params['BED_TEMP'] = bed_temp

            for tool_id in range(4):
                key = f"T{tool_id}_TEMP"
                value = gcmd.get_int(key, None)
                if value is not None:
                    params[key] = value

            args = []
            if 'BED_TEMP' in params:
                args.append(f"BED_TEMP={params['BED_TEMP']}")

            for tool_id in range(4):
                key = f"T{tool_id}_TEMP"
                if key in params:
                    args.append(f"{key}={params[key]}")

            macro = self.printer.lookup_object('gcode_macro _EXTRUDER_OFFSET_ACTION_PREHEAT', None)
            if macro is not None:
                gcode_script = "_EXTRUDER_OFFSET_ACTION_PREHEAT"
                if args:
                    gcode_script += " " + " ".join(args)
                self.gcode.run_script_from_command(gcode_script)
        except Exception as e:
            # with self.lock:
            #     self.calibration_step = 'idle'
            #     self.error_message = str(e)
            raise gcmd.error(str(e))
        finally:
            pass

    def cmd_EXTRUDER_OFFSET_ACTION_MANUAL_CLEAN(self, gcmd):
        self._verify_calibration_state("EXTRUDER_OFFSET_ACTION_MANUAL_CLEAN")
        try:
            tool_id = gcmd.get('TOOL_ID', None)
            if tool_id is None:
                raise gcmd.error('EXTRUDER_OFFSET_ACTION_MANUAL_CLEAN: TOOL_ID is required')
            extruder = self.extruder_mapping.get(tool_id)
            if extruder is not None:
                with self.lock:
                    self.calibration_step = '{}_nozzle_clean'.format(extruder)
                self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=MANUAL_CLEAN_{}".format(extruder.upper()))

            macro = self.printer.lookup_object('gcode_macro _EXTRUDER_OFFSET_ACTION_MANUAL_CLEAN_{}'.format(tool_id), None)
            if macro is not None:
                self.gcode.run_script_from_command("_EXTRUDER_OFFSET_ACTION_MANUAL_CLEAN_{}".format(tool_id))

            if extruder is not None:
                with self.lock:
                    self.manual_clean_nozzle_status[extruder] = True

        except Exception as e:
            # with self.lock:
            #     self.calibration_step = 'idle'
            #     self.error_message = str(e)
            raise gcmd.error(str(e))
        finally:
            pass

    def cmd_EXTRUDER_OFFSET_ACTION_HEAT(self, gcmd):
        self._verify_calibration_state("EXTRUDER_OFFSET_ACTION_HEAT")
        try:
            tool_id = gcmd.get('TOOL_ID', None)
            if tool_id is None:
                raise gcmd.error('EXTRUDER_OFFSET_ACTION_HEAT: TOOL_ID is required')

            extruder = self.extruder_mapping.get(tool_id, None)
            if extruder is None:
                supported_tools = list(self.extruder_mapping.keys())
                raise gcmd.error(f'EXTRUDER_OFFSET_ACTION_HEAT: Unsupported TOOL_ID={tool_id}. Supported IDs: {supported_tools}')

            extruder_index = None
            heat_temp = 200
            if tool_id is not None:
                extruder_index = int(tool_id[1:])
                heat_temp = gcmd.get_float('HEAT_TEMP', self._get_filament_temp(extruder_index), minval=0.)

            with self.lock:
                self.calibration_step = '{}_heating'.format(extruder)

            macro = self.printer.lookup_object('gcode_macro _EXTRUDER_OFFSET_ACTION_HEAT_{}'.format(tool_id), None)
            if macro is not None:
                self.gcode.run_script_from_command("_EXTRUDER_OFFSET_ACTION_HEAT_{} HEAT_TEMP={}".format(tool_id, heat_temp))

            with self.lock:
                self.calibration_step = '{}_heated'.format(extruder)
        except Exception as e:
            with self.lock:
                self.calibration_step = 'heat_extruder_error'
            raise gcmd.error(str(e))

    def cmd_EXTRUDER_OFFSET_ACTION_AUTO_CLEAN(self, gcmd):
        self._verify_calibration_state("EXTRUDER_OFFSET_ACTION_AUTO_CLEAN")
        try:
            tool_id = gcmd.get('TOOL_ID', None)
            if tool_id is None:
                raise gcmd.error('EXTRUDER_OFFSET_ACTION_AUTO_CLEAN: TOOL_ID is required')

            extruder = self.extruder_mapping.get(tool_id, None)
            if extruder is None:
                supported_tools = list(self.extruder_mapping.keys())
                raise gcmd.error(f'EXTRUDER_OFFSET_ACTION_AUTO_CLEAN: Unsupported TOOL_ID={tool_id}. Supported IDs: {supported_tools}')

            extruder_obj = self.printer.lookup_object(extruder, None)
            if extruder_obj is None:
                raise gcmd.error(f'EXTRUDER_OFFSET_ACTION_AUTO_CLEAN: Can get extruder:{extruder}')

            with self.lock:
                self.calibration_step = '{}_nozzle_auto_cleaning'.format(extruder)

            self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=AUTO_CLEAN_NOZZLE")

            # not need
            # safe_move_y_pos = gcmd.get_float('SAFE_MOVE_Y_POS', None, minval=0.)
            # if safe_move_y_pos is not None:
            #     toolhead = self.printer.lookup_object('toolhead')
            #     toolhead.wait_moves()
            #     pos = toolhead.get_position()
            #     if pos[1] > safe_move_y_pos:
            #         toolhead.manual_move([None, safe_move_y_pos, None], 200)

            is_soft = int(self._get_filament_soft(extruder_obj.extruder_index))
            macro = self.printer.lookup_object('gcode_macro _EXTRUDER_OFFSET_ACTION_AUTO_CLEAN_{}'.format(tool_id), None)
            if macro is not None:
                self.gcode.run_script_from_command("_EXTRUDER_OFFSET_ACTION_AUTO_CLEAN_{} SOFT={} NOZZLE_DIAMETER={}".format(
                    tool_id, is_soft, extruder_obj.nozzle_diameter))

            with self.lock:
                self.calibration_step = '{}_nozzle_auto_cleaned'.format(extruder)
        except Exception as e:
            with self.lock:
                self.calibration_step = 'nozzle_auto_clean_failed'
            raise gcmd.error(str(e))
        finally:
            self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=IDLE")

    def cmd_EXTRUDER_OFFSET_ACTION_WAIT_COOL(self, gcmd):
        self._verify_calibration_state("EXTRUDER_OFFSET_ACTION_WAIT_COOL")
        try:
            tool_id = gcmd.get('TOOL_ID', None)
            if tool_id is None:
                raise gcmd.error('EXTRUDER_OFFSET_ACTION_WAIT_COOL: TOOL_ID is required')

            extruder = self.extruder_mapping.get(tool_id, None)
            if extruder is None:
                supported_tools = list(self.extruder_mapping.keys())
                raise gcmd.error(f'EXTRUDER_OFFSET_ACTION_WAIT_COOL: Unsupported TOOL_ID={tool_id}. Supported IDs: {supported_tools}')

            with self.lock:
                self.calibration_step = '{}_wait_cooling'.format(extruder)

            toolhead = self.printer.lookup_object('toolhead')
            toolhead.wait_moves()
            pos = toolhead.get_position()
            safe_move_y_pos = gcmd.get_float('SAFE_MOVE_Y_POS', 250, minval=0.)
            if pos[1] > safe_move_y_pos:
                toolhead.manual_move([None, safe_move_y_pos, None], 200)

            self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=WAIT_NOZZLE_COOLING")

            temp = gcmd.get_float('TEMP', 130, minval=0.)
            macro = self.printer.lookup_object('gcode_macro _EXTRUDER_OFFSET_ACTION_WAIT_COOL_{}'.format(tool_id), None)
            if macro is not None:
                self.gcode.run_script_from_command("_EXTRUDER_OFFSET_ACTION_WAIT_COOL_{} TEMP={}".format(tool_id, temp))

            with self.lock:
                self.calibration_step = '{}_wait_cooled'.format(extruder)
        except Exception as e:
            with self.lock:
                self.calibration_step = 'wait_cooling_failed'
            raise gcmd.error(str(e))
        finally:
            self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=IDLE")

    def cmd_EXTRUDER_OFFSET_ACTION_CHECK_TARGET_TEMP(self, gcmd):
        heater_type = gcmd.get('HEATER', 'all')
        extruder_range = gcmd.get_float('EXTRUDER_RANGE', 5.0)
        bed_range = gcmd.get_float('BED_RANGE', 1.5)

        expected_targets = {
            'heater_bed': gcmd.get_int('BED_TARGET', None),
            'extruder': gcmd.get_int('EXTRUDER_TARGET', None),
            'extruder1': gcmd.get_int('EXTRUDER1_TARGET', None),
            'extruder2': gcmd.get_int('EXTRUDER2_TARGET', None),
            'extruder3': gcmd.get_int('EXTRUDER3_TARGET', None)
        }

        heaters = {
            'heater_bed': 'heater_bed',
            'extruder': 'extruder',
            'extruder1': 'extruder1',
            'extruder2': 'extruder2',
            'extruder3': 'extruder3',
            'all': ['heater_bed', 'extruder', 'extruder1', 'extruder2', 'extruder3']
        }

        heater_names = heaters.get(heater_type.lower())
        if heater_names is None:
            raise gcmd.error("Unknown heater type: %s" % (heater_type,))

        if not isinstance(heater_names, list):
            heater_names = [heater_names]

        not_reached = []
        curtime = self.printer.get_reactor().monotonic()
        for name in heater_names:
            heater = self.printer.lookup_object(name, None)
            if heater is None:
                continue
            status = heater.get_status(curtime)
            expected_target = expected_targets.get(name)
            if expected_target is not None and status['target'] != expected_target:
                not_reached.append(f"{name} (expected target: {expected_target}, actual: {status['target']})")
                continue

            if status['target'] == 0:
                continue

            target_range = bed_range if name == 'heater_bed' else extruder_range
            if abs(status['temperature'] - status['target']) > target_range:
                not_reached.append(name)

        if not_reached:
            raise gcmd.error("Heaters not reached target temperature: %s" % (not_reached,))

    def cmd_EXTRUDER_OFFSET_ACTION_PROBE_CALIBRATE(self, gcmd):
        self._verify_calibration_state("EXTRUDER_OFFSET_ACTION_PROBE")
        try:
            # with self.lock:
            #     self.calibration_step = 'calibrating'
            #     self.error_message = None
            extruder = tool_id = None
            tool_id = gcmd.get('TOOL_ID', None)
            if tool_id == None:
                raise gcmd.error('EXTRUDER_OFFSET_ACTION_PROBE_CALIBRATE: TOOL_ID is required')

            extruder = self.extruder_mapping.get(tool_id, None)
            if extruder is None:
                supported_tools = list(self.extruder_mapping.keys())
                raise gcmd.error(f'EXTRUDER_OFFSET_ACTION_PROBE: Unsupported TOOL_ID={tool_id}. Supported IDs: {supported_tools}')

            self.gcode.run_script_from_command("SET_ACTION_CODE ACTION={}_XYZ_OFFSET_PROBE".format(
                                                extruder.upper()))

            toolhead = self.printer.lookup_object('toolhead')
            toolhead.wait_moves()
            pos = toolhead.get_position()
            safe_move_y_pos = gcmd.get_float('SAFE_MOVE_Y_POS', 250, minval=0.)
            if pos[1] > safe_move_y_pos:
                toolhead.manual_move([None, safe_move_y_pos, None], 200)

            macro = self.printer.lookup_object('gcode_macro _EXTRUDER_OFFSET_ACTION_PROBE_CALIBRATE_{}'.format(tool_id), None)
            if macro is not None:
                with self.lock:
                    self.calibration_step = '{}_calibrating'.format(extruder)

                self.gcode.run_script_from_command("_EXTRUDER_OFFSET_ACTION_PROBE_CALIBRATE_{}".format(tool_id))
                if extruder in self.last_xyz_result and self.last_xyz_result[extruder] is None:
                    with self.lock:
                        self.calibration_step = '{}_calibration_incomplete'.format(extruder)
                    return

                with self.lock:
                    completed = True
                    for position in self.last_xyz_result.values():
                        if position is None:
                            completed = False
                            break
                    if completed:
                        self.calibration_step = 'calibration_completed'
                    else:
                        self.calibration_step = '{}_calibration_done'.format(extruder)
                if self.calibration_step == 'calibration_completed':
                    self.gcode.run_script_from_command("EXTRUDER_OFFSET_ACTION_SAVE_RESULT FORCE_SAVE=0")
        except Exception as e:
            if extruder is not None:
                with self.lock:
                    self.calibration_step = 'calibration_err_{}'.format(extruder)
            raise gcmd.error(str(e))
        finally:
            self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=IDLE")

    def cmd_EXTRUDER_OFFSET_ACTION_SAVE_RESULT(self, gcmd):
        try:
            empty_extruders = []
            force_save = not not gcmd.get_int('FORCE_SAVE', 0)
            if not force_save:
                for extruder, position in self.last_xyz_result.items():
                    if position is None:
                        empty_extruders.append(extruder)

            if len(empty_extruders) != 0:
                raise gcmd.error('{} calibration detection not completed'.format(empty_extruders))

            need_save_cfg = False
            configfile = self.printer.lookup_object('configfile')
            extruder_list = self.printer.lookup_object('extruder_list', [])
            extruder_bak = self.printer.lookup_object('extruder_config_bak', None)
            for i in range(len(extruder_list)):
                if extruder_list[i].name in self.last_xyz_result and self.last_xyz_result[extruder_list[i].name] is not None:
                    extruder_list[i].base_position = self.last_xyz_result[extruder_list[i].name]
                    gcmd.respond_info("{} base_position: {}".format(extruder_list[i].name, extruder_list[i].base_position))
                    if extruder_bak is None or not os.path.exists(extruder_bak.base_position_config_path):
                        need_save_cfg = True
                        configfile.set(extruder_list[i].name, 'base_position',
                        "\n%.6f, %.6f, %.6f\n" % (extruder_list[i].base_position[0], extruder_list[i].base_position[1], extruder_list[i].base_position[2]))
                    else:
                        extruder_bak.update_extruder_config(extruder_list[i].name, "base_position", extruder_list[i].base_position)

            if need_save_cfg:
                self.printer.lookup_object('gcode').run_script_from_command("SAVE_CONFIG RESTART=0")
            self.printer.send_event("probe_inductance_coil: update_extruder_offset")

            if self.factory_mode and not force_save and extruder_list[0].base_position is not None:
                axis = ""
                is_offset_out_of_range = False

                for i in range(1, len(extruder_list)):
                    if extruder_list[i].base_position is not None:
                        if abs(extruder_list[i].base_position[0] - extruder_list[0].base_position[0]) > MAX_OFFSET_DELTA_X:
                            is_offset_out_of_range = True
                            if 'X' not in axis:
                                axis += "X"
                        if abs(extruder_list[i].base_position[1] - extruder_list[0].base_position[1]) > MAX_OFFSET_DELTA_Y:
                            is_offset_out_of_range = True
                            if 'Y' not in axis:
                                axis += "Y"
                        if abs(extruder_list[i].base_position[2] - extruder_list[0].base_position[2]) > MAX_OFFSET_DELTA_Z:
                            is_offset_out_of_range = True
                            if 'Z' not in axis:
                                axis += "Z"
                if is_offset_out_of_range:
                    msg = f"{axis} offset is out-of-range.\\n\\n"
                    if 'X' in axis:
                        msg += " X: "
                        for i in range(len(extruder_list)):
                            if extruder_list[i].base_position is not None:
                                msg += f"e{i}_{extruder_list[i].base_position[0]:.3f},  "
                        msg = msg[:-3]
                        msg += ".\\n"
                    if 'Y' in axis:
                        msg += " Y: "
                        for i in range(len(extruder_list)):
                            if extruder_list[i].base_position is not None:
                                msg += f"e{i}_{extruder_list[i].base_position[1]:.3f},  "
                        msg = msg[:-3]
                        msg += ".\\n"
                    if 'Z' in axis:
                        msg += " Z: "
                        for i in range(len(extruder_list)):
                            if extruder_list[i].base_position is not None:
                                msg += f"e{i}_{extruder_list[i].base_position[2]:.3f},  "
                        msg = msg[:-3]
                        msg += "."

                    message = '{"coded": "0003-0530-0000-0018", "oneshot": 1, "msg": "%s"}' % (msg)
                    raise gcmd.error(message)

            with self.lock:
                self.calibration_step = 'save_result_completed'
        except Exception as e:
            # with self.lock:
            #     self.calibration_step = 'calibration_save_result_err'
            raise gcmd.error(str(e))
        finally:
            pass

    def cmd_EXTRUDER_OFFSET_ACTION_EXIT(self, gcmd):
        self._verify_calibration_state("EXTRUDER_OFFSET_ACTION_EXIT")
        try:
            # with self.lock:
            #     self.calibration_step = 'exiting'
            #     self._cleanup_resources()
            macro = self.printer.lookup_object('gcode_macro _EXTRUDER_OFFSET_ACTION_EXIT', None)
            if macro:
                self.gcode.run_script_from_command("_EXTRUDER_OFFSET_ACTION_EXIT")
            # with self.lock:
            #     self.calibration_step = 'idle'
            #     self._cleanup_resources()
        except Exception as e:
            # with self.lock:
            #     self.calibration_step = 'error'
            raise gcmd.error(str(e))
        finally:
            with self.lock:
                self.calibration_step = 'idle'
                self._cleanup_resources()
            if (self.machine_state_manager and
                str(self.machine_state_manager.get_status()['main_state']) == "XYZ_OFFSET_CALIBRATE"):
                self.gcode.run_script_from_command("EXIT_TO_IDLE REQ_FROM_STATE=XYZ_OFFSET_CALIBRATE")

class PrinterProbe:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.mcu_probe = inductance_coil.InductanceCoilEndstopWrapper(config)
        self.cmd_helper = ProbeCommandHelper(config, self,
                                             self.mcu_probe.query_endstop)
        self.probe_offsets = ProbeOffsetsHelper(config)
        self.probe_session = ProbeSessionHelper(config, self.mcu_probe)

        if self.printer.lookup_object('extruder_offset_calibration', None) is None:
            self.printer.add_object('extruder_offset_calibration', ExtruderOffsetCalibration(config))
    def get_probe_params(self, gcmd=None):
        return self.probe_session.get_probe_params(gcmd)
    def get_offsets(self):
        return self.probe_offsets.get_offsets()
    def get_status(self, eventtime):
        return self.cmd_helper.get_status(eventtime)
    def start_probe_session(self, gcmd):
        return self.probe_session.start_probe_session(gcmd)
    def set_mcu_probe(self, new_probe):
        self.mcu_probe = new_probe
        self.cmd_helper.query_endstop = self.mcu_probe.query_endstop
        self.probe_session.mcu_probe = self.mcu_probe
        self.probe_session.homing_helper.mcu_probe = self.mcu_probe

# def load_config_prefix(config):
#     return PrinterProbe(config)
