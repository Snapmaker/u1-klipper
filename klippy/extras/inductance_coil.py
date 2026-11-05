import logging, multiprocessing, os, time
import shutil, pathlib
from . import probe, bulk_sensor
from . import probe_inductance_coil

FIXED_TIME_FREQ_CAL_MODE              = 0
FIXED_PULSE_NUM_CAL_MODE              = 1
DEFAULT_FREQ_CAL_CYCLE                = 0
DEFAULT_FREQ_TRG_MODE                 = 0
DEFAULT_INPUT_CAPTURE_OVER_CNT        = 1000
DEFAULT_INPUT_CAPTURE_CAL_TIMEOUT     = 1.0
DEFAULT_INPUT_CAPTURE_TRIGGER_FREQ    = 1200000
DEFAULT_INPUT_CAPTURE_TRIGGER_INVERT  = False

MIN_MSG_TIME  = 0.100
BATCH_UPDATES = 0.100

# max frequency 2MHz
MAX_INDUCTANCE_COIL_FREQUENCY = 2000000
MIN_INDUCTANCE_COIL_FREQUENCY = 1000000

class FrequencyQueryHelper:
    def __init__(self, printer):
        self.printer = printer
        self.is_finished = False
        print_time = printer.lookup_object('toolhead').get_last_move_time()
        self.request_start_time = self.request_end_time = print_time
        self.frequency = []
        self.print_time = []
        self.msgs = []
    def finish_measurements(self):
        logging.info("FrequencyQueryHelper: finish frequency measurements")
        toolhead = self.printer.lookup_object('toolhead')
        self.request_end_time = toolhead.get_last_move_time()
        toolhead.wait_moves()
        self.is_finished = True
    def handle_batch(self, msg):
        if self.is_finished:
            return False
        if len(self.msgs) >= 10000:
            # Avoid filling up memory with too many samples
            return False
        self.msgs.append(msg)
        return True
    def has_valid_samples(self):
        for msg in self.msgs:
            data = msg['data']
            first_sample_time = data[0][0]
            last_sample_time = data[-1][0]
            if (first_sample_time > self.request_end_time
                    or last_sample_time < self.request_start_time):
                continue
            # The time intervals [first_sample_time, last_sample_time]
            # and [request_start_time, request_end_time] have non-zero
            # intersection. It is still theoretically possible that none
            # of the samples from msgs fall into the time interval
            # [request_start_time, request_end_time] if it is too narrow
            # or on very heavy data losses. In practice, that interval
            # is at least 1 second, so this possibility is negligible.
            return True
        return False
    def get_samples(self):
        if not self.msgs:
            return self.print_time, self.frequency
        total = sum([len(m['data']) for m in self.msgs])
        count = 0
        self.print_time = print_time = [None] * total
        self.frequency = frequency = [None] * total
        for msg in self.msgs:
            for samp_time, freq in msg['data']:
                if samp_time < self.request_start_time:
                    continue
                if samp_time > self.request_end_time:
                    break
                print_time[count] = samp_time
                frequency[count] = freq
                count += 1
        del print_time[count:]
        del frequency[count:]
        del self.msgs[:]
        return self.print_time, self.frequency
    def write_to_file(self, filename):
        def write_impl():
            try:
                # Try to re-nice writing process
                os.nice(20)
            except:
                pass
            f = open(filename, 'w+')
            f.write("time,frequency\n")
            print_time, frequency = self.get_samples()
            for t, freq in zip(print_time, frequency):
                f.write("%.4f,%d\n" % (
                    t, freq))
            f.close()
        write_proc = multiprocessing.Process(target=write_impl)
        write_proc.daemon = True
        write_proc.start()

# Helper class for G-Code commands
class FrequencyCommandHelper:
    def __init__(self, config, probe):
        self.printer = config.get_printer()
        self.probe = probe
        self.bg_client = None
        name_parts = config.get_name().split()
        self.base_name = name_parts[0]
        self.name = name_parts[-1]
        self.register_commands(self.name)
    def register_commands(self, name):
        # Register commands
        gcode = self.printer.lookup_object('gcode')
        gcode.register_mux_command("FREQUENCY_MEASURE", "PROBE", name,
                                   self.cmd_FREQUENCY_MEASURE,
                                   desc=self.cmd_FREQUENCY_MEASURE_help)
        gcode.register_mux_command("FREQUENCY_QUERY", "PROBE", name,
                                   self.cmd_FREQUENCY_QUERY,
                                   desc=self.cmd_FREQUENCY_QUERY_help)
    cmd_FREQUENCY_MEASURE_help = "Start/stop frequency messurement of inductance coil"
    def cmd_FREQUENCY_MEASURE(self, gcmd):
        if self.bg_client is None:
            # Start measurements
            self.bg_client = self.probe.start_internal_client()
            gcmd.respond_info("frequency measurements started")
            return
        # End measurements
        name = gcmd.get("NAME", time.strftime("%m%d_%H%M"))
        if not name.replace('-', '').replace('_', '').isalnum():
            raise gcmd.error("Invalid NAME parameter")
        bg_client = self.bg_client
        self.bg_client = None
        bg_client.finish_measurements()
        try:
            vsd = self.printer.lookup_object('virtual_sdcard', None)
            if vsd is None:
                gcmd.respond_info("No virtual_sdcard dir to save frequency_data data")
                data_path = pathlib.Path('/userdata/gcodes/frequency_data')
            else:
                data_path = pathlib.Path(f'{vsd.sdcard_dirname}/frequency_data')
            if not os.path.exists(data_path):
                os.makedirs(data_path)
            filename = data_path.joinpath("frequency-%s-%s.csv" % (self.name, name))
            bg_client.write_to_file(filename)
            gcmd.respond_info("Writing raw frequency data to %s file"
                            % (str(filename),))
        except Exception as e:
            gcmd.error(e)
    cmd_FREQUENCY_QUERY_help = "Query current frequency of inductance coil"
    def cmd_FREQUENCY_QUERY(self, gcmd):
        toolhead = self.printer.lookup_object('toolhead')
        aclient = self.probe.start_internal_client()
        toolhead.dwell(0.2)
        aclient.finish_measurements()
        toolhead.dwell(0.1)
        pt, values = aclient.get_samples()
        if values is None or len(values) == 0:
            raise gcmd.error("No frequency measurements found")
        freq = values[-1]
        t = pt[-1]
        gcmd.respond_info("frequency data: %.4fs: %dHz"
                          % (t, freq))
    cmd_ACCELEROMETER_DEBUG_READ_help = "Query register (for debugging)"

class InductanceCoil:
    def __init__(self, config, mcu):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = config.get_printer().lookup_object('gcode')
        self._mcu = mcu
        self._name = config.get_name().split()[1]
        self._freq_cal_mode = config.getint('freq_cal_mode', minval=0, maxval=1)
        self._freq_cal_cycle = config.getfloat('freq_cal_cycle', 0.001, above=0.)
        self._capture_over_cnt = config.getint('capture_over_cnt', DEFAULT_INPUT_CAPTURE_OVER_CNT)
        self._cal_time_out = config.getfloat('cal_time_out', DEFAULT_INPUT_CAPTURE_CAL_TIMEOUT)
        self._trg_freq_ht = config.getfloat('trg_freq_ht', DEFAULT_INPUT_CAPTURE_TRIGGER_FREQ)
        self._trg_freq_lt = config.getfloat('trg_freq_lt', DEFAULT_INPUT_CAPTURE_TRIGGER_FREQ)
        self._trigger_mode = config.getfloat('trigger_mode', DEFAULT_FREQ_TRG_MODE)
        self._trigger_invert = config.getboolean('trigger_invert', DEFAULT_INPUT_CAPTURE_TRIGGER_INVERT)
        self._max_freq = config.getint('max_freq', 1500000, minval=1)
        self._min_freq = config.getint('min_freq', 1000000, minval=1, maxval=self._max_freq)
        self._cal_window_size = config.getint('cal_window_size', 1, minval=1, maxval=50)
        self._cmd_queue = self._mcu.alloc_command_queue()

        # setup bulk sensor helper, Process messages in batches
        FrequencyCommandHelper(config, self)
        self._data_rate = config.getint('date_rate', 1000)
        chip_smooth = self._data_rate * BATCH_UPDATES * 2
        self.ffreader = bulk_sensor.FixedFreqReader(mcu, chip_smooth, "<I")
        self.batch_bulk = bulk_sensor.BatchBulkHelper(
            self.printer, self._process_batch,
            self._start_measurements, self._finish_measurements, BATCH_UPDATES)
        self.name = config.get_name().split()[-1]
        hdr = ('time', 'frequency')
        self.batch_bulk.add_mux_endpoint("inductance_coil/dump_inductance_coil", "sensor",
                                         self.name, {'header': hdr})
        self.gcode.register_mux_command("SET_TRIG_FREQ", "PROBE", self._name,
                                        self.cmd_SET_TRIG_FREQ,
                                        desc=self.cmd_SET_TRIG_FREQ_help)
        self.gcode.register_mux_command("INDUCTANCE_COIL_QUERY", "PROBE", self._name,
                                        self.cmd_INDUCTANCE_COIL_QUERY,
                                        desc=self.cmd_INDUCTANCE_COIL_QUERY_help)

        self._mcu.register_config_callback(self._build_config)

    def _build_config(self):
        if self._mcu.is_fileoutput():
            return
        self._oid = self._mcu.create_oid()

        self._mcu.add_config_cmd(
            "inductance_coil_config oid=%d cal_mode=%u capture_over_cnt=%u freq_cal_cycle=%u cal_time_out=%u"
            " trigger_mode=%u trigger_invert=%u trg_freq_ht=%u trg_freq_lt=%u cal_window_size=%u"
            % (self._oid, self._freq_cal_mode, self._capture_over_cnt, self._freq_cal_cycle*1000000, self._cal_time_out*1000000,
               self._trigger_mode, self._trigger_invert, self._trg_freq_ht, self._trg_freq_lt, self._cal_window_size))

        self._mcu.add_config_cmd(
            "query_inductance_coil oid=%d rest_ticks=%u"
            % (self._oid, 0))

        self.set_trig_freq_cmd = self._mcu.lookup_command(
            "virtual_gpio_trigger oid=%c absolute_mode=%u trigger_mode=%u trigger_invert=%u trg_freq_ht=%u trg_freq_lt=%u force_update=%u")

        self.set_trig_freq_with_timer_cmd = self._mcu.lookup_command(
            "virtual_gpio_trigger_with_timer oid=%c absolute_mode=%u trigger_mode=%u trigger_invert=%u trg_freq_ht=%u trg_freq_lt=%u force_update=%u clock=%u")

        self.query_inductance_coil_cmd = self._mcu.lookup_command(
            "query_inductance_coil oid=%c rest_ticks=%u", cq=None)
        self.ffreader.setup_query_command("query_inductance_coil_status oid=%c",
                                          oid=self._oid, cq=None)

        self.query_inductance_coil_info_cmd = self._mcu.lookup_query_command(
            "query_inductance_coil_config_info oid=%c",
            "inductance_coil_info oid=%c cal_mode=%u capture_over_cnt=%u freq_cal_cycle=%u cal_time_out=%u"
            " trigger_mode=%u trigger_invert=%u trg_freq_ht=%u trg_freq_lt=%u capture_freq=%u virtual_gpio=%u",
            oid=self._oid, cq=self._cmd_queue)

    def _cmd_set_trig_freq(self, freq_ht, freq_lt, absolute_mode=True, trigger_mode=0, trigger_invert=False, force_update=True):
        if self._mcu.is_fileoutput():
            return
        self.set_trig_freq_cmd.send([self._oid, absolute_mode, trigger_mode, trigger_invert, freq_ht, freq_lt, force_update])

    def _cmd_set_trig_freq_with_timer(self, freq_ht, freq_lt, clock, absolute_mode=True, trigger_mode=0, trigger_invert=False, force_update=True):
        if self._mcu.is_fileoutput():
            return
        self.set_trig_freq_with_timer_cmd.send([self._oid, absolute_mode, trigger_mode, trigger_invert, freq_ht, freq_lt, force_update, clock])

    def _cmd_query_trig_freq_info(self):
        if self._mcu.is_fileoutput():
            return {'capture_freq': 1400000, 'virtual_gpio': 0}
        param = self.query_inductance_coil_info_cmd.send([self._oid])
        return param

    def _convert_samples(self, samples):
        count = 0
        for ptime, freq in samples:
            if freq > MAX_INDUCTANCE_COIL_FREQUENCY or \
                freq < MIN_INDUCTANCE_COIL_FREQUENCY:
                self.last_error_count += 1
            samples[count] = (round(ptime, 6), freq)
            count += 1
        del samples[count:]

    def _process_batch(self, eventtime):
        samples = self.ffreader.pull_samples()
        self._convert_samples(samples)
        if not samples:
            return {}
        # if self.calibration is not None:
        #     self.calibration.apply_calibration(samples)
        return {'data': samples, 'errors': self.last_error_count,
                'overflows': self.ffreader.get_last_overflows()}

    def _start_measurements(self):
        # Start bulk reading
        rest_ticks = self._mcu.seconds_to_clock(1 / self._data_rate)
        self.query_inductance_coil_cmd.send([self._oid, rest_ticks])
        logging.info("Inductance coil starting '%s' measurements", self.name)
        # Initialize clock tracking
        self.ffreader.note_start()
        self.last_error_count = 0

    def _finish_measurements(self):
        # Halt bulk reading
        self.query_inductance_coil_cmd.send_wait_ack([self._oid, 0])
        self.ffreader.note_end()
        logging.info("Inductance coil finished '%s' measurements", self.name)

    def check_coil_freq(self):
        param = self._cmd_query_trig_freq_info()
        if param['capture_freq'] > self._max_freq or param['capture_freq'] < self._min_freq:
            return False, param['capture_freq']
        return True, param['capture_freq']

    def get_coil_freq(self):
        param = self._cmd_query_trig_freq_info()
        return param['capture_freq']

    cmd_SET_TRIG_FREQ_help = 'Setting the trigger frequency of the inductance coil'
    def cmd_SET_TRIG_FREQ(self, gcmd):
        absolute_trig = gcmd.get_int("ABSOLUTE", 0, minval=0, maxval=1)
        trigger_invert = gcmd.get_int("TRIGGER_INVERT", 0, minval=0, maxval=1)
        trigger_mode = gcmd.get_int("TRIGGER_MODE", 0, minval=0, maxval=1)
        trigger_freq_ht = 0
        trigger_freq_lt = 0
        params = gcmd.get_command_parameters()

        # Unidirectional Trigger
        if trigger_mode == 0:
            if not ('TRIGGER_FREQ_HT' in params):
                self.gcode.respond_info("Error: parameter must contain TRIGGER_FREQ_HT")
                return
            else:
                trigger_freq_ht = gcmd.get_int("TRIGGER_FREQ_HT", 0)
        else:
            # Bidirectional Trigger
            if not ('TRIGGER_FREQ_HT' in params):
                self.gcode.respond_info("Error: parameter must contain TRIGGER_FREQ_HT")
                return
            else:
                trigger_freq_ht = gcmd.get_int("TRIGGER_FREQ_HT", 0)
                if absolute_trig:
                    if not ('TRIGGER_FREQ_LT' in params):
                        self.gcode.respond_info("Error: TRIGGER_FREQ_LT is not configured")
                        return
                    trigger_freq_lt = gcmd.get_int("TRIGGER_FREQ_LT", 0)
                else:
                    if not ('TRIGGER_FREQ_LT' in params):
                        trigger_freq_ht = abs(trigger_freq_ht)
                        trigger_freq_lt = -trigger_freq_ht
                    else:
                        trigger_freq_lt = gcmd.get_int("TRIGGER_FREQ_LT", 0)

        if absolute_trig:
            trigger_freq_ht = max(0, trigger_freq_ht)
            trigger_freq_lt = max(0, trigger_freq_lt)

        if trigger_mode and trigger_freq_ht < trigger_freq_lt:
            self.gcode.respond_info("Error: Bidirectional Trigger TRIGGER_FREQ_HT must be greater than TRIGGER_FREQ_LT")
            return

        self._cmd_set_trig_freq(trigger_freq_ht, trigger_freq_lt, absolute_trig, trigger_mode, trigger_invert)

    cmd_INDUCTANCE_COIL_QUERY_help = 'QUERY inductance coil information'
    def cmd_INDUCTANCE_COIL_QUERY(self, gcmd):
        param = self._cmd_query_trig_freq_info()
        show_all = gcmd.get_int("SHOW_ALL", 0)
        if show_all:
            self.gcode.respond_info("cal_mode: %d capture_over_cnt: %d freq_cal_cycle: %f cal_time_out: %f trigger_mode: %d"
                                    " trigger_invert: %d trg_freq_ht: %d trg_freq_lt: %d capture_freq=%u virtual_gpio=%u"
                                    % (param['cal_mode'], param['capture_over_cnt'], param['freq_cal_cycle']/1000000,
                                    param['cal_time_out']/1000000, param['trigger_mode'], param['trigger_invert'],
                                    param['trg_freq_ht'], param['trg_freq_lt'], param['capture_freq'], param['virtual_gpio']))
        else:
            self.gcode.respond_info("capture_freq: %u virtual_gpio: %s" % (param['capture_freq'], ["open", "TRIGGERED"][not not param['virtual_gpio']]))

    def start_internal_client(self):
        aqh = FrequencyQueryHelper(self.printer)
        self.batch_bulk.add_client(aqh.handle_batch)
        return aqh

class InductanceCoilEndstopWrapper:
# Endstop wrapper that enables probe specific features
    def __init__(self, config):
        self.name = config.get_name()
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
        pin = config.get('pin')
        pin_params = ppins.lookup_pin(pin, can_invert=True, can_pullup=True)
        mcu = pin_params['chip']
        # Currently only supports AT32415 PA0
        self.sensor = InductanceCoil(config, mcu)
        self.mcu_endstop = mcu.setup_pin('pulse_endstop', pin_params)
        self.printer.register_event_handler('klippy:mcu_identify',
                                            self._handle_mcu_identify)
        # Wrappers
        self.get_mcu = self.mcu_endstop.get_mcu
        self.add_stepper = self.mcu_endstop.add_stepper
        self.get_steppers = self.mcu_endstop.get_steppers
        self.home_start = self.mcu_endstop.home_start
        self.home_wait = self.mcu_endstop.home_wait
        self.query_endstop = self.mcu_endstop.query_endstop
        # multi probes state
        self.multi = 'OFF'
    def _handle_mcu_identify(self):
        kin = self.printer.lookup_object('toolhead').get_kinematics()
        for stepper in kin.get_steppers():
            if stepper.is_active_axis('x') or stepper.is_active_axis('y') or stepper.is_active_axis('z'):
                self.add_stepper(stepper)
    def _raise_probe(self):
        toolhead = self.printer.lookup_object('toolhead')
        start_pos = toolhead.get_position()
        self.deactivate_gcode.run_gcode_from_command()
        if toolhead.get_position()[:3] != start_pos[:3]:
            raise self.printer.command_error(
                "Toolhead moved during probe activate_gcode script")
    def _lower_probe(self):
        toolhead = self.printer.lookup_object('toolhead')
        start_pos = toolhead.get_position()
        self.activate_gcode.run_gcode_from_command()
        if toolhead.get_position()[:3] != start_pos[:3]:
            raise self.printer.command_error(
                "Toolhead moved during probe deactivate_gcode script")
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

def load_config_prefix(config):
    if config.get_printer().lookup_object('probe', None) is None:
        config.get_printer().add_object('probe', probe_inductance_coil.PrinterProbe(config))
        return config.get_printer().lookup_object('probe', None).mcu_probe
    else:
        ind_probe = InductanceCoilEndstopWrapper(config)
    return ind_probe
