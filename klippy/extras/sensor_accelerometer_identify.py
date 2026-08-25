import logging
from . import bus


class SensorAccelerometerIdentify:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.name = config.get_name().split()[-1]
        self.spi = bus.MCU_SPI_from_config(config, 3, default_speed=5000000)

        self.sensor_list = config.getlist('sensor_list', default=[])
        self.sensor_selected_name = config.get('sensor_selected', None)

        self.sensor_identified = None
        self.sensor_selected = None

        self.printer.register_event_handler("klippy:connect", self._connect)

    def _connect(self):
        if self.sensor_selected_name is not None:
            self.sensor_selected = self.printer.lookup_object(self.sensor_selected_name)
            if self.sensor_selected.check_devid():
                logging.info(f"[{self.name}] Sensor {self.sensor_selected.name} selected and identified")
                self.sensor_identified = self.sensor_selected
            else:
                logging.error(f"[{self.name}] Sensor {self.sensor_selected.name} selected but not identified")
        else:
            for sensor in self.sensor_list:
                sensor_obj = self.printer.lookup_object(sensor, None)
                if sensor_obj is not None:
                    if sensor_obj.check_devid():
                        self.sensor_identified = sensor_obj
                        break

            if self.sensor_identified is None:
                logging.error(f"[{self.name}] No sensor identified")
            else:
                logging.info(f"[{self.name}] Sensor {self.sensor_identified.name} identified")

def load_config_prefix(config):
    return SensorAccelerometerIdentify(config)

