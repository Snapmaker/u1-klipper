# Support for extruder park detection
import logging

class ParkDetector:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.name = config.get_name().split(' ')[-1]
        self.pin = config.get('pin')
        self.active_state = 0
        self.park_state = 0
        self.grab_valid_state = 0
        self.ignore_active_pin = config.getboolean('ignore_active_pin', False)
        self.gcode = self.printer.lookup_object('gcode')
        self.park_adc_button = None
        self.active_adc_button = None
        self.grab_valid_adc_button = None
        buttons = self.printer.load_object(config, "buttons")
        if config.get('analog_range', None) is None:
            buttons.register_buttons([self.pin], self.park_detector_callback)
        else:
            amin, amax = config.getfloatlist('analog_range', count=2)
            pullup = config.getfloat('analog_pullup_resistor', 4700., above=0.)
            self.park_adc_button = buttons.register_adc_button(self.pin, amin, amax, pullup,
                                        self.park_detector_callback)

        self.active_pin = config.get('active_pin', None)
        if self.active_pin is not None:
            if config.get('active_analog_range', None) is None:
                buttons.register_buttons([self.active_pin], self.active_detector_callback)
            else:
                amin, amax = config.getfloatlist('active_analog_range', count=2)
                pullup = config.getfloat('active_analog_pullup_resistor', 4700., above=0.)
                self.active_adc_button = buttons.register_adc_button(self.active_pin, amin, amax, pullup,
                                            self.active_detector_callback)

        self.grab_valid_pin = config.get('grab_valid_pin', None)
        if self.grab_valid_pin is not None:
            if config.get('grab_valid_analog_range', None) is None:
                buttons.register_buttons([self.grab_valid_pin], self.grab_valid_detector_callback)
            else:
                amin, amax = config.getfloatlist('grab_valid_analog_range', count=2)
                pullup = config.getfloat('grab_valid_analog_pullup_resistor', 4700., above=0.)
                self.grab_valid_adc_button = buttons.register_adc_button(self.grab_valid_pin, amin, amax, pullup,
                                            self.grab_valid_detector_callback)

        self.gcode.register_mux_command("QUERY_PARK_STA", "NAME", self.name,
                                        self.cmd_QUERY_PARK,
                                        desc=self.cmd_QUERY_PARK_help)

    cmd_QUERY_PARK_help = "Report on the state of a Park Detector"
    def cmd_QUERY_PARK(self, gcmd):
        state = self.get_park_detector_status()
        msg_info = self.name + " state: " + state['state'] + '\n'
        msg_info += "park_pin: {} active_pin: {} grab_valid_pin: {}".format(state['park_pin'], state['active_pin'], state['grab_valid_pin'])
        self.get_park_detector_adc_value()
        gcmd.respond_info(msg_info)

    def park_detector_callback(self, eventtime, state):
        self.park_state = bool(state)
        # self.gcode.respond_info("{} park_state {}, tick {}".format(self.name, self.park_state, self.reactor.monotonic()))

    def active_detector_callback(self, eventtime, state):
        self.active_state = bool(state)
        # self.gcode.respond_info("{} active_state {}, tick {}".format(self.name, self.active_state, self.reactor.monotonic()))

    def grab_valid_detector_callback(self, eventtime, state):
        self.grab_valid_state = bool(state)

    def get_park_detector_status(self):
        state = {}
        if self.active_pin is not None and not self.ignore_active_pin:
            if self.active_state and not self.park_state:
                state['state'] = 'ACTIVATE'
            elif not self.active_state and self.park_state:
                state['state'] = 'PARKED'
            else:
                state['state'] = 'UNKNOWN'
        else:
            state['state'] =  'PARKED' if self.park_state else 'ACTIVATE'
        state['park_pin'] = bool(self.park_state)
        state['active_pin'] = bool(self.active_state) if self.active_pin is not None else bool(not self.park_state)
        state['grab_valid_pin'] = bool(self.grab_valid_state)
        # self.get_park_detector_adc_value()
        return state

    def get_park_detector_adc_value(self):
        if self.park_adc_button is not None and getattr(self.park_adc_button, 'last_adc_value', None) is not None:
            self.gcode.respond_info("{} park_adc {:.3f}v".format(self.name, self.park_adc_button.last_adc_value*3.3))
        if self.active_adc_button is not None and getattr(self.active_adc_button, 'last_adc_value', None) is not None:
            self.gcode.respond_info("{} active_adc {:.3f}v".format(self.name, self.active_adc_button.last_adc_value*3.3))
        if self.grab_valid_adc_button is not None and getattr(self.grab_valid_adc_button, 'last_adc_value', None) is not None:
            self.gcode.respond_info("{} grab_valid_adc {:.3f}v".format(self.name, self.grab_valid_adc_button.last_adc_value*3.3))

def load_config_prefix(config):
    return ParkDetector(config)