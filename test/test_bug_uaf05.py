import unittest
import threading
import time

class DummyDevice:
    def __init__(self):
        self.is_closed = False
        self.access_after_close = False

    def access(self):
        if self.is_closed:
            self.access_after_close = True
            raise OSError(9, "Bad file descriptor")

    def close(self):
        self.is_closed = True

class TestBugUaf05(unittest.TestCase):
    def test_shutdown_avoids_use_after_close(self):
        device = DummyDevice()
        stop_event = threading.Event()
        bg_finished = threading.Event()
        worker_error = []

        def bg_worker():
            try:
                while not stop_event.is_set():
                    device.access()
                    time.sleep(0.01)
            except Exception as e:
                worker_error.append(e)
            finally:
                bg_finished.set()

        thread = threading.Thread(target=bg_worker)
        thread.start()

        # Perform proper shutdown: stop signal -> join thread -> deinit device
        stop_event.set()
        thread.join(timeout=2.0)
        device.close()

        self.assertTrue(bg_finished.is_set())
        self.assertFalse(thread.is_alive())
        self.assertTrue(device.is_closed)
        self.assertFalse(device.access_after_close)
        self.assertEqual(len(worker_error), 0)

    def test_uncoordinated_shutdown_triggers_bad_fd(self):
        # Demonstrates the pre-fix bug behavior where closing before join races
        device = DummyDevice()
        stop_event = threading.Event()
        worker_error = []

        def slow_worker():
            try:
                time.sleep(0.02)
                device.access()
            except Exception as e:
                worker_error.append(e)

        thread = threading.Thread(target=slow_worker)
        thread.start()

        # Buggy shutdown: close device immediately without waiting for thread
        stop_event.set()
        device.close()
        thread.join(timeout=2.0)

        self.assertTrue(device.access_after_close)
        self.assertEqual(len(worker_error), 1)
        self.assertIsInstance(worker_error[0], OSError)

if __name__ == '__main__':
    unittest.main()

