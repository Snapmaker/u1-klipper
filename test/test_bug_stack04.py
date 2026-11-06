# Unit test for BUG-STACK-04: Infinite loop in cmd_FILAMENT_DT_SELF_TEST
import unittest
from unittest.mock import MagicMock
from extras import filament_detect


class CommandError(Exception):
    pass


class TestBugStack04(unittest.TestCase):
    def setUp(self):
        self.config = MagicMock()
        self.printer = MagicMock()
        self.reactor = MagicMock()
        self.printer.get_reactor.return_value = self.reactor
        self.printer.get_snapmaker_config_dir.return_value = '/tmp'
        self.printer.load_snapmaker_config_file.return_value = {
            'startup_stay': False
        }
        self.printer.is_shutdown.return_value = False

        self.gcode = MagicMock()
        self.printer.lookup_object.side_effect = lambda name, default=None: {
            'gcode': self.gcode
        }.get(name, default)

        self.config.get_printer.return_value = self.printer

        self.detector = filament_detect.FilamentDetector(self.config)
        self.reader = MagicMock()
        self.detector._fm175xx_reader = self.reader

        self.current_time = [0.0]

        def mock_monotonic():
            return self.current_time[0]

        def mock_pause(target):
            self.current_time[0] += 0.3

        self.reactor.monotonic.side_effect = mock_monotonic
        self.reactor.pause.side_effect = mock_pause

    def test_self_test_timeout(self):
        gcmd = MagicMock()
        gcmd.error = CommandError
        gcmd.get_int.side_effect = (
            lambda name, default=None, **kw: 0 if name == 'CHANNEL' else 10
        )
        gcmd.get_float.side_effect = (
            lambda name, default=None, **kw: 0.1 if name == 'TIMEOUT' else default
        )

        self.reader.self_test_result.return_value = (False, 0, 0)
        with self.assertRaises(CommandError) as ctx:
            self.detector.cmd_FILAMENT_DT_SELF_TEST(gcmd)

        self.assertIn("Self test timed out after 0.1s on channel 0", str(ctx.exception))
        self.assertEqual(
            self.detector._state[0], filament_detect.FILAMENT_DT_STATE_IDLE
        )

    def test_self_test_shutdown_abort(self):
        gcmd = MagicMock()
        gcmd.error = CommandError
        gcmd.get_int.side_effect = (
            lambda name, default=None, **kw: 0 if name == 'CHANNEL' else 10
        )
        gcmd.get_float.side_effect = (
            lambda name, default=None, **kw: 5.0 if name == 'TIMEOUT' else default
        )

        self.printer.is_shutdown.return_value = True
        with self.assertRaises(CommandError) as ctx:
            self.detector.cmd_FILAMENT_DT_SELF_TEST(gcmd)

        self.assertIn("Self test aborted due to printer shutdown", str(ctx.exception))
        self.assertEqual(
            self.detector._state[0], filament_detect.FILAMENT_DT_STATE_IDLE
        )

    def test_self_test_success(self):
        gcmd = MagicMock()
        gcmd.error = CommandError
        gcmd.get_int.side_effect = (
            lambda name, default=None, **kw: 0 if name == 'CHANNEL' else 10
        )
        gcmd.get_float.side_effect = (
            lambda name, default=None, **kw: 5.0 if name == 'TIMEOUT' else default
        )

        self.reader.self_test_result.return_value = (True, 10, 10)
        self.detector.cmd_FILAMENT_DT_SELF_TEST(gcmd)
        self.assertEqual(
            self.detector._state[0], filament_detect.FILAMENT_DT_STATE_IDLE
        )

    def test_self_test_reader_none(self):
        self.detector._fm175xx_reader = None
        gcmd = MagicMock()
        gcmd.error = CommandError
        gcmd.get_int.side_effect = (
            lambda name, default=None, **kw: 0 if name == 'CHANNEL' else 10
        )
        with self.assertRaises(CommandError) as ctx:
            self.detector.cmd_FILAMENT_DT_SELF_TEST(gcmd)

        self.assertIn("RFID reader fm175xx_reader is not available", str(ctx.exception))


if __name__ == '__main__':
    unittest.main()

