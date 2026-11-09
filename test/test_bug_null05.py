# Unit test for BUG-NULL-05: Missing initialization of self.mqtt_jsonrpc
# in defect_detection.py and None dereference in timelapse.py
import unittest
from unittest.mock import MagicMock
import os
import sys

# Ensure klippy is on path
KLIPPY_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'klippy'))
if KLIPPY_PATH not in sys.path:
    sys.path.insert(0, KLIPPY_PATH)

from extras.defect_detection import DefectDetection
from extras.timelapse import TimeLapse


class MockGCodeCommand:
    def __init__(self):
        self.error_raised = False
        self.error_msg = None
        self.respond_msg = []

    def error(self, msg, **kwargs):
        self.error_raised = True
        self.error_msg = msg
        return RuntimeError(msg)

    def respond_info(self, msg):
        self.respond_msg.append(msg)

    def get(self, key, default=None):
        return default

    def get_int(self, key, default=0):
        return default


class TestBugNull05(unittest.TestCase):
    def _create_mock_printer_and_config(self):
        printer = MagicMock()
        reactor = MagicMock()
        reactor.monotonic.return_value = 100.0
        printer.get_reactor.return_value = reactor
        gcode = MagicMock()
        printer.lookup_object.side_effect = lambda name, default=None: gcode if name == 'gcode' else default
        printer.get_snapmaker_config_dir.return_value = "/tmp"
        printer.load_snapmaker_config_file.return_value = {
            'main_enable': True,
            'clean_bed': {'enable': True, 'sensitivity': 'low'},
            'noodle': {'enable': True, 'sensitivity': 'low'},
            'residue': {'enable': True, 'sensitivity': 'low'},
            'nozzle': {'enable': True, 'sensitivity': 'low'},
        }

        config = MagicMock()
        config.get_printer.return_value = printer
        config.getboolean.return_value = False
        config.getfloat.side_effect = lambda name, default, **kw: default
        config.getint.side_effect = lambda name, default, **kw: default
        return printer, config

    def test_defect_detection_mqtt_jsonrpc_initialized_none(self):
        printer, config = self._create_mock_printer_and_config()
        dd = DefectDetection(config)
        self.assertTrue(hasattr(dd, 'mqtt_jsonrpc'))
        self.assertIsNone(dd.mqtt_jsonrpc)

    def test_defect_detection_safe_when_mqtt_jsonrpc_none(self):
        printer, config = self._create_mock_printer_and_config()
        dd = DefectDetection(config)
        dd._handle_ready()
        self.assertIsNone(dd.mqtt_jsonrpc)

        dd.request_detect()
        self.assertFalse(dd._request_detect_noodle_first_sync())
        self.assertFalse(dd.request_detect_clean_bed_sync())
        self.assertFalse(dd.request_detect_nozzle_sync())

        gcmd = MockGCodeCommand()
        dd.cmd_DEFECT_DETECTION_START(gcmd)
        dd.cmd_DEFECT_DETECTION_DETECT(gcmd)
        dd.cmd_DEFECT_DETECT_NOODLE_FIRST(gcmd)
        dd.cmd_DEFECT_DETECTION_DETECT_BED(gcmd)
        dd.cmd_DEFECT_DETECTION_DETECT_NOZZLE(gcmd)

    def test_timelapse_safe_when_mqtt_jsonrpc_none(self):
        printer, config = self._create_mock_printer_and_config()
        tl = TimeLapse(config)
        self.assertTrue(hasattr(tl, 'mqtt_jsonrpc'))
        self.assertIsNone(tl.mqtt_jsonrpc)

        tl._handle_ready()
        self.assertIsNone(tl.mqtt_jsonrpc)

        gcmd = MockGCodeCommand()
        with self.assertRaises(RuntimeError):
            tl.cmd_TIMELAPSE_START(gcmd)

        tl.cmd_TIMELAPSE_STOP(gcmd)
        self.assertFalse(tl.is_active)
        self.assertTrue(any("stop error, mqtt not ready!" in m for m in gcmd.respond_msg))

        tl.cmd_TIMELAPSE_TAKE_FRAME(gcmd)


if __name__ == '__main__':
    unittest.main()

