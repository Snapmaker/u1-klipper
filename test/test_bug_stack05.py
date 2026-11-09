# Unit test for BUG-STACK-05: Broken timeout in cmd_WAIT_CHAMBER_TEMP
import unittest
from unittest.mock import MagicMock
from extras import purifier


class TestBugStack05(unittest.TestCase):
    def setUp(self):
        self.config = MagicMock()
        self.printer = MagicMock()
        self.reactor = MagicMock()
        self.printer.get_reactor.return_value = self.reactor
        self.printer.get_snapmaker_config_dir.return_value = '/tmp'
        self.printer.load_snapmaker_config_file.return_value = dict(
            purifier.DEFAULT_PURIFIER_CONFIG
        )
        self.printer.is_shutdown.return_value = False

        self.gcode = MagicMock()
        self.webhooks = MagicMock()
        self.printer.lookup_object.side_effect = lambda name, default=None: {
            'gcode': self.gcode,
            'webhooks': self.webhooks
        }.get(name, default)

        self.config.get_printer.return_value = self.printer
        self.config.get.side_effect = lambda k, default=None: default
        self.config.getfloat.side_effect = (
            lambda k, default=None, **kw: default if default is not None else 1.0
        )
        self.config.getint.side_effect = (
            lambda k, default=None, **kw: default if default is not None else 1
        )
        self.config.getboolean.side_effect = (
            lambda k, default=None: default or False
        )

        self.purifier = purifier.Purifier(self.config)
        self.purifier._power_detected = True
        self.purifier.average_temperature = 25.0
        self.purifier.desired_chamber_temp = 50.0

        self.current_time = [0.0]

        def mock_monotonic():
            return self.current_time[0]

        def mock_pause(target):
            self.current_time[0] += 0.5
            # Simulate periodic status check ticking
            self.purifier.timer_execution_counter += 1

        self.reactor.monotonic.side_effect = mock_monotonic
        self.reactor.pause.side_effect = mock_pause

    def test_wait_chamber_temp_times_out(self):
        gcmd = MagicMock()
        gcmd.get_float.return_value = 5.0  # 5 seconds timeout

        self.purifier.cmd_WAIT_CHAMBER_TEMP(gcmd)

        # Timeout was 5s + 5s buffer = 10s total deadline
        self.assertGreaterEqual(self.current_time[0], 10.0)
        self.assertFalse(self.purifier.preheat_wait_enabled)

    def test_wait_chamber_temp_shutdown_abort(self):
        gcmd = MagicMock()
        gcmd.get_float.return_value = 100.0

        def pause_and_shutdown(target):
            self.current_time[0] += 0.5
            self.printer.is_shutdown.return_value = True

        self.reactor.pause.side_effect = pause_and_shutdown

        self.purifier.cmd_WAIT_CHAMBER_TEMP(gcmd)
        self.assertLess(self.current_time[0], 5.0)
        self.assertFalse(self.purifier.preheat_wait_enabled)

    def test_wait_chamber_temp_preheat_disabled_early(self):
        gcmd = MagicMock()
        gcmd.get_float.return_value = 100.0

        def pause_and_disable(target):
            self.current_time[0] += 0.5
            self.purifier.preheat_wait_enabled = False

        self.reactor.pause.side_effect = pause_and_disable

        self.purifier.cmd_WAIT_CHAMBER_TEMP(gcmd)
        self.assertLess(self.current_time[0], 5.0)
        self.assertFalse(self.purifier.preheat_wait_enabled)


if __name__ == '__main__':
    unittest.main()

