# print task config info
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging, os, copy, string
import ast
from . import filament_feed

LOGICAL_EXTRUDER_NUM = 32
PHYSICAL_EXTRUDER_NUM = 4

ENTANGLE_SENSITIVITY_LOW    = 'low'
ENTANGLE_SENSITIVITY_MEDIUM = 'medium'
ENTANGLE_SENSITIVITY_HIGH   = 'high'

SNAPMAKER_OFFICIAL_ORCASLICER = 'SnapmakerOrca'

FILAMENT_COLOR_NUMS_MAX     = 5

INVALID_WB_NUMBER = -9999999
VALID_NOZZLE_DIAMETERS = [0.2, 0.4, 0.6, 0.8]

PRINT_TASK_CONFIG_FILE = "print_task.json"
PRINT_TASK_CONFIG_2_FILE = "print_task_2.json"

DEFAULT_PRINT_TASK_CONFIG = {
    'filament_vendor': ['NONE'] * PHYSICAL_EXTRUDER_NUM,
    'filament_type': ['NONE'] * PHYSICAL_EXTRUDER_NUM,
    'filament_sub_type': ['NONE'] * PHYSICAL_EXTRUDER_NUM,
    'filament_color': [0xFFFFFFFF] * PHYSICAL_EXTRUDER_NUM,
    'filament_color_rgba': ['FFFFFFFF'] * PHYSICAL_EXTRUDER_NUM,
    'filament_color_multi': [
        {'nums': 1, 'alpha': 0xFF, 'mode': 0, 'colors': ['FFFFFF']}
        for _ in range(PHYSICAL_EXTRUDER_NUM)
    ],
    'filament_official': [False] * PHYSICAL_EXTRUDER_NUM,
    'filament_sku': [0] * PHYSICAL_EXTRUDER_NUM,
    'filament_edit': [True] * PHYSICAL_EXTRUDER_NUM,
    'filament_exist': [False] * PHYSICAL_EXTRUDER_NUM,
    'filament_soft': [False] * PHYSICAL_EXTRUDER_NUM,
    'extruder_map_table': [i for i in range(PHYSICAL_EXTRUDER_NUM)] + [0] * (LOGICAL_EXTRUDER_NUM - PHYSICAL_EXTRUDER_NUM),
    'extruders_used' : [False] * PHYSICAL_EXTRUDER_NUM,
    'extruders_replenished': [i for i in range(PHYSICAL_EXTRUDER_NUM)],
    'time_lapse_camera': False,
    'auto_bed_leveling': False,
    'flow_calibrate': False,
    'flow_calib_extruders': [True] * PHYSICAL_EXTRUDER_NUM,
    'shaper_calibrate': False,
    'auto_replenish_filament': True,
    'replenish_ignore_color' : False,
    'filament_entangle_detect': False,
    'filament_entangle_sen': ENTANGLE_SENSITIVITY_MEDIUM,
    'end_led_turn_off': False,
    'end_unload_filament': [False] * PHYSICAL_EXTRUDER_NUM,
    'reprint_info': {
        'auto_bed_leveling': False,
        'flow_calibrate': False,
        'flow_calib_extruders': [True] * PHYSICAL_EXTRUDER_NUM,
        'time_lapse_camera': False,
        'extruder_map_table': [i for i in range(PHYSICAL_EXTRUDER_NUM)] + [0] * (LOGICAL_EXTRUDER_NUM - PHYSICAL_EXTRUDER_NUM),
        'extruders_used' : [False] * PHYSICAL_EXTRUDER_NUM,
        'end_unload_filament': [False] * PHYSICAL_EXTRUDER_NUM,
    }
}

DEFAULT_PRINT_TASK_CONFIG_2 = {
    'line_width': 0,
    'layer_height': 0,
    'outer_wall_speed': 0,
    'outer_wall_speed_hf': 0,
    'outer_wall_accel': 0,
    'outer_wall_accel_hf': 0,
    'nozzle_temp': [0] * LOGICAL_EXTRUDER_NUM,
    'nozzle_diameter': [0] * LOGICAL_EXTRUDER_NUM,
    'filament_type': [None] * LOGICAL_EXTRUDER_NUM,
    'filament_diameter': [0] * LOGICAL_EXTRUDER_NUM,
    'filament_used_g': [0] * LOGICAL_EXTRUDER_NUM,
    'filament_used_mm': [0] * LOGICAL_EXTRUDER_NUM,
    'filament_flow_ratio': [1.0] * LOGICAL_EXTRUDER_NUM,
    'filament_max_vol_speed': [0] * LOGICAL_EXTRUDER_NUM,
    'filament_volume_type': ['standard'] * LOGICAL_EXTRUDER_NUM,
}

class PrintTaskConfig:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()

        self.filament_dt_obj = None
        self.filament_param_obj = None
        self.filament_feed_objects = None
        self.filament_info_backup = {
            'filament_vendor': ['NONE'] * PHYSICAL_EXTRUDER_NUM,
            'filament_type': ['NONE'] * PHYSICAL_EXTRUDER_NUM,
            'filament_sub_type': ['NONE'] * PHYSICAL_EXTRUDER_NUM,
            'filament_soft': [False] * PHYSICAL_EXTRUDER_NUM,
            'filament_color': [0xFFFFFFFF] * PHYSICAL_EXTRUDER_NUM,
            'filament_color_rgba': ['FFFFFFFF'] * PHYSICAL_EXTRUDER_NUM,
            'filament_color_multi': [{}] * PHYSICAL_EXTRUDER_NUM,
        }
        self.perform_auto_replenish = False
        self.is_exec_print_end_action = False

        config_dir = self.printer.get_snapmaker_config_dir()
        config_name = PRINT_TASK_CONFIG_FILE
        self.config_path = os.path.join(config_dir, config_name)
        self.print_task_config = self.printer.load_snapmaker_config_file(self.config_path, DEFAULT_PRINT_TASK_CONFIG)

        config_dir = self.printer.get_snapmaker_config_dir()
        config_name = PRINT_TASK_CONFIG_2_FILE
        self.config_path_2 = os.path.join(config_dir, config_name)
        self.print_task_config_2 = self.printer.load_snapmaker_config_file(self.config_path_2, DEFAULT_PRINT_TASK_CONFIG_2)

        self._early_check()

        self.reset_print_info()

        self.gcode = self.printer.lookup_object('gcode')
        self.gcode.register_command(
            "SET_PRINT_EXTRUDER_MAP", self.cmd_SET_PRINT_EXTRUDER_MAP)
        self.gcode.register_command(
            "GET_PRINT_EXTRUDER_MAP", self.cmd_GET_PRINT_EXTRUDER_MAP)
        self.gcode.register_command(
            "SET_PRINT_FILAMENT_CONFIG", self.cmd_SET_PRINT_FILAMENT_CONFIG)
        self.gcode.register_command(
            "GET_PRINT_TASK_CONFIG", self.cmd_GET_PRINT_TASK_CONFIG)
        self.gcode.register_command(
            "SAVE_CURRENT_PRINT_TASK_CONFIG", self.cmd_SAVE_CURRENT_PRINT_TASK_CONFIG)
        self.gcode.register_command(
            "RESET_PRINT_TASK_CONFIG", self.cmd_RESET_PRINT_TASK_CONFIG)
        self.gcode.register_command(
            "LOAD_PRINT_TASK_CONFIG", self.cmd_LOAD_PRINT_TASK_CONFIG)
        self.gcode.register_command(
            "SET_PRINT_PREFERENCES", self.cmd_SET_PRINT_PREFERENCES)
        self.gcode.register_command(
            "SET_PRINT_USED_EXTRUDERS", self.cmd_SET_PRINT_USED_EXTRUDERS)
        self.gcode.register_command(
            "INNER_CHECK_AND_RELOAD_FILAMENT_INFO", self.cmd_INNER_CHECK_AND_RELOAD_FILAMENT_INFO)
        self.gcode.register_command(
            "INNER_AUTO_REPLENISH_FILAMENT", self.cmd_INNER_AUTO_REPLENISH_FILAMENT)
        self.gcode.register_command(
            "SET_PRINT_TASK_PARAMETERS", self.cmd_SET_PRINT_TASK_PARAMETERS)
        self.gcode.register_command(
            "INNER_PRINT_END", self.cmd_INNER_PRINT_END)

        webhooks = self.printer.lookup_object('webhooks')
        webhooks.register_endpoint("print_task_config/set_print_preferences",
                                   self._handle_set_print_preferences)
        self.printer.register_event_handler("klippy:ready", self._ready)

    def _handle_set_print_preferences(self, web_request):
        tmp_print_task_config = copy.deepcopy(self.print_task_config)

        try:
            logging.info(f"[print_task_config] wb, set_print_preferences: {web_request.get_raw_parameters()}")

            auto_replenish_filament = web_request.get_int('auto_replenish_filament', None)
            filament_entangle_detect = web_request.get_int('filament_entangle_detect', None)
            filament_entangle_sen = web_request.get_str('filament_entangle_sen', None)
            auto_replenish_ignore_color = web_request.get_int('replenish_ignore_color', None)
            end_led_turn_off = web_request.get_int('end_led_turn_off', None)

            if auto_replenish_filament is not None:
                tmp_print_task_config['auto_replenish_filament'] = bool(auto_replenish_filament)

            if auto_replenish_ignore_color is not None:
                tmp_print_task_config['replenish_ignore_color'] = bool(auto_replenish_ignore_color)

            if filament_entangle_detect is not None:
                tmp_print_task_config['filament_entangle_detect'] = bool(filament_entangle_detect)

            if filament_entangle_sen is not None:
                if filament_entangle_sen not in [ENTANGLE_SENSITIVITY_LOW, ENTANGLE_SENSITIVITY_MEDIUM, ENTANGLE_SENSITIVITY_HIGH]:
                    raise ValueError(f"filament_entangle_sen error: {filament_entangle_sen}")
                tmp_print_task_config['filament_entangle_sen'] = filament_entangle_sen

            if filament_entangle_detect is not None or filament_entangle_sen is not None:
                self.printer.send_event("print_task_config:set_entangle_detect", tmp_print_task_config['filament_entangle_detect'])

            if end_led_turn_off is not None:
                tmp_print_task_config['end_led_turn_off'] = bool(end_led_turn_off)

            self.print_task_config = tmp_print_task_config
            if not self.printer.update_snapmaker_config_file(self.config_path,
                        self.print_task_config, DEFAULT_PRINT_TASK_CONFIG):
                logging.error("[print_task_config] save print_task_config failed\r\n")

            web_request.send({'state': 'success'})

        except Exception as e:
            logging.error("[print_task_config] set_print_preferences: %s", str(e))
            web_request.send({'state': 'error', 'message': str(e)})

    def _early_check(self):
        need_save = False
        tmp_print_task_config = copy.deepcopy(self.print_task_config)
        try:
            ###################################################################
            ##################### simple check ################################
            if len(tmp_print_task_config['filament_vendor']) != PHYSICAL_EXTRUDER_NUM or \
                    len(tmp_print_task_config['filament_type']) != PHYSICAL_EXTRUDER_NUM or \
                    len(tmp_print_task_config['filament_sub_type']) != PHYSICAL_EXTRUDER_NUM or \
                    len(tmp_print_task_config['filament_color']) != PHYSICAL_EXTRUDER_NUM or \
                    len(tmp_print_task_config['filament_color_rgba']) != PHYSICAL_EXTRUDER_NUM or \
                    len(tmp_print_task_config['filament_color_multi']) != PHYSICAL_EXTRUDER_NUM or \
                    len(tmp_print_task_config['filament_official']) != PHYSICAL_EXTRUDER_NUM or \
                    len(tmp_print_task_config['filament_sku']) != PHYSICAL_EXTRUDER_NUM or \
                    len(tmp_print_task_config['filament_edit']) != PHYSICAL_EXTRUDER_NUM or \
                    len(tmp_print_task_config['filament_exist']) != PHYSICAL_EXTRUDER_NUM or \
                    len(tmp_print_task_config['filament_soft']) != PHYSICAL_EXTRUDER_NUM or \
                    len(tmp_print_task_config['extruders_used']) != PHYSICAL_EXTRUDER_NUM or \
                    len(tmp_print_task_config['extruders_replenished']) != PHYSICAL_EXTRUDER_NUM or \
                    len(tmp_print_task_config['end_unload_filament']) != PHYSICAL_EXTRUDER_NUM or \
                    len(tmp_print_task_config['flow_calib_extruders']) != PHYSICAL_EXTRUDER_NUM or \
                    len(tmp_print_task_config['extruder_map_table']) != LOGICAL_EXTRUDER_NUM:
                raise ValueError(f"print_task_config invalid")

            for i in range(PHYSICAL_EXTRUDER_NUM):
                if not isinstance(tmp_print_task_config['filament_color_rgba'][i], str) or \
                                len(tmp_print_task_config['filament_color_rgba'][i]) != 8:
                    raise ValueError(f"print_task_config invalid")
                for j in range(tmp_print_task_config['filament_color_multi'][i]['nums']):
                    if not isinstance(tmp_print_task_config['filament_color_multi'][i]['colors'][j], str) or \
                                len(tmp_print_task_config['filament_color_multi'][i]['colors'][j]) != 6:
                        raise ValueError(f"print_task_config invalid")

            ###################################################################

            ###################################################################
            ################## compatiable with old version ###################
            for i in range(PHYSICAL_EXTRUDER_NUM):
                if isinstance(tmp_print_task_config['filament_color'][i], str):
                    raise ValueError(f"print_task_config invalid")

            for i in range(PHYSICAL_EXTRUDER_NUM):
                if tmp_print_task_config['filament_color_rgba'][i][0:6] != tmp_print_task_config['filament_color_multi'][i]['colors'][0]:
                    rgb = tmp_print_task_config['filament_color_rgba'][i][0:6]
                    alpha = int(tmp_print_task_config['filament_color_rgba'][i][6:8], 16)
                    color_multi = {
                        'nums': 1,
                        'alpha': alpha,
                        'mode': 0,
                        'colors': [rgb]
                    }
                    tmp_print_task_config['filament_official'][i] = False
                    tmp_print_task_config['filament_color_multi'][i] = color_multi
                    need_save = True
            ###################################################################

            if 'auto_bed_leveling' not in tmp_print_task_config['reprint_info'] or \
                    'flow_calibrate' not in tmp_print_task_config['reprint_info'] or \
                    'flow_calib_extruders' not in tmp_print_task_config['reprint_info'] or \
                    'time_lapse_camera' not in tmp_print_task_config['reprint_info'] or \
                    'extruder_map_table' not in tmp_print_task_config['reprint_info'] or \
                    'extruders_used' not in tmp_print_task_config['reprint_info'] or \
                    'end_unload_filament' not in tmp_print_task_config['reprint_info']:
                tmp_print_task_config['reprint_info'] = copy.deepcopy(DEFAULT_PRINT_TASK_CONFIG['reprint_info'])
                need_save = True

            self.print_task_config = tmp_print_task_config

        except Exception as e:
            logging.error("[print_task_config] _early_check err: %s", str(e))
            self.print_task_config = copy.deepcopy(DEFAULT_PRINT_TASK_CONFIG)
            need_save = True

        finally:
            if need_save:
                if not self.printer.update_snapmaker_config_file(self.config_path,
                        self.print_task_config, DEFAULT_PRINT_TASK_CONFIG):
                    logging.error("[print_task_config] save print_task_config failed\r\n")

    def _ready(self):
        self.filament_feed_objects = self.printer.lookup_objects('filament_feed')
        self.filament_param_obj = self.printer.lookup_object('filament_parameters', None)
        self.filament_dt_obj = self.printer.lookup_object("filament_detect", None)
        if self.filament_dt_obj is not None:
            self.filament_dt_obj.register_cb_2_update_filament_info(self._rfid_filament_info_update_cb)

        self.backup_filament_info()

    def _reset_print_task_config(self):
        self.print_task_config = copy.deepcopy(DEFAULT_PRINT_TASK_CONFIG)
        self.backup_filament_info()
        if not self.printer.update_snapmaker_config_file(self.config_path,
                self.print_task_config, DEFAULT_PRINT_TASK_CONFIG):
            logging.error("[print_task_config] save print_task_config failed\r\n")

    def get_print_task_config(self):
        return copy.deepcopy(self.print_task_config)

    def backup_filament_info(self, extruder_index=None):
        if extruder_index is None:
            self.filament_info_backup['filament_vendor'] = copy.deepcopy(self.print_task_config['filament_vendor'])
            self.filament_info_backup['filament_type'] = copy.deepcopy(self.print_task_config['filament_type'])
            self.filament_info_backup['filament_sub_type'] = copy.deepcopy(self.print_task_config['filament_sub_type'])
            self.filament_info_backup['filament_soft'] = copy.deepcopy(self.print_task_config['filament_soft'])
            self.filament_info_backup['filament_color'] = copy.deepcopy(self.print_task_config['filament_color'])
            self.filament_info_backup['filament_color_rgba'] = copy.deepcopy(self.print_task_config['filament_color_rgba'])
            self.filament_info_backup['filament_color_multi'] = copy.deepcopy(self.print_task_config['filament_color_multi'])
            return

        if extruder_index < 0 or extruder_index >= PHYSICAL_EXTRUDER_NUM:
            logging.error("[print_task_config] backup_filament_info: extruder_index error")
            return
        if self.print_task_config['filament_vendor'][extruder_index] != "" and self.print_task_config['filament_vendor'][extruder_index] != "NONE":
            self.filament_info_backup['filament_vendor'][extruder_index] = self.print_task_config['filament_vendor'][extruder_index]
            self.filament_info_backup['filament_type'][extruder_index] = self.print_task_config['filament_type'][extruder_index]
            self.filament_info_backup['filament_sub_type'][extruder_index] = self.print_task_config['filament_sub_type'][extruder_index]
            self.filament_info_backup['filament_soft'][extruder_index] = self.print_task_config['filament_soft'][extruder_index]
            self.filament_info_backup['filament_color'][extruder_index] = self.print_task_config['filament_color'][extruder_index]
            self.filament_info_backup['filament_color_rgba'][extruder_index] = self.print_task_config['filament_color_rgba'][extruder_index]
            self.filament_info_backup['filament_color_multi'][extruder_index] = copy.deepcopy(self.print_task_config['filament_color_multi'][extruder_index])

    def _rfid_filament_info_update_cb(self, channel, info, is_clear=False):
        if channel < 0 or channel >= PHYSICAL_EXTRUDER_NUM:
            logging.error("[print_task_config] rfid channel[%d] is out of range[0, %d]",
                          channel, PHYSICAL_EXTRUDER_NUM -1)
            return

        if is_clear == False and info['OFFICIAL'] == False and \
                self.print_task_config['filament_vendor'][channel] != 'NONE':
            return

        if is_clear == False and self.print_task_config['filament_sku'][channel] == info['SKU'] and \
                self.print_task_config['filament_official'][channel] == info['OFFICIAL'] and \
                info['OFFICIAL'] == True:
            return

        tmp_print_task_config = copy.deepcopy(self.print_task_config)
        try:
            filament_color_rgba = f"{info['RGB_1']:06X}" + f"{info['ALPHA']:02X}"

            tmp_print_task_config['filament_vendor'][channel] = info['VENDOR']
            tmp_print_task_config['filament_type'][channel] = info['MAIN_TYPE']
            tmp_print_task_config['filament_sub_type'][channel] = info['SUB_TYPE']
            tmp_print_task_config['filament_color'][channel] = info['ARGB_COLOR']
            tmp_print_task_config['filament_color_rgba'][channel] = filament_color_rgba

            color_multi = {
                'nums': info['COLOR_NUMS'],
                'alpha': info['ALPHA'],
                'mode': info['MULTI_MODE'],
                'colors':[f"{info['RGB_1']:06X}", f"{info['RGB_2']:06X}", f"{info['RGB_3']:06X}",
                        f"{info['RGB_4']:06X}", f"{info['RGB_5']:06X}"]
            }
            color_multi['colors'] = color_multi['colors'][:color_multi['nums']]
            tmp_print_task_config['filament_color_multi'][channel] = color_multi

            tmp_print_task_config['filament_official'][channel] = info['OFFICIAL']
            tmp_print_task_config['filament_sku'][channel] = info['SKU']
            if self.filament_param_obj is not None:
                tmp_print_task_config['filament_soft'][channel] = \
                    self.filament_param_obj.get_is_soft(info['VENDOR'], info['MAIN_TYPE'], info['SUB_TYPE'])
            else:
                tmp_print_task_config['filament_soft'][channel] = False

            self.print_task_config = tmp_print_task_config
            if not self.printer.update_snapmaker_config_file(self.config_path,
                    self.print_task_config, DEFAULT_PRINT_TASK_CONFIG):
                logging.error("[print_task_config] save print_task_config failed\r\n")

            if info['OFFICIAL'] == True:
                logging.info(f"[print_task_config] rfid info: {info['VENDOR']} {info['MAIN_TYPE']} {info['SUB_TYPE']} {color_multi}")

        except Exception as e:
            logging.error(f"[print_task_config] rfid info error: {str(e)}")


        if is_clear == False:
            # do not use run_script_from_command api
            self.gcode.run_script(f"FLOW_RESET_K EXTRUDER={channel}\r\n")

    def reset_filament_info(self, extruder_index):
        if extruder_index < 0 or extruder_index >= PHYSICAL_EXTRUDER_NUM:
            logging.error(f"[print_task_config] reset_filament_info: extruder_index error: {extruder_index}")
            return False

        logging.info(f"[print_task_config] reset_filament_info: {extruder_index}")
        tmp_print_task_config = copy.deepcopy(self.print_task_config)
        try:
            tmp_print_task_config['filament_vendor'][extruder_index] = "NONE"
            tmp_print_task_config['filament_type'][extruder_index] = "NONE"
            tmp_print_task_config['filament_sub_type'][extruder_index] = "NONE"
        except Exception as e:
            logging.error(f"[print_task_config] reset_filament_info error: {str(e)}")
            return False
        else:
            self.print_task_config = tmp_print_task_config
            if not self.printer.update_snapmaker_config_file(self.config_path,
                    self.print_task_config, DEFAULT_PRINT_TASK_CONFIG):
                logging.error("[print_task_config] save print_task_config failed\r\n")
            return True

    def get_extruder_map_table(self):
        return self.print_task_config['extruder_map_table']

    def get_extruder_map_index(self, index):
        if index + 1 > len(self.print_task_config['extruder_map_table']):
            raise ValueError("[print_task_config] index out of range[0,%d]" % (LOGICAL_EXTRUDER_NUM - 1))
        else:
            return self.print_task_config['extruder_map_table'][index]

    def reset_print_info(self, is_finish_print=False):
        try:
            logging.info("[print_task_config] reset print info")
            self.is_exec_print_end_action = False
            if is_finish_print:
                self.print_task_config_2 = copy.deepcopy(DEFAULT_PRINT_TASK_CONFIG_2)
            tmp_print_task_config = copy.deepcopy(self.print_task_config)
            tmp_print_task_config['extruder_map_table'] = copy.deepcopy(DEFAULT_PRINT_TASK_CONFIG['extruder_map_table'])
            tmp_print_task_config['extruders_used'] = copy.deepcopy(DEFAULT_PRINT_TASK_CONFIG['extruders_used'])
            tmp_print_task_config['extruders_replenished'] = copy.deepcopy(DEFAULT_PRINT_TASK_CONFIG['extruders_replenished'])
            tmp_print_task_config['flow_calibrate'] = False
            tmp_print_task_config['flow_calib_extruders'] = copy.deepcopy(DEFAULT_PRINT_TASK_CONFIG['flow_calib_extruders'])
            tmp_print_task_config['auto_bed_leveling'] = False
            tmp_print_task_config['time_lapse_camera'] = False
            tmp_print_task_config['end_unload_filament'] = copy.deepcopy(DEFAULT_PRINT_TASK_CONFIG['end_unload_filament'])
            # Compatible with old firmware versions
            if 'reprint_info' not in tmp_print_task_config or \
                    'auto_bed_leveling' not in tmp_print_task_config['reprint_info'] or \
                    'flow_calibrate' not in tmp_print_task_config['reprint_info'] or \
                    'flow_calib_extruders' not in tmp_print_task_config['reprint_info'] or \
                    'time_lapse_camera' not in tmp_print_task_config['reprint_info'] or \
                    'extruder_map_table' not in tmp_print_task_config['reprint_info'] or \
                    'extruders_used' not in tmp_print_task_config['reprint_info'] or \
                    len(tmp_print_task_config['reprint_info']['flow_calib_extruders']) != PHYSICAL_EXTRUDER_NUM or \
                    len(tmp_print_task_config['reprint_info']['extruder_map_table']) != LOGICAL_EXTRUDER_NUM or \
                    len(tmp_print_task_config['reprint_info']['extruders_used']) != PHYSICAL_EXTRUDER_NUM:
                tmp_print_task_config['auto_replenish_filament'] = DEFAULT_PRINT_TASK_CONFIG['auto_replenish_filament']
                if tmp_print_task_config['filament_entangle_sen'] == ENTANGLE_SENSITIVITY_LOW:
                    tmp_print_task_config['filament_entangle_sen'] = ENTANGLE_SENSITIVITY_MEDIUM
                tmp_print_task_config['reprint_info'] = copy.deepcopy(DEFAULT_PRINT_TASK_CONFIG['reprint_info'])
            self.print_task_config = tmp_print_task_config
        except Exception as e:
            logging.error("[print_task_config] reset print info failed: %s", str(e))
            self.print_task_config = copy.deepcopy(DEFAULT_PRINT_TASK_CONFIG)
            if is_finish_print:
                self.print_task_config_2 = copy.deepcopy(DEFAULT_PRINT_TASK_CONFIG_2)
        finally:
            if not self.printer.update_snapmaker_config_file(self.config_path,
                    self.print_task_config, DEFAULT_PRINT_TASK_CONFIG):
                logging.error("[print_task_config] save print_task_config failed\r\n")
            if is_finish_print and not self.printer.update_snapmaker_config_file(self.config_path_2,
                    self.print_task_config_2, DEFAULT_PRINT_TASK_CONFIG_2):
                logging.error("[print_task_config] save print_task_config_2 failed\r\n")

    def apply_reprint_info(self):
        logging.info("[print_task_config] apply reprint info")
        self.print_task_config['extruder_map_table'] = list(self.print_task_config['reprint_info']['extruder_map_table'])
        self.print_task_config['extruders_used'] = list(self.print_task_config['reprint_info']['extruders_used'])
        self.print_task_config['time_lapse_camera'] = self.print_task_config['reprint_info']['time_lapse_camera']
        self.print_task_config['flow_calibrate'] = self.print_task_config['reprint_info']['flow_calibrate']
        self.print_task_config['flow_calib_extruders'] = list(self.print_task_config['reprint_info']['flow_calib_extruders'])
        self.print_task_config['auto_bed_leveling'] = self.print_task_config['reprint_info']['auto_bed_leveling']
        self.print_task_config['end_unload_filament'] = list(self.print_task_config['reprint_info']['end_unload_filament'])
        if not self.printer.update_snapmaker_config_file(self.config_path,
                self.print_task_config, DEFAULT_PRINT_TASK_CONFIG):
            logging.error("[print_task_config] save print_task_config failed\r\n")

    def set_reprint_info(self):
        logging.info("[print_task_config] set reprint info")
        try:
            tmp_reprint_info = copy.deepcopy(self.print_task_config['reprint_info'])
            tmp_reprint_info['extruder_map_table'] = list(self.print_task_config['extruder_map_table'])
            tmp_reprint_info['extruders_used'] = list(self.print_task_config['extruders_used'])
            tmp_reprint_info['time_lapse_camera'] = self.print_task_config['time_lapse_camera']
            tmp_reprint_info['flow_calibrate'] = self.print_task_config['flow_calibrate']
            tmp_reprint_info['flow_calib_extruders'] = list(self.print_task_config['flow_calib_extruders'])
            tmp_reprint_info['auto_bed_leveling'] = self.print_task_config['auto_bed_leveling']
            tmp_reprint_info.update({'end_unload_filament': list(self.print_task_config['end_unload_filament'])})
            self.print_task_config['reprint_info'] = tmp_reprint_info
            if not self.printer.update_snapmaker_config_file(self.config_path,
                    self.print_task_config, DEFAULT_PRINT_TASK_CONFIG):
                logging.error("[print_task_config] save print_task_config failed\r\n")

        except Exception as e:
            logging.error("[print_task_config] set reprint info failed")

    def set_new_print_info(self):
        if True not in self.print_task_config['extruders_used']:
            tmp_extruders_used = list(self.print_task_config['extruders_used'])
            for i in range(LOGICAL_EXTRUDER_NUM):
                if self.print_task_config_2['filament_used_g'][i] > 0:
                    tmp_extruders_used[self.print_task_config['extruder_map_table'][i]] = True
            self.print_task_config['extruders_used'] = tmp_extruders_used

        self.is_exec_print_end_action = False
        self.backup_filament_info()
        self.set_reprint_info()

    def update_filament_edit_flag(self):
        tmp_filament_edit = list(self.print_task_config['filament_edit'])
        for ch in range(PHYSICAL_EXTRUDER_NUM):
            allowed_edit = False
            if self.print_task_config['filament_exist'][ch]:
                if self.print_task_config['filament_official'][ch] == False:
                    allowed_edit = True

            tmp_filament_edit[ch] = allowed_edit
        if tmp_filament_edit != self.print_task_config['filament_edit']:
            self.print_task_config['filament_edit'] = tmp_filament_edit

    def update_filament_exist_flag(self):
        filament_feed_infos = {}
        if self.filament_feed_objects is not None:
            for obj_name, obj in self.filament_feed_objects:
                status = obj.get_status(0)
                filament_feed_infos.update(status)

        tmp_filament_exist = list(self.print_task_config['filament_exist'])
        for ch in range(PHYSICAL_EXTRUDER_NUM):
            sensor_obj = self.printer.lookup_object(f'filament_motion_sensor e{ch}_filament', None)
            e_obj = filament_feed_infos.get(f'extruder{ch}', None)
            is_exist = True
            if sensor_obj is not None:
                sensor_status = sensor_obj.get_status(0)
                if sensor_status['enabled']:
                    if not sensor_status['filament_detected']:
                        if e_obj != None and e_obj['module_exist'] and not e_obj['disable_auto']:
                            if not e_obj['filament_detected']:
                                is_exist = False
                        else:
                            is_exist = False

            tmp_filament_exist[ch] = is_exist
        if tmp_filament_exist != self.print_task_config['filament_exist']:
            self.print_task_config['filament_exist'] = tmp_filament_exist

    def get_status(self, eventtime=None):
        self.update_filament_exist_flag()
        self.update_filament_edit_flag()
        print_task_config = dict(self.print_task_config)
        return print_task_config

    def cmd_SET_PRINT_EXTRUDER_MAP(self, gcmd):
        config_extruder = gcmd.get_int("CONFIG_EXTRUDER", None)
        map_extruder = gcmd.get_int("MAP_EXTRUDER", None)
        logging.info("[print_task_config] SET_PRINT_EXTRUDER_MAP %s", gcmd.get_raw_command_parameters())

        print_stats = self.printer.lookup_object('print_stats', None)
        if print_stats is not None and print_stats.state in ['printing', 'paused']:
            raise gcmd.error(
                message = "[print_task_config] not allowed to set extruder map during printing!",
                id = 531,
                index = 0,
                code = 15,
                oneshot = 1,
                level = 1)

        if config_extruder is None or map_extruder is None:
            raise gcmd.error("[print_task_config] extruder map, incomplete parameters")

        if (config_extruder < 0 or config_extruder >= LOGICAL_EXTRUDER_NUM) or \
                (map_extruder < 0 or map_extruder >= PHYSICAL_EXTRUDER_NUM):
            raise gcmd.error("[print_task_config] extruder map, invalid extruder index!!!")

        try:
            tmp_map_table = copy.deepcopy(self.print_task_config['extruder_map_table'])
            tmp_reprint_info = copy.deepcopy(self.print_task_config['reprint_info'])

            tmp_map_table[config_extruder] = map_extruder
            tmp_reprint_info['extruder_map_table'][config_extruder] = map_extruder

            self.print_task_config['extruder_map_table'] = tmp_map_table
            self.print_task_config['reprint_info'] = tmp_reprint_info

        except Exception as e:
            logging.error(f"[print_task_config] set extruder map failed: {str(e)}")

    def cmd_GET_PRINT_EXTRUDER_MAP(self, gcmd):
        map_info = ""
        for n in range(len(self.print_task_config['extruder_map_table'])):
            map_info += "T{} -> T{}\n".format(n, self.print_task_config['extruder_map_table'][n])
        self.gcode.respond_info(map_info)

    def cmd_GET_PRINT_TASK_CONFIG(self, gcmd):
        self.gcode.respond_info(str(self.print_task_config))

    def cmd_SAVE_CURRENT_PRINT_TASK_CONFIG(self, gcmd):
        if self.printer.update_snapmaker_config_file(self.config_path, self.print_task_config, DEFAULT_PRINT_TASK_CONFIG):
            self.gcode.respond_info("print task config saved successfully!!!")
        else:
            raise gcmd.error("Error: print task config save failure!!!")

    def cmd_SET_PRINT_FILAMENT_CONFIG(self, gcmd):
        config_extruder = gcmd.get_int('CONFIG_EXTRUDER')
        filament_vendor = gcmd.get('VENDOR', None)
        filament_type = gcmd.get('FILAMENT_TYPE', None)
        filament_sub_type = gcmd.get('FILAMENT_SUBTYPE', None)
        filament_soft = gcmd.get_int('SOFT', None)
        filament_color = gcmd.get_int('FILAMENT_COLOR', None)
        filament_color_rgba = gcmd.get('FILAMENT_COLOR_RGBA', None)
        filament_alpha = gcmd.get_int('ALPHA', None, minval=0, maxval=255)
        filament_color_nums = gcmd.get_int('COLOR_NUMS', None, minval=1, maxval=FILAMENT_COLOR_NUMS_MAX)
        filament_colors_str = gcmd.get('COLORS', None)
        filament_color_multi_mode = gcmd.get_int('MULTI_MODE', 0, minval=0, maxval=255)
        force = gcmd.get_int('FORCE', False)

        tmp_print_task_config = copy.deepcopy(self.print_task_config)

        try:
            logging.info("[print_task_config] PRINT_FILAMENT_CONFIG %s", gcmd.get_raw_command_parameters())

            if config_extruder < 0 or config_extruder >= PHYSICAL_EXTRUDER_NUM:
                raise gcmd.error("[print_task_config] extruder{} is out of range[0, {}]".format(config_extruder, PHYSICAL_EXTRUDER_NUM -1))

            if tmp_print_task_config['filament_official'][config_extruder] and bool(force) == False:
                raise gcmd.error("[print_task_config] filament_config, official filament, not configurable!")

            # alpha
            if filament_alpha == None:
                filament_alpha = int(tmp_print_task_config['filament_color_rgba'][config_extruder][6:8], 16)
                old_rgba = tmp_print_task_config['filament_color_rgba'][config_extruder]
                tmp_print_task_config['filament_color_rgba'][config_extruder] = old_rgba[0:6] + f"{filament_alpha:02X}"
                tmp_print_task_config['filament_color_multi'][config_extruder]['alpha'] = filament_alpha

            # vendor and type
            if filament_type is not None:
                if filament_vendor is None or filament_sub_type is None:
                    raise gcmd.error("[print_task_config] filament_config, incomplete parameters")

                tmp_print_task_config['filament_vendor'][config_extruder] = filament_vendor
                tmp_print_task_config['filament_type'][config_extruder] = filament_type
                tmp_print_task_config['filament_sub_type'][config_extruder] = filament_sub_type

                if filament_soft is not None:
                    tmp_print_task_config['filament_soft'][config_extruder] = bool(filament_soft)
                else:
                    if self.filament_param_obj is not None:
                        tmp_print_task_config['filament_soft'][config_extruder] = \
                            self.filament_param_obj.get_is_soft(filament_vendor, filament_type, filament_sub_type)
                    else:
                        tmp_print_task_config['filament_soft'][config_extruder] = False

            # color
            if filament_color_nums is not None or filament_color_rgba is not None or filament_color is not None:
                dest_filament_color = copy.deepcopy(DEFAULT_PRINT_TASK_CONFIG['filament_color'][config_extruder])
                dest_filament_color_rgba = copy.deepcopy(DEFAULT_PRINT_TASK_CONFIG['filament_color_rgba'][config_extruder])
                dest_filament_color_multi = copy.deepcopy(DEFAULT_PRINT_TASK_CONFIG['filament_color_multi'][config_extruder])

                if filament_color_nums is not None:
                    if filament_colors_str == None or filament_color_multi_mode == None:
                        raise gcmd.error("[print_task_config] filament_config, incomplete parameters")

                    filament_colors_list = filament_colors_str.split(',')
                    if len(filament_colors_list) != filament_color_nums:
                        raise gcmd.error("[print_task_config] filament_config, colors error")
                    for i in range(filament_color_nums):
                        if len(filament_colors_list[i]) != 6:
                            raise gcmd.error("[print_task_config] filament_config, colors error")
                        else:
                            for j in range(6):
                                if not filament_colors_list[i][j] in string.hexdigits:
                                    raise gcmd.error("[print_task_config] filament_config, colors error")

                    dest_filament_color_multi['nums'] = filament_color_nums
                    dest_filament_color_multi['alpha'] = filament_alpha
                    dest_filament_color_multi['colors'] = filament_colors_list
                    dest_filament_color_multi['mode'] = filament_color_multi_mode
                    dest_filament_color_rgba = filament_colors_list[0] + f'{filament_alpha:02X}'
                    dest_filament_color = (filament_alpha << 24) | int(filament_colors_list[0], 16)

                elif filament_color_rgba is not None:
                    if len(filament_color_rgba) == 6:
                        filament_color_rgba = filament_color_rgba + 'FF'

                    if len(filament_color_rgba) != 8:
                        raise gcmd.error("[print_task_config] filament_config, rgba error")

                    for i in range(len(filament_color_rgba)):
                        if not filament_color_rgba[i] in string.hexdigits:
                            raise gcmd.error("[print_task_config] filament_config, rgba error")

                    dest_filament_color_multi['nums'] = 1
                    dest_filament_color_multi['alpha'] = int(filament_color_rgba[6:8], 16)
                    dest_filament_color_multi['colors'] = [filament_color_rgba[0:6]]
                    dest_filament_color_multi['mode'] = 0
                    dest_filament_color_rgba = filament_color_rgba
                    dest_filament_color = (int(filament_color_rgba[6:8], 16) << 24) | int(filament_color_rgba[0:6], 16)

                elif filament_color is not None:
                    filament_color = filament_color & 0xFFFFFFFF
                    alpha = (filament_color & 0xFF000000) >> 24
                    red =   (filament_color & 0x00FF0000) >> 16
                    green = (filament_color & 0x0000FF00) >> 8
                    blue =  (filament_color & 0x000000FF) >> 0
                    dest_filament_color_rgba = f'{red:02X}' + f'{green:02X}' + f'{blue:02X}' + f'{alpha:02X}'
                    dest_filament_color_multi['nums'] = 1
                    dest_filament_color_multi['alpha'] = alpha
                    dest_filament_color_multi['colors'] = [dest_filament_color_rgba]
                    dest_filament_color_multi['mode'] = 0
                    dest_filament_color = filament_color

                tmp_print_task_config['filament_color'][config_extruder] = dest_filament_color
                tmp_print_task_config['filament_color_rgba'][config_extruder] = dest_filament_color_rgba
                tmp_print_task_config['filament_color_multi'][config_extruder] = dest_filament_color_multi

            tmp_print_task_config['filament_official'][config_extruder] = False
            tmp_print_task_config['filament_sku'][config_extruder] = 0

            self.print_task_config = tmp_print_task_config
            self.backup_filament_info(config_extruder)

            if not self.printer.update_snapmaker_config_file(self.config_path,
                    self.print_task_config, DEFAULT_PRINT_TASK_CONFIG):
                logging.error("[print_task_config] save print_task_config failed\r\n")

            self.gcode.run_script_from_command(f"FLOW_RESET_K EXTRUDER={config_extruder}\r\n")

        except Exception as e:
            raise gcmd.error(str(e))

    def cmd_SET_PRINT_PREFERENCES(self, gcmd):
        bed_level = gcmd.get_int('BED_LEVEL', None, minval=0, maxval=1)
        flow_calibrate = gcmd.get_int('FLOW_CALIBRATE', None, minval=0, maxval=1)
        flow_calibrate_extruders = gcmd.get('FLOW_CALIBRATE_EXTRUDERS', None)
        shaper_calibrate = gcmd.get_int('SHAPER_CALIBRATE', None, minval=0, maxval=1)
        time_lapse_camera  = gcmd.get_int('TIME_LAPSE_CAMERA', None, minval=0, maxval=1)
        auto_replenish_filament  = gcmd.get_int('AUTO_REPLENISH_FILAMENT', None, minval=0, maxval=1)
        auto_replenish_ignore_color = gcmd.get_int('REPLENISH_IGNORE_COLOR', None, minval=0, maxval=1)
        filament_entangle_detect = gcmd.get_int('FILAMENT_ENTANGLE_DETECT', None, minval=0, maxval=1)
        filament_entangle_sen = gcmd.get('FILAMENT_ENTANGLE_SEN', None)
        end_led_turn_off = gcmd.get_int('END_LED_TURN_OFF', None, minval=0, maxval=1)
        end_unload_filament = gcmd.get('END_UNLOAD_FILAMENT', None)
        logging.info("[print_task_config] SET_PRINT_PREFERENCES %s", gcmd.get_raw_command_parameters())

        print_stats = self.printer.lookup_object('print_stats', None)
        if print_stats is not None and print_stats.state in ['printing', 'paused']:
            if bed_level is not None or flow_calibrate is not None or shaper_calibrate is not None or \
                    time_lapse_camera is not None or end_unload_filament is not None:
                raise gcmd.error(
                    message = "[print_task_config] not allow to set preferences during printing!",
                    id = 531,
                    index = 0,
                    code = 16,
                    oneshot = 1,
                    level = 1)

        tmp_print_task_config = copy.deepcopy(self.print_task_config)
        try:
            if bed_level is not None:
                tmp_print_task_config['auto_bed_leveling'] = bool(bed_level)
                tmp_print_task_config['reprint_info']['auto_bed_leveling'] = bool(bed_level)

            if flow_calibrate is not None:
                tmp_print_task_config['flow_calibrate'] = bool(flow_calibrate)
                tmp_print_task_config['reprint_info']['flow_calibrate'] = bool(flow_calibrate)

            if flow_calibrate_extruders is not None:
                tmp_print_task_config['flow_calibrate_extruders'] = [True for i in range(PHYSICAL_EXTRUDER_NUM)]
                tmp_print_task_config['reprint_info'].update({'flow_calibrate_extruders': [True for i in range(PHYSICAL_EXTRUDER_NUM)]})
                calib_extruders = [int(value) for value in flow_calibrate_extruders.split(',')]
                for i in range(PHYSICAL_EXTRUDER_NUM):
                    if i in calib_extruders:
                        tmp_print_task_config['flow_calib_extruders'][i] = True
                        tmp_print_task_config['reprint_info']['flow_calib_extruders'][i] = True
                    else:
                        tmp_print_task_config['flow_calib_extruders'][i] = False
                        tmp_print_task_config['reprint_info']['flow_calib_extruders'][i] = False

            if shaper_calibrate is not None:
                tmp_print_task_config['shaper_calibrate'] = bool(shaper_calibrate)

            if time_lapse_camera is not None:
                tmp_print_task_config['time_lapse_camera'] = bool(time_lapse_camera)
                tmp_print_task_config['reprint_info']['time_lapse_camera'] = bool(time_lapse_camera)

            if auto_replenish_filament is not None:
                tmp_print_task_config['auto_replenish_filament'] = bool(auto_replenish_filament)

            if auto_replenish_ignore_color is not None:
                tmp_print_task_config['replenish_ignore_color'] = bool(auto_replenish_ignore_color)

            if filament_entangle_detect is not None:
                tmp_print_task_config['filament_entangle_detect'] = bool(filament_entangle_detect)
                self.printer.send_event("print_task_config:set_entangle_detect", tmp_print_task_config['filament_entangle_detect'])

            if filament_entangle_sen is not None:
                if filament_entangle_sen not in [ENTANGLE_SENSITIVITY_HIGH, ENTANGLE_SENSITIVITY_MEDIUM, ENTANGLE_SENSITIVITY_LOW]:
                    raise gcmd.error(f"[print_task_config] filament_entangle_sen error: {filament_entangle_sen}")
                tmp_print_task_config['filament_entangle_sen'] = filament_entangle_sen
                self.printer.send_event("print_task_config:set_entangle_detect", tmp_print_task_config['filament_entangle_detect'])

            if end_led_turn_off is not None:
                tmp_print_task_config['end_led_turn_off'] = bool(end_led_turn_off)

            if end_unload_filament is not None:
                end_unload_filament_list = None
                try:
                    end_unload_filament_list = self._parse_str_to_list(end_unload_filament)
                except Exception as e:
                    raise gcmd.error("Invalid END_UNLOAD_FILAMENT")

                tmp_print_task_config.update({'end_unload_filament': [False for i in range(PHYSICAL_EXTRUDER_NUM)]})
                tmp_print_task_config['reprint_info'].update({'end_unload_filament': [False for i in range(PHYSICAL_EXTRUDER_NUM)]})

                for i in range(min(len(end_unload_filament_list), PHYSICAL_EXTRUDER_NUM)):
                    if not isinstance(end_unload_filament_list[i], int):
                        raise gcmd.error("[print_task_config] Invalid END_UNLOAD_EXTRUDERS")
                    tmp_print_task_config['end_unload_filament'][i] = bool(end_unload_filament_list[i])
                    tmp_print_task_config['reprint_info']['end_unload_filament'][i] = bool(end_unload_filament_list[i])

            self.print_task_config = tmp_print_task_config

            if not self.printer.update_snapmaker_config_file(self.config_path,
                        self.print_task_config, DEFAULT_PRINT_TASK_CONFIG):
                logging.error("[print_task_config] save print_task_config failed\r\n")

        except Exception as e:
            logging.error("[print_task_config] save print_task_config failed\r\n")
            raise gcmd.error(str(e))

    def cmd_SET_PRINT_USED_EXTRUDERS(self, gcmd):
        extruders_str = gcmd.get('EXTRUDERS', None)
        logging.info("[print_task_config] SET_PRINT_USED_EXTRUDERS %s", gcmd.get_raw_command_parameters())

        print_stats = self.printer.lookup_object('print_stats', None)
        if print_stats is not None and print_stats.state in ['printing', 'paused']:
            raise gcmd.error(
                message = "[print_task_config] not allow to set used_extruders during printing!",
                id = 531,
                index = 0,
                code = 16,
                oneshot = 1,
                level = 1)

        if extruders_str is not None:
            tmp_extruders_used = copy.deepcopy(self.print_task_config['extruders_used'])
            tmp_reprint_info = copy.deepcopy(self.print_task_config['reprint_info'])
            try:
                tmp_extruders_used = [False] * PHYSICAL_EXTRUDER_NUM
                tmp_reprint_info.update({'extruders_used': [False] * PHYSICAL_EXTRUDER_NUM})
                used_extruders = [int(value) for value in extruders_str.split(',')]
                for i in range(min(len(used_extruders), LOGICAL_EXTRUDER_NUM)):
                    tmp_extruders_used[used_extruders[i]] = True
                    tmp_reprint_info['extruders_used'][used_extruders[i]] = True

                self.print_task_config['extruders_used'] = tmp_extruders_used
                self.print_task_config['reprint_info'] = tmp_reprint_info

                if not self.printer.update_snapmaker_config_file(self.config_path,
                        self.print_task_config, DEFAULT_PRINT_TASK_CONFIG):
                    logging.error("[print_task_config] save print_task_config failed\r\n")

            except Exception as e:
                raise gcmd.error(str(e))
    def cmd_RESET_PRINT_TASK_CONFIG(self, gcmd):
        self._reset_print_task_config()

    def cmd_LOAD_PRINT_TASK_CONFIG(self, gcmd):
        self.print_task_config = self.printer.load_snapmaker_config_file(self.config_path, DEFAULT_PRINT_TASK_CONFIG)

    def cmd_INNER_CHECK_AND_RELOAD_FILAMENT_INFO(self, gcmd):
        extruder_index = gcmd.get_int('EXTRUDER', minval=0, maxval=PHYSICAL_EXTRUDER_NUM - 1)
        is_runout = gcmd.get_int('IS_RUNOUT')

        toolhead = self.printer.lookup_object("toolhead")
        toolhead.wait_moves()

        logging.info(f"[print_task_config] INNER_CHECK_AND_RELOAD_FILAMENT_INFO extruder_index: {extruder_index}")

        if self.print_task_config['filament_type'][extruder_index] != "" and self.print_task_config['filament_type'][extruder_index] != "NONE":
            return

        if is_runout and self.filament_info_backup:
            try:
                if self.filament_info_backup['filament_type'][extruder_index] != "" and self.filament_info_backup['filament_type'][extruder_index] != "NONE":
                    tmp_print_task_config = copy.deepcopy(self.print_task_config)
                    tmp_print_task_config['filament_type'][extruder_index] = self.filament_info_backup['filament_type'][extruder_index]
                    tmp_print_task_config['filament_vendor'][extruder_index] = self.filament_info_backup['filament_vendor'][extruder_index]
                    tmp_print_task_config['filament_sub_type'][extruder_index] = self.filament_info_backup['filament_sub_type'][extruder_index]
                    tmp_print_task_config['filament_soft'][extruder_index] = self.filament_info_backup['filament_soft'][extruder_index]
                    tmp_print_task_config['filament_color'][extruder_index] = self.filament_info_backup['filament_color'][extruder_index]
                    tmp_print_task_config['filament_color_rgba'][extruder_index] = self.filament_info_backup['filament_color_rgba'][extruder_index]
                    tmp_print_task_config['filament_color_multi'][extruder_index] = copy.deepcopy(self.filament_info_backup['filament_color_multi'][extruder_index])

                    tmp_print_task_config['filament_official'][extruder_index] = False
                    tmp_print_task_config['filament_sku'][extruder_index] = 0

                    self.print_task_config = tmp_print_task_config

                    if not self.printer.update_snapmaker_config_file(self.config_path,
                            self.print_task_config, DEFAULT_PRINT_TASK_CONFIG):
                        logging.error("[print_task_config] save print_task_config failed\r\n")

                    self.gcode.run_script_from_command(f"FLOW_RESET_K EXTRUDER={extruder_index}\r\n")

            except Exception as e:
                logging.error("[print_task_config] INNER_CHECK_AND_RELOAD_FILAMENT_INFO error: %s", str(e))

        if self.print_task_config['extruders_used'][extruder_index] == True:
            if self.print_task_config['filament_type'][extruder_index] == "" or self.print_task_config['filament_type'][extruder_index] == "NONE":
                raise gcmd.error(
                        message = f"e{extruder_index} not edit filament",
                        action = 'pause',
                        id = 523,
                        index = extruder_index,
                        code = 39,
                        oneshot = 1,
                        level = 2)

    def cmd_INNER_AUTO_REPLENISH_FILAMENT(self, gcmd):
        self.perform_auto_replenish = False
        if self.print_task_config['auto_replenish_filament'] == False:
            logging.info("[print_task_config] auto_replenish_filament is disabled.")
            return
        else:
            logging.info("[print_task_config] try to auto replenish filament...")

        toolhead = self.printer.lookup_object("toolhead")
        toolhead.wait_moves()

        if self.is_exec_print_end_action == True:
            logging.info("[print_task_config] print end ....")
            return

        current_extruder = gcmd.get_int('EXTRUDER')
        if current_extruder < 0 or current_extruder >= PHYSICAL_EXTRUDER_NUM:
            logging.error(f"[print_task_config] extruder_index input error: {current_extruder}")
            return

        if current_extruder != toolhead.get_extruder().extruder_index:
            logging.error("[print_task_config] current extruder is %d, but input extruder is %d",
                          toolhead.get_extruder().extruder_index, current_extruder)
            return

        if self.filament_info_backup is None or \
                self.filament_info_backup['filament_type'][current_extruder] == "" or \
                self.filament_info_backup['filament_type'][current_extruder] == "NONE":
            logging.error("[print_task_config] filament_info_backup is none.\r\n")
            return

        print_stats = self.printer.lookup_object("print_stats", None)
        if print_stats is None or print_stats.state != 'paused':
            logging.error(f"[print_task_config] print_stats error: {print_stats.state}\r\n")
            return

        macro = self.printer.lookup_object('gcode_macro INNER_RESUME', None)
        if macro is None:
            logging.error("[print_task_config] INNER_RESUME macro is none.\r\n")
            return

        replenish_extruder = None
        replenish_extruder_name = None
        current_extruder_obj = toolhead.get_extruder()
        current_extruder_name = current_extruder_obj.name
        current_extruder_temp = macro.variables.get('last_extruder_temp', 0)
        current_extruder_nozzle_diameter = current_extruder_obj.nozzle_diameter
        current_extruder_nozzle_volume_type = current_extruder_obj.nozzle_volume_type

        filament_feed_infos = {}
        for obj_name, obj in self.filament_feed_objects:
            status = obj.get_status(0)
            filament_feed_infos.update(status)

        e_obj = filament_feed_infos.get(f'extruder{current_extruder}', None)
        runout_sensor = self.printer.lookup_object(f"filament_motion_sensor e{current_extruder}_filament", None)
        if e_obj is not None and runout_sensor is not None and \
                e_obj['module_exist'] == True and \
                e_obj['disable_auto'] == False and \
                e_obj['filament_detected'] == True and \
                runout_sensor.get_status(0)['enabled'] == True:
            replenish_extruder = current_extruder
        else:
            best_match_extruder = None
            best_match_distance = None
            for i in range(PHYSICAL_EXTRUDER_NUM):
                if i == current_extruder:
                    continue

                extruder_obj = self.printer.lookup_object(f"extruder", None)
                if i != 0:
                    extruder_obj = self.printer.lookup_object(f"extruder{i}", None)
                if extruder_obj is None:
                    continue
                else:
                    if extruder_obj.nozzle_diameter != current_extruder_nozzle_diameter:
                        continue
                    if extruder_obj.nozzle_volume_type != current_extruder_nozzle_volume_type:
                        continue

                runout_sensor = self.printer.lookup_object(f"filament_motion_sensor e{i}_filament", None)
                e_obj = filament_feed_infos.get(f'extruder{i}', None)
                if e_obj is None or runout_sensor is None:
                    continue

                if e_obj['channel_state'] == filament_feed.FEED_STA_LOAD_FINISH or \
                        (e_obj['module_exist'] == True and e_obj['disable_auto'] == False and \
                         e_obj['filament_detected'] == True and \
                         runout_sensor.get_status(0)['enabled'] == True):
                    if self.print_task_config['filament_vendor'][i] != 'NONE' and \
                            self.print_task_config['filament_vendor'][i] == self.filament_info_backup['filament_vendor'][current_extruder] and \
                            self.print_task_config['filament_type'][i] == self.filament_info_backup['filament_type'][current_extruder] and \
                            self.print_task_config['filament_sub_type'][i] == self.filament_info_backup['filament_sub_type'][current_extruder]:
                        if self.print_task_config['filament_color_multi'][i] == self.filament_info_backup['filament_color_multi'][current_extruder]:
                            # Exact match (regardless of single or multi color) - highest priority
                            replenish_extruder = i
                            break
                        elif self.print_task_config['replenish_ignore_color'] == True:
                            # Weighted RGB distance match against the first color
                            color1 = self.print_task_config['filament_color_multi'][i]['colors'][0]
                            color2 = self.filament_info_backup['filament_color_multi'][current_extruder]['colors'][0]
                            distance = self._weighted_rgb_distance(color1, color2)
                            if best_match_distance is None or distance < best_match_distance:
                                best_match_distance = distance
                                best_match_extruder = i

        if replenish_extruder is None and best_match_extruder is not None:
            replenish_extruder = best_match_extruder

        if replenish_extruder == None:
            runout_sensors = self.printer.lookup_objects('filament_motion_sensor')
            runout_sensor_infos = {}
            for obj_name, obj in runout_sensors:
                status = obj.get_status(0)
                runout_sensor_infos[obj_name] = status
            extruder_nozzle_diameter = []
            extruder_nozzle_volume_type = []
            for i in range(PHYSICAL_EXTRUDER_NUM):
                extruder_obj = self.printer.lookup_object(f"extruder", None)
                if i != 0:
                    extruder_obj = self.printer.lookup_object(f"extruder{i}", None)
                extruder_nozzle_diameter.append(extruder_obj.nozzle_diameter)
                extruder_nozzle_volume_type.append(extruder_obj.nozzle_volume_type)
            logging.info("[print_task_config] =========== cannot auto replenish filament ====================== ")
            logging.info(f"feeder info: {str(filament_feed_infos)}")
            logging.info(f"runout sensor info: {str(runout_sensor_infos)}")
            logging.info(f"backup info: {str(self.filament_info_backup)}")
            logging.info(f"filament info: {str(self.print_task_config)}")
            logging.info(f"extruder nozzle diameter: {str(extruder_nozzle_diameter)}")
            logging.info(f"extruder nozzle volume type: {str(extruder_nozzle_volume_type)}")
            logging.info("[print_task_config] ================================================================= ")
            return
        else:
            logging.info(f"[print_task_config] auto replenish filament: T{current_extruder} -> T{replenish_extruder}")

        if replenish_extruder == 0:
            replenish_extruder_name = 'extruder'
        else:
            replenish_extruder_name = f'extruder{replenish_extruder}'

        toolhead.wait_moves()
        if current_extruder != replenish_extruder:
            virtual_sdcard = self.printer.lookup_object('virtual_sdcard', None)
            if virtual_sdcard is not None:
                temp_dir = {
                    replenish_extruder_name: current_extruder_temp,
                    current_extruder_name: 0
                }
                virtual_sdcard.record_pl_print_temperature_env(temp_dir, ignore_pl_condition = True)
                virtual_sdcard.force_refresh_move_env_extruder(replenish_extruder_name)
            self.gcode.run_script_from_command(f"SET_GCODE_VARIABLE MACRO=INNER_RESUME VARIABLE=extruder{current_extruder}_temp VALUE=0\n")
            self.gcode.run_script_from_command(f"M104 S0 T{current_extruder} A0\n")

            tmp_print_task_config = copy.deepcopy(self.print_task_config)
            for i in range(LOGICAL_EXTRUDER_NUM):
                if tmp_print_task_config['extruder_map_table'][i] == current_extruder:
                    tmp_print_task_config['extruder_map_table'][i] = replenish_extruder
            tmp_print_task_config['extruders_used'][current_extruder] = False
            tmp_print_task_config['extruders_used'][replenish_extruder] = True
            tmp_print_task_config['flow_calib_extruders'][replenish_extruder] = True
            tmp_print_task_config['extruders_replenished'][current_extruder] = replenish_extruder
            tmp_print_task_config['reprint_info']['extruder_map_table'] = list(tmp_print_task_config['extruder_map_table'])
            tmp_print_task_config['reprint_info']['flow_calib_extruders'] = list(tmp_print_task_config['flow_calib_extruders'])
            tmp_print_task_config['reprint_info']['extruders_used'] = list(tmp_print_task_config['extruders_used'])
            self.print_task_config = tmp_print_task_config
            self.printer.update_snapmaker_config_file(self.config_path, self.print_task_config, DEFAULT_PRINT_TASK_CONFIG)

        self.perform_auto_replenish = True
        self.gcode.run_script_from_command(f"RESUME REPLENISH=1 REPLENISH_EXTRUDER={replenish_extruder}\n")

    def _parse_str_to_list(self, param_str):
        result = ast.literal_eval(param_str)
        if isinstance(result, list):
            return result
        else:
            raise ValueError("Not a list")

    @staticmethod
    def _weighted_rgb_distance(hex1, hex2):
        """Calculate weighted RGB distance between two 6-char hex color strings.
        Uses Rec. 601 luma weights for human perception (green weighted highest).
        """
        r1, g1, b1 = int(hex1[0:2], 16), int(hex1[2:4], 16), int(hex1[4:6], 16)
        r2, g2, b2 = int(hex2[0:2], 16), int(hex2[2:4], 16), int(hex2[4:6], 16)
        # Weighted Euclidean distance: R=0.299, G=0.587, B=0.114
        return ((0.299 * (r1 - r2)) ** 2 +
                (0.587 * (g1 - g2)) ** 2 +
                (0.114 * (b1 - b2)) ** 2) ** 0.5

    def cmd_SET_PRINT_TASK_PARAMETERS(self, gcmd):
        logging.info("[print_task_config] SET_PRINT_TASK_PARAMETERS %s", gcmd.get_raw_command_parameters())

        map_table = gcmd.get('MAP_TABLE', None)

        bed_level = gcmd.get_int('BED_LEVEL', None, minval=0, maxval=1)
        flow_calibrate = gcmd.get_int('FLOW_CALIBRATE', None, minval=0, maxval=1)
        flow_calibrate_extruders = gcmd.get('FLOW_CALIBRATE_EXTRUDERS', None)
        shaper_calibrate = gcmd.get_int('SHAPER_CALIBRATE', None, minval=0, maxval=1)
        time_lapse_camera  = gcmd.get_int('TIME_LAPSE_CAMERA', None, minval=0, maxval=1)
        end_unload_filament = gcmd.get('END_UNLOAD_FILAMENT', None)

        line_width = gcmd.get_float('LINE_WIDTH', None)
        layer_height = gcmd.get_float('LAYER_HEIGHT', None)
        outer_wall_speed_list = gcmd.get('OUTER_WALL_SPEED_LIST', None)
        outer_wall_accel_list = gcmd.get('OUTER_WALL_ACCELERATION_LIST', None)
        process_flow_support = gcmd.get('PROCESS_FLOW_SUPPORT', None)

        nozzle_diameter = gcmd.get('NOZZLE_DIAMETER_LIST', None)
        nozzle_temp = gcmd.get('NOZZLE_TEMP', None)
        filament_type = gcmd.get('FILAMENT_TYPE', None)
        filament_flow_ratio = gcmd.get('FILAMENT_FLOW_RATIO', None)
        filament_max_vol_speed = gcmd.get('FILAMENT_MAX_VOLUMETRIC_SPEED', None)
        filament_volume_type = gcmd.get('FILAMENT_VOLUME_TYPE', None)


        filament_used_g = gcmd.get('FILAMENT_USED_G', None)
        filament_used_mm = gcmd.get('FILAMENT_USED_MM', None)

        slicer = gcmd.get('SLICER', None)
        slicer_version = gcmd.get('SLICER_VERSION', None)

        exception_id = 531
        exception_code = 17
        exception_index = 0
        exception_level = 3
        exception_oneshot = 1

        print_stats = self.printer.lookup_object('print_stats', None)
        if print_stats is not None and print_stats.state in ['printing', 'paused']:
            exception_code = 16
            raise gcmd.error(
                message = "[print_task_config] Cannot set print task parameters during printing",
                id = exception_id,
                code = exception_code,
                index = exception_index,
                level = exception_level,
                oneshot = exception_oneshot)

        try:
            tmp_print_task_config = copy.deepcopy(self.print_task_config)
            tmp_print_task_config_2 = copy.deepcopy(DEFAULT_PRINT_TASK_CONFIG_2)
            tmp_print_task_config['extruder_map_table'] = copy.deepcopy(DEFAULT_PRINT_TASK_CONFIG['extruder_map_table'])
            tmp_print_task_config['extruders_used'] = [False for i in range(PHYSICAL_EXTRUDER_NUM)]
            # actual nozzle properties
            actual_nozzle_diameter = [0.4] * PHYSICAL_EXTRUDER_NUM
            actual_nozzle_volume_type = ['standard'] * PHYSICAL_EXTRUDER_NUM
            for i in range(PHYSICAL_EXTRUDER_NUM):
                extruder_obj = self.printer.lookup_object('extruder', None)
                if i != 0:
                    extruder_obj = self.printer.lookup_object(f'extruder{i}', None)
                if extruder_obj is not None:
                    actual_nozzle_diameter[i] = extruder_obj.nozzle_diameter
                    actual_nozzle_volume_type[i] = extruder_obj.nozzle_volume_type
                else:
                    raise gcmd.error(f"[print_task_config] Cannot find extruder:{i}")

            # extruder map table
            if map_table is not None:
                map_table_list = None
                try:
                    map_table_list = self._parse_str_to_list(map_table)
                except:
                    raise gcmd.error("[print_task_config] Invalid MAP_TABLE")

                if len(map_table_list) > LOGICAL_EXTRUDER_NUM:
                    raise gcmd.error("[print_task_config] Invalid MAP_TABLE")

                for i in range(len(map_table_list)):
                    if len(map_table_list[i]) != 2:
                        raise gcmd.error("[print_task_config] Invalid MAP_TABLE")
                    else:
                        if not isinstance(map_table_list[i][0], int) or not isinstance(map_table_list[i][1], int):
                            raise gcmd.error("[print_task_config] Invalid MAP_TABLE")
                        if map_table_list[i][0] >= LOGICAL_EXTRUDER_NUM or map_table_list[i][1] >= PHYSICAL_EXTRUDER_NUM:
                            raise gcmd.error("[print_task_config] Invalid MAP_TABLE")

                    tmp_print_task_config['extruder_map_table'][map_table_list[i][0]] = map_table_list[i][1]

            # preferences
            if bed_level is not None:
                tmp_print_task_config['auto_bed_leveling'] = bool(bed_level)
            if flow_calibrate is not None:
                tmp_print_task_config['flow_calibrate'] = bool(flow_calibrate)
            if flow_calibrate_extruders is not None:
                flow_calibrate_extruders_list = None
                try:
                    flow_calibrate_extruders_list = self._parse_str_to_list(flow_calibrate_extruders)
                except:
                    raise gcmd.error("[print_task_config] Invalid FLOW_CALIBRATE_EXTRUDERS")
                tmp_print_task_config['flow_calib_extruders'] = [False for i in range(PHYSICAL_EXTRUDER_NUM)]

                if len(flow_calibrate_extruders_list) > PHYSICAL_EXTRUDER_NUM:
                    raise gcmd.error("[print_task_config] Invalid FLOW_CALIBRATE_EXTRUDERS")

                for i in range(len(flow_calibrate_extruders_list)):
                    if not isinstance(flow_calibrate_extruders_list[i], int):
                        raise gcmd.error("[print_task_config] Invalid FLOW_CALIBRATE_EXTRUDERS")
                    if flow_calibrate_extruders_list[i] >= PHYSICAL_EXTRUDER_NUM:
                        raise gcmd.error("[print_task_config] Invalid FLOW_CALIBRATE_EXTRUDERS")
                    tmp_print_task_config['flow_calib_extruders'][flow_calibrate_extruders_list[i]] = True
            if time_lapse_camera is not None:
                tmp_print_task_config['time_lapse_camera'] = bool(time_lapse_camera)
            if shaper_calibrate is not None:
                tmp_print_task_config['shaper_calibrate'] = bool(shaper_calibrate)
            if end_unload_filament is not None:
                end_unload_filament_list = None
                try:
                    end_unload_filament_list = self._parse_str_to_list(end_unload_filament)
                except Exception as e:
                    raise gcmd.error("Invalid END_UNLOAD_FILAMENT")

                tmp_print_task_config.update({'end_unload_filament': [False for i in range(PHYSICAL_EXTRUDER_NUM)]})

                for i in range(min(len(end_unload_filament_list), PHYSICAL_EXTRUDER_NUM)):
                    if not isinstance(end_unload_filament_list[i], int):
                        raise gcmd.error("[print_task_config] Invalid END_UNLOAD_EXTRUDERS")
                    tmp_print_task_config['end_unload_filament'][i] = bool(end_unload_filament_list[i])

            # gcode parameters
            if line_width is not None:
                tmp_print_task_config_2['line_width'] = line_width
            if layer_height is not None:
                tmp_print_task_config_2['layer_height'] = layer_height

            try:
                if filament_type is not None:
                    filament_type_list = self._parse_str_to_list(filament_type)

                    if len(filament_type_list) > LOGICAL_EXTRUDER_NUM:
                        raise gcmd.error("[print_task_config] Invalid FILAMENT_TYPE")

                    for i in range(len(filament_type_list)):
                        if not isinstance(filament_type_list[i], str):
                            raise gcmd.error("[print_task_config] Invalid FILAMENT_TYPE")
                        tmp_print_task_config_2['filament_type'][i] = filament_type_list[i]
            except Exception as e:
                logging.exception(e)
                tmp_print_task_config_2['filament_type'] = [None for i in range(LOGICAL_EXTRUDER_NUM)]

            try:
                if nozzle_diameter is not None:
                    nozzle_diameter_list  = self._parse_str_to_list(nozzle_diameter)

                    if len(nozzle_diameter_list) > LOGICAL_EXTRUDER_NUM:
                        raise gcmd.error("[print_task_config] Invalid NOZZLE_DIAMETER")

                    for i in range(len(nozzle_diameter_list)):
                        if not isinstance(nozzle_diameter_list[i], float):
                            raise gcmd.error("[print_task_config] Invalid NOZZLE_DIAMETER")
                        tmp_print_task_config_2['nozzle_diameter'][i] = float(nozzle_diameter_list[i])
            except Exception as e:
                logging.exception(e)
                tmp_print_task_config_2['nozzle_diameter'] = [0 for i in range(LOGICAL_EXTRUDER_NUM)]

            try:
                if nozzle_temp is not None:
                    nozzle_temp_list = self._parse_str_to_list(nozzle_temp)

                    if len(nozzle_temp_list) > LOGICAL_EXTRUDER_NUM:
                        raise gcmd.error("[print_task_config] Invalid NOZZLE_TEMP")

                    for i in range(len(nozzle_temp_list)):
                        if not isinstance(nozzle_temp_list[i], float) and not isinstance(nozzle_temp_list[i], int):
                            raise gcmd.error("[print_task_config] Invalid NOZZLE_TEMP")
                        tmp_print_task_config_2['nozzle_temp'][i] = float(nozzle_temp_list[i])
            except Exception as e:
                logging.exception(e)
                tmp_print_task_config_2['nozzle_temp'] = [0 for i in range(LOGICAL_EXTRUDER_NUM)]

            try:
                if filament_flow_ratio is not None:
                    filament_flow_ratio_list = self._parse_str_to_list(filament_flow_ratio)

                    if len(filament_flow_ratio_list) > LOGICAL_EXTRUDER_NUM:
                        raise gcmd.error("[print_task_config] Invalid FILAMENT_FLOW_RATIO")

                    for i in range(len(filament_flow_ratio_list)):
                        if not isinstance(filament_flow_ratio_list[i], float) and not isinstance(filament_flow_ratio_list[i], int):
                            raise gcmd.error("[print_task_config] Invalid FILAMENT_FLOW_RATIO")
                        if filament_flow_ratio_list[i] <= 0.001:
                            raise gcmd.error("[print_task_config] Invalid FILAMENT_FLOW_RATIO")
                        tmp_print_task_config_2['filament_flow_ratio'][i] = float(filament_flow_ratio_list[i])
            except Exception as e:
                logging.exception(e)
                tmp_print_task_config_2['filament_flow_ratio'] = [1.0 for i in range(LOGICAL_EXTRUDER_NUM)]

            nozzle_volume_index_standard = 0
            nozzle_volume_index_high_flow = 1
            try:
                if process_flow_support is not None:
                    process_flow_support_list = self._parse_str_to_list(process_flow_support)
                    if len(process_flow_support_list) >= 2 and process_flow_support_list[0] == 'high_flow' and \
                            process_flow_support_list[1] == 'standard':
                        nozzle_volume_index_standard = 1
                        nozzle_volume_index_high_flow = 0
            except Exception as e:
                logging.exception(e)

            tmp_print_task_config_2['outer_wall_accel'] = 5000
            tmp_print_task_config_2['outer_wall_accel_hf'] = 5000
            try:
                if outer_wall_accel_list is not None:
                    outer_wall_accel_list_list = self._parse_str_to_list(outer_wall_accel_list)
                    if len(outer_wall_accel_list_list) == 1:
                        tmp_print_task_config_2['outer_wall_accel'] = float(outer_wall_accel_list_list[0])
                    elif len(outer_wall_accel_list_list) == 2:
                        tmp_print_task_config_2['outer_wall_accel'] = float(outer_wall_accel_list_list[nozzle_volume_index_standard])
                        tmp_print_task_config_2['outer_wall_accel_hf'] = float(outer_wall_accel_list_list[nozzle_volume_index_high_flow])
            except Exception as e:
                logging.exception(e)
                tmp_print_task_config_2['outer_wall_accel'] = 5000
                tmp_print_task_config_2['outer_wall_accel_hf'] = 5000

            tmp_print_task_config_2['outer_wall_speed'] = 200
            tmp_print_task_config_2['outer_wall_speed_hf'] = 200
            try:
                if outer_wall_speed_list is not None:
                    outer_wall_speed_list_list = self._parse_str_to_list(outer_wall_speed_list)
                    if len(outer_wall_speed_list_list) == 1:
                        tmp_print_task_config_2['outer_wall_speed'] = float(outer_wall_speed_list_list[0])
                    elif len(outer_wall_speed_list_list) == 2:
                        tmp_print_task_config_2['outer_wall_speed'] = float(outer_wall_speed_list_list[nozzle_volume_index_standard])
                        tmp_print_task_config_2['outer_wall_speed_hf'] = float(outer_wall_speed_list_list[nozzle_volume_index_high_flow])
            except Exception as e:
                logging.exception(e)
                tmp_print_task_config_2['outer_wall_speed'] = 200
                tmp_print_task_config_2['outer_wall_speed_hf'] = 200

            try:
                if filament_max_vol_speed is not None:
                    filament_max_vol_speed_list = self._parse_str_to_list(filament_max_vol_speed)

                    if len(filament_max_vol_speed_list) > LOGICAL_EXTRUDER_NUM:
                        raise gcmd.error("[print_task_config] Invalid FILAMENT_MAX_VOLUMETRIC_SPEED")

                    for i in range(len(filament_max_vol_speed_list)):
                        if not isinstance(filament_max_vol_speed_list[i], float) and not isinstance(filament_max_vol_speed_list[i], int):
                            raise gcmd.error("[print_task_config] Invalid FILAMENT_MAX_VOLUMETRIC_SPEED")
                        tmp_print_task_config_2['filament_max_vol_speed'][i] = float(filament_max_vol_speed_list[i])
            except Exception as e:
                logging.exception(e)
                tmp_print_task_config_2['filament_max_vol_speed'] = [0 for i in range(LOGICAL_EXTRUDER_NUM)]

            try:
                if filament_volume_type is not None:
                    filament_volume_type_list = None
                    try:
                        filament_volume_type_list = self._parse_str_to_list(filament_volume_type)
                    except:
                        raise gcmd.error("[print_task_config] Invalid FILAMENT_VOLUME_TYPE")
                    if len(filament_volume_type_list) > LOGICAL_EXTRUDER_NUM:
                        raise gcmd.error("[print_task_config] Invalid FILAMENT_VOLUME_TYPE")
                    for i in range(len(filament_volume_type_list)):
                        if not isinstance(filament_volume_type_list[i], str):
                            raise gcmd.error("[print_task_config] Invalid FILAMENT_VOLUME_TYPE")
                        tmp_print_task_config_2['filament_volume_type'][i] = filament_volume_type_list[i]
            except Exception as e:
                logging.exception(e)
                tmp_print_task_config_2['filament_volume_type'] = ['standard' for i in range(LOGICAL_EXTRUDER_NUM)]

            try:
                if filament_used_g is not None:
                    filament_used_g_list = self._parse_str_to_list(filament_used_g)

                    if len(filament_used_g_list) > LOGICAL_EXTRUDER_NUM:
                        raise gcmd.error("[print_task_config] Invalid FILAMENT_USED_G")

                    for i in range(len(filament_used_g_list)):
                        if not isinstance(filament_used_g_list[i], float) and not isinstance(filament_used_g_list[i], int):
                            raise gcmd.error("[print_task_config] Invalid FILAMENT_USED_G")
                        tmp_print_task_config_2['filament_used_g'][i] = float(filament_used_g_list[i])
            except Exception as e:
                logging.exception(e)
                tmp_print_task_config_2['filament_used_g'] = [0 for i in range(LOGICAL_EXTRUDER_NUM)]

            try:
                if filament_used_mm is not None:
                    filament_used_mm_list = self._parse_str_to_list(filament_used_mm)

                    if len(filament_used_mm_list) > LOGICAL_EXTRUDER_NUM:
                        raise gcmd.error("[print_task_config] Invalid FILAMENT_USED_MM")

                    for i in range(len(filament_used_mm_list)):
                        if not isinstance(filament_used_mm_list[i], float) and not isinstance(filament_used_mm_list[i], int):
                            raise gcmd.error("[print_task_config] Invalid FILAMENT_USED_MM")
                        tmp_print_task_config_2['filament_used_mm'][i] = float(filament_used_mm_list[i])
            except Exception as e:
                logging.exception(e)
                tmp_print_task_config_2['filament_used_mm'] = [0 for i in range(LOGICAL_EXTRUDER_NUM)]

            ########## check parameters ###########
            # extruders_used
            for i in range(LOGICAL_EXTRUDER_NUM):
                if tmp_print_task_config_2['filament_used_g'][i] > 0.0001 or tmp_print_task_config_2['filament_used_mm'][i] > 0.0001:
                    tmp_print_task_config['extruders_used'][tmp_print_task_config['extruder_map_table'][i]] = True

            # check nozzle diameter
            if nozzle_diameter is not None:
                for i in range(PHYSICAL_EXTRUDER_NUM):
                    if tmp_print_task_config['extruders_used'][i]:
                        if abs(tmp_print_task_config_2['nozzle_diameter'][0] - actual_nozzle_diameter[i]) > 0.001:
                            exception_code = 14
                            raise gcmd.error(f"[print_task_config] nozzle diameter mismatch:" +
                                                f"f{i}_{tmp_print_task_config_2['nozzle_diameter'][0]} != e{i}_{actual_nozzle_diameter[i]}")

            # check filament volume type
            if filament_volume_type is not None:
                for i in range(min(LOGICAL_EXTRUDER_NUM, len(tmp_print_task_config_2['filament_volume_type']))):
                    if tmp_print_task_config_2['filament_volume_type'][i] == None:
                        continue
                    if tmp_print_task_config_2['filament_used_g'][i] < 0.0001 and tmp_print_task_config_2['filament_used_mm'][i] < 0.0001:
                        continue
                    map_e = tmp_print_task_config['extruder_map_table'][i]
                    if tmp_print_task_config['extruders_used'][map_e]:
                        if tmp_print_task_config_2['filament_volume_type'][i] != actual_nozzle_volume_type[map_e]:
                            exception_code = 19
                            raise gcmd.error("[print_task_config] nozzle volume type mismatch:" +
                                f"f{i}_{tmp_print_task_config_2['filament_volume_type'][i]} != " +
                                f"e{map_e}_{actual_nozzle_volume_type[map_e]}")
            else:
                if slicer == SNAPMAKER_OFFICIAL_ORCASLICER:
                    for i in range(PHYSICAL_EXTRUDER_NUM):
                        if tmp_print_task_config['extruders_used'][i]:
                            if actual_nozzle_volume_type[i] != 'standard':
                                exception_code = 19
                                raise gcmd.error("[print_task_config] nozzle volume type mismatch:" +
                                    f"f_standard != e{i}_{actual_nozzle_volume_type[i]}")

            # check flow calibration
            if tmp_print_task_config['flow_calibrate']:
                for i in range(PHYSICAL_EXTRUDER_NUM):
                    if tmp_print_task_config['extruders_used'][i] == False:
                        continue
                    if tmp_print_task_config['flow_calib_extruders'][i] == False:
                        continue
                    is_allow = self.filament_param_obj.is_allow_to_print(
                            tmp_print_task_config['filament_vendor'][i],
                            tmp_print_task_config['filament_type'][i],
                            tmp_print_task_config['filament_sub_type'][i],
                            actual_nozzle_diameter[i],
                            actual_nozzle_volume_type[i])
                    if not is_allow:
                        exception_code = 18
                        raise gcmd.error("[flow_calibrate] %.1f nozzle, %s %s %s not allow to calibrate!" % (
                                            actual_nozzle_diameter[i],
                                            tmp_print_task_config['filament_vendor'][i],
                                            tmp_print_task_config['filament_type'][i],
                                            tmp_print_task_config['filament_sub_type'][i]))

            self.print_task_config = tmp_print_task_config
            self.print_task_config_2 = tmp_print_task_config_2
            if not self.printer.update_snapmaker_config_file(self.config_path, self.print_task_config, DEFAULT_PRINT_TASK_CONFIG):
                logging.error("[print_task_config] Failed to update print task config")
            if not self.printer.update_snapmaker_config_file(self.config_path_2, self.print_task_config_2, DEFAULT_PRINT_TASK_CONFIG_2):
                logging.error("[print_task_config] Failed to update print task config 2")

        except Exception as e:
            raise gcmd.error(
                message = f"{str(e)}",
                id = exception_id,
                code = exception_code,
                index = exception_index,
                oneshot = exception_oneshot,
                level = exception_level)

    def cmd_INNER_PRINT_END(self, gcmd):
        self.is_exec_print_end_action = True

def load_config(config):
    return PrintTaskConfig(config)
