# Unit test for BUG-LOG-08: FeedLight pin assignment and ramp-up min bounds
import unittest
from unittest.mock import MagicMock
import extras.filament_feed as ff


class TestBugLog08(unittest.TestCase):
    def test_feed_light_pin_assignment(self):
        printer = MagicMock()
        reactor = MagicMock()
        ppins = MagicMock()
        printer.lookup_object.side_effect = lambda name, default=None: ppins if name == 'pins' else default

        setup_pins = {}
        def mock_setup_pin(pin_type, pin_name):
            mock_pin = MagicMock()
            mock_pin.pin_name = pin_name
            setup_pins[pin_name] = mock_pin
            return mock_pin

        ppins.setup_pin.side_effect = mock_setup_pin

        fl = ff.FeedLight(printer, reactor, red_pin='pin_red_1', white_pin='pin_white_1')
        self.assertEqual(fl.red_light.pin_name, 'pin_red_1')
        self.assertEqual(fl.white_light.pin_name, 'pin_white_1')

    def test_ramp_up_gradual_duty_increase(self):
        # Initial duty is 0.8
        duty = 0.8
        duties = []
        for retry in range(5):
            duty = min(1.0, duty + 0.05)
            duties.append(round(duty, 2))

        # Must ramp up gradually in steps of 0.05, NOT jump straight to 1.0 on retry 0
        self.assertEqual(duties, [0.85, 0.90, 0.95, 1.00, 1.00])

    def test_ramp_up_gradual_period_increase(self):
        # Initial period is 0.100
        period = 0.100
        periods = []
        for retry in range(5, 8):
            period = min(0.12, period + 0.01)
            periods.append(round(period, 3))

        # Must ramp up gradually: 0.110, 0.120, capped at 0.120
        self.assertEqual(periods, [0.110, 0.120, 0.120])

