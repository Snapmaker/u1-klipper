# Unit test for BUG-LOG-10: EXCLUDE_OBJECT crash, dead code, and hardcoded Z stepper in virtual_sdcard.py
import unittest
from unittest.mock import MagicMock
import os
import sys

KLIPPY_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'klippy'))
if KLIPPY_PATH not in sys.path:
    sys.path.insert(0, KLIPPY_PATH)

from extras.virtual_sdcard import VirtualSD, GCodeStateTracker


class TestBugLog10(unittest.TestCase):
    def _create_tracker(self):
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
        return GCodeStateTracker(printer, pl_save_data)

    def test_exclude_object_current_without_name(self):
        tracker = self._create_tracker()
        tracker.current_object = "OBJECT_A"
        # Should not raise exception or crash due to missing NAME parameter
        tracker.update_position("EXCLUDE_OBJECT CURRENT=1\n")
        self.assertIn("OBJECT_A", tracker.excluded_objects)

    def test_exclude_object_reset_without_name(self):
        tracker = self._create_tracker()
        tracker.excluded_objects = ["OBJ1", "OBJ2"]
        # Should not raise exception or crash due to missing NAME parameter
        tracker.update_position("EXCLUDE_OBJECT RESET=1\n")
        self.assertEqual(tracker.excluded_objects, [])

    def test_exclude_object_with_name(self):
        tracker = self._create_tracker()
        tracker.update_position("EXCLUDE_OBJECT NAME=cube\n")
        self.assertIn("CUBE", tracker.excluded_objects)

    def test_flush_pl_z_homing_stepper_z_info_short_steppers(self):
        printer = MagicMock()
        toolhead = MagicMock()
        toolhead.get_position.return_value = [0.0, 0.0, 25.0]

        kin = MagicMock()
        # Simulate kinematics with only 1 or 2 steppers
        s_x = MagicMock()
        s_x.get_mcu_position.return_value = 100
        kin.get_steppers.return_value = [s_x]

        rail_z = MagicMock()
        s_z = MagicMock()
        s_z.get_mcu_position.return_value = 5000
        s_z.get_dir_inverted.return_value = (1,)
        s_z.get_step_dist.return_value = 0.0025
        rail_z.get_steppers.return_value = [s_z]
        kin.rails = [MagicMock(), MagicMock(), rail_z]
        toolhead.get_kinematics.return_value = kin

        homing_xyz = MagicMock()
        printer.lookup_object.side_effect = lambda name, default=None: {
            'toolhead': toolhead,
            'homing_xyz_override': homing_xyz,
            'gcode': MagicMock(),
        }.get(name, default)

        config = MagicMock()
        config.get_printer.return_value = printer
        config.get.return_value = "/tmp"
        config.getboolean.return_value = True
        config.getint.return_value = 10

        sd = VirtualSD(config)
        # Previously raised IndexError: list index out of range when len(steppers) < 3
        res = sd.flush_pl_z_homing_stepper_z_info(z_offset=0)
        self.assertEqual(res['stepper_z_pos'], 5000)
        self.assertEqual(res['z_pos'], 25.0)


if __name__ == '__main__':
    unittest.main()
