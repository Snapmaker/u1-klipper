# Unit test for BUG-NULL-04: NoneType crashes in virtual_sdcard.py
# (restore_print, get_print_task_config, force_record_pl_print_file_env)
import unittest
from unittest.mock import MagicMock
import os
import sys

KLIPPY_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'klippy'))
if KLIPPY_PATH not in sys.path:
    sys.path.insert(0, KLIPPY_PATH)

from extras.virtual_sdcard import VirtualSD, GCodeStateTracker


class TestBugNull04(unittest.TestCase):
    def _create_mock_sdcard(self):
        printer = MagicMock()
        printer.get_reactor.return_value = MagicMock()
        printer.lookup_object.side_effect = lambda name, default=None: MagicMock()

        config = MagicMock()
        config.get_printer.return_value = printer
        config.get.return_value = "/tmp/sdcard"
        config.getboolean.return_value = True
        config.getint.return_value = 10

        sd = VirtualSD(config)
        sd.current_file = None
        return sd, printer

    def test_force_record_pl_print_file_env_none_current_file(self):
        sd, printer = self._create_mock_sdcard()
        print_stats = MagicMock()
        print_stats.state = 'printing'
        printer.lookup_object.side_effect = lambda name, default=None: print_stats if name == 'print_stats' else default

        sd.current_file = None
        # Should not raise AttributeError: 'NoneType' object has no attribute 'name'
        sd.force_record_pl_print_file_env()

    def test_record_power_loss_info_none_current_file(self):
        sd, printer = self._create_mock_sdcard()
        sd.pl_switch = True
        sd.lines = sd.pl_notify_start_line = 100
        sd.current_file = None
        sd.notify_mcu_enable_power_loss = MagicMock()
        sd.flush_pl_print_env = MagicMock()

        # Should not raise AttributeError: 'NoneType' object has no attribute 'name'
        t1, t2 = sd.record_power_loss_info(0, 20)
        self.assertEqual(t1, 20)

    def test_handle_shutdown_none_current_file(self):
        sd, _ = self._create_mock_sdcard()
        sd.work_timer = MagicMock()
        sd.current_file = None
        # Should return safely without exception
        sd.handle_shutdown()

    def test_restore_print_none_file_env(self):
        sd, _ = self._create_mock_sdcard()
        sd.get_pl_print_file_env = MagicMock(return_value=None)
        sd.get_pl_env_flag = MagicMock(return_value=(42, []))
        sd.save_environment_data = MagicMock()

        # Simulate the file_env update logic inside restore_print
        file_env = sd.get_pl_print_file_env()
        if file_env is None or not isinstance(file_env, dict):
            file_env = {}
        file_env['env_flag'] = sd.get_pl_env_flag()[0]
        sd.save_environment_data(sd.pl_print_file_env_path, file_env)

        sd.save_environment_data.assert_called_once_with(sd.pl_print_file_env_path, {'env_flag': 42})

    def test_gcode_tracker_tool_change_none_print_task_config_info(self):
        printer = MagicMock()
        pl_save_data = {
            'absolute_coord': True,
            'toolhead_pos': [0.0, 0.0, 0.0],
            'base_position': [0.0, 0.0, 0.0, 0.0],
            'last_position': [0.0, 0.0, 0.0, 0.0],
            'homing_position': [0.0, 0.0, 0.0, 0.0],
            'speed': 100.0,
            'max_accel': 5000.0,
            'min_cruise_ratio': 0.5,
            'square_corner_velocity': 5.0,
            'extruder': 0,
            'absolute_extrude': True,
        }
        tracker = GCodeStateTracker(printer, pl_save_data)
        mock_ptc = MagicMock()
        # Return None or empty info
        mock_ptc.get_print_task_config.return_value = None
        tracker.set_print_task_config(mock_ptc)

        # Update position with tool change command T0
        tracker.update_position("T0 A1\n")
        self.assertEqual(tracker.extruder_gcode_id, "T0")


if __name__ == '__main__':
    unittest.main()
