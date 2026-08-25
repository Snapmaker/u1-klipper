import logging, os, copy
from .jsonrpc import *

TIME_INTERVAL               = 3.5
REQUEST_TIMEOUT             = 5.0

CLEAN_BED_THRESHOLD_HIGH    = 0.80
CLEAN_BED_THRESHOLD_LOW     = 0.83
RESIDUE_THRESHOLD_HIGH      = 0.80
RESIDUE_THRESHOLD_LOW       = 0.83
NOODLE_THRESHOLD_HIGH       = 0.80
NOODLE_THRESHOLD_LOW        = 0.83
NOZZLE_THRESHOLD_HIGH       = 0.50
NOZZLE_THRESHOLD_LOW        = 0.20

CLEAN_BED_CHECK_WINDOW      = 3
NOODLE_CHECK_WINDOW         = 10
RESIDUE_CHECK_WINDOW        = 10
CHECK_WINDOW_MIN            = 1
CHECK_WINDOW_MAX            = 20

CONFIRM_DIRTY_BED           = 1
CONFIRM_NOODLE              = 2
CONFIRM_RESIDUE             = 3
CONFIRM_DIRTY_NOZZLE        = 4

SENSITIVITY_HIGH            = 'high'
SENSITIVITY_LOW             = 'low'
SENSITIVITY_VALUE_HIGH      = 0.2
SENSITIVITY_VALUE_LOW       = 0.5

DETECT_STATUS_FIRST_DETECT  = 'first'
DETECT_STATUS_LAST_DETECT   = 'last'

REQUEST_TOPIC = "camera/request"
RESPONSE_TOPIC = "camera/response"

CONFIG_FILE = "defect_detection.json"
DEFAULT_CONFIG = {
    'main_enable': True,
    "sen_high_factor": SENSITIVITY_VALUE_HIGH,
    'sen_low_factor': SENSITIVITY_VALUE_LOW,
    'clean_bed': {
        'enable': True,
        'check_window': CLEAN_BED_CHECK_WINDOW,
        'sensitivity': SENSITIVITY_LOW,
    },
    'noodle': {
        'enable': True,
        'check_window': NOODLE_CHECK_WINDOW,
        'sensitivity': SENSITIVITY_LOW,
    },
    'residue': {
        'enable': False,
        'check_window': RESIDUE_CHECK_WINDOW,
        'sensitivity': SENSITIVITY_LOW,
    },
    'nozzle': {
        'enable': False,
        'sensitivity': SENSITIVITY_LOW,
    }
}

class DefectDetection:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')

        config_dir = self.printer.get_snapmaker_config_dir()
        config_name = CONFIG_FILE
        self.config_path = os.path.join(config_dir, config_name)
        self.config = self.printer.load_snapmaker_config_file(self.config_path, DEFAULT_CONFIG)

        self.debug_mode = config.getboolean('debug_mode', False)
        self.bed_detect_pos_x = config.getfloat('bed_detect_pos_x', 5.0)
        self.bed_detect_pos_y = config.getfloat('bed_detect_pos_y', 5.0)
        self.bed_detect_probe_distance = config.getfloat('bed_detect_probe_distance', 50.0)
        self.ignore_detect_layer = config.getint('ignore_detect_layer', 30)
        self.clean_bed_threshold_high = config.getfloat('clean_bed_threshold_high', CLEAN_BED_THRESHOLD_HIGH)
        self.clean_bed_threshold_low = config.getfloat('clean_bed_threshold_low', CLEAN_BED_THRESHOLD_LOW)
        self.residue_threshold_high = config.getfloat('residue_threshold_high', RESIDUE_THRESHOLD_HIGH)
        self.residue_threshold_low = config.getfloat('residue_threshold_low', RESIDUE_THRESHOLD_LOW)
        self.noodle_threshold_high = config.getfloat('noodle_threshold_high', NOODLE_THRESHOLD_HIGH)
        self.noodle_threshold_low = config.getfloat('noodle_threshold_low', NOODLE_THRESHOLD_LOW)
        self.nozzle_threshold_high = config.getfloat('nozzle_threshold_high', NOZZLE_THRESHOLD_HIGH)
        self.nozzle_threshold_low = config.getfloat('nozzle_threshold_low', NOZZLE_THRESHOLD_LOW)

        self.mqtt_client = None
        self.last_request_time = 0
        self.check_noodle_result = []
        self.check_residue_result = []
        self.ignore_detect_bed = False
        self.ignore_detect_nozzle = False
        self.ignore_detect_start_layer = -9999999999
        self.is_pause_resume = False
        self.is_detected = False
        self.cavity_led = None
        self.print_stats = None
        self._request_cancel_print = False

        self.gcode.register_command("DEFECT_DETECTION_CONFIG",
                self.cmd_DEFECT_DETECTION_CONFIG)
        self.gcode.register_command("DEFECT_DETECTION_START",
                self.cmd_DEFECT_DETECTION_START)
        self.gcode.register_command("DEFECT_DETECTION_DETECT",
                self.cmd_DEFECT_DETECTION_DETECT)
        self.gcode.register_command("DEFECT_DETECTION_DETECT_BED",
                self.cmd_DEFECT_DETECTION_DETECT_BED)
        self.gcode.register_command("DEFECT_DETECTION_DETECT_NOZZLE",
                self.cmd_DEFECT_DETECTION_DETECT_NOZZLE)
        self.gcode.register_command("DEFECT_DETECT_NOODLE_FIRST",
                self.cmd_DEFECT_DETECT_NOODLE_FIRST)

        self.printer.register_event_handler('klippy:ready',
                self._handle_ready)
        self.printer.register_event_handler('print_stats:start',
                self._handle_start_print_job)
        self.printer.register_event_handler('print_stats:paused',
                self._handle_pause_print_job)
        self.printer.register_event_handler('print_stats:stop',
                self._handle_stop_print_job)
        self.printer.register_event_handler("pause_resume:cancel", self._handle_cancel_print)

        webhooks = self.printer.lookup_object('webhooks', None)
        if webhooks is not None:
            webhooks.register_endpoint("defect_detection/config",
                                            self._handle_webhooks_config)
    def _handle_ready(self):
        self.cavity_led = self.printer.lookup_object('led cavity_led', None)
        self.print_stats = self.printer.lookup_object('print_stats', None)
        self.mqtt_client = self.printer.lookup_object("mqtt", None)
        if self.mqtt_client is None:
            logging.error("[defect_detection]: cannot load necessary objects.")
            return
        self.mqtt_jsonrpc = JSONRPCClient(
                                reactor=self.reactor,
                                transport_type=JSONRPC_TRANSPORT_MQTT,
                                mqtt_client=self.mqtt_client,
                                request_topic=REQUEST_TOPIC,
                                response_topic=RESPONSE_TOPIC,
                                qos=0)
        self.mqtt_jsonrpc.connect()

    def _handle_start_print_job(self):
        self.reset_check_data()
        if self.is_pause_resume == True:
            if self.is_detected == True:
                if self.print_stats and self.print_stats.info_current_layer:
                    self.ignore_detect_start_layer = self.print_stats.info_current_layer
                else:
                    self.ignore_detect_start_layer = -9999999999
            self.is_detected  = False
        else:
            self.ignore_detect_start_layer = -9999999999
            self.ignore_detect_bed = False
            self.ignore_detect_nozzle = False

        self.is_pause_resume = False
        self._request_cancel_print = False

    def _handle_pause_print_job(self):
        self.is_pause_resume = True

    def _handle_stop_print_job(self):
        self.reset_check_data()
        self.ignore_detect_bed = False
        self.ignore_detect_nozzle = False
        self.ignore_detect_start_layer = -9999999999
        self.is_pause_resume = False
        self.is_detected  = False

    def _handle_cancel_print(self):
        self._request_cancel_print = True

    def _handle_webhooks_config(self, web_request):
        main_enable = web_request.get_int('main_enable', None)
        sensitivity = web_request.get_str('sensitivity', None)
        clean_bed_enable = web_request.get_int('clean_bed_enable', None)
        clean_bed_check_window = web_request.get_int('clean_bed_check_window', None)
        clean_bed_sensitivity = web_request.get_str('clean_bed_sensitivity', None)
        noodle_enable = web_request.get_int('noodle_enable', None)
        noodle_check_window = web_request.get_int('noodle_check_window', None)
        noodle_sensitivity = web_request.get_str('noodle_sensitivity', None)
        residue_enable = web_request.get_int('residue_enable', None)
        residue_check_window = web_request.get_int('residue_check_window', None)
        residue_sensitivity = web_request.get_str('residue_sensitivity', None)
        tmp_config = copy.deepcopy(self.config)
        need_turn_on_led = False

        try:
            if main_enable is not None:
                tmp_config['main_enable'] = bool(main_enable)
            if sensitivity is not None:
                if sensitivity not in [SENSITIVITY_HIGH, SENSITIVITY_LOW]:
                    raise ValueError(f"invalid sensitivity: {sensitivity}")
                tmp_config['clean_bed']['sensitivity'] = sensitivity
                tmp_config['noodle']['sensitivity'] = sensitivity
                tmp_config['residue']['sensitivity'] = sensitivity
            if clean_bed_enable is not None:
                tmp_config['clean_bed']['enable'] = bool(clean_bed_enable)
                if tmp_config['clean_bed']['enable'] == True:
                    need_turn_on_led = True
            if clean_bed_check_window is not None:
                clean_bed_check_window = max(clean_bed_check_window, CHECK_WINDOW_MIN)
                clean_bed_check_window = min(clean_bed_check_window, CHECK_WINDOW_MAX)
                tmp_config['clean_bed']['check_window'] = clean_bed_check_window
            if clean_bed_sensitivity is not None and sensitivity is None:
                if clean_bed_sensitivity not in [SENSITIVITY_HIGH, SENSITIVITY_LOW]:
                    raise ValueError(f"invalid clean_bed_sensitivity: {clean_bed_sensitivity}")
                tmp_config['clean_bed']['sensitivity'] = clean_bed_sensitivity
            if noodle_enable is not None:
                tmp_config['noodle']['enable'] = bool(noodle_enable)
                if tmp_config['noodle']['enable'] == True:
                    need_turn_on_led = True
            if noodle_check_window is not None:
                noodle_check_window = max(noodle_check_window, CHECK_WINDOW_MIN)
                noodle_check_window = min(noodle_check_window, CHECK_WINDOW_MAX)
                tmp_config['noodle']['check_window'] = noodle_check_window
            if noodle_sensitivity is not None and sensitivity is None:
                if noodle_sensitivity not in [SENSITIVITY_HIGH, SENSITIVITY_LOW]:
                    raise ValueError(f"invalid noodle_sensitivity: {noodle_sensitivity}")
                tmp_config['noodle']['sensitivity'] = noodle_sensitivity
            if residue_enable is not None:
                tmp_config['residue']['enable'] = bool(residue_enable)
                if tmp_config['residue']['enable'] == True:
                    need_turn_on_led = True
            if residue_check_window is not None:
                residue_check_window = max(residue_check_window, CHECK_WINDOW_MIN)
                residue_check_window = min(residue_check_window, CHECK_WINDOW_MAX)
                tmp_config['residue']['check_window'] = residue_check_window
            if residue_sensitivity is not None and sensitivity is None:
                if residue_sensitivity not in [SENSITIVITY_HIGH, SENSITIVITY_LOW]:
                    raise ValueError(f"invalid residue_sensitivity: {residue_sensitivity}")
                tmp_config['residue']['sensitivity'] = residue_sensitivity

            if tmp_config['main_enable'] == True and need_turn_on_led == True:
                if self.cavity_led and self.print_stats and \
                        (self.print_stats.state == 'printing' or self.print_stats.state == 'paused'):
                    gcmd = self.gcode.create_gcode_command("", "", {'WHITE': 1})
                    self.cavity_led.led_helper.cmd_SET_LED(gcmd)

        except Exception as e:
            logging.error("[defect_detection] wb config failed: %s", str(e))
            return

        else:
            self.reset_check_data()
            self.config = tmp_config
            if not self.printer.update_snapmaker_config_file(self.config_path, self.config, DEFAULT_CONFIG):
                logging.error("[defect_detection] config save failed")

    def reset_check_data(self):
        self.check_noodle_result = []
        self.check_residue_result = []

    def detect_noodle(self, json_obj):
        if self.config['main_enable'] == False:
            return False
        if self.config['noodle']['enable'] == False:
            return False
        if self.debug_mode == False and self.print_stats and self.print_stats.info_current_layer:
            if self.print_stats.info_current_layer - self.ignore_detect_start_layer < self.ignore_detect_layer:
                return False

        if len(self.check_noodle_result) >= self.config['noodle']['check_window']:
            self.check_noodle_result.pop(0)

        if json_obj is None:
            self.check_noodle_result.append(False)
            return False

        probability = json_obj.get("obj_probs", 0)
        detect_threshold = self.noodle_threshold_low
        detect_factor = self.config['sen_low_factor']
        if self.config['noodle']['sensitivity'] == SENSITIVITY_HIGH:
            detect_threshold = self.noodle_threshold_high
            detect_factor = self.config['sen_high_factor']

        if probability >= detect_threshold:
            self.check_noodle_result.append(True)
            logging.info("[defect_detection] detected noodle, times: %d",
                         self.check_noodle_result.count(True))
        else:
            self.check_noodle_result.append(False)
            return False

        if self.check_noodle_result.count(True) >= self.config['noodle']['check_window'] * detect_factor:
            self.check_noodle_result = []
            return True
        else:
            return False

    def detect_residue(self, json_obj):
        if self.config['main_enable'] == False:
            return False
        if self.config['residue']['enable'] == False:
            return False
        if self.debug_mode == False and self.print_stats and self.print_stats.info_current_layer:
            if self.print_stats.info_current_layer - self.ignore_detect_start_layer < self.ignore_detect_layer:
                return False

        if len(self.check_residue_result) >= self.config['residue']['check_window']:
            self.check_residue_result.pop(0)

        if json_obj is None:
            self.check_residue_result.append(False)
            return False

        probability = json_obj.get("obj_probs", 0)
        detect_threshold = self.residue_threshold_low
        detect_factor = self.config['sen_low_factor']
        if self.config['residue']['sensitivity'] == SENSITIVITY_HIGH:
            detect_threshold = self.residue_threshold_high
            detect_factor = self.config['sen_high_factor']

        if probability >= detect_threshold:
            self.check_residue_result.append(True)
            logging.info("[defect_detection] detected residue, times: %d",
                         self.check_residue_result.count(True))
        else:
            self.check_residue_result.append(False)
            return False

        if self.check_residue_result.count(True) >= self.config['residue']['check_window'] * detect_factor:
            self.check_residue_result = []
            return True
        else:
            return False

    def detect_dirty_bed(self, json_obj):
        if self.config['main_enable'] == False:
            return False
        if self.config['clean_bed']['enable'] == False:
            return False
        if self.debug_mode == False:
            if self.ignore_detect_bed == True:
                return False

        if json_obj is None:
            return False

        probability = json_obj.get("obj_probs", 0)
        detect_threshold = self.clean_bed_threshold_low
        if self.config['clean_bed']['sensitivity'] == SENSITIVITY_HIGH:
            detect_threshold = self.clean_bed_threshold_high

        if probability >= detect_threshold:
            return True
        else:
            return False

    def detect_dirty_nozzle(self, json_obj):
        if self.config['main_enable'] == False:
            return False

        if self.debug_mode == False:
            if self.ignore_detect_nozzle == True:
                return False

        if json_obj is None:
            return True

        detect_threshold = self.nozzle_threshold_low
        if self.config['nozzle']['sensitivity'] == SENSITIVITY_HIGH:
            detect_threshold = self.nozzle_threshold_high

        probability = json_obj.get("obj_probs", 0)
        if probability > detect_threshold:
            return False
        else:
            return True

    def request_detect(self):
        if self.mqtt_client is None:
            return

        if self.config['main_enable'] == False:
            return

        if self.reactor.monotonic() < self.last_request_time + TIME_INTERVAL:
            logging.info("[defect_detection] request too frequent, ignored")
            return

        self.last_request_time = self.reactor.monotonic()

        labels = []
        params = {"labels": labels}

        for detect_type in ["noodle", "residue"]:
            if not self.config[detect_type]['enable']:
                continue
            labels.append(detect_type)
            threshold = getattr(self, f"{detect_type}_threshold_low")
            if self.config[detect_type]['sensitivity'] == SENSITIVITY_HIGH:
                threshold = getattr(self, f"{detect_type}_threshold_high")
            params[detect_type] = {
                "threshold": threshold,
                "sensitivity": self.config[detect_type]['sensitivity']
            }

        if not labels:
            return

        # logging.info(f"[defect_detection] request params: {params}")
        self.mqtt_jsonrpc.send_request("camera.detect_capture",
                                        params,
                                        self.response_callback)

    def _request_detect_noodle_first_sync(self):
        try:
            self.last_request_time = self.reactor.monotonic()
            noodle_detect_threshold = self.noodle_threshold_low
            if self.config['noodle']['sensitivity'] == SENSITIVITY_HIGH:
                noodle_detect_threshold = self.noodle_threshold_high

            params = {
                "labels": ["noodle"],
                "detect_status": DETECT_STATUS_FIRST_DETECT,
                "noodle": {
                    "threshold": noodle_detect_threshold,
                    "sensitivity": self.config['noodle']['sensitivity']
                }
            }

            logging.info(f"[defect_detection] request params: {params}")

            response_info = self.mqtt_jsonrpc.send_request_with_response(
                                        "camera.detect_capture",
                                        params,
                                        timeout=REQUEST_TIMEOUT)

            logging.info(f"[defect_detection] response info: {response_info}")

        except Exception as e:
            logging.error(f"[defect_detection] request failed: {e}")

    def response_callback(self, respond_info):
        try:
            if self.config['main_enable'] == False:
                return

            logging.info(f"[defect_detection] response info: {respond_info}")

            if self.print_stats is not None and self.print_stats.state != 'printing':
                return

            result = respond_info.get("result", None)
            if result == None:
                logging.error(f"[defect_detection] request failed")
                return

            noodle = result.get("noodle", None)
            residue = result.get("residue", None)

            if noodle is not None:
                if self.detect_noodle(noodle):
                    logging.info("[defect_detection] noodle detected")
                    self.is_detected = True
                    self.reactor.register_async_callback(
                        (lambda et, evt=CONFIRM_NOODLE,
                            c=self.defect_event_handler: c(evt)))

            if residue is not None:
                if self.detect_residue(residue):
                    logging.info("[defect_detection] residue detected")
                    self.is_detected = True
                    self.reactor.register_async_callback(
                        (lambda et, evt=CONFIRM_RESIDUE,
                            c=self.defect_event_handler: c(evt)))

        except Exception as e:
            logging.error(f"[defect_detection] response info parse failed: {str(e)}")
            return

    def request_detect_clean_bed_sync(self, ignore_ratio=None, z_pos=None, detect_status=None):
        try:
            if self.mqtt_client is None:
                return False

            if self.config['main_enable'] == False:
                return False

            if ignore_ratio is not None and not isinstance(ignore_ratio, (int, float)):
                logging.error("ignore_ratio must be a number")
                return False

            if ignore_ratio is None:
                ignore_ratio = 1.0

            detect_threshold = self.clean_bed_threshold_low
            if self.config['clean_bed']['sensitivity'] == SENSITIVITY_HIGH:
                detect_threshold = self.clean_bed_threshold_high
            if detect_status is None:
                detect_status = ""

            params = {
                "labels": ["item"],
                "item": {
                    "threshold": detect_threshold,
                    "sensitivity": self.config['clean_bed']['sensitivity'],
                    "ignore_ratio": ignore_ratio
                },
                'detect_status': detect_status,
                'z_position': z_pos
            }
            logging.info(f"[defect_detection] request params: {params}")

            response_info = self.mqtt_jsonrpc.send_request_with_response(
                                        "camera.detect_capture",
                                        params,
                                        timeout=REQUEST_TIMEOUT)

            logging.info(f"[defect_detection] response info: {response_info}")
            result = response_info.get("result", None)
            if result is not None:
                clean_bed = result.get("item", None)
                if self.detect_dirty_bed(clean_bed):
                    logging.info("[defect_detection] dirty bed detected")
                    return True
                else:
                    return False
            else:
                logging.error(f"[defect_detection] request failed")

            return False

        except Exception as e:
            logging.error(f"[defect_detection] request to analyze clean bed failed: {str(e)}")
            return False

    def request_detect_nozzle_sync(self):
        if self.mqtt_client is None:
            return False

        if self.config['main_enable'] == False or self.config['nozzle']['enable'] == False:
            return False

        detect_threshold = self.nozzle_threshold_low
        if self.config['nozzle']['sensitivity'] == SENSITIVITY_HIGH:
            detect_threshold = self.nozzle_threshold_high

        try:
            params = {
                "labels": ["nozzle"],
                "nozzle": {
                    "threshold": detect_threshold,
                    "sensitivity": self.config['nozzle']['sensitivity']
                }
            }

            response_info = self.mqtt_jsonrpc.send_request_with_response(
                                        "camera.detect_capture",
                                        params,
                                        timeout=REQUEST_TIMEOUT)

            logging.info(f"[defect_detection] response info: {response_info}")
            result = response_info.get("result", None)
            if result is not None:
                nozzle = result.get("nozzle", None)
                if self.detect_dirty_nozzle(nozzle):
                    logging.info("[defect_detection] dirty nozzle detected")
                    return True
                else:
                    return False
            else:
                logging.error(f"[defect_detection] request failed")

            return False

        except Exception as e:
            logging.error(f"[defect_detection] request to analyze nozzle failed: {str(e)}")
            return False

    def defect_event_handler(self, event, from_command=False):
        code = 0
        msg = 'generic error'
        if event == CONFIRM_DIRTY_BED:
            code = 1
            msg = 'detected dirty bed'
        elif event == CONFIRM_NOODLE:
            code = 2
            msg = 'detected noodle'
        elif event == CONFIRM_RESIDUE:
            code = 3
            msg = 'detected residue'
        elif event == CONFIRM_DIRTY_NOZZLE:
            code = 4
            msg = 'detected dirty nozzle'

        self.reset_check_data()

        if from_command == False:
            self.printer.send_event("print_stats:update_exception_info",
                                    532,
                                    0,
                                    code,
                                    msg,
                                    2)
            exception_manager = self.printer.lookup_object('exception_manager', None)
            if exception_manager is not None:
                exception_manager.raise_exception_async(
                    id = 532,
                    index = 0,
                    code = code,
                    message = msg,
                    oneshot = 1,
                    level = 2)
            pause_resume = self.printer.lookup_object('pause_resume', None)
            if pause_resume is not None:
                pause_resume.send_pause_command()
            self.gcode.run_script("PAUSE\n")
        else:
            raise self.gcode.error(
                    message = msg,
                    action = 'pause',
                    id = 532,
                    index = 0,
                    code = code,
                    oneshot = 1,
                    level = 2)

    def get_status(self, eventtime=None):
        return self.config

    def cmd_DEFECT_DETECTION_CONFIG(self, gcmd):
        main_enable = gcmd.get_int('MAIN_ENABLE', None)
        sensitivity = gcmd.get('SENSITIVITY', None)
        clean_bed_enable = gcmd.get_int('CLEAN_BED_ENABLE', None)
        clean_bed_check_window = gcmd.get_int('CLEAN_BED_CHECK_WINDOW', None,
                                    minval=CHECK_WINDOW_MIN, maxval=CHECK_WINDOW_MAX)
        clean_bed_sensitivity = gcmd.get('CLEAN_BED_SENSITIVITY', None)
        noodle_enable = gcmd.get_int('NOODLE_ENABLE', None)
        noodle_check_window = gcmd.get_int('NOODLE_CHECK_WINDOW', None,
                                    minval=CHECK_WINDOW_MIN, maxval=CHECK_WINDOW_MAX)
        noodle_sensitivity = gcmd.get('NOODLE_SENSITIVITY', None)
        residue_enable = gcmd.get_int('RESIDUE_ENABLE', None)
        residue_check_window = gcmd.get_int('RESIDUE_CHECK_WINDOW', None,
                                    minval=CHECK_WINDOW_MIN, maxval=CHECK_WINDOW_MAX)
        residue_sensitivity = gcmd.get('RESIDUE_SENSITIVITY', None)
        logging.info("[defect_detection] DEFECT_DETECTION_CONFIG %s",
                                    gcmd.get_raw_command_parameters())
        tmp_config = copy.deepcopy(self.config)
        need_turn_on_led = False

        try:
            if main_enable is not None:
                tmp_config['main_enable'] = bool(main_enable)
            if sensitivity is not None:
                if sensitivity not in [SENSITIVITY_HIGH, SENSITIVITY_LOW]:
                    raise ValueError(f"invalid sensitivity: {sensitivity}")
                tmp_config['clean_bed']['sensitivity'] = sensitivity
                tmp_config['noodle']['sensitivity'] = sensitivity
                tmp_config['residue']['sensitivity'] = sensitivity
            if clean_bed_enable is not None:
                tmp_config['clean_bed']['enable'] = bool(clean_bed_enable)
                if tmp_config['clean_bed']['enable'] == True:
                    need_turn_on_led = True
            if clean_bed_check_window is not None:
                tmp_config['clean_bed']['check_window'] = clean_bed_check_window
            if clean_bed_sensitivity is not None and sensitivity is None:
                if clean_bed_sensitivity not in [SENSITIVITY_HIGH, SENSITIVITY_LOW]:
                    raise ValueError(f"invalid clean_bed_sensitivity: {clean_bed_sensitivity}")
                tmp_config['clean_bed']['sensitivity'] = clean_bed_sensitivity
            if noodle_enable is not None:
                tmp_config['noodle']['enable'] = bool(noodle_enable)
                if tmp_config['noodle']['enable'] == True:
                    need_turn_on_led = True
            if noodle_check_window is not None:
                tmp_config['noodle']['check_window'] = noodle_check_window
            if noodle_sensitivity is not None and sensitivity is None:
                if noodle_sensitivity not in [SENSITIVITY_HIGH, SENSITIVITY_LOW]:
                    raise ValueError(f"invalid noodle_sensitivity: {noodle_sensitivity}")
                tmp_config['noodle']['sensitivity'] = noodle_sensitivity
            if residue_enable is not None:
                tmp_config['residue']['enable'] = bool(residue_enable)
                if tmp_config['residue']['enable'] == True:
                    need_turn_on_led = True
            if residue_check_window is not None:
                tmp_config['residue']['check_window'] = residue_check_window
            if residue_sensitivity is not None and sensitivity is None:
                if residue_sensitivity not in [SENSITIVITY_HIGH, SENSITIVITY_LOW]:
                    raise ValueError(f"invalid residue_sensitivity: {residue_sensitivity}")
                tmp_config['residue']['sensitivity'] = residue_sensitivity

            if tmp_config['main_enable'] == True and need_turn_on_led == True:
                if self.cavity_led and self.print_stats and \
                        (self.print_stats.state == 'printing' or self.print_stats.state == 'paused'):
                    self.gcode.run_script_from_command("SET_LED LED=cavity_led WHITE=1\n")

        except Exception as e:
            raise gcmd.error(f"[defect_detection] gcode config failed: {str(e)}")

        else:
            self.reset_check_data()
            self.config = tmp_config
            if not self.printer.update_snapmaker_config_file(self.config_path, self.config, DEFAULT_CONFIG):
                logging.error("[defect_detection] config save failed")

    def cmd_DEFECT_DETECTION_START(self, gcmd):
        if self.mqtt_client is None:
            logging.error("[defect_detection] start error, mqtt not ready!")
            return

        if self.config['main_enable'] == False:
            logging.info("[defect_detection] start error, detection is disabled")
            return

        if self.config['clean_bed']['enable'] == False and \
                self.config['noodle']['enable'] == False and \
                self.config['residue']['enable'] == False and \
                self.config['nozzle']['enable'] == False:
            logging.info("[defect_detection] start error, no defect type is enabled")
            return

        logging.info("[defect_detection] started")
        self.gcode.run_script_from_command("SET_LED LED=cavity_led WHITE=1\r\n")

    def cmd_DEFECT_DETECTION_DETECT(self, gcmd):
        if self.mqtt_client is None:
            return

        if self.config['main_enable'] == False:
            return

        if self.config['noodle']['enable'] == False and self.config['residue']['enable'] == False:
            return

        if self.debug_mode == False and self.print_stats and self.print_stats.info_current_layer:
            if self.print_stats.info_current_layer - self.ignore_detect_start_layer < self.ignore_detect_layer:
                return

        self.request_detect()

    def cmd_DEFECT_DETECT_NOODLE_FIRST(self, gcmd):
        if self.mqtt_client is None:
            return

        if self.config['main_enable'] == False:
            return

        if self.config['noodle']['enable'] == False:
            return

        toolhead = self.printer.lookup_object("toolhead")
        toolhead.wait_moves()
        self._request_detect_noodle_first_sync()
        toolhead.wait_moves()

    def cmd_DEFECT_DETECTION_DETECT_BED(self, gcmd):
        if self.mqtt_client is None:
            logging.error("[defect_detection] cannot detect bed, mqtt not ready!")
            return

        if not self.config['main_enable'] or not self.config['clean_bed']['enable']:
            logging.info("[defect_detection] bed detection is disabled")
            return

        if self.debug_mode == False:
            if self.ignore_detect_bed == True:
                logging.info("[defect_detection] bed detection is ignored")
                return

        is_dirty_bed = False
        toolhead = self.printer.lookup_object("toolhead")
        gcode_move = self.printer.lookup_object('gcode_move')
        toolhead.wait_moves()
        homed_axes_list = toolhead.get_status(self.reactor.monotonic())['homed_axes']
        safety_z = 0
        rail = toolhead.get_kinematics().rails[2]

        if 'x' not in homed_axes_list or 'y' not in homed_axes_list:
            raise gcmd.error("[defect_detection] XY have not been homed")

        gcode_move_status = copy.deepcopy(gcode_move.get_status())
        gcode_move.absolute_coord = True

        position_min, position_max = rail.get_range()
        start_pos = list(toolhead.get_position())
        start_pos[2] = position_max - 0.5
        toolhead.set_position(start_pos, homing_axes=[2])

        try:
            machine_state_manager = self.printer.lookup_object('machine_state_manager', None)
            if machine_state_manager is not None:
                machine_sta = machine_state_manager.get_status()
                if str(machine_sta["main_state"]) == "PRINTING":
                    self.gcode.run_script_from_command("SET_MAIN_STATE MAIN_STATE=PRINTING ACTION=PRINT_BED_DETECTING")

            if self._request_cancel_print == True:
                return

            self.gcode.run_script_from_command(f"G1 Y{self.bed_detect_pos_y} F10000")
            self.gcode.run_script_from_command(f"G1 X{self.bed_detect_pos_x} F10000")
            toolhead.wait_moves()

            if self.reactor.monotonic() < self.last_request_time + TIME_INTERVAL:
                self.reactor.pause(self.reactor.monotonic() + TIME_INTERVAL + 0.1)
            self.last_request_time = self.reactor.monotonic()

            is_full_probe = False
            if self.request_detect_clean_bed_sync(ignore_ratio=0,
                                                    z_pos=start_pos[2],
                                                    detect_status=DETECT_STATUS_FIRST_DETECT):
                is_dirty_bed = True
                return

            probe_max_times = max(1, int(start_pos[2] / self.bed_detect_probe_distance))
            for probe_times in range(probe_max_times):
                if self._request_cancel_print == True:
                    return
                logging.info("[defect_detection] bed probe times: %d", probe_times + 1)
                try:
                    self.gcode.run_script_from_command(f"PROBE SAMPLE_TRIG_FREQ=450 SAMPLES=1 PROBE_SPEED=5 SAMPLE_DIST_Z={self.bed_detect_probe_distance}")
                    toolhead.wait_moves()
                except Exception as e:
                    coded_message = self.printer.extract_encoded_message(str(e))
                    if coded_message is not None:
                        message = coded_message.get("msg", None)
                        if message != "No trigger on probe after full movement":
                            raise gcmd.error(str(e))
                        else:
                            is_full_probe = True

                if probe_times == 0:
                    pos_1 = list(toolhead.get_position())
                    if start_pos[2] - pos_1[2] < self.bed_detect_probe_distance - 0.2:
                        for i in range(3):
                            if self._request_cancel_print == True:
                                return
                            current_pos = list(toolhead.get_position())
                            toolhead.manual_move([None, None, min(current_pos[2] + 2, start_pos[2])], 30)
                            toolhead.wait_moves()
                            if self._request_cancel_print == True:
                                return
                            try:
                                self.gcode.run_script_from_command(f"PROBE SAMPLE_TRIG_FREQ=450 SAMPLES=1 PROBE_SPEED=5 SAMPLE_DIST_Z={self.bed_detect_probe_distance}")
                                toolhead.wait_moves()
                            except Exception as e:
                                coded_message = self.printer.extract_encoded_message(str(e))
                                if coded_message is not None:
                                    message = coded_message.get("msg", None)
                                    if message != "No trigger on probe after full movement":
                                        raise gcmd.error(str(e))
                            pos_2 = list(toolhead.get_position())
                            if abs(pos_1[2] - pos_2[2]) > 0.15:
                                if i == 2:
                                    gcmd.respond_info("[defect_detection] Probe accidentally triggered.")
                                    return
                                else:
                                    gcmd.respond_info("[defect_detection] Probe accidentally triggered...retrying")
                                    continue
                            else:
                                break

                        current_pos = list(toolhead.get_position())
                        safety_z += start_pos[2] - current_pos[2]
                        toolhead.manual_move([None, None, current_pos[2] + safety_z], 30)
                        toolhead.wait_moves()
                        current_pos = list(toolhead.get_position())
                        if self.request_detect_clean_bed_sync(ignore_ratio=0,
                                                                z_pos=current_pos[2]):
                            is_dirty_bed = True
                            return

                        for i in range(3):
                            if self._request_cancel_print == True:
                                return
                            tmp_detect_status = ""
                            if i == 2:
                                tmp_detect_status = DETECT_STATUS_LAST_DETECT
                            dest_z = current_pos[2] - safety_z / 3.0
                            if abs(dest_z - pos_2[2]) < 0.5:
                                dest_z = pos_2[2] + 0.5
                            toolhead.manual_move([None, None, dest_z], 30)
                            toolhead.wait_moves()
                            current_pos = list(toolhead.get_position())
                            if self.request_detect_clean_bed_sync(ignore_ratio=0,
                                                                    z_pos=current_pos[2],
                                                                    detect_status=tmp_detect_status):
                                is_dirty_bed = True
                                return

                        logging.info("[defect_detection] not detected dirty bed")
                        return
                    else:
                        current_pos = list(toolhead.get_position())
                        if self.request_detect_clean_bed_sync(ignore_ratio=0,
                                                                z_pos=current_pos[2]):
                            is_dirty_bed = True
                            return
                        toolhead.manual_move([None, None, current_pos[2] + 5], 30)
                        toolhead.wait_moves()
                        if self._request_cancel_print == True:
                            return
                        current_pos = list(toolhead.get_position())
                        if self.request_detect_clean_bed_sync(ignore_ratio=0,
                                                                z_pos=current_pos[2]):
                            is_dirty_bed = True
                            return
                        toolhead.manual_move([None, None, current_pos[2] - 5], 30)
                        toolhead.wait_moves()

                else:
                    if is_full_probe == True:
                        current_pos = list(toolhead.get_position())
                        if self.request_detect_clean_bed_sync(ignore_ratio=0,
                                                                z_pos=current_pos[2]):
                            is_dirty_bed = True
                            return
                        toolhead.manual_move([None, None, current_pos[2] + 5], 30)
                        toolhead.wait_moves()
                        if self._request_cancel_print == True:
                            return
                        current_pos = list(toolhead.get_position())
                        if probe_times == probe_max_times - 1:
                            if self.request_detect_clean_bed_sync(ignore_ratio=0,
                                                                    z_pos=current_pos[2],
                                                                    detect_status=DETECT_STATUS_LAST_DETECT):
                                is_dirty_bed = True
                            return
                        else:
                            if self.request_detect_clean_bed_sync(ignore_ratio=0,
                                                                    z_pos=current_pos[2]):
                                is_dirty_bed = True
                                return
                        toolhead.manual_move([None, None, current_pos[2] - 5], 30)
                        toolhead.wait_moves()
                    else:
                        current_pos = list(toolhead.get_position())
                        toolhead.manual_move([None, None, current_pos[2] + 5], 30)
                        toolhead.wait_moves()
                        if self._request_cancel_print == True:
                            return
                        current_pos = list(toolhead.get_position())
                        if self.request_detect_clean_bed_sync(ignore_ratio=0,
                                                                z_pos=current_pos[2],
                                                                detect_status=DETECT_STATUS_LAST_DETECT):
                            is_dirty_bed = True
                        return

        finally:
            current_pos = list(toolhead.get_position())
            toolhead.manual_move([None, None, max(0, min(current_pos[2] + 5, start_pos[2]))], 30)
            toolhead.wait_moves()

            gcode_move.absolute_coord = gcode_move_status['absolute_coordinates']
            toolhead.get_kinematics().note_z_not_homed()
            toolhead.wait_moves()

            if machine_state_manager is not None:
                machine_sta = machine_state_manager.get_status()
                if str(machine_sta["main_state"]) == "PRINTING":
                    self.gcode.run_script_from_command("SET_MAIN_STATE MAIN_STATE=PRINTING ACTION=IDLE")
                toolhead.wait_moves()

            if is_dirty_bed == True:
                logging.info("[defect_detection] detected dirty bed.")
                self.ignore_detect_bed = True
                self.defect_event_handler(CONFIRM_DIRTY_BED, from_command=True)

    def cmd_DEFECT_DETECTION_DETECT_NOZZLE(self, gcmd):
        if self.mqtt_client is None:
            logging.error("[defect_detection] cannot detect nozzle, mqtt not ready!")
            return

        if not self.config['main_enable'] or not self.config['nozzle']['enable']:
            logging.info("[defect_detection] nozzle detection is disabled")
            return

        if self.debug_mode == False:
            if self.ignore_detect_nozzle == True:
                logging.info("[defect_detection] nozzle detection is ignored")
                return

        toolhead = self.printer.lookup_object("toolhead")
        toolhead.wait_moves()
        logging.info("[defect_detection] nozzle detecting...")
        old_pos = toolhead.get_position()
        retract_e = 0
        try:
            extruder_status = toolhead.get_extruder().get_status(self.reactor.monotonic())
            if extruder_status['printing_e_pos'] > -0.001 and extruder_status['can_extrude'] == True:
                retract_e = 1
            self.gcode.run_script_from_command(f"INNER_DETECT_NOZZLE_STAGE_1 RETRACT={retract_e}")
        except Exception as e:
            raise gcmd.error(f"[defect_detection] INNER_DETECT_NOZZLE_STAGE_1 failed, {str(e)}")

        dirty_nozzle = False
        try:
            dirty_nozzle = self.request_detect_nozzle_sync()
        except Exception as e:
            logging.error(f"[defect_detection] detect nozzle failed, {str(e)}")
            dirty_nozzle = False

        try:
            self.gcode.run_script_from_command(f"INNER_DETECT_NOZZLE_STAGE_2 X={old_pos[0]} Y={old_pos[1]} Z={old_pos[2]} EXTRUDE={retract_e}")
        except Exception as e:
            raise gcmd.error(f"[defect_detection] INNER_DETECT_NOZZLE_STAGE_2 failed, {str(e)}")

        if dirty_nozzle:
            self.ignore_detect_nozzle = True
            self.defect_event_handler(CONFIRM_DIRTY_NOZZLE, from_command=True)

def load_config(config):
    return DefectDetection(config)

