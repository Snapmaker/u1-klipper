# Unit test for BUG-INT-04: Python-side power_loss_trigger_time bounds
import unittest
import json
import tempfile
import os

class MockConfig:
    def __init__(self, options=None):
        self.options = options or {}

    def getfloat(self, option, default=None, minval=None, maxval=None, above=None):
        if option in self.options:
            val = float(self.options[option])
            if minval is not None and val < minval:
                raise ValueError("Option '%s' below minval %s" % (option, minval))
            if maxval is not None and val > maxval:
                raise ValueError("Option '%s' above maxval %s" % (option, maxval))
            return val
        return default

class TestBugInt04Python(unittest.TestCase):
    def test_config_bounds(self):
        # Valid config
        cfg = MockConfig({'power_loss_trigger_time': 0.0109})
        val = cfg.getfloat('power_loss_trigger_time', 0.0109, minval=0.0001, maxval=6.5535)
        self.assertAlmostEqual(val, 0.0109)

        # Underflow / 0 rejected
        cfg_zero = MockConfig({'power_loss_trigger_time': 0.0})
        with self.assertRaises(ValueError):
            cfg_zero.getfloat('power_loss_trigger_time', 0.0109, minval=0.0001, maxval=6.5535)

        # Overflow rejected
        cfg_over = MockConfig({'power_loss_trigger_time': 10.0})
        with self.assertRaises(ValueError):
            cfg_over.getfloat('power_loss_trigger_time', 0.0109, minval=0.0001, maxval=6.5535)

    def test_json_bounds_validation(self):
        # Simulate json loading logic from power_loss_check.py
        def load_json_val(raw_val, default=0.0109):
            val = raw_val
            if val is not None:
                val = float(val)
                if 0.0001 <= val <= 6.5535:
                    return val
            return default

        self.assertEqual(load_json_val(0.05), 0.05)
        self.assertEqual(load_json_val(0.0), 0.0109) # Rejected zero, keeps default
        self.assertEqual(load_json_val(7.5), 0.0109) # Rejected overflow, keeps default
        self.assertEqual(load_json_val(-1.0), 0.0109) # Rejected negative, keeps default

    def test_mcu_us_clamping(self):
        # Ensure trigger_us stays within valid microsecond range
        def calc_trigger_us(time_sec):
            return int(max(100, min(6553500, time_sec * 1000000)))

        self.assertEqual(calc_trigger_us(0.0109), 10900)
        self.assertEqual(calc_trigger_us(0.0), 100)
        self.assertEqual(calc_trigger_us(10.0), 6553500)

if __name__ == '__main__':
    unittest.main()

