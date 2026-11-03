# Support fans that are controlled by gcode
#
# Copyright (C) 2016-2020  Kevin O'Connor <kevin@koconnor.net>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
from . import fan
import logging

class PrinterFanGeneric:
    cmd_SET_FAN_SPEED_help = "Sets the speed of a fan"
    def __init__(self, config):
        self.printer = config.get_printer()
        self.fan = fan.Fan(config, default_shutdown_speed=0.)
        self.fan_name = config.get_name().split()[-1]

        gcode = self.printer.lookup_object("gcode")
        gcode.register_mux_command("SET_FAN_SPEED", "FAN",
                                   self.fan_name,
                                   self.cmd_SET_FAN_SPEED,
                                   desc=self.cmd_SET_FAN_SPEED_help)
        wh = self.printer.lookup_object('webhooks')
        wh.register_mux_endpoint("control/generic_fan", 'fan', self.fan_name, self._handle_control_generic_fan)
    def _handle_control_generic_fan(self, web_request):
        try:
            speed = web_request.get_int('S', 0)
            if speed > 100:
                speed = 100
            if speed < 0:
                speed = 0
            self.fan.set_speed_from_command(speed / 100.0)
            web_request.send({'state': 'success'})
        except Exception as e:
            logging.error(f'failed to set fan: {str(e)}')
            web_request.send({'state': 'error', 'message': str(e)})
    def get_status(self, eventtime):
        return self.fan.get_status(eventtime)
    def cmd_SET_FAN_SPEED(self, gcmd):
        speed = gcmd.get_float('SPEED', 0.)
        self.fan.set_speed_from_gcode(speed)

def load_config_prefix(config):
    return PrinterFanGeneric(config)
