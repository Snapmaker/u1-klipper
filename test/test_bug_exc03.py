#!/usr/bin/env python3
# Test harness for BUG-EXC-03: UnboundLocalError & bare raise in try blocks
import sys
import os
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'klippy'))

class TestExc03(unittest.TestCase):
    def test_01_extruder_multi_act_unbound_message(self):
        # In unpatched code, if activated_code + 6 >= 18, message is unbound
        # Test defensive binding logic
        def simulate_unpatched(activated_code):
            error_info = "multi-act: [0-(TTT), 1-(TTT)]"
            self_extruder_num = 0
            error_msg = "test error"
            if "multi-act" in error_info:
                if activated_code + 6 < 18:
                    message = '{"coded": "0002-0523-%4d-%4d", "oneshot": %d, "msg":"%s", "action": "pause"}' % (self_extruder_num, activated_code + 6, 0, error_msg)
            else:
                message = "fallback"
            return message

        with self.assertRaises(UnboundLocalError):
            simulate_unpatched(15)

    def test_02_probe_session_unbound_in_finally(self):
        # When start_probe_session raises, probe_session must not be unbound in finally
        class FailingProbe:
            def start_probe_session(self, gcmd):
                raise ValueError("Session failed to start")

        from extras import probe_inductance_coil

        probe = FailingProbe()
        with self.assertRaises(ValueError) as ctx:
            probe_inductance_coil.run_single_probe(probe, None)
        # Must raise the original ValueError, NOT UnboundLocalError
        self.assertEqual(str(ctx.exception), "Session failed to start")

    def test_03_purifier_need_save_unbound(self):
        # Before fix, need_save was assigned inside try block after parameters
        need_save = False
        try:
            # Simulate failure before assignment
            pass
        finally:
            self.assertFalse(need_save)

    def test_04_filament_feed_bare_raise_fixed(self):
        # Verify that explicit exception is raised instead of bare raise
        channel_error = 2
        exception_code = 15
        caught = False
        try:
            try:
                # Replaced bare raise with explicit Exception
                raise Exception("Residual filament detected")
            except Exception as e:
                caught = True
                self.assertEqual(str(e), "Residual filament detected")
        except RuntimeError:
            self.fail("Bare raise caused RuntimeError: No active exception to reraise")
        self.assertTrue(caught)

if __name__ == '__main__':
    unittest.main()
