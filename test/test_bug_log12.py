# Unit test for BUG-LOG-12: Unconditional Z-move and resetting state to PRINTING
# in finally: block of cmd_DEFECT_DETECTION_DETECT_BED after print cancel or shutdown
import unittest
from unittest.mock import MagicMock
import os
import sys

# Ensure klippy is on path
KLIPPY_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'klippy'))
if KLIPPY_PATH not in sys.path:
    sys.path.insert(0, KLIPPY_PATH)

from extras.defect_detection import DefectDetection


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


class TestBugLog12(unittest.TestCase):
    def _create_fixture(self, is_shutdown=False, cancel_print=False):
        printer = MagicMock()
        printer.is_shutdown.return_value = is_shutdown

        reactor = MagicMock()
        reactor.monotonic.return_value = 100.0
        printer.get_reactor.return_value = reactor

        gcode = MagicMock()
        toolhead = MagicMock()
        toolhead.get_position.return_value = [10.0, 10.0, 50.0]
        toolhead.get_status.return_value = {'homed_axes': 'xyz'}

        rail = MagicMock()
        rail.get_range.return_value = (0.0, 200.0)
        kinematics = MagicMock()
        kinematics.rails = [None, None, rail]
        toolhead.get_kinematics.return_value = kinematics

        gcode_move = MagicMock()
        gcode_move.get_status.return_value = {'absolute_coordinates': True}

        machine_state_manager = MagicMock()
        machine_state_manager.get_status.return_value = {'main_state': 'PRINTING'}

        def lookup_obj(name, default=None):
            if name == 'gcode':
                return gcode
            elif name == 'toolhead':
                return toolhead
            elif name == 'gcode_move':
                return gcode_move
            elif name == 'machine_state_manager':
                return machine_state_manager
            elif name == 'mqtt':
                return MagicMock()
            return default

        printer.lookup_object.side_effect = lookup_obj
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

        dd = DefectDetection(config)
        dd.mqtt_client = MagicMock()
        dd.mqtt_jsonrpc = MagicMock()
        if cancel_print:
            dd._request_cancel_print = True

        return dd, toolhead, gcode, kinematics, machine_state_manager

    def test_normal_completion_restores_state_and_moves_z(self):
        dd, toolhead, gcode, kinematics, msm = self._create_fixture(is_shutdown=False, cancel_print=False)
        dd.request_detect_clean_bed_sync = MagicMock(return_value=False)

        gcmd = MockGCodeCommand()
        dd.cmd_DEFECT_DETECTION_DETECT_BED(gcmd)

        self.assertTrue(toolhead.manual_move.called)
        self.assertTrue(kinematics.note_z_not_homed.called)
        state_idle_calls = [
            c for c in gcode.run_script_from_command.call_args_list
            if "SET_MAIN_STATE MAIN_STATE=PRINTING ACTION=IDLE" in str(c)
        ]
        self.assertEqual(len(state_idle_calls), 1)

    def test_cancel_print_skips_manual_move_and_printing_state_restore(self):
        dd, toolhead, gcode, kinematics, msm = self._create_fixture(is_shutdown=False, cancel_print=True)
        dd.request_detect_clean_bed_sync = MagicMock(return_value=False)

        toolhead.manual_move.reset_mock()
        gcode.run_script_from_command.reset_mock()

        gcmd = MockGCodeCommand()
        dd.cmd_DEFECT_DETECTION_DETECT_BED(gcmd)

        self.assertFalse(toolhead.manual_move.called)
        state_idle_calls = [
            c for c in gcode.run_script_from_command.call_args_list
            if "SET_MAIN_STATE MAIN_STATE=PRINTING ACTION=IDLE" in str(c)
        ]
        self.assertEqual(len(state_idle_calls), 0)
        self.assertTrue(kinematics.note_z_not_homed.called)

    def test_shutdown_skips_manual_move_and_kinematics(self):
        dd, toolhead, gcode, kinematics, msm = self._create_fixture(is_shutdown=True, cancel_print=False)
        toolhead.manual_move.reset_mock()
        kinematics.note_z_not_homed.reset_mock()
        gcode.run_script_from_command.reset_mock()

        gcmd = MockGCodeCommand()
        dd.cmd_DEFECT_DETECTION_DETECT_BED(gcmd)

        self.assertFalse(toolhead.manual_move.called)
        self.assertFalse(kinematics.note_z_not_homed.called)
        state_idle_calls = [
            c for c in gcode.run_script_from_command.call_args_list
            if "SET_MAIN_STATE" in str(c)
        ]
        self.assertEqual(len(state_idle_calls), 0)


if __name__ == '__main__':
    unittest.main()
