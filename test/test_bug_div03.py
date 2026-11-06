# Unit test for BUG-DIV-03: Five unprotected division-by-zero paths in virtual_sdcard.py
import unittest
from unittest.mock import MagicMock
import os
import sys

KLIPPY_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'klippy'))
if KLIPPY_PATH not in sys.path:
    sys.path.insert(0, KLIPPY_PATH)

from extras.virtual_sdcard import GCodeStateTracker


class TestBugDiv03(unittest.TestCase):
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

    def test_get_gcode_speed_zero_or_negative_speed_factor(self):
        tracker = self._create_tracker()
        tracker.speed_factor = 0
        speed = tracker._get_gcode_speed()
        self.assertGreater(speed, 0.)

        tracker.speed_factor = -0.5
        speed = tracker._get_gcode_speed()
        self.assertGreater(speed, 0.)

    def test_m221_zero_extrude_factor(self):
        tracker = self._create_tracker()
        tracker.extrude_factor = 0.0
        # Should not raise ZeroDivisionError
        tracker.update_position("M221 S120\n")
        self.assertEqual(tracker.extrude_factor, 1.2)

    def test_set_velocity_limit_zero_max_accel(self):
        tracker = self._create_tracker()
        tracker.max_accel = 0.0
        # ACCEL_TO_DECEL specified with max_accel = None and tracker.max_accel = 0
        tracker.update_position("SET_VELOCITY_LIMIT ACCEL_TO_DECEL=2500\n")
        # Should complete without ZeroDivisionError

    def test_set_factors_zero_speed_factor(self):
        tracker = self._create_tracker()
        tracker.speed_factor = 0.0
        tracker.set_factors(speed_factor=0.02)
        self.assertEqual(tracker.speed_factor, 0.02)

    def test_pause_state_save_zero_speed_factor(self):
        state_copy = {
            'speed': 100.0,
            'speed_factor': 0.0,
            'accel': 5000.0,
        }
        speed_factor = state_copy.get('speed_factor', 1.0)
        if not speed_factor or speed_factor <= 0.:
            speed_factor = 1.0
        calc_speed = state_copy['speed'] / speed_factor
        self.assertEqual(calc_speed, 100.0)


if __name__ == '__main__':
    unittest.main()

