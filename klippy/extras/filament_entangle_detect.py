import logging, os
from . import print_task_config

CHECK_ENTANGLE_INTERVAL                     = 0.1
ENTANGLE_DETECT_LENGTH_DEFAULT              = 6.0
ENTANGLE_DETECT_LENGTH_DEFAULT_SOFT         = 120.0
ENTANGLE_DETECT_LENGTH_DEFAULT_TPU_85       = 180.0
ENTANGLE_DETECT_LENGTH_DEFAULT_TPU_90       = 120.0
ENTANGLE_DETECT_LENGTH_DEFAULT_TPU_95       = 60.0
ENTANGLE_DETECT_FACTOR                      = 1.0
ENTANGLE_DETECT_MIN_CNT                      = 6

ENTANGLE_GLOBAL_SENSITIVITY_HIGH            = 1.0
ENTANGLE_GLOBAL_SENSITIVITY_MEDIUM          = 1.5
ENTANGLE_GLOBAL_SENSITIVITY_LOW             = 3.0

POSTFIX_CONFIG_FILE ='_entangle.json'
DEFAULT_CONFIG = {
    'detect_factor': ENTANGLE_DETECT_FACTOR,
}

class FilamentEntangleDetect:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')

        self.name = config.get_name().split()[-1]
        self.extruder_name = config.get('extruder')
        self.filament_feed_name = config.get('filament_feed')
        self.skip_length = config.getfloat('skip_length', 20., above=0.)

        self.extruder = None
        self.extruder_index = None
        self.check_entangle_timer = None
        self.estimated_print_time = None
        self.filament_feed_module = None
        self.filament_feed_channel = None
        self.print_task_config = None
        self.print_stats = None
        self.init_ok = False
        self.last_position = 0
        self.last_wheel_counts = 0
        self.last_wheel_2_counts = 0
        self.skip_check_flag = False
        self.skip_length_remained = self.skip_length
        self.detection_length = ENTANGLE_DETECT_LENGTH_DEFAULT
        self.last_log_time = 0

        config_dir = self.printer.get_snapmaker_config_dir()
        config_name = self.name + POSTFIX_CONFIG_FILE
        self.config_path = os.path.join(config_dir, config_name)
        self.config = self.printer.load_snapmaker_config_file(self.config_path,
                                                              DEFAULT_CONFIG,
                                                              create_if_not_exist=True)
        self._is_factory_mode = os.path.exists('/oem/.factory')

        self.gcode.register_mux_command(
            "SET_FILAMENT_ENTANGLE_DETECT_FACTOR", "SENSOR", self.name,
            self.cmd_SET_FILAMENT_ENTANGLE_DETECT_FACTOR)

        self.printer.register_event_handler('klippy:ready',
                self._handle_ready)
        self.printer.register_event_handler('klippy:shutdown',
                self._handle_shutdown)

        self.printer.register_event_handler('print_stats:start',
                self._handle_start_print_job)
        self.printer.register_event_handler('print_stats:stop',
                self._handle_stop_print_job)
        self.printer.register_event_handler('print_stats:paused',
                self._handle_pause_print_job)
        self.printer.register_event_handler('print_task_config:set_entangle_detect',
                self._handle_set_entangle_detect)

    def _handle_ready(self):
        self.extruder = self.printer.lookup_object(self.extruder_name, None)
        self.estimated_print_time = self.printer.lookup_object('mcu').estimated_print_time
        self.filament_feed_module = self.printer.lookup_object(f"filament_feed {self.filament_feed_name}", None)
        self.print_task_config = self.printer.lookup_object("print_task_config", None)
        self.exception_manager = self.printer.lookup_object('exception_manager', None)
        self.print_stats = self.printer.lookup_object('print_stats', None)
        if self.extruder is None or self.filament_feed_module is None or \
                self.print_task_config is None or self.exception_manager is None or\
                self.print_stats is None:
            self.init_ok = False
            return
        else:
            self.init_ok = True

        self.extruder_index = self.extruder.extruder_index
        if self.filament_feed_module.filament_ch[0] == self.extruder_index:
            self.filament_feed_channel = 0
        else:
            self.filament_feed_channel = 1

        self.check_entangle_timer = self.reactor.register_timer(self._check_entangle_event)

    def _handle_shutdown(self):
        self.reactor.update_timer(self.check_entangle_timer, self.reactor.NEVER)
        self.reactor.unregister_timer(self.check_entangle_timer)

    def _handle_start_print_job(self):
        if self.print_task_config.print_task_config['filament_soft'][self.extruder_index] == True:
            self.detection_length = ENTANGLE_DETECT_LENGTH_DEFAULT_SOFT
            if self.print_task_config.print_task_config['filament_type'][self.extruder_index] == 'TPU':
                if self.print_task_config.print_task_config['filament_sub_type'][self.extruder_index].startswith('90'):
                    self.detection_length = ENTANGLE_DETECT_LENGTH_DEFAULT_TPU_90
                elif self.print_task_config.print_task_config['filament_sub_type'][self.extruder_index].startswith('95'):
                    self.detection_length = ENTANGLE_DETECT_LENGTH_DEFAULT_TPU_95
                elif self.print_task_config.print_task_config['filament_sub_type'][self.extruder_index].startswith('85'):
                    self.detection_length = ENTANGLE_DETECT_LENGTH_DEFAULT_TPU_85
        else:
            self.detection_length = ENTANGLE_DETECT_LENGTH_DEFAULT
        self.last_position = self._get_extruder_pos()
        self.skip_length_remained = self.skip_length
        self.last_wheel_counts = self.filament_feed_module.wheel[self.filament_feed_channel].get_counts()
        self.last_wheel_2_counts = self.filament_feed_module.wheel_2[self.filament_feed_channel].get_counts()
        self.reactor.update_timer(self.check_entangle_timer, self.reactor.monotonic() + 0.2 + 0.02 * self.extruder_index)
    def _handle_stop_print_job(self):
        self.reactor.update_timer(self.check_entangle_timer, self.reactor.NEVER)

    def _handle_pause_print_job(self):
        self.reactor.update_timer(self.check_entangle_timer, self.reactor.NEVER)

    def _handle_set_entangle_detect(self, enable):
        if enable:
            self.skip_length_remained = self.skip_length
        self.last_position = self._get_extruder_pos()
        self.last_wheel_counts = self.filament_feed_module.wheel[self.filament_feed_channel].get_counts()
        self.last_wheel_2_counts = self.filament_feed_module.wheel_2[self.filament_feed_channel].get_counts()

    def _need_to_check_entanglement(self):
        try:
            if self.init_ok == False:
                return False

            if self.skip_check_flag == True:
                return False

            if self.print_task_config.print_task_config['filament_entangle_detect'] == False:
                return False

            if self.print_stats.get_status(self.reactor.monotonic())["state"] != 'printing':
                return False

            feed_module_status = self.filament_feed_module.get_status()
            if self.extruder_index == 0:
                feed_module_status = feed_module_status[self.extruder_name + "0"]
            else:
                feed_module_status = feed_module_status[self.extruder_name]
            if feed_module_status['module_exist'] == False or \
                    feed_module_status['disable_auto'] == True or \
                    feed_module_status['filament_detected'] == False:
                return False
        except Exception as e:
            logging.error("[filament_entangle_detect] %s", str(e))
            return False

        return True

    def _get_extruder_pos(self):
        print_time = self.estimated_print_time(self.reactor.monotonic())
        position = self.extruder.find_past_position(print_time)
        return position

    def _check_entangle_event(self, eventtime):
        if self._need_to_check_entanglement() == False:
            return self.reactor.monotonic() + CHECK_ENTANGLE_INTERVAL

        new_position = self._get_extruder_pos()
        new_wheel_counts = self.filament_feed_module.wheel[self.filament_feed_channel].get_counts()
        new_wheel_2_counts = self.filament_feed_module.wheel_2[self.filament_feed_channel].get_counts()
        delta_position = new_position - self.last_position
        delta_count = new_wheel_counts - self.last_wheel_counts
        delta_count_2 = new_wheel_2_counts - self.last_wheel_2_counts
        wheel_data_update_time = self.filament_feed_module.wheel[self.filament_feed_channel].get_last_report_time()
        wheel_2_data_update_time = self.filament_feed_module.wheel_2[self.filament_feed_channel].get_last_report_time()

        if self.reactor.monotonic() >= self.last_log_time + 5.0:
            self.last_log_time = self.reactor.monotonic()
            toolhead = self.printer.lookup_object('toolhead', None)
            if toolhead and toolhead.get_extruder().extruder_index == self.extruder_index:
                logging.info(f"[entangle] e[{self.extruder_index}], pos:{new_position}, whl:{new_wheel_counts}, whl2:{new_wheel_2_counts} "
                             f"whl_time:{wheel_data_update_time:0.4f}, whl2_time:{wheel_2_data_update_time:0.4f}, cur_time:{self.reactor.monotonic():0.4f}")

        check_wheel_counts = False
        check_wheel_2_counts = False
        if new_wheel_counts < ENTANGLE_DETECT_MIN_CNT and new_wheel_2_counts < ENTANGLE_DETECT_MIN_CNT:
            return self.reactor.monotonic() + CHECK_ENTANGLE_INTERVAL
        else:
            if new_wheel_counts >= ENTANGLE_DETECT_MIN_CNT:
                check_wheel_counts = True
            if new_wheel_2_counts >= ENTANGLE_DETECT_MIN_CNT:
                check_wheel_2_counts = True

        if self.skip_length_remained >= 0:
            self.skip_length_remained -= delta_position
            self.last_position = new_position
            self.last_wheel_counts = new_wheel_counts
            self.last_wheel_2_counts = new_wheel_2_counts
            return self.reactor.monotonic() + CHECK_ENTANGLE_INTERVAL

        global_detect_sen = ENTANGLE_GLOBAL_SENSITIVITY_HIGH
        if self.print_task_config.print_task_config['filament_entangle_sen'] == print_task_config.ENTANGLE_SENSITIVITY_MEDIUM:
            global_detect_sen = ENTANGLE_GLOBAL_SENSITIVITY_MEDIUM
        elif self.print_task_config.print_task_config['filament_entangle_sen'] == print_task_config.ENTANGLE_SENSITIVITY_LOW:
            global_detect_sen = ENTANGLE_GLOBAL_SENSITIVITY_LOW

        if delta_position >= (self.detection_length * self.config['detect_factor'] * global_detect_sen):
            dest_delta_count = int(delta_position / (self.detection_length * self.config['detect_factor'] * global_detect_sen))
            is_tangled = False
            if self._is_factory_mode:
                if check_wheel_counts == True:
                    if delta_count < dest_delta_count:
                        is_tangled = True
                if check_wheel_2_counts == True:
                    if delta_count_2 < dest_delta_count:
                        is_tangled = True
            else:
                if check_wheel_counts == True and check_wheel_2_counts == True:
                    if delta_count < dest_delta_count and delta_count_2 < dest_delta_count:
                        is_tangled = True
                else:
                    if check_wheel_counts == True:
                        if delta_count < dest_delta_count:
                            is_tangled = True
                    if check_wheel_2_counts == True:
                        if delta_count_2 < dest_delta_count:
                            is_tangled = True

            if is_tangled:
                self.printer.send_event("print_stats:update_exception_info",
                                        523,
                                        self.extruder_index,
                                        38,
                                        "detect filament tangled!",
                                        2)
                pause_resume = self.printer.lookup_object('pause_resume')
                pause_resume.send_pause_command()
                self.printer.send_event("filament_entangle_detect:tangled", self.extruder_index)
                self.gcode.respond_info("[filament_entangle_detect] extruder[%d] filament has tangled!" % (self.extruder_index))
                logging.info(f"[filament_entangle_detect] extruder[{self.extruder_index}], length: {self.detection_length}, factor: {self.config['detect_factor']}, "
                                f"g_factor: {global_detect_sen}, "
                                f"last_pos: {self.last_position:0.4f}, new pos: {new_position:0.4f}, "
                                f"last_cnt: {self.last_wheel_counts}, new_cnt: {new_wheel_counts}, "
                                f"last_cnt2: {self.last_wheel_2_counts}, new_cnt2: {new_wheel_2_counts}, "
                                f"whl_time: {wheel_data_update_time:0.4f}, whl2_time: {wheel_2_data_update_time:0.4f}, cur_time: {self.reactor.monotonic():0.4f}")
                self.last_position = new_position
                self.last_wheel_counts = new_wheel_counts
                self.last_wheel_2_counts = new_wheel_2_counts
                self.exception_manager.raise_exception_async(
                    id = 523,
                    index = self.extruder_index,
                    code = 38,
                    message = "detect filament tangled!",
                    oneshot = 1,
                    level = 2)
                self.gcode.run_script('\nPAUSE\nM400\n')

                return self.reactor.NEVER
            else:
                self.last_position = new_position
                self.last_wheel_counts = new_wheel_counts
                self.last_wheel_2_counts = new_wheel_2_counts

        return self.reactor.monotonic() + CHECK_ENTANGLE_INTERVAL

    def skip_entangle_check(self, skip=False):
        self.last_position = self._get_extruder_pos()
        self.last_wheel_counts = self.filament_feed_module.wheel[self.filament_feed_channel].get_counts()
        self.last_wheel_2_counts = self.filament_feed_module.wheel_2[self.filament_feed_channel].get_counts()
        self.skip_check_flag = bool(skip)

    def get_status(self, eventtime=None):
        return {
            'detect_factor': self.config['detect_factor']
        }

    def cmd_SET_FILAMENT_ENTANGLE_DETECT_FACTOR(self, gcmd):
        detect_factor = gcmd.get_float('DETECT_FACTOR', None, minval=0.5)
        if detect_factor is None:
            raise gcmd.error('[filament_entangle_detect] missing DETECT_FACTOR!')

        self.config['detect_factor'] = detect_factor
        gcmd.respond_info("[filament_entangle_detect] set detect_factor: %f" % (self.config['detect_factor']))
        ret = self.printer.update_snapmaker_config_file(self.config_path, self.config, DEFAULT_CONFIG)
        if not ret:
            raise gcmd.error("save filament_entangle_detect config failed!")

def load_config_prefix(config):
    return FilamentEntangleDetect(config)

