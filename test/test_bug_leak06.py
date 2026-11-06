# Unit test for BUG-LEAK-06: Memory Leak & Zombie Process in FrequencyQueryHelper
import unittest
import os
import sys
import tempfile
import time
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../klippy')))
from extras.inductance_coil import FrequencyQueryHelper

class MockToolhead:
    def get_last_move_time(self):
        return 10.0

    def wait_moves(self):
        pass

class MockPrinter:
    def lookup_object(self, name):
        if name == 'toolhead':
            return MockToolhead()
        return None

class TestBugLeak06(unittest.TestCase):
    def test_write_to_file_clears_parent_messages(self):
        printer = MockPrinter()
        helper = FrequencyQueryHelper(printer)
        helper.request_start_time = 0.0
        helper.request_end_time = 20.0

        # Feed sample batches
        helper.handle_batch({'data': [(1.0, 1500000), (2.0, 1500500)]})
        helper.handle_batch({'data': [(3.0, 1501000), (4.0, 1501500)]})

        self.assertEqual(len(helper.msgs), 2)

        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp:
            tmp_path = tmp.name

        try:
            helper.write_to_file(tmp_path)

            # In parent process, msgs must be emptied immediately
            self.assertEqual(len(helper.msgs), 0,
                             "helper.msgs must be cleared in parent process")

            # Allow process to finish writing
            for _ in range(50):
                if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                    break
                time.sleep(0.05)

            with open(tmp_path, 'r') as f:
                content = f.read()

            self.assertIn("time,frequency\n", content)
            self.assertIn("1.0000,1500000\n", content)
            self.assertIn("4.0000,1501500\n", content)

            # Wait for background process to terminate
            for p in helper.active_procs:
                p.join(timeout=1.0)

            # Reaping check
            helper.write_to_file(tmp_path)
            # Old process should be reaped
            self.assertFalse(any(p.is_alive() for p in helper.active_procs[:-1]))
        finally:
            for p in helper.active_procs:
                if p.is_alive():
                    p.terminate()
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

if __name__ == '__main__':
    unittest.main()
