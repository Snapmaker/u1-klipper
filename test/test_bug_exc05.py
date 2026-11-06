# Unit test for BUG-EXC-05: Unhandled exceptions and swallowed gcmd.error
import unittest
from unittest.mock import MagicMock

class MockGCodeCommand:
    def __init__(self, params=None):
        self.params = params or {}
        self.responses = []

    def get(self, name, default=None):
        return self.params.get(name, default)

    def respond_info(self, msg):
        self.responses.append(msg)

    def error(self, msg):
        return ValueError(msg)

class TestBugExc05(unittest.TestCase):
    def test_swallowed_vs_raised_error(self):
        gcmd = MockGCodeCommand({'NAME': 'test_run'})

        # Buggy behavior: error is created but never raised
        def buggy_handler():
            try:
                raise OSError("Permission denied: /userdata/gcodes")
            except Exception as e:
                gcmd.error(e) # Swallowed, no raise!

        # Does not raise - silently swallows failure
        try:
            buggy_handler()
            swallowed = True
        except ValueError:
            swallowed = False
        self.assertTrue(swallowed, "Buggy code silently swallows the error")

        # Patched behavior: error is properly raised with string conversion
        def patched_handler():
            try:
                raise OSError("Permission denied: /userdata/gcodes")
            except Exception as e:
                raise gcmd.error(str(e))

        with self.assertRaises(ValueError) as ctx:
            patched_handler()
        self.assertIn("Permission denied", str(ctx.exception))

    def test_frequency_command_helper_raises_on_write_failure(self):
        import sys
        import os
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../klippy')))
        from extras.inductance_coil import FrequencyCommandHelper

        config = MagicMock()
        printer = MagicMock()
        config.get_printer.return_value = printer
        config.get_name.return_value = "probe_inductance_coil myprobe"

        probe = MagicMock()
        helper = FrequencyCommandHelper(config, probe)

        # Simulate background client failing on write_to_file
        bg_client = MagicMock()
        bg_client.write_to_file.side_effect = IOError("Disk full")
        helper.bg_client = bg_client

        printer.lookup_object.return_value = None

        gcmd = MockGCodeCommand({'NAME': 'run1'})

        with self.assertRaises(ValueError) as ctx:
            helper.cmd_FREQUENCY_MEASURE(gcmd)

        self.assertIn("Disk full", str(ctx.exception))

if __name__ == '__main__':
    unittest.main()

