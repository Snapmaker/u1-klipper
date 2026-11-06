import logging, json, copy, os
from . import fan
from . import pulse_counter

FAN_STATE_TURN_ON                                   = 0
FAN_STATE_TURN_OFF                                  = 1


DEFAULT_POWER_DT_SAMPLE_TIME                        = 0.08
DEFAULT_POWER_DT_SAMPLE_COUNT                       = 4
DEFAULT_POWER_DT_REPORT_TIME                        = 0.350
DEFAULT_POWER_DT_THRESHOLD                          = 0.88


class PurifierFanTachometer:
    def __init__(self, printer, pin, ppr, sample_time, poll_time):
        self._frequence = pulse_counter.FrequencyCounter(printer, pin, sample_time, poll_time)
        self._ppr = ppr

    def get_status(self, eventtime=None):
        rpm = None
        if self._frequence is not None:
            if self._ppr > 0:
                rpm = self._frequence.get_frequency() * 30. / self._ppr
            else:
                rpm = 0.0
        return {'rpm': rpm}

class Purifier:
    def __init__(self, config):
        self.printer = config.get_printer()
        ppins = self.printer.lookup_object('pins')
        self.reactor = self.printer.get_reactor()

        # read config
        tach_ppr = config.getint('tachometer_ppr', 2, minval=1)
        tach_poll_time = config.getfloat('tachometer_poll_interval', 0.001)
        extra_fan_tach_pin = config.get('extra_fan_tach_pin')

        # main fan
        self._fan = fan.Fan(config, default_shutdown_speed=0.)
        # extra fan
        sample_time = 1.
        self._extra_fan_tach = PurifierFanTachometer(self.printer, extra_fan_tach_pin,
                                    tach_ppr, sample_time, tach_poll_time)

        # power detect
        power_det_pin = config.get('power_det_pin')
        self._power_det_threshold = config.getfloat('power_det_threshold', DEFAULT_POWER_DT_THRESHOLD)
        self._power_det_pin = ppins.setup_pin('adc', power_det_pin)
        self._power_det_pin.setup_adc_sample(DEFAULT_POWER_DT_SAMPLE_TIME, DEFAULT_POWER_DT_SAMPLE_COUNT)
        self._power_det_pin.setup_adc_callback(DEFAULT_POWER_DT_REPORT_TIME, self._adc_callback)
        self._power_detected = False
        self._power_det_value = 1

        self._fan_state = FAN_STATE_TURN_OFF

        # gcode commands
        gcode = self.printer.lookup_object("gcode")
        gcode.register_command('SET_PURIFIER', self.cmd_SET_PURIFIER)
        gcode.register_command('GET_PURIFIER', self.cmd_GET_PURIFIER)

        # webhook api
        wh = self.printer.lookup_object('webhooks')
        wh.register_endpoint("control/purifier_factory", self._handle_control_purifier)

    def _adc_callback(self, read_time, read_value):
        self._power_det_value = read_value
        if (self._power_det_value < self._power_det_threshold):
            self._power_detected = True
        else:
            if self._power_detected:
                self.set_fan_speed(0)
            self._power_detected = False

    def set_fan_speed(self, speed):
        if speed <= 0:
            self._fan_state = FAN_STATE_TURN_OFF
            speed = 0
        else:
            if speed > 1.0:
                speed = 1.0
            self._fan_state = FAN_STATE_TURN_ON

        self._fan.set_speed_from_command(speed)

    def get_fan_speed(self):
        return self._fan.last_fan_value

    def get_status(self, eventtime):
        fan_status = self._fan.get_status(eventtime)
        extra_fan_status = self._extra_fan_tach.get_status(eventtime)

        return {
            'power_detected': self._power_detected,
            'power_det_value': self._power_det_value * 3.3,
            'fan_state': self._fan_state,
            'fan_speed': fan_status['speed'],
            'fan_rpm': fan_status['rpm'],
            'extra_fan_speed': fan_status['speed'],
            'extra_fan_rpm': extra_fan_status['rpm']
        }

    def cmd_SET_PURIFIER(self, gcmd):
        fan_speed = gcmd.get_int('FAN_SPEED', None, minval= 0, maxval=255)

        if fan_speed is not None:
            if not self._power_detected and fan_speed > 0:
                raise gcmd.error("Purifier not exist!")
            self.set_fan_speed(fan_speed / 255.0)

    def cmd_GET_PURIFIER(self, gcmd):
        sta = self.get_status(self.reactor.monotonic())
        gcmd.respond_info(str(sta), log=False)

    def _handle_control_purifier(self, web_request):
        try:
            fan_speed = web_request.get_int('fan_speed', None)

            if fan_speed is not None:
                if not self._power_detected and fan_speed > 0:
                    raise ValueError("Purifier not exist!")
                self.set_fan_speed(fan_speed / 100.0)

            web_request.send({'state': 'success'})

        except Exception as e:
            web_request.send({'state': 'error', 'message': str(e)})

def load_config(config):
    return Purifier(config)

