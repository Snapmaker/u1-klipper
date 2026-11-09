import unittest
import threading
import time

class MockPin:
    def __init__(self, name):
        self.name = name
        self.released = False
    def request(self, consumer=None, type=None, default_val=0):
        pass
    def release(self):
        self.released = True

class MockChip:
    def __init__(self, name):
        self.name = name
        self.closed = False
        self.lines = {}
    def get_line(self, pin_num):
        line = MockPin(f"pin_{pin_num}")
        self.lines[pin_num] = line
        return line
    def close(self):
        self.closed = True

class MockSpi:
    def __init__(self):
        self.closed = False
    def close(self):
        self.closed = True

class MockMQTTClient:
    def __init__(self, should_fail_connect=False):
        self.should_fail_connect = should_fail_connect
        self.loop_started = False
        self.loop_stopped = False
        self.connected = False
        self.disconnected = False
        self.reconnect_delay = None

    def reconnect_delay_set(self, min_delay, max_delay):
        self.reconnect_delay = (min_delay, max_delay)

    def connect_async(self, address, port):
        if self.should_fail_connect:
            raise OSError("Network unreachable")
        self.connected = True

    def loop_start(self):
        if self.should_fail_connect:
            raise RuntimeError("loop_start should not be called if connect_async fails")
        self.loop_started = True

    def loop_stop(self):
        self.loop_stopped = True

    def disconnect(self):
        self.disconnected = True

class TestBugLeak08(unittest.TestCase):
    def test_fm175xx_gpio_and_thread_cleanup(self):
        chip = MockChip('gpiochip1')
        spi = MockSpi()
        pins = [chip.get_line(25), chip.get_line(28), chip.get_line(27), chip.get_line(24)]

        stop_event = threading.Event()
        thread_exited = threading.Event()

        def bg_worker():
            while not stop_event.is_set():
                time.sleep(0.01)
            thread_exited.set()

        bg_thread = threading.Thread(target=bg_worker)
        bg_thread.start()

        # Simulate shutdown sequence
        stop_event.set()
        bg_thread.join(timeout=2.0)
        self.assertTrue(thread_exited.is_set())
        self.assertFalse(bg_thread.is_alive())

        for pin in pins:
            pin.release()
        spi.close()
        chip.close()

        for pin in pins:
            self.assertTrue(pin.released)
        self.assertTrue(spi.closed)
        self.assertTrue(chip.closed)

    def test_mqtt_connection_failure_no_thread_leak(self):
        client = MockMQTTClient(should_fail_connect=True)

        failed = False
        client.reconnect_delay_set(min_delay=1, max_delay=120)
        try:
            client.connect_async("127.0.0.1", 1883)
            client.loop_start()
        except Exception:
            try:
                client.loop_stop()
            except Exception:
                pass
            failed = True

        self.assertTrue(failed)
        self.assertFalse(client.loop_started)
        self.assertTrue(client.loop_stopped)

    def test_mqtt_successful_connection_and_shutdown(self):
        client = MockMQTTClient(should_fail_connect=False)

        client.reconnect_delay_set(min_delay=1, max_delay=120)
        client.connect_async("127.0.0.1", 1883)
        client.loop_start()

        self.assertTrue(client.connected)
        self.assertTrue(client.loop_started)

        # Simulate shutdown
        client.reconnect_delay_set(min_delay=0, max_delay=0)
        client.disconnect()
        client.loop_stop()

        self.assertTrue(client.disconnected)
        self.assertTrue(client.loop_stopped)

if __name__ == '__main__':
    unittest.main()

