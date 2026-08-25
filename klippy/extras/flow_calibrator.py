import logging, multiprocessing, os, time, pathlib, queuefile
from . import motion_report
import numpy as np
import json
import copy
import struct
import errno
import threading
import random

AERA_CALC_MODE_ORIGINAL                 = 0
AERA_CALC_MODE_OS                       = 1

# algorithm type
ALGORITHM_TYPE_DICHOTOMY                = 'DICHOTOMY'
ALGORITHM_TYPE_LINEAR_FITTING           = 'LINEAR_FITTING'
ALGORITHM_TYPE_OS_ACCEL                 = 'OS_ACCEL'
ALGORITHM_TYPE_OS_DECEL                 = 'OS_DECEL'
ALGORITHM_TYPE_OS_ACCEL_DECEL           = 'OS_ACCEL_DECEL'

# abort reason
ABORT_REASON_CANCEL_BY_USER             = 'cancel_by_user'
ABORT_REASON_FILAMENT_RUNOUT            = 'filament_runout'
ABORT_REASON_OUT_OF_RANGE               = 'out_of_range'
ABORT_REASON_FILAMENT_TANGLED           = 'filament_tangled'

class FlowCalcError(Exception):
    pass

class FlowCalcClient:
    REQ_PIPE = '/tmp/flow_calculator_req'
    RESP_PIPE = '/tmp/flow_calculator_resp'
    TIMEOUT = 30  # seconds

    def check_server(self):
        """Verify the flow calculator server is running."""
        if not os.path.exists(self.REQ_PIPE) or not os.path.exists(self.RESP_PIPE):
            raise FlowCalcError("Flow calculator server is not running: FIFO not found")
        try:
            fd = os.open(self.REQ_PIPE, os.O_WRONLY | os.O_NONBLOCK)
            os.close(fd)
        except OSError as e:
            if e.errno == errno.ENXIO:
                raise FlowCalcError("Flow calculator server is not running: no reader on FIFO")
            raise

    @staticmethod
    def _read_exact(fd, n):
        """Read exactly n bytes from fd."""
        data = b''
        while len(data) < n:
            chunk = os.read(fd, n - len(data))
            if not chunk:
                raise FlowCalcError("Connection closed by server")
            data += chunk
        return data

    @staticmethod
    def _write_request(fd, pt, freq, accel_time, loop, slowv, fastv, drop1, drop2,
                        calc_mode=0, calc_mode_params=None):
        """Write mixed-protocol request.

        total_length = len(header) + len(pt) + len(freq) + len(accel),
        i.e. the payload after the two prefix ints.
        """
        pt_len = len(pt)
        freq_len = len(freq)
        accel_len = len(accel_time)

        header = {
            'loop': loop, 'slowv': slowv, 'fastv': fastv,
            'drop1': drop1, 'drop2': drop2,
            'pt_len': pt_len, 'freq_len': freq_len, 'accel_len': accel_len,
            'calc_mode': calc_mode,
        }
        if calc_mode == AERA_CALC_MODE_OS:
            try:
                header['os_count'] = int(calc_mode_params['os_count'])
            except Exception:
                logging.error(f"Invalid calc_mode_params: {calc_mode_params}\r\n")
                header['os_count'] = 5

        logging.info(f"[flow_calibrator] Sending request: {header}")

        header_bytes = json.dumps(header).encode('utf-8')

        pt_bytes = np.array(pt, dtype='<f8').tobytes()
        freq_bytes = np.array(freq, dtype='<i8').tobytes()
        flat_accel = [v for tup in accel_time for v in tup]
        accel_bytes = np.array(flat_accel, dtype='<f8').tobytes()

        total_length = len(header_bytes) + len(pt_bytes) + len(freq_bytes) + len(accel_bytes)

        os.write(fd, struct.pack('<II', total_length, len(header_bytes)))
        os.write(fd, header_bytes)
        os.write(fd, pt_bytes)
        os.write(fd, freq_bytes)
        os.write(fd, accel_bytes)

    @staticmethod
    def _read_response(fd):
        """Read response: [total_len(4B)] [JSON payload]"""
        header = FlowCalcClient._read_exact(fd, 4)
        length = struct.unpack('<I', header)[0]
        data = FlowCalcClient._read_exact(fd, length)
        return json.loads(data.decode('utf-8'))

    def calc_flow_factor(self, pt, freq, accel_time, loop, slowv, fastv,
                          drop1, drop2, calc_mode=0, calc_mode_params=None):
        """Send calculation request via pipe and return result."""
        result = [None]
        error = [None]

        def _do_io():
            try:
                req_fd = os.open(self.REQ_PIPE, os.O_WRONLY)
                self._write_request(req_fd, pt, freq, accel_time,
                                    loop, slowv, fastv, drop1, drop2,
                                    calc_mode, calc_mode_params)
                os.close(req_fd)

                resp_fd = os.open(self.RESP_PIPE, os.O_RDONLY)
                response = self._read_response(resp_fd)
                os.close(resp_fd)
                result[0] = response
            except Exception as e:
                error[0] = e

        thread = threading.Thread(target=_do_io, daemon=True)
        thread.start()
        thread.join(timeout=self.TIMEOUT)

        if thread.is_alive():
            raise FlowCalcError("Timeout communicating with flow calculator server")
        if error[0] is not None:
            raise FlowCalcError(str(error[0]))

        response = result[0]
        logging.info(f"[flow_calibrator] Response: {response}\r\n")
        if response.get('status') != 'ok':
            raise FlowCalcError(response.get('message', 'Unknown error from flow calculator'))

        if calc_mode == AERA_CALC_MODE_OS:
            return (float(response['decel_result']),
                    float(response['accel_result']))
        else:
            return float(response['result'])

DEFAULT_ENV = {
    'k_min': 0.005,
    'k_max': 0.065,
    'k_step': 0.005,
    'start_vel': 4,
    'start_dist': 20,
    'slow_vel': 0.8,
    'slow_dist': 0.8,
    'fast_dist': 2,
    'fast_vel': 8,
    'accel': 200,
    'loop': 14
}

DEFAULT_K = {'extruder': 0.02, 'extruder1': 0.02, 'extruder2': 0.02, 'extruder3': 0.02}
DEFAULT_CALI_STATE = {'extruder': False, 'extruder1': False, 'extruder2': False, 'extruder3': False}

class AbortCalibration(Exception):
    def __init__(self, msg=''):
        self.message = msg
        Exception.__init__(self, msg)

class AccelTimeQueryHelper:
    def __init__(self, printer):
        self._printer = printer
        self.is_finished = False
        print_time = printer.lookup_object('toolhead').get_last_move_time()
        self.request_start_time = self.request_end_time = print_time
        self.msgs = []
        self.samples = []
    def finish_measurements(self):
        toolhead = self._printer.lookup_object('toolhead')
        self.request_end_time = toolhead.get_last_move_time()
        toolhead.wait_moves()
        self.is_finished = True
    def handle_batch(self, msg):
        # "trapq:extruder","params":{"data":[[17713.215392520833,0.036,8.0,-200.0,[8538.241600000292,1.8415999999999997,0.0],[1.0,1.0,0.0]]]
        if self.is_finished:
            return False
        if len(self.msgs) >= 10000:
            # Avoid filling up memory with too many samples
            return False
        # logging.info(f'got mesg: {msg}')
        self.msgs.append(msg)
        return True
    def get_samples(self):
        if not self.msgs:
            logging.warning("no mesg")
            return self.samples
        total = sum([len(m['data']) for m in self.msgs])
        count = 0
        self.samples = samples = [None] * total

        # 'time', 'duration', 'start_velocity',
        # 'acceleration', 'start_position', 'direction'
        for msg in self.msgs:
            for t, d, sv, a, sp, dir in msg['data']:
                # logging.info("t:%.4f, d:%.4f, sv: %.4f, a:%.4f\n" % (t, d, sv, a))
                samples[count] = (t, d, sv, a)
                count += 1
        del samples[count:]
        del self.msgs[:]
        logging.info('got accel time sameple len: {}'.format(len(self.samples)))
        return self.samples
    def write_to_file(self, filename, slowv=None, fastv=None):
        """
        need to detect acceleration time:
        8 mm/s        _____       ___     ___
        0.8mm/s ___|/|     |\|___/   \___/   \___
                   1 2     3 4
        1 -> acceleration start
        2 -> cruise start of fast speed, 8mm/s
        3 -> decceleration start
        4 -> cruise start of slow speed, 0.8mm/s
        """
        samples = list(self.samples or self.get_samples())
        def write_impl():
            try:
                # Try to re-nice writing process
                os.nice(20)
            except:
                pass
            f = open(filename, 'w+')
            f.write("time, duration, start speed, accel\n")
            for t, d, sv, a in samples:
                if slowv is None and fastv is None:
                    f.write("%.4f,%.4f,%.4f,%.4f\n" % (t,d,sv,a))
                    continue
                if slowv is not None and fastv is not None:
                    if abs(sv - slowv) >= 0.00001 and abs(sv - fastv) >= 0.00001:
                        continue
                f.write("%.4f,%.4f,%.4f,%.4f\n" % (t,d,sv,a))
            f.close()
        write_proc = multiprocessing.Process(target=write_impl)
        write_proc.daemon = True
        write_proc.start()
        reactor = self._printer.get_reactor()
        eventtime = reactor.monotonic()
        while write_proc.is_alive():
            eventtime = reactor.pause(eventtime + .05)
        write_proc.join()

class FlowCalibrator(object):
    def __init__(self, config) -> None:
        self._printer = config.get_printer()
        config_dir = self._printer.get_snapmaker_config_dir()
        config_name = config.get('config_name', 'flow_calibrator.json')
        self._config_path = os.path.join(config_dir, config_name)
        self._current_k = dict()
        self._env = dict()
        self._load_json_config(self._config_path)
        self._calibrated_in_printing = DEFAULT_CALI_STATE
        self._flow_calc_client = FlowCalcClient()

        debug = config.getint('debug', 0)
        start_args = self._printer.get_start_args()
        factory_mode = start_args.get('factory_mode', False)
        if debug or factory_mode:
            self._debug_mode = True
        else:
            self._debug_mode = False
        self._abort_calibration = False
        self._abort_reason = None

        # register gcode commands
        self._gcode = self._printer.lookup_object('gcode')
        self._gcode.register_command('ACCEL_TIME_MEASURE',
                               self.cmd_ACCEL_TIME_MEASURE,
                               desc=self.cmd_ACCEL_TIME_MEASURE_help)
        self._gcode.register_command('FLOW_CALIBRATE',
                               self.cmd_FLOW_CALIBRATE,
                               desc=self.cmd_FLOW_CALIBRATE_help)
        self._gcode.register_command('FLOW_MEASURE_K',
                               self.cmd_FLOW_MEASURE_K,
                               desc=self.cmd_ACCEL_TIME_MEASURE_help)
        self._gcode.register_command('FLOW_RESET_K',
                               self.cmd_FLOW_RESET_K)
        self._gcode.register_command('FLOW_APPLY_CALIBRATE_K',
                               self.cmd_FLOW_APPLY_CALIBRATE_K)
        self._bg_client = None
        self._motion_report: motion_report.PrinterMotionReport = None
        self._printer.register_event_handler("klippy:ready", self._handle_ready)
        self._printer.register_event_handler("virtual_sdcard:reset_file", self._handle_reset_file)
        self._printer.register_event_handler("pause_resume:cancel", self._handle_cancel_print)
        self._printer.register_event_handler("filament_switch_sensor:runout", self._handle_filament_runout)
        self._printer.register_event_handler("filament_entangle_detect:tangled", self._handle_filament_tangled)

    def _apply_k(self):
        extruder_list = self._printer.lookup_object('extruder_list', None)
        for extruder in extruder_list:
            if extruder:
                logging.info('update k{} for {}'.format(self._current_k[extruder.get_name()], extruder.get_name()))
                self._set_pressure_advance(extruder, self._current_k[extruder.get_name()])

    def _load_json_config(self, json_file):
        try:
            params = json.load(open(json_file, 'r'))
            if not params.get('factor') or not params.get('env'):
                raise "invalid parameters in json config"
            k = params.get('factor')
            env = params.get('env')

            if not k.get('extruder') or not k.get('extruder1') or not k.get('extruder2') or not k.get('extruder3'):
                raise
            if not env.get('k_min') or not env.get('k_max') or not env.get('start_vel') or not env.get('start_dist') or \
                not env.get('slow_vel') or not env.get('slow_dist') or not env.get('fast_dist') or not env.get('fast_vel') \
                or not env.get('accel') or not env.get('loop') or not env.get('k_step') :
                raise
            self._current_k = k
            self._env = env
        except Exception as e:
            logging.info(f'reset flowcalibration config: {e}')
            if os.path.exists(json_file):
                os.remove(json_file)
            settings = {'factor': DEFAULT_K, 'env': DEFAULT_ENV}
            with open(json_file, 'w+') as f:
                f.write(json.dumps(settings))
            self._current_k = DEFAULT_K
            self._env = DEFAULT_ENV

    def _save_config(self):
        try:
            config = {'factor': self._current_k, 'env': self._env}
            json_content = json.dumps(config)
            queuefile.async_write_file(self._config_path, json_content, safe_write=True)
        except Exception as e:
            logging.exception(f"Failed to save flow calibrator config to {self._config_path}: {e}")
    def _handle_ready(self):
        self._apply_k()
        self._motion_report = self._printer.lookup_object('motion_report')
        self._toolhead = self._printer.lookup_object('toolhead')
        self._task_config = self._printer.lookup_object('print_task_config', None)
        self._filament_parameters = self._printer.lookup_object('filament_parameters', None)
        try:
            self._flow_calc_client.check_server()
        except FlowCalcError as e:
            logging.warning("[flow_calibrator] Flow calculator server check failed: %s", e)

    def _handle_reset_file(self):
        extruder_list = self._printer.lookup_object('extruder_list', None)
        for extruder in extruder_list:
            self._calibrated_in_printing[extruder.get_name()] = False

    def _handle_cancel_print(self):
        self._abort_calibration = True
        self._abort_reason = ABORT_REASON_CANCEL_BY_USER

    def _handle_filament_runout(self, extruder, present):
        if not present and extruder == self._toolhead.get_extruder().extruder_index:
            self._abort_calibration = True
            self._abort_reason = ABORT_REASON_FILAMENT_RUNOUT


    def _handle_filament_tangled(self, extruder):
        if extruder == self._toolhead.get_extruder().extruder_index:
            self._abort_calibration = True
            self._abort_reason = ABORT_REASON_FILAMENT_TANGLED

    def start_measure_acceleration_time(self, axis='toolhead'):
        atqh = AccelTimeQueryHelper(self._printer)
        self._motion_report.start_trapq_client(axis, atqh.handle_batch)
        return atqh

    def _end_of_measure(self):
        self._gcode.run_script_from_command("INNER_FLOW_MEASURE_END_BASE_DISCARD")

    def _end_of_calibration(self, extruder):
        self._gcode.run_script_from_command("INNER_FLOW_CALIB_END_BASE_DISCARD")

    def _set_pressure_advance(self, extruder, k, st=None):
        estepper = extruder.extruder_stepper
        if st == None:
            st = estepper.config_smooth_time
        estepper._set_pressure_advance(k, st)

    def _prepare_phase(self, extruder, k, accel, velocity, distance):
        self._toolhead.wait_moves()
        extruder.set_max_accel(accel)
        self._set_pressure_advance(extruder, k, 0.001)
        curpos = self._toolhead.get_position()
        curpos[3] += distance
        self._toolhead.manual_move(curpos, velocity)

    def _extrude_loop(self, extruder, slow_v, slow_d, fast_v, fast_d, loop):
        for i in range(loop):
            if not self._abort_calibration:
                curpos = self._toolhead.get_position()
                curpos[3] += slow_d
                self._toolhead.manual_move(curpos, slow_v)
            if not self._abort_calibration:
                curpos[3] += fast_d
                self._toolhead.manual_move(curpos, fast_v)
            if self._abort_calibration:
                if self._abort_reason != None:
                    raise AbortCalibration(f'{self._abort_reason}')
                else:
                    raise AbortCalibration(f'generic')
        curpos = self._toolhead.get_position()
        curpos[3] += slow_d * 5
        self._toolhead.manual_move(curpos, slow_v)

    def _measure_k(self, extruder, inductance_coil, k, params, extruder_dir=None):
        accel_client = None
        freq_client = None
        original_accel = None
        try:
            self._gcode.run_script_from_command("MOVE_TO_DISCARD_FILAMENT_POSITION")
            pheaters = self._printer.lookup_object('heaters')
            pheaters.set_temperature(extruder.get_heater(), params['temp'], True)

            self._toolhead.wait_moves()
            original_accel = extruder.get_max_accel()
            accel_client = self.start_measure_acceleration_time(extruder.get_name())
            freq_client = inductance_coil.start_internal_client()

            self._prepare_phase(extruder, k, params['accel'], params['start_vel'], params['start_dist'])

            self._extrude_loop(extruder, params['slow_vel'], params['slow_dist'], params['fast_vel'],
                                params['fast_dist'], params['loop'])

            self._toolhead.dwell(0.5)
            self._toolhead.wait_moves()
        except AbortCalibration as e:
            raise
        except Exception as e:
            raise e
        finally:
            if original_accel is not None and extruder.get_max_accel() != original_accel:
                extruder.set_max_accel(original_accel)
            # Ensure measurements are always finished, even if aborted
            if freq_client:
                freq_client.finish_measurements()
            if accel_client:
                accel_client.finish_measurements()
        self._toolhead.dwell(0.1)
        freq_pt, freq = freq_client.get_samples()
        accel_ts = accel_client.get_samples()

        self._end_of_measure()

        self._flow_calc_client.check_server()
        if params['calc_mode'] == AERA_CALC_MODE_OS:
            area_result = self._flow_calc_client.calc_flow_factor(
                freq_pt, freq, accel_ts,
                params['loop'], params['slow_vel'], params['fast_vel'], 1, 1,
                calc_mode=AERA_CALC_MODE_OS,
                calc_mode_params={'os_count': params['os_sample_count']})
            logging.info("area decel: %.3f, accel: %.3f", area_result[0], area_result[1])
        else:
            area_result = self._flow_calc_client.calc_flow_factor(
                freq_pt, freq, accel_ts,
                params['loop'], params['slow_vel'], params['fast_vel'], 1, 1)
            logging.info("area: %.3f", area_result)

        if extruder_dir is None:
            return area_result

        # Write data to file
        if not extruder_dir.exists():
            os.makedirs(str(extruder_dir))
        accel_filename = extruder_dir.joinpath("accelts-k%.5f.csv"  % (k,))
        freq_filename = extruder_dir.joinpath("freq-k%.5f.csv"  % (k, ))
        accel_client.write_to_file(str(accel_filename), params['slow_vel'], params['fast_vel'])
        freq_client.write_to_file(str(freq_filename))
        # waiting write process ending
        logging.info("Writing raw accel ts to %s, and freq to %s file"
                            % (accel_filename, freq_filename))
        return area_result

    def _get_next_k(self, k_left, k_right, area_left, area_right):
        area_sum = area_left + area_right
        # actual k is to the right of k_right
        if area_sum > area_left and area_sum > area_right:
            return round(k_right + (k_right - k_left), 6)
        # actual k is to the left of k_left
        if area_sum < area_left and area_sum < area_right:
            if (k_right - k_left) > k_left:
                return 0
            else:
                return round(k_left - (k_right - k_left), 6)
        if area_sum < area_left or area_sum < area_right:
            return round(k_left + (k_right - k_left) / 2, 6)

    def _calculate_zero_crossing(self, point1, point2):
        x1, y1 = point1
        x2, y2 = point2

        if abs(y2 - y1) < 0.0001:
            self._abort_reason = ABORT_REASON_OUT_OF_RANGE
            self._abort_calibration = True
            raise AbortCalibration(f'{self._abort_reason}')

        return x1 - y1 * (x2 - x1) / (y2 - y1)

    def _calculate_linear_fitting_zero_crossing(self, measure_data_list):
        if len(measure_data_list) < 2:
            raise ValueError("[flow_calibrate] measure_data_list not enough data")

        k_values = np.array([point[0] for point in measure_data_list])
        area_values = np.array([point[1] for point in measure_data_list])
        coefficients = np.polyfit(k_values, area_values, 1)
        slope = coefficients[0]
        intercept = coefficients[1]
        zero_crossing_k = -intercept / slope

        return zero_crossing_k

    def _calculate_os_linear_fitting_zero_crossing(self,
                                                    decel_data_list=None,
                                                    accel_data_list=None,
                                                    default_k=0.02):
        def _fit_one(data_list, expected_slope_sign=0):
            if len(data_list) < 2:
                raise ValueError("[flow_calibrate] measure_data_list not enough data")

            sorted_pts = sorted(data_list, key=lambda p: p[0])
            ks = np.array([p[0] for p in sorted_pts])
            areas = np.array([p[1] for p in sorted_pts])

            if float(np.max(areas) - np.min(areas)) < 500.0:
                raise ValueError("[flow_calibrate] the linear characteristics are not obvious")

            a, b = np.polyfit(ks, areas, 1)
            if abs(a) < 1e-12:
                return ks[np.argmin(np.abs(areas))]

            if expected_slope_sign != 0:
                if (expected_slope_sign > 0 and a <= 0.0) or \
                    (expected_slope_sign < 0 and a >= 0.0):
                    raise ValueError(
                        f"Slope sign mismatch: expected {'+' if expected_slope_sign > 0 else '-'}"
                        f" but got a={a:.6f}")

            k_zero = -b / a
            k_lo, k_hi = float(np.min(ks)), float(np.max(ks))
            margin = (k_hi - k_lo) * 0.2
            if k_zero < k_lo - margin:
                return k_lo
            if k_zero > k_hi + margin:
                return k_hi
            return k_zero

        k_decel = default_k
        k_accel = default_k

        try:
            if decel_data_list is None:
                raise ValueError("[flow_calibrate] decel_data_list is None, using default")
            k_decel = _fit_one(decel_data_list, expected_slope_sign=-1)

        except Exception as e:
            logging.error("[flow_calibrate] calc error: %s" % str(e))
            k_decel = default_k

        try:
            if accel_data_list is None:
                raise ValueError("[flow_calibrate] accel_data_list is None, using default")
            k_accel = _fit_one(accel_data_list, expected_slope_sign=1)

        except Exception as e:
            logging.error("[flow_calibrate] calc error: %s" % str(e))
            k_accel = default_k

        return k_decel, k_accel

    def _reset_pressure_advance(self, extruder_index):
        filament_parameters = self._printer.lookup_object('filament_parameters', None)
        print_task_config = self._printer.lookup_object('print_task_config', None)
        extruder = None
        if extruder_index == 0:
            extruder = self._printer.lookup_object('extruder', None)
        else:
            extruder = self._printer.lookup_object(f'extruder{extruder_index}', None)

        default_k = 0.02
        if filament_parameters is None or print_task_config is None or extruder is None:
            logging.error("[flow_calibrate] cannot get necessary objects")
        else:
            status = print_task_config.get_status()
            default_k = filament_parameters.get_flow_k(
                status['filament_vendor'][extruder_index],
                status['filament_type'][extruder_index],
                status['filament_sub_type'][extruder_index],
                extruder.nozzle_diameter,
                extruder.nozzle_volume_type)

        self._set_pressure_advance(extruder, default_k)
        need_save = False
        if extruder.get_name() not in self._current_k:
            need_save = True
        else:
            if self._current_k[extruder.get_name()] != default_k:
                need_save = True
        self._current_k[extruder.get_name()] = default_k
        if need_save:
            self._save_config()

    def _apply_calibrate_k(self, extruder_index):
        extruder = None
        if extruder_index == 0:
            extruder = self._printer.lookup_object('extruder', None)
        else:
            extruder = self._printer.lookup_object(f'extruder{extruder_index}', None)

        if extruder is None or extruder.get_name() not in self._current_k:
            logging.error("[flow_calibrate] apply_calibrate_k err")
            return

        self._set_pressure_advance(extruder, self._current_k[extruder.get_name()])

    def cmd_FLOW_RESET_K(self, gcmd):
        extruder_index = gcmd.get_int("EXTRUDER")
        self._reset_pressure_advance(extruder_index)

    def cmd_FLOW_APPLY_CALIBRATE_K(self, gcmd):
        extruder_index = gcmd.get_int("EXTRUDER")
        self._apply_calibrate_k(extruder_index)

    cmd_FLOW_CALIBRATE_help = """start calibrate the factor for pressure advance\n
    TARGET      -> target extruder name, must specify it
    TEMP        -> temperature for test
    MIN         -> min K
    MAX         -> max K
    STARTV      -> extrude velocity in prepare phase
    STARTD      -> extrude distance in prepare phase
    SLOWV       -> slow velocity in normal phase
    SLOWD       -> extrude distance in slow velocity
    FASTV       -> fast velocity in normal phase
    FASTD       -> extrude distance in fast velocity
    ACCEL       -> acceleration for extruding
    LOOP        -> extrude count for one loop
    ALGORITHM   -> calc algorithm
    """
    def cmd_FLOW_CALIBRATE(self, gcmd):
        self._abort_calibration = False
        self._abort_reason = None
        machine_state_manager = None

        ######### check whether calibration is allowed or required
        if self._task_config is None or self._filament_parameters is None:
            raise gcmd.error("[flow_calibrate] cannot get necessary objects")

        extruder = self._toolhead.get_extruder()
        extruder_index = extruder.extruder_index
        nozzle_diameter = extruder.nozzle_diameter
        nozzle_volume_type = extruder.nozzle_volume_type
        task_config_status = self._task_config.get_status()
        filament_parameters = self._filament_parameters.get_filament_parameters(
                                            task_config_status['filament_vendor'][extruder_index],
                                            task_config_status['filament_type'][extruder_index],
                                            task_config_status['filament_sub_type'][extruder_index],
                                            nozzle_diameter,
                                            nozzle_volume_type)

        runout_sensor = self._printer.lookup_object(f'filament_motion_sensor e{extruder_index}_filament', None)
        if runout_sensor is not None and runout_sensor.get_status(0)['enabled'] == True and \
                runout_sensor.get_status(0)['filament_detected'] == False:
            raise gcmd.error(
                    message = f'e{extruder_index}_filament runout',
                    action = 'pause',
                    id = 523,
                    index = extruder_index,
                    code = 0,
                    oneshot = 0,
                    level = 2)

        force_flag = gcmd.get_int('FORCE', 0)
        print_stats = self._printer.lookup_object('print_stats', None)
        if force_flag == 0:
            if print_stats and print_stats.state in ['printing', 'paused']:
                if not self._task_config.print_task_config['flow_calibrate']:
                    gcmd.respond_info("[flow_calibrate] flow calibration is disabled")
                    return

                if self._calibrated_in_printing[extruder.get_name()]:
                    gcmd.respond_info(f'[flow_calibrate]flow calibration of {extruder.get_name()} has been finished')
                    return

            if task_config_status['filament_type'][extruder_index] == 'NONE':
                raise gcmd.error(
                        message = "[flow_calibrate] not edit filament info!",
                        action = 'pause',
                        id = 523,
                        index = extruder_index,
                        code = 39,
                        oneshot = 1,
                        level = 2)

            is_allow_flag = self._filament_parameters.is_allow_to_print(
                                            task_config_status['filament_vendor'][extruder_index],
                                            task_config_status['filament_type'][extruder_index],
                                            task_config_status['filament_sub_type'][extruder_index],
                                            nozzle_diameter,
                                            nozzle_volume_type)
            if not is_allow_flag:
                raise gcmd.error(
                    message = "[flow_calibrate] not allow to calibrate!",
                    action = 'pause',
                    id = 523,
                    index = extruder_index,
                    code = 9001,
                    oneshot = 1,
                    level = 3)

        ######### parse and apply parameters
        flow_temp = 250
        flow_accel = self._env['accel']
        flow_slow_v = self._env['slow_vel']
        flow_fast_v = self._env['fast_vel']
        flow_loop = self._env['loop']
        flow_k_min = self._env['k_min']
        flow_k_max = self._env['k_max']
        flow_k = DEFAULT_K[extruder.get_name()]
        max_flow_k = 1.0

        # built-in filament parameters
        try:
            builtin_flow_temp = filament_parameters['print_temp']
            builtin_flow_accel = filament_parameters['accel']
            builtin_flow_slow_v = filament_parameters['slow_v']
            builtin_flow_fast_v = filament_parameters['fast_v']
            builtin_flow_k_min = filament_parameters['flow_k_min']
            builtin_flow_k_max = filament_parameters['flow_k_max']
            builtin_flow_k = filament_parameters['flow_k']
            builtin_max_flow_k = filament_parameters['max_flow_k']

            flow_temp = builtin_flow_temp
            flow_accel = builtin_flow_accel
            flow_slow_v = builtin_flow_slow_v
            flow_fast_v = builtin_flow_fast_v
            flow_k_min = builtin_flow_k_min
            flow_k_max = builtin_flow_k_max
            flow_k = builtin_flow_k
            max_flow_k = builtin_max_flow_k

        except:
            logging.error(f'[flow_calibrate] cannot get built-in filament parameters for {extruder.get_name()}')

        # gcode file parameters
        if print_stats and print_stats.state in ['printing', 'paused']:
            try:
                gcode_parameters = copy.deepcopy(self._task_config.print_task_config_2)
                filament_index = None
                for i in range(len(task_config_status['extruder_map_table'])):
                    if task_config_status['extruder_map_table'][i] != extruder_index:
                        continue
                    if gcode_parameters['filament_used_g'][i] < 0.00001 and gcode_parameters['filament_used_mm'][i] < 0.00001:
                        continue
                    filament_index = i
                    break

                if filament_index is None:
                    raise

                gcode_max_vol_speed = gcode_parameters['filament_max_vol_speed'][filament_index]
                gcode_flow_ratio = gcode_parameters['filament_flow_ratio'][filament_index]
                gcode_temp = gcode_parameters['nozzle_temp'][filament_index]
                gcode_print_accel = gcode_parameters['outer_wall_accel']
                if gcode_parameters['filament_volume_type'][filament_index] == 'high_flow' or \
                        nozzle_volume_type == 'high_flow':
                    gcode_print_accel = gcode_parameters['outer_wall_accel_hf']

                if gcode_parameters['line_width'] < 0.00001 or gcode_parameters['line_width'] > nozzle_diameter * 2 or \
                        gcode_parameters['layer_height'] < 0.00001 or gcode_parameters['layer_height'] > nozzle_diameter * 1.1 or \
                        gcode_max_vol_speed < 0.00001 or gcode_max_vol_speed > 1000.0 or \
                        gcode_print_accel < 0.00001 or gcode_print_accel > 100000.0 or \
                        gcode_flow_ratio < 0.00001 or gcode_flow_ratio > 5 or \
                        gcode_temp < extruder.heater.min_extrude_temp or gcode_temp > extruder.heater.max_temp:
                    raise

                area_line = gcode_parameters['layer_height'] * (gcode_parameters['line_width'] - gcode_parameters['layer_height'] * ( \
                                1.0 - 3.1415926 / 4.0))
                area_filament = 0.875 * 0.875 * 3.1415926

                gcode_fast_v = gcode_max_vol_speed / area_filament
                gcode_fast_v = min(gcode_fast_v, extruder.max_e_velocity)
                gcode_slow_v = area_line * 20 / area_filament
                gcode_slow_v = max(gcode_slow_v, 0.16)
                gcode_accel = gcode_print_accel * area_line / area_filament * gcode_flow_ratio
                gcode_accel = min(gcode_accel, extruder.max_e_accel)
                if gcode_fast_v <= gcode_slow_v:
                    raise

                flow_temp = gcode_temp
                flow_accel = gcode_accel
                flow_slow_v = gcode_slow_v
                flow_fast_v = gcode_fast_v
                logging.info(f"[flow_calibrate] using gcode parameters for {extruder.get_name()}")

            except:
                logging.error(f'[flow_calibrate] gcode parameters not valid for {extruder.get_name()}')

        # Gcode parameter takes precedence
        temperature = gcmd.get_int('TEMP', flow_temp, minval=extruder.heater.min_extrude_temp, maxval=extruder.heater.max_temp)
        fast_v = gcmd.get_float('FASTV', flow_fast_v, minval=0)
        slow_v = gcmd.get_float('SLOWV', flow_slow_v, minval=0)
        start_vel = gcmd.get_float('STARTV', (fast_v + slow_v) / 2.0, minval=0)
        accel = gcmd.get_float('ACCEL', flow_accel, minval=5)
        loop = gcmd.get_int('LOOP', flow_loop, minval=0)
        algorithm = gcmd.get('ALGORITHM', None)
        os_count = gcmd.get_int('OS_COUNT', 20, minval=1, maxval=100)
        if algorithm is None:
            if nozzle_volume_type == 'high_flow':
                algorithm = ALGORITHM_TYPE_OS_DECEL
            else:
                algorithm = ALGORITHM_TYPE_LINEAR_FITTING
        k_min = gcmd.get_float('MIN', flow_k_min, minval=0, maxval=1.0)
        k_max = gcmd.get_float('MAX', flow_k_max, minval=0, maxval=1.0)
        flow_start_d = max(start_vel * 1, 3)
        flow_slow_d = max(slow_v * 1, 0.5)
        flow_fast_d = max(fast_v * 0.5, 0.8)
        if algorithm in [ALGORITHM_TYPE_OS_ACCEL, ALGORITHM_TYPE_OS_DECEL, ALGORITHM_TYPE_OS_ACCEL_DECEL]:
            _ramp_dist = (fast_v**2 - slow_v**2) / (2.0 * accel)
            flow_slow_d = max(slow_v * 0.5 , 0.5)
            flow_fast_d = max(fast_v * 0.5 + 2 * _ramp_dist, 0.8)

        start_dist = gcmd.get_float('STARTD', flow_start_d, minval=0)
        slow_dist = gcmd.get_float('SLOWD', flow_slow_d, minval=0)
        fast_dist = gcmd.get_float('FASTD', flow_fast_d, minval=0)

        _area_algo_map = {
            ALGORITHM_TYPE_OS_ACCEL:       (1, os_count),
            ALGORITHM_TYPE_OS_DECEL:       (1, os_count),
            ALGORITHM_TYPE_OS_ACCEL_DECEL: (1, os_count),
        }
        _algo_calc_mode, _algo_sample_count = _area_algo_map.get(
            algorithm, (0, 0))

        # parameters check
        if fast_v <= slow_v:
            raise gcmd.error("[flow_calibrate] FASTV should be greater than SLOWV\r\n")
        if k_min >= k_max:
            raise gcmd.error("[flow_calibrate] MIN should be less than MAX\r\n")
        if start_vel <= slow_v or start_vel >= fast_v:
            raise gcmd.error("[flow_calibrate] STARTV should be between SLOWV and FASTV\r\n")

        filament_default_k = flow_k
        filaments_max_flow_k = max_flow_k
        if filament_parameters['is_soft'] != task_config_status['filament_soft'][extruder_index]:
            if task_config_status['filament_soft'][extruder_index]:
                filaments_max_flow_k = filament_parameters['soft_filaments_max_flow_k']
            else:
                filaments_max_flow_k = filament_parameters['hard_filaments_max_flow_k']

        # apply parameters
        cali_params = {
            'k_min': k_min,
            'k_max': k_max,
            'start_vel': start_vel,
            'start_dist': start_dist,
            'slow_vel': slow_v,
            'slow_dist': slow_dist,
            'fast_dist': fast_dist,
            'fast_vel': fast_v,
            'accel': accel,
            'loop': loop,
            'temp': temperature,
            'calc_mode': _algo_calc_mode,
            'os_sample_count': _algo_sample_count
        }

        gcmd.respond_info("[flow_calibrate] filament: %s %s %s , calib_param: %s \r\n" % (
                        task_config_status['filament_vendor'][extruder_index],
                        task_config_status['filament_type'][extruder_index],
                        task_config_status['filament_sub_type'][extruder_index],
                        str(cali_params)))
        gcmd.respond_info("[flow_calibrate] algorithm: %s \r\n" % (str(algorithm)))

        try:
            self._toolhead.wait_moves()
            machine_state_manager = self._printer.lookup_object('machine_state_manager', None)
            if machine_state_manager is not None:
                cur_sta = machine_state_manager.get_status()
                if str(cur_sta["main_state"]) == "PRINTING":
                    self._gcode.run_script_from_command("SET_ACTION_CODE ACTION={}_FLOW_CALIBRATING".format(extruder.get_name().upper()))
                else:
                    self._gcode.run_script_from_command("SET_MAIN_STATE MAIN_STATE=FLOW_CALIBRATION ACTION={}_FLOW_CALIBRATING".format(extruder.get_name().upper()))

            if not extruder.check_xy_homing():
                self._gcode.run_script_from_command("G28 X Y")
                self._toolhead.wait_moves()

            estepper = extruder.extruder_stepper
            backup_st = estepper.config_smooth_time
            inductance_coil_name = f'inductance_coil {extruder.get_name()}'
            self._toolhead.get_last_move_time()
            try:
                pheaters = self._printer.lookup_object('heaters')
                inductance_coil_wrapper = self._printer.lookup_object(inductance_coil_name)
                status = extruder.get_extruder_activate_status()
                retry_extruder_id = extruder.check_allow_retry_switch_extruder()
                info = status[0]
                if info[1] != 0 and retry_extruder_id != extruder.extruder_num:
                    gcmd.respond_info(f'{status}')
                    raise gcmd.error(f'[{extruder.get_name()}] is not available for flow calibration!')
            except self._printer.config_error as e:
                raise gcmd.error(str(e))

            # move to extrusion position before heating nozzle, avoid dripping on the bed
            self._gcode.run_script_from_command("MOVE_TO_DISCARD_FILAMENT_POSITION")

            gcmd.respond_info(f'start flow calibration for {extruder.get_name()}')
            gcmd.respond_info(f'start heating heater to {temperature} degre')
            pheaters.set_temperature(extruder.get_heater(), temperature, True)

            # start measuring inductance coil frequency
            gcmd.respond_info(f'start measuring frequency')
            inductance_coil = inductance_coil_wrapper.sensor

            gcmd.respond_info(f'start extruding')

            measure_success_k = None

            # prepaire direcotry for data
            extruder_dir = None
            if self._debug_mode:
                vsd = self._printer.lookup_object('virtual_sdcard', None)
                if vsd is None:
                    gcmd.respond_info("No virtual_sdcard dir to save frequency_data data")
                    data_path = pathlib.Path('/userdata/gcodes/frequency_data/flow_test')
                else:
                    data_path = pathlib.Path(f'{vsd.sdcard_dirname}/frequency_data/flow_test')

                if not os.path.exists(data_path):
                    os.makedirs(data_path)
                extruder_dir = data_path.joinpath(f'{time.strftime("%m%d-%H%M")}_{extruder.get_name()}')
                if not os.path.exists(extruder_dir):
                    os.makedirs(extruder_dir)

            # notify other objects to start flow calibration
            self._printer.send_event('flow_calibration:begin')
            try:
                if algorithm == ALGORITHM_TYPE_DICHOTOMY:
                    # gcmd.respond_info("Starting flow calibration, algorithm: dichotomy")
                    k_left = cali_params['k_min']
                    k_right = cali_params['k_max']
                    gcmd.respond_info(f'measure k: {k_left:.5f}')
                    area_left = self._measure_k(extruder, inductance_coil, k_left, cali_params, extruder_dir)
                    gcmd.respond_info(f'measure k: {k_right:.5f}')
                    area_right = self._measure_k(extruder, inductance_coil, k_right, cali_params, extruder_dir)
                    next_k = self._get_next_k(k_left, k_right, area_left, area_right)
                    gcmd.respond_info(f'calculate next_k: {next_k:.5f}')
                    if next_k < cali_params['k_min'] or next_k > cali_params['k_max']:
                        self._abort_reason = ABORT_REASON_OUT_OF_RANGE
                        self._abort_calibration = True
                        raise AbortCalibration(f'{self._abort_reason}')

                    gcmd.respond_info(f'area_left[k{k_left:.5f}]: {area_left}, next k: {next_k:.5f}, area_right[k{k_right:.5f}]: {area_right}')

                    for i in range(4):
                        gcmd.respond_info(f'measure k: {next_k:.5f}')
                        measure_area = self._measure_k(extruder, inductance_coil, next_k, cali_params, extruder_dir)
                        gcmd.respond_info(f'area_left[k{k_left:.5f}]: {area_left}, measure_area[k{next_k:.5f}]: {measure_area}, area_right[k{k_right:.5f}]: {area_right}')
                        if measure_area > 0:
                            k_left = next_k
                            area_left = measure_area
                        elif measure_area < 0:
                            k_right = next_k
                            area_right = measure_area
                        else:
                            break
                        next_k = self._get_next_k(k_left, k_right, area_left, area_right)

                    measure_success_k = next_k

                elif algorithm == ALGORITHM_TYPE_LINEAR_FITTING:
                    # gcmd.respond_info("Starting flow calibration, algorithm: linear fitting")
                    measure_data_list = []
                    measure_point_1_k = cali_params['k_min']
                    measure_point_2_k = cali_params['k_max']
                    filament_parameters = self._filament_parameters.get_filament_parameters(
                        task_config_status['filament_vendor'][extruder_index],
                        task_config_status['filament_type'][extruder_index],
                        task_config_status['filament_sub_type'][extruder_index],
                        extruder.nozzle_diameter,
                        extruder.nozzle_volume_type)
                    filaments_max_flow_k = max(filaments_max_flow_k, measure_point_2_k)
                    gcmd.respond_info(f'measure k: {measure_point_1_k:.5f}')
                    measure_point_1_area = self._measure_k(extruder, inductance_coil, measure_point_1_k, cali_params, extruder_dir)
                    gcmd.respond_info(f'measure area: {measure_point_1_area:.5f}')
                    gcmd.respond_info(f'measure k: {measure_point_2_k:.5f}')
                    measure_point_2_area = self._measure_k(extruder, inductance_coil, measure_point_2_k, cali_params, extruder_dir)
                    gcmd.respond_info(f'measure area: {measure_point_2_area:.5f}')
                    measure_point_1 = measure_point_1_k, measure_point_1_area
                    measure_point_2 = measure_point_2_k, measure_point_2_area
                    if measure_point_2_area >= measure_point_1_area:
                        self._abort_reason = ABORT_REASON_OUT_OF_RANGE
                        self._abort_calibration = True
                        raise AbortCalibration(f'{self._abort_reason}')
                    measure_data_list.append((measure_point_1_k, measure_point_1_area))
                    measure_data_list.append((measure_point_2_k, measure_point_2_area))

                    # middle point
                    next_k = (measure_point_2_k + measure_point_1_k) / 2
                    gcmd.respond_info(f'measure k: {next_k:.5f}')
                    next_area = self._measure_k(extruder, inductance_coil, next_k, cali_params, extruder_dir)
                    gcmd.respond_info(f'measure area: {next_area:.5f}')
                    measure_data_list.append((next_k, next_area))

                    # default point
                    if next_area <= measure_point_2_area or next_area >= measure_point_1_area:
                        next_k = filament_default_k
                        gcmd.respond_info(f'measure k: {next_k:.5f}')
                        next_area = self._measure_k(extruder, inductance_coil, next_k, cali_params, extruder_dir)
                        gcmd.respond_info(f'measure area: {next_area:.5f}')
                        measure_data_list.append((next_k, next_area))

                    # zero point
                    calculate_k_zero_12 = self._calculate_zero_crossing(measure_point_1, measure_point_2)
                    next_k = calculate_k_zero_12
                    if calculate_k_zero_12 < 0.001:
                        next_k = 0.001
                    elif calculate_k_zero_12 >= filaments_max_flow_k:
                        next_k = (filaments_max_flow_k + measure_point_2_k) / 2
                    gcmd.respond_info(f'measure k: {next_k:.5f}')
                    next_area = self._measure_k(extruder, inductance_coil, next_k, cali_params, extruder_dir)
                    gcmd.respond_info(f'measure area: {next_area:.5f}')
                    measure_data_list.append((next_k, next_area))

                    measure_success_k = self._calculate_linear_fitting_zero_crossing(measure_data_list)
                    if measure_success_k < 0:
                        measure_success_k = 0
                    elif measure_success_k > filaments_max_flow_k:
                        measure_success_k = filaments_max_flow_k
                    gcmd.respond_info(f'measure_data_list: {measure_data_list}, cali_k: {measure_success_k:.5f}')

                elif algorithm in (ALGORITHM_TYPE_OS_ACCEL, ALGORITHM_TYPE_OS_DECEL, ALGORITHM_TYPE_OS_ACCEL_DECEL):
                    decel_data_list = []
                    accel_data_list = []

                    def _unpack_area(result):
                        """Return (decel, accel) area pair; accel is 0 for single mode."""
                        if isinstance(result, tuple):
                            return result[0], result[1]
                        return result, 0.0

                    k_min = cali_params['k_min']
                    k_max = cali_params['k_max']
                    filament_parameters = self._filament_parameters.get_filament_parameters(
                        task_config_status['filament_vendor'][extruder_index],
                        task_config_status['filament_type'][extruder_index],
                        task_config_status['filament_sub_type'][extruder_index],
                        extruder.nozzle_diameter,
                        extruder.nozzle_volume_type)
                    filaments_max_flow_k = max(filaments_max_flow_k, k_max)

                    # ---- point 1: default K ----
                    gcmd.respond_info(f'measure k: {filament_default_k:.5f}')
                    r = self._measure_k(extruder, inductance_coil, filament_default_k, cali_params, extruder_dir)
                    d, a = _unpack_area(r)
                    gcmd.respond_info(f'measure area: decel {d:.5f}, accel {a:.5f}')
                    decel_data_list.append((filament_default_k, d))
                    accel_data_list.append((filament_default_k, a))

                    # ---- point 2: k_min ----
                    gcmd.respond_info(f'measure k: {k_min:.5f}')
                    r = self._measure_k(extruder, inductance_coil, k_min, cali_params, extruder_dir)
                    d, a = _unpack_area(r)
                    gcmd.respond_info(f'measure area: decel {d:.5f}, accel {a:.5f}')
                    decel_data_list.append((k_min, d))
                    accel_data_list.append((k_min, a))

                    # ---- point 3: k_max ----
                    gcmd.respond_info(f'measure k: {k_max:.5f}')
                    r = self._measure_k(extruder, inductance_coil, k_max, cali_params, extruder_dir)
                    d, a = _unpack_area(r)
                    gcmd.respond_info(f'measure area: decel {d:.5f}, accel {a:.5f}')
                    decel_data_list.append((k_max, d))
                    accel_data_list.append((k_max, a))

                    # ---- point 4: midpoint of k_min and k_max ----
                    k_mid = (k_min + k_max) / 2.0
                    gcmd.respond_info(f'measure k: {k_mid:.5f}')
                    r = self._measure_k(extruder, inductance_coil, k_mid, cali_params, extruder_dir)
                    d, a = _unpack_area(r)
                    gcmd.respond_info(f'measure area: decel {d:.5f}, accel {a:.5f}')
                    decel_data_list.append((k_mid, d))
                    accel_data_list.append((k_mid, a))

                    # ---- fit & decide ----
                    calc_decel_k, calc_accel_k = self._calculate_os_linear_fitting_zero_crossing(
                        decel_data_list, accel_data_list, default_k=filament_default_k)
                    measure_success_k = filament_default_k
                    if algorithm == ALGORITHM_TYPE_OS_ACCEL_DECEL:
                        measure_success_k = (calc_decel_k + calc_accel_k) / 2.0
                    elif algorithm == ALGORITHM_TYPE_OS_DECEL:
                        measure_success_k = calc_decel_k
                    elif algorithm == ALGORITHM_TYPE_OS_ACCEL:
                        measure_success_k = calc_accel_k
                    else:
                        logging.error(f'unknown algorithm: {algorithm}')
                        measure_success_k = filament_default_k

                    if measure_success_k < 0:
                        measure_success_k = 0
                    elif measure_success_k > filaments_max_flow_k:
                        measure_success_k = filaments_max_flow_k
                    gcmd.respond_info(f'decel_data_list: {decel_data_list}, accel_data_list: {accel_data_list}')
                    gcmd.respond_info(f'calc_decel_k: {calc_decel_k:.5f}, calc_accel_k: {calc_accel_k:.5f}, select_k: {measure_success_k:.5f}')

            except AbortCalibration as e:
                if self._abort_reason == ABORT_REASON_FILAMENT_RUNOUT:
                    raise gcmd.error(
                            message = f'e{extruder_index}_filament runout',
                            action = 'pause',
                            id = 523,
                            index = extruder_index,
                            code = 0,
                            oneshot = 0,
                            level = 2,
                            proactive_report = 0)
                elif self._abort_reason == ABORT_REASON_FILAMENT_TANGLED:
                    raise gcmd.error(
                            message = 'detect filament tangled!',
                            action = 'pause',
                            id = 523,
                            index = extruder_index,
                            code = 38,
                            oneshot = 1,
                            level = 2,
                            proactive_report = 0)
                else:
                    gcmd.respond_info(f'abort calibration: {e}')

            except Exception as e:
                raise gcmd.error(
                        message = f'error: {e}',
                        action = 'pause',
                        id = 523,
                        index = extruder_index,
                        code = 9000,
                        oneshot = 1,
                        level = 2)

            finally:
                # notify other objects to end flow calibration
                self._printer.send_event('flow_calibration:end')
                virtual_sdcard = self._printer.lookup_object('virtual_sdcard', None)
                # measure success
                if not self._abort_calibration and measure_success_k != None:
                    measure_success_k = round(measure_success_k, 6)
                    gcmd.respond_info(f'Got pressure advance: {measure_success_k}')
                    self._set_pressure_advance(extruder, measure_success_k, backup_st)
                    if virtual_sdcard is not None:
                        estepper = extruder.extruder_stepper
                        virtual_sdcard.record_pl_print_pressure_advance({estepper.name: [estepper.pressure_advance, estepper.pressure_advance_smooth_time]})
                    self._current_k[extruder.get_name()] = measure_success_k
                    self._save_config()

                    if print_stats and print_stats.state == 'printing':
                        self._calibrated_in_printing[extruder.get_name()] = True
                    self._end_of_calibration(extruder)

                # measure failure
                else:
                    # out of range
                    if self._abort_reason == ABORT_REASON_OUT_OF_RANGE:
                        measure_success_k = filament_default_k
                        gcmd.respond_info(f'flow k is out of range, use default value:{filament_default_k}')
                        self._set_pressure_advance(extruder, measure_success_k, backup_st)
                        if virtual_sdcard is not None:
                            estepper = extruder.extruder_stepper
                            virtual_sdcard.record_pl_print_pressure_advance({estepper.name: [estepper.pressure_advance, estepper.pressure_advance_smooth_time]})
                        self._current_k[extruder.get_name()] = measure_success_k
                        self._save_config()
                        if print_stats and print_stats.state == 'printing':
                            self._calibrated_in_printing[extruder.get_name()] = True
                        self._end_of_calibration(extruder)

                self._abort_calibration = False
                self._abort_reason = None
                self._gcode.run_script_from_command("MOVE_TO_XY_IDLE_POSITION_EXTRUDER")
                self._toolhead.wait_moves()
                pheaters.set_temperature(extruder.get_heater(), 0)

        finally:
            if machine_state_manager is not None:
                cur_sta = machine_state_manager.get_status()
                if str(cur_sta["main_state"]) == "PRINTING":
                    self._gcode.run_script_from_command("SET_ACTION_CODE ACTION=IDLE")
                elif str(cur_sta["main_state"]) == "FLOW_CALIBRATION":
                    self._gcode.run_script_from_command("SET_MAIN_STATE MAIN_STATE=IDLE")

    cmd_ACCEL_TIME_MEASURE_help = 'measure acceleration time of specified axis'
    def cmd_ACCEL_TIME_MEASURE(self, gcmd):
        axis = gcmd.get('AXIS')
        if self._bg_client is None:
            self._bg_client = self.start_measure_acceleration_time(axis)
            gcmd.respond_info("acceleration measurements started")
            return
        # End measurements
        name = gcmd.get("NAME", time.strftime("%m%d_%H%M"))
        if not name.replace('-', '').replace('_', '').isalnum():
            raise gcmd.error("Invalid NAME parameter")
        bg_client = self._bg_client
        self._bg_client = None
        bg_client.finish_measurements()
        # Write data to file
        vsd = self._printer.lookup_object('virtual_sdcard', None)
        if vsd is None:
            gcmd.respond_info("No virtual_sdcard dir to save frequency_data data")
            data_path = pathlib.Path('/userdata/gcodes/frequency_data')
        else:
            data_path = pathlib.Path(f'{vsd.sdcard_dirname}/frequency_data')
        if not os.path.exists(data_path):
            os.makedirs(data_path)
        filename = data_path.joinpath("accelts-%s-%s.csv" % (str(axis), name))
        bg_client.write_to_file(filename)

        gcmd.respond_info("Writing raw accel time data to %s file"
                          % (filename,))

    def cmd_FLOW_MEASURE_K(self, gcmd):
        extruder_index = self._toolhead.get_extruder().extruder_index
        task_config_status = self._task_config.get_status()
        extruder = self._toolhead.get_extruder()
        extruder_index = extruder.extruder_index
        nozzle_diameter = extruder.nozzle_diameter
        nozzle_volume_type = extruder.nozzle_volume_type
        task_config_status = self._task_config.get_status()
        filament_parameters = self._filament_parameters.get_filament_parameters(
                                            task_config_status['filament_vendor'][extruder_index],
                                            task_config_status['filament_type'][extruder_index],
                                            task_config_status['filament_sub_type'][extruder_index],
                                            nozzle_diameter,
                                            nozzle_volume_type)
        builtin_flow_temp = filament_parameters['print_temp']
        builtin_flow_accel = filament_parameters['accel']
        builtin_flow_slow_v = filament_parameters['slow_v']
        builtin_flow_fast_v = filament_parameters['fast_v']
        builtin_flow_k_min = filament_parameters['flow_k_min']
        builtin_flow_k_max = filament_parameters['flow_k_max']
        builtin_flow_k = filament_parameters['flow_k']

        temperature = gcmd.get_int('TEMP', builtin_flow_temp)
        self._abort_calibration = False
        self._abort_reason = None

        algorithm = gcmd.get('ALGORITHM', ALGORITHM_TYPE_LINEAR_FITTING)
        os_count = gcmd.get_int('OS_COUNT', 20, minval=1, maxval=100)

        _area_algo_map = {
            ALGORITHM_TYPE_OS_ACCEL:       (AERA_CALC_MODE_OS, os_count),
            ALGORITHM_TYPE_OS_DECEL:       (AERA_CALC_MODE_OS, os_count),
            ALGORITHM_TYPE_OS_ACCEL_DECEL: (AERA_CALC_MODE_OS, os_count),
        }
        _algo_calc_mode, _algo_sample_count = _area_algo_map.get(algorithm, (AERA_CALC_MODE_ORIGINAL, 0))

        fast_v = gcmd.get_float('FASTV', builtin_flow_fast_v, minval=0)
        slow_v = gcmd.get_float('SLOWV', builtin_flow_slow_v, minval=0)
        start_vel = gcmd.get_float('STARTV', (fast_v + slow_v) / 2.0, minval=0)
        accel = gcmd.get_float('ACCEL', builtin_flow_accel, minval=5)

        _ramp_dist = (fast_v**2 - slow_v**2) / (2.0 * accel)
        flow_start_d = max(start_vel * 1, 3)
        # flow_slow_d = max(slow_v * 1.0 + _ramp_dist, 0.5)
        # flow_fast_d = max(fast_v * 1.0 + _ramp_dist, 0.8)
        flow_slow_d = max(slow_v * 0.5 , 0.5)
        flow_fast_d = max(fast_v * 0.5 + 2 * _ramp_dist, 0.8)

        start_dist = gcmd.get_float('STARTD', flow_start_d, minval=0)
        slow_dist = gcmd.get_float('SLOWD', flow_slow_d, minval=0)
        fast_dist = gcmd.get_float('FASTD', flow_fast_d, minval=0)

        cali_params = {
            'k_min': gcmd.get_float('MIN', builtin_flow_k_min),
            'k_max': gcmd.get_float('MAX', builtin_flow_k_max),
            'k_step': gcmd.get_float('STEP', self._env['k_step']),
            'start_vel': start_vel,
            'start_dist': start_dist,
            'slow_vel': slow_v,
            'slow_dist': slow_dist,
            'fast_dist': fast_dist,
            'fast_vel': fast_v,
            'accel': accel,
            'loop': gcmd.get_int('LOOP', self._env['loop']),
            'temp': temperature,
            'calc_mode': _algo_calc_mode,
            'os_sample_count': _algo_sample_count
        }

        gcmd.respond_info("[flow_measure_k] calib_param: %s \r\n" % (str(cali_params)))

        # check if target extruder is current extruder?
        extruder = self._toolhead.get_extruder()
        estepper = extruder.extruder_stepper
        backup_st = estepper.config_smooth_time
        inductance_coil_name = f'inductance_coil {extruder.get_name()}'
        self._toolhead.get_last_move_time()
        try:
            pheaters = self._printer.lookup_object('heaters')
            inductance_coil_wrapper = self._printer.lookup_object(inductance_coil_name)
            status = extruder.get_extruder_activate_status()
            retry_extruder_id = extruder.check_allow_retry_switch_extruder()
            info = status[0]
            if info[1] != 0 and retry_extruder_id != extruder.extruder_num:
                raise gcmd.error(f'extruder {extruder.get_name()} is not activated!')
        except self._printer.config_error as e:
            raise gcmd.error(str(e))

        try:
            # move to extrusion position before heating nozzle, avoid dripping on the bed
            self._gcode.run_script_from_command("MOVE_TO_DISCARD_FILAMENT_POSITION")

            gcmd.respond_info(f'start flow calibration for {extruder.get_name()}')
            gcmd.respond_info(f'start heating heater to {temperature} degre')
            pheaters.set_temperature(extruder.get_heater(), temperature, True)

            # start measuring inductance coil frequency
            gcmd.respond_info(f'start measuring frequency')
            inductance_coil = inductance_coil_wrapper.sensor

            gcmd.respond_info(f'start extruding')

            k_min = int(cali_params['k_min'] * 1000)
            k_max = int(cali_params['k_max'] * 1000)
            k_step = int(cali_params['k_step'] * 1000)

            # prepaire direcotry for data
            vsd = self._printer.lookup_object('virtual_sdcard', None)
            if vsd is None:
                gcmd.respond_info("No virtual_sdcard dir to save frequency_data data")
                data_path = pathlib.Path('/userdata/gcodes/frequency_data/flow_test')
            else:
                data_path = pathlib.Path(f'{vsd.sdcard_dirname}/frequency_data/flow_test')
            if not os.path.exists(data_path):
                os.makedirs(data_path)
            extruder_dir = data_path.joinpath(f'{time.strftime("%m%d-%H%M")}_{extruder.get_name()}')
            if not os.path.exists(extruder_dir):
                os.makedirs(extruder_dir)
            else:
                logging.info(f'frequency_data dir {extruder_dir} already exists')
                extruder_dir = data_path.joinpath(f'{time.strftime("%m%d-%H%M")}_{extruder.get_name()}_{random.randint(0, 10000)}')
            # notify other objects to start flow calibration
            self._printer.send_event('flow_calibration:begin')
            gcmd.respond_info(f'k min: {k_min/1000:.3f}, max: {k_max/1000:.3f}, step: {k_step/1000:.3f}')
            for k in range(k_min, k_max, k_step):
                float_k = round(k / 1000, 3)
                area = self._measure_k(extruder, inductance_coil, float_k, cali_params, extruder_dir)
                if isinstance(area, tuple):
                    gcmd.respond_info(f'k{float_k:.3f}: decel={area[0]:.3f}, accel={area[1]:.3f}')
                else:
                    gcmd.respond_info(f'k{float_k:.3f}: area={area:.3f}')
        except AbortCalibration as e:
            gcmd.respond_info(f'abort calibration')
        self._set_pressure_advance(extruder, DEFAULT_K[extruder.get_name()], backup_st)
        if not self._abort_calibration:
            self._end_of_calibration(extruder)
        self._abort_calibration = False
        self._abort_reason = None
        # notify other objects to end flow calibration
        self._printer.send_event('flow_calibration:end')
        pheaters.set_temperature(extruder.get_heater(), 0)

def load_config(config):
    return FlowCalibrator(config)
