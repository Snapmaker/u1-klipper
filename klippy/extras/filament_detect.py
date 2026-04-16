import logging, copy, os
from . import filament_protocol
from . import fm175xx_reader
from . import filament_feed

# Error code
FILAMENT_DT_OK                                  = 0
FILAMENT_DT_ERR                                 = -1
FILAMENT_DT_PARAM_ERR                           = -2

# State
FILAMENT_DT_STATE_IDLE                          = 0
FILAMENT_DT_STATE_DETECTING                     = 1
FILAMENT_DT_STATE_SELF_TESTING                  = 2

FILAMENT_DT_CHANNEL_NUMS                        = 4
FILAMENT_DT_CONFIG_FILE                         = "filament_detect.json"

DEFAULT_FILAMENT_DT_CONFIG = {
    'startup_stay': False
}

class FilamentDetector:
    def __init__(self, config) -> None:
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()

        config_dir = self.printer.get_snapmaker_config_dir()
        config_name = FILAMENT_DT_CONFIG_FILE
        self._config_path = os.path.join(config_dir, config_name)

        self._config = self.printer.load_snapmaker_config_file(self._config_path, DEFAULT_FILAMENT_DT_CONFIG)

        self._channel_nums = FILAMENT_DT_CHANNEL_NUMS
        self._filament_info = [copy.deepcopy(filament_protocol.FILAMENT_INFO_STRUCT) for i in range(self._channel_nums)]
        self._state = [FILAMENT_DT_STATE_IDLE for i in range(self._channel_nums)]
        self._notify_data_update_cb = []

        self.filament_feed_objects = None
        self._fm175xx_reader = None
        self._self_test_success_cnt = 0

        gcode = self.printer.lookup_object('gcode')
        gcode.register_command('FILAMENT_DT_QUERY', self.cmd_FILAMENT_DT_QUERY)
        gcode.register_command('FILAMENT_DT_UPDATE', self.cmd_FILAMENT_DT_UPDATE)
        gcode.register_command('FILAMENT_DT_CLEAR', self.cmd_FILAMENT_DT_CLEAR)
        gcode.register_command('FILAMENT_DT_SELF_TEST', self.cmd_FILAMENT_DT_SELF_TEST)
        gcode.register_command('FILAMENT_DT_STARTUP_STAY', self.cmd_FILAMENT_DT_STARTUP_STAY)

        self.printer.register_event_handler("klippy:ready", self._ready)
        self.printer.register_event_handler("filament_feed:port", self._feed_port_evt_handle)
        self.printer.register_event_handler("filament_switch_sensor:runout", self._runout_evt_handle)

    def _ready(self):
        self.filament_feed_objects = self.printer.lookup_objects('filament_feed')
        self._fm175xx_reader = self.printer.lookup_object('fm175xx_reader')
        if (self._fm175xx_reader is not None):
            self._fm175xx_reader.register_cb_2_card_info_deal(self._fm175xx_card_info_deal_callback)

        if self._config['startup_stay'] == False:
            for i in range(self._channel_nums):
                filament_sensor = self.printer.lookup_object('filament_motion_sensor e%d_filament' % (i))
                if filament_sensor.get_status(0)['filament_detected'] and filament_sensor.get_status(0)['enabled']:
                    self.request_update_filament_info(i)

    def _feed_port_evt_handle(self, channel, detect):
        filament_sensor = self.printer.lookup_object('filament_motion_sensor e%d_filament' % (channel))
        filament_sensor_status = filament_sensor.get_status(0)

        if filament_sensor_status['filament_detected'] and filament_sensor_status['enabled']:
            pass
        else:
            if detect:
                self.request_update_filament_info(channel)
            else:
                self.request_clear_filament_info(channel)

    def _runout_evt_handle(self, extruder, present):
        filament_feed_infos = {}
        for obj_name, obj in self.filament_feed_objects:
            status = obj.get_status(0)
            filament_feed_infos.update(status)
        e_obj = filament_feed_infos.get('extruder%d' % (extruder), None)

        if e_obj is not None and e_obj['module_exist'] and not e_obj['disable_auto']:
            if present:
                self.request_update_filament_info(extruder)
            else:
                if e_obj['filament_detected'] == True:
                    self.request_clear_filament_info(extruder)
                    self.request_update_filament_info(extruder)
                else:
                    self.request_clear_filament_info(extruder)
        else:
            if present:
                self.request_update_filament_info(extruder)
            else:
                self.request_clear_filament_info(extruder)


    def _filament_info_update(self, channel, info, is_clear=False):
        self._filament_info[channel] = info

        # notify
        if (0 != len(self._notify_data_update_cb)):
            for i in range(len(self._notify_data_update_cb)):
                self.reactor.register_async_callback(
                    (lambda et, c=self._notify_data_update_cb[i],
                        info=self._filament_info[channel]: c(channel, info, is_clear)))

    def _fm175xx_card_info_deal_callback(self, channel, operation, result, card_type, card_data):
        filament_info = None
        is_clear = False

        if channel < 0 or channel >= self._channel_nums:
            return

        if (fm175xx_reader.FM175XX_CARD_INFO_READ == operation):
            if (fm175xx_reader.FM175XX_MIFARE_CARD_TYPE_M1 == card_type and  fm175xx_reader.FM175XX_OK == result):
                logging.info("channel[%d] m1 card data parsing....", channel)
                error, info = filament_protocol.m1_proto_data_parse(card_data)
                if (error == filament_protocol.FILAMENT_PROTO_OK):
                    logging.info("channel[%d] m1 parse ok....", channel)
                    filament_info = info
                else:
                    logging.error("channel[%d] m1 parse err: %d", channel, error)
            elif (fm175xx_reader.FM175XX_MIFARE_CARD_TYPE_NTAG == card_type and fm175xx_reader.FM175XX_OK == result):
                logging.info("channel[%d] ntag card data parsing....", channel)
                error, info = filament_protocol.ntag_ndef_data_parse(card_data)
                if (error == filament_protocol.FILAMENT_PROTO_OK):
                    logging.info("channel[%d] ntag parse ok....", channel)
                    filament_info = info
                else:
                    logging.error("channel[%d] ntag parse err: %d", channel, error)
        else:
            is_clear = True

        if (filament_info is None):
            filament_info = copy.deepcopy(filament_protocol.FILAMENT_INFO_STRUCT)
        else:
            self._self_test_success_cnt += 1

        self._state[channel] = FILAMENT_DT_STATE_IDLE
        self._filament_info_update(channel, filament_info, is_clear)

    def register_cb_2_update_filament_info(self, cb):
        try:
            if callable(cb):
                self._notify_data_update_cb.append(cb)
            else:
                raise TypeError()
        except Exception as e:
            logging.error("Param[cb] is not a callable function")

    def request_update_filament_info(self, channel):
        if channel < 0 or channel >= self._channel_nums:
            return

        if self._fm175xx_reader is not None:
            self._state[channel] = FILAMENT_DT_STATE_DETECTING
            self._fm175xx_reader.request_read_card_info(channel)

    def request_clear_filament_info(self, channel):
        if channel < 0 or channel >= self._channel_nums:
            return

        if self._fm175xx_reader is not None:
            self._state[channel] = FILAMENT_DT_STATE_DETECTING
            self._fm175xx_reader.request_clear_card_info(channel)

    def get_a_filament_info(self, channel):
        error = FILAMENT_DT_ERR
        info = None

        if channel < 0 or channel >= self._channel_nums:
            error = FILAMENT_DT_PARAM_ERR
        else:
            error = FILAMENT_DT_OK
            info = self._filament_info[channel]

        return error, info

    def get_all_filament_info(self):
        return self._filament_info

    def is_startup_stay(self):
        return self._config['startup_stay']

    def cmd_FILAMENT_DT_QUERY(self, gcmd):
        channel = gcmd.get_int('CHANNEL', None)

        if (channel is None):
            raise gcmd.error("CHANNEL must be specified!")

        if (channel < 0 or channel >= self._channel_nums):
            msg = ("channel[%d] is out of range[0, %d]" % (channel, self._channel_nums - 1))
            raise gcmd.error(msg)

        msg = ("channel[%d] vendor = %s, main_type: %s, sub_type= %s, rgba_color = %08X\n"
                % (channel,
                    self._filament_info[channel]['VENDOR'],
                    self._filament_info[channel]['MAIN_TYPE'],
                    self._filament_info[channel]['SUB_TYPE'],
                    self._filament_info[channel]['ARGB_COLOR']))
        gcmd.respond_info(msg, log=False)

    def cmd_FILAMENT_DT_UPDATE(self, gcmd):
        channel = gcmd.get_int('CHANNEL', None)

        if (channel is None):
            raise gcmd.error("CHANNEL must be specified!")

        if (channel < 0 or channel >= self._channel_nums):
            msg = ("channel[%d] is out of range[0, %d]" % (channel, self._channel_nums - 1))
            raise gcmd.error(msg)

        self.request_update_filament_info(channel)

    def cmd_FILAMENT_DT_CLEAR(self, gcmd):
        channel = gcmd.get_int('CHANNEL', None)

        if (channel is None):
            raise gcmd.error("CHANNEL must be specified!")

        if (channel < 0 or channel >= self._channel_nums):
            msg = ("channel[%d] is out of range[0, %d]" % (channel, self._channel_nums - 1))
            raise gcmd.error(msg)

        self.request_clear_filament_info(channel)

    def cmd_FILAMENT_DT_SELF_TEST(self, gcmd):
        channel = gcmd.get_int('CHANNEL', None)
        times = gcmd.get_int('TIMES', 100)

        if (channel is None):
            raise gcmd.error("CHANNEL must be specified!")

        if (channel < 0 or channel >= self._channel_nums):
            msg = ("channel[%d] is out of range[0, %d]" % (channel, self._channel_nums - 1))
            raise gcmd.error(msg)

        self._state[channel] = FILAMENT_DT_STATE_SELF_TESTING
        finish = False
        test_times = 0
        success_times = 0
        self._self_test_success_cnt = 0
        self._fm175xx_reader.self_test(channel, times)
        while (1):
            finish, test_times, success_times = self._fm175xx_reader.self_test_result()
            if finish:
                break
            self.reactor.pause(self.reactor.monotonic() + 0.3)

        msg = ("channel[%d] test times = %d, success times: %d\n" % (
                channel, test_times, self._self_test_success_cnt))
        gcmd.respond_info(msg, log=False)
        msg = ("channel[%d] vendor = %s, main_type: %s, sub_type= %s, rgba_color = %08X\n"
                % (channel,
                    self._filament_info[channel]['VENDOR'],
                    self._filament_info[channel]['MAIN_TYPE'],
                    self._filament_info[channel]['SUB_TYPE'],
                    self._filament_info[channel]['ARGB_COLOR']))
        gcmd.respond_info(msg, log=False)
        self._state[channel] = FILAMENT_DT_STATE_IDLE

    def cmd_FILAMENT_DT_STARTUP_STAY(self, gcmd):
        stay = gcmd.get_int('STAY', None)
        need_save = gcmd.get_int('SAVE', 1, minval=0, maxval=1)
        if (stay is None):
            raise gcmd.error("STAY must be specified!")

        self._config['startup_stay']= bool(stay)

        if (need_save):
            load_config = self.printer.load_snapmaker_config_file(self._config_path, DEFAULT_FILAMENT_DT_CONFIG)
            load_config['startup_stay'] = bool(stay)
            ret = self.printer.update_snapmaker_config_file(self._config_path, load_config, DEFAULT_FILAMENT_DT_CONFIG)
            if not ret:
                raise gcmd.error("save startup stay failed!")

    def get_status(self, eventtime=None):
        return {
            'info': copy.deepcopy(self._filament_info),
            'state': copy.deepcopy(self._state),
            'config': copy.deepcopy(self._config)}

    def factory_reset(self):
        self._config = copy.deepcopy(DEFAULT_FILAMENT_DT_CONFIG)
        ret = self.printer.update_snapmaker_config_file(self._config_path, self._config, DEFAULT_FILAMENT_DT_CONFIG)
        if not ret:
            logging.error("save filament_detect config failed!")
        return ret

def load_config(config):
    return FilamentDetector(config)

