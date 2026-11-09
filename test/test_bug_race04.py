# Unit test for BUG-RACE-04: TOCTOU race and thread safety in exception_manager
import unittest
import threading
from unittest.mock import MagicMock, patch
import exception_manager


class TestBugRace04(unittest.TestCase):
    def setUp(self):
        self.printer = MagicMock()
        self.reactor = MagicMock()
        self.reactor.monotonic.return_value = 0.0
        self.printer.get_reactor.return_value = self.reactor
        self.printer.get_snapmaker_config_dir.return_value = '/tmp'
        self.gcode = MagicMock()
        self.webhooks = MagicMock()
        self.printer.lookup_object.side_effect = lambda name, default=None: {
            'gcode': self.gcode,
            'webhooks': self.webhooks
        }.get(name, default)

    @patch('exception_manager.queuefile.async_write_file')
    def test_in_memory_cache_consistency(self, mock_write):
        mgr = exception_manager.ExceptionManager(self.printer)
        mgr._persistent_cache = {}

        # Save exceptions rapidly
        res1 = mgr.save_persistent_exception('0522-0000-0001', 3, 'Error 1')
        res2 = mgr.save_persistent_exception('0522-0000-0002', 3, 'Error 2')

        self.assertTrue(res1)
        self.assertTrue(res2)
        self.assertIn('0522-0000-0001', mgr._persistent_cache)
        self.assertIn('0522-0000-0002', mgr._persistent_cache)

        # Clear first exception
        res3 = mgr.clear_persistent_exception('0522-0000-0001')
        self.assertTrue(res3)
        self.assertNotIn('0522-0000-0001', mgr._persistent_cache)
        self.assertIn('0522-0000-0002', mgr._persistent_cache)

        # Duplicate clear returns False cleanly
        res4 = mgr.clear_persistent_exception('0522-0000-0001')
        self.assertFalse(res4)

    def test_handle_async_exception_empty_queue(self):
        mgr = exception_manager.ExceptionManager(self.printer)
        mgr.async_exceptions.clear()

        # Must not raise IndexError when queue is empty
        res = mgr._handle_async_exception(0.0)
        self.assertEqual(res, self.reactor.NEVER)

    def test_concurrent_raise_exception_async(self):
        mgr = exception_manager.ExceptionManager(self.printer)
        mgr.async_exceptions.clear()

        threads = []

        def worker(tid):
            for i in range(25):
                mgr.raise_exception_async(522, tid, i, f"Error {tid}-{i}")

        for t in range(4):
            th = threading.Thread(target=worker, args=(t,))
            threads.append(th)
            th.start()

        for th in threads:
            th.join()

        self.assertEqual(len(mgr.async_exceptions), 100)

    @patch('exception_manager.queuefile.async_delete_file')
    def test_remove_persistent_exceptions_clears_cache(self, mock_delete):
        mgr = exception_manager.ExceptionManager(self.printer)
        mgr._persistent_cache = {'0522-0000-0001': {'level': 3, 'message': 'err'}}

        mgr.remove_persistent_exceptions()
        self.assertEqual(len(mgr._persistent_cache), 0)


if __name__ == '__main__':
    unittest.main()
