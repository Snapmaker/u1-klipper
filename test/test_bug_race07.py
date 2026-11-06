import unittest
import threading
import time

class MockPrinter:
    def __init__(self):
        self.objects = {}
    def lookup_object(self, name, default=None):
        return self.objects.get(name, default)
    def command_error(self, msg):
        return ValueError(msg)

class MockReactor:
    def __init__(self):
        self.callbacks = []
        self.lock = threading.Lock()

    def register_async_callback(self, cb):
        with self.lock:
            self.callbacks.append(cb)

    def run_all(self):
        with self.lock:
            cbs = list(self.callbacks)
            self.callbacks.clear()
        for cb in cbs:
            cb(time.time())

class MockHeater:
    def __init__(self):
        self.lock = threading.Lock()
        self.printer = MockPrinter()
        self.idle_hold_max_power = None
        self.active_hold_max_power = None

class MockControlPID:
    def __init__(self, heater):
        self.heater = heater
        self.heater_max_power = 1.0
        self.pid_profiles = {
            'default': {'Kp': 10.0, 'Ki': 1.0, 'Kd': 5.0,
                        'full_power_threshold': 5.0, 'zero_power_threshold': 5.0,
                        'settle_delta': 1.0, 'settle_slope': 0.1},
            'alt': {'Kp': 20.0, 'Ki': 2.0, 'Kd': 10.0,
                    'full_power_threshold': 10.0, 'zero_power_threshold': 10.0,
                    'settle_delta': 2.0, 'settle_slope': 0.2}
        }
        self.current_profile = 'default'
        self.Kp = 10.0
        self.Ki = 1.0
        self.Kd = 5.0
        self.temp_integ_max = 1.0

    def set_pid_profile(self, profile):
        if profile not in self.pid_profiles:
            raise self.heater.printer.command_error(f"Unknown profile: {profile}")
        with self.heater.lock:
            self.current_profile = profile
            p = self.pid_profiles[profile]
            self.Kp = p['Kp']
            self.Ki = p['Ki']
            self.Kd = p['Kd']
            if self.Ki:
                self.temp_integ_max = self.heater_max_power / self.Ki

    def read_coefficients_under_lock(self):
        with self.heater.lock:
            return (self.Kp, self.Ki, self.Kd, self.temp_integ_max)

class MockFM175XXReader:
    def __init__(self, reactor):
        self.__reactor = reactor
        self.__lock = threading.Lock()
        self.__card_info_deal_cb = None
        self.__card_info_read_flag = 0
        self.__card_info_clear_flag = 0

    def register_cb_2_card_info_deal(self, cb):
        with self.__lock:
            self.__card_info_deal_cb = cb

    def _dispatch_card_info_cb(self, ch, op, result, card_type, card_data):
        with self.__lock:
            cb = self.__card_info_deal_cb
        if cb is not None:
            self.__reactor.register_async_callback(
                lambda et, c=ch, o=op, r=result, t=card_type, d=card_data:
                cb(c, o, r, t, d))

    def request_read_card_info(self, channel):
        if channel < 0 or channel >= 4:
            return
        with self.__lock:
            self.__card_info_clear_flag &= ~(1 << channel) & 0xFFFFFFFF
            self.__card_info_read_flag |= (1 << channel)

    def request_clear_card_info(self, channel):
        if channel < 0 or channel >= 4:
            return
        with self.__lock:
            self.__card_info_read_flag &= ~(1 << channel) & 0xFFFFFFFF
            self.__card_info_clear_flag |= (1 << channel)

    def get_flags(self):
        with self.__lock:
            return self.__card_info_read_flag, self.__card_info_clear_flag

class TestBugRace07(unittest.TestCase):
    def test_pid_profile_thread_safe_update(self):
        heater = MockHeater()
        ctrl = MockControlPID(heater)

        running = True
        inconsistencies = []

        def reader_loop():
            while running:
                kp, ki, kd, integ_max = ctrl.read_coefficients_under_lock()
                # Kp must always match Ki and Kd in our known profiles
                if kp == 10.0 and (ki != 1.0 or kd != 5.0 or integ_max != 1.0):
                    inconsistencies.append((kp, ki, kd, integ_max))
                elif kp == 20.0 and (ki != 2.0 or kd != 10.0 or integ_max != 0.5):
                    inconsistencies.append((kp, ki, kd, integ_max))

        thread = threading.Thread(target=reader_loop)
        thread.start()

        for _ in range(500):
            ctrl.set_pid_profile('alt')
            ctrl.set_pid_profile('default')

        running = False
        thread.join()

        self.assertEqual(len(inconsistencies), 0, f"Found inconsistent PID state: {inconsistencies}")

    def test_fm175xx_async_callback_dispatch(self):
        reactor = MockReactor()
        reader = MockFM175XXReader(reactor)

        dispatched_events = []
        def on_card(ch, op, res, ctype, cdata):
            dispatched_events.append((ch, op, res))

        reader.register_cb_2_card_info_deal(on_card)

        # Dispatch from simulated background thread
        reader._dispatch_card_info_cb(1, 0, 0, 0x08, None)

        # Before reactor loop runs, callback has NOT executed synchronously on thread
        self.assertEqual(len(dispatched_events), 0)
        self.assertEqual(len(reactor.callbacks), 1)

        # Run reactor loop
        reactor.run_all()
        self.assertEqual(len(dispatched_events), 1)
        self.assertEqual(dispatched_events[0], (1, 0, 0))

    def test_fm175xx_concurrent_flag_modifications(self):
        reactor = MockReactor()
        reader = MockFM175XXReader(reactor)

        def worker():
            for _ in range(200):
                reader.request_read_card_info(0)
                reader.request_clear_card_info(0)
                reader.request_read_card_info(1)
                reader.request_clear_card_info(1)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        r_flag, c_flag = reader.get_flags()
        self.assertIsInstance(r_flag, int)
        self.assertIsInstance(c_flag, int)

if __name__ == '__main__':
    unittest.main()

