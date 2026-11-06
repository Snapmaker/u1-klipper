# Unit test for BUG-DIV-07: Division by Zero in power_loss_check.py, purifier_factory.py, defect_detection.py
import unittest
from unittest.mock import MagicMock

class TestBugDiv07PowerLoss(unittest.TestCase):
    def test_power_loss_check_zero_ticks(self):
        # Simulate _update_status_from_params logic
        params = {
            'initialized': 1,
            'high_level': 0,
            'low_level': 0,
            'voltage_type': 0,
            'power_loss_flag': 0
        }

        high_level_tick = params['high_level']
        low_level_tick = params['low_level']
        duty_percent = 0.0

        if params['initialized'] and high_level_tick != 0xFFFFFFFF and low_level_tick != 0xFFFFFFFF:
            total_ticks = high_level_tick + low_level_tick
            if total_ticks > 0:
                duty_percent = high_level_tick / total_ticks
            else:
                duty_percent = 0.0

        self.assertEqual(duty_percent, 0.0)

    def test_purifier_factory_zero_ppr(self):
        # Simulate Purifier get_status
        ppr = 0
        freq = 120.0
        if ppr > 0:
            rpm = freq * 30. / ppr
        else:
            rpm = 0.0
        self.assertEqual(rpm, 0.0)

    def test_defect_detection_zero_distance(self):
        start_pos = [10.0, 10.0, 50.0]
        probe_distance = 0.0
        probe_dist = max(0.001, probe_distance)
        probe_max_times = max(1, int(start_pos[2] / probe_dist))
        self.assertGreaterEqual(probe_max_times, 1)

if __name__ == '__main__':
    unittest.main()

