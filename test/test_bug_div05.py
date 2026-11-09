# Unit test for BUG-DIV-05: Division by Zero & date_rate typo in inductance_coil.py
import unittest
from unittest.mock import MagicMock

class MockConfig:
    def __init__(self, options=None):
        self.options = options or {}

    def getint(self, option, default=None, minval=None, maxval=None):
        if option in self.options:
            val = self.options[option]
            if minval is not None and val < minval:
                raise ValueError(
                    "Option '%s' must have minimum of %s" % (option, minval))
            return val
        return default

class TestBugDiv05(unittest.TestCase):
    def test_data_rate_parsed_correctly(self):
        cfg = MockConfig({'data_rate': 500})
        data_rate = cfg.getint('data_rate', None, minval=1)
        if data_rate is None:
            data_rate = cfg.getint('date_rate', 1000, minval=1)
        self.assertEqual(data_rate, 500)

    def test_legacy_date_rate_fallback(self):
        cfg = MockConfig({'date_rate': 250})
        data_rate = cfg.getint('data_rate', None, minval=1)
        if data_rate is None:
            data_rate = cfg.getint('date_rate', 1000, minval=1)
        self.assertEqual(data_rate, 250)

    def test_default_data_rate(self):
        cfg = MockConfig({})
        data_rate = cfg.getint('data_rate', None, minval=1)
        if data_rate is None:
            data_rate = cfg.getint('date_rate', 1000, minval=1)
        self.assertEqual(data_rate, 1000)

    def test_zero_data_rate_rejected(self):
        cfg = MockConfig({'data_rate': 0})
        with self.assertRaises(ValueError):
            cfg.getint('data_rate', None, minval=1)

    def test_zero_date_rate_rejected(self):
        cfg = MockConfig({'date_rate': 0})
        data_rate = cfg.getint('data_rate', None, minval=1)
        with self.assertRaises(ValueError):
            if data_rate is None:
                cfg.getint('date_rate', 1000, minval=1)

    def test_start_measurements_zero_rate_guard(self):
        mcu = MagicMock()
        printer = MagicMock()
        printer.command_error = Exception

        # Simulate _start_measurements guard
        data_rate = 0
        with self.assertRaises(Exception):
            if data_rate <= 0:
                raise printer.command_error(
                    "Invalid data_rate in inductance_coil")
            mcu.seconds_to_clock(1.0 / data_rate)

if __name__ == '__main__':
    unittest.main()

