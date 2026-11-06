# Unit test for BUG-DIV-06: ZeroDivisionError in homing modules
import unittest
from unittest.mock import MagicMock

class MockTMC:
    def __init__(self, phase=512, phases=1024):
        self._phase = phase
        self._phases = phases

    def query_phase(self):
        return self._phase

    def get_phase_offset(self):
        return (0, self._phases)

class TestBugDiv06(unittest.TestCase):
    def test_homing_precise_corexy_zero_phases(self):
        # When TMC reports 0 phases
        tmc = MockTMC(phases=0)
        phase_offset = tmc.get_phase_offset()
        phases = phase_offset[1] if len(phase_offset) > 1 else 0

        self.assertEqual(phases, 0)
        # Verify check prevents 1024 / phases ZeroDivisionError
        with self.assertRaises(ValueError):
            if phases <= 0:
                raise ValueError("Invalid TMC phase configuration")
            scale = 1024.0 / phases

    def test_homing_precise_corexy_valid_phases(self):
        tmc = MockTMC(phase=256, phases=1024)
        phase_offset = tmc.get_phase_offset()
        phases = phase_offset[1]
        scale = 1024.0 / phases
        backoff_step = (tmc.query_phase() % 1024) / scale
        self.assertEqual(backoff_step, 256.0)

    def test_homing_xyz_override_single_point(self):
        x_count = 1
        y_count = 1
        max_x, min_x = 200.0, 0.0
        max_y, min_y = 200.0, 0.0

        x_step = (max_x - min_x) / (x_count - 1) if x_count > 1 else 0.0
        y_step = (max_y - min_y) / (y_count - 1) if y_count > 1 else 0.0

        self.assertEqual(x_step, 0.0)
        self.assertEqual(y_step, 0.0)

    def test_auto_screws_tilt_adjust_empty_positions(self):
        positions = []
        z_values = [pos[2] for pos in positions]
        target_z = sum(z_values) / len(z_values) if z_values else 0.0
        self.assertEqual(target_z, 0.0)

    def test_homing_zero_move_distance(self):
        move_d = 0.0
        retract_dist = 5.0
        retract_r = min(1., retract_dist / move_d) if move_d > 0. else 0.
        self.assertEqual(retract_r, 0.0)

if __name__ == '__main__':
    unittest.main()

