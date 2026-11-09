import unittest

class MockGCodeCommand:
    def __init__(self, params=None):
        self.params = params or {}

    def get_int(self, name, default=0, minval=None, maxval=None):
        val = int(self.params.get(name, default))
        if minval is not None and val < minval:
            raise Exception("Val below min")
        if maxval is not None and val > maxval:
            raise Exception("Val above max")
        return val

    def get_float(self, name, default=0.0):
        return float(self.params.get(name, default))

    def error(self, msg):
        return ValueError(msg)

class MockVref:
    def __init__(self, name):
        self.name = name
        self.history = []

    def _set_pin(self, print_time, val):
        self.history.append((self.name, print_time, val))

class MockExtruder:
    def __init__(self, name, xy_park_position=None):
        self.name = name
        self.vref_sw = MockVref(name)
        self.xy_park_position = xy_park_position or [35.0, 332.2]

class TestBugLog05Extruder(unittest.TestCase):
    def test_late_binding_closure(self):
        extruder_list = [MockExtruder(f"extruder{i}") for i in range(4)]
        active_name = "extruder1"
        callbacks = []

        # Mimic fixed loop in extruder.py line 1787-1793
        for i in range(len(extruder_list)):
            if extruder_list[i].vref_sw is not None:
                if extruder_list[i].name == active_name:
                    callbacks.append(lambda print_time, ext=extruder_list[i]: ext.vref_sw._set_pin(print_time, 1))
                else:
                    callbacks.append(lambda print_time, ext=extruder_list[i]: ext.vref_sw._set_pin(print_time, 0))

        # Execute registered lookahead callbacks
        for cb in callbacks:
            cb(1.5)

        # Check each extruder received its proper state
        self.assertEqual(extruder_list[0].vref_sw.history, [("extruder0", 1.5, 0)])
        self.assertEqual(extruder_list[1].vref_sw.history, [("extruder1", 1.5, 1)])
        self.assertEqual(extruder_list[2].vref_sw.history, [("extruder2", 1.5, 0)])
        self.assertEqual(extruder_list[3].vref_sw.history, [("extruder3", 1.5, 0)])

    def test_verify_park_position_y_diff_check(self):
        MAX_ALLOWED_DIFFERENCE = 3.0
        park_pos = [35.0, 332.2]

        def verify_park_pos(gcmd):
            force_move = not not gcmd.get_int('FORCE_MOVE', 0)
            verify_x = gcmd.get_float('X', park_pos[0])
            verify_y = gcmd.get_float('Y', park_pos[1])
            x_diff = abs(verify_x - park_pos[0])
            y_diff = abs(verify_y - park_pos[1])

            if (x_diff > MAX_ALLOWED_DIFFERENCE or y_diff > MAX_ALLOWED_DIFFERENCE) and not force_move:
                exceeded = []
                if x_diff > MAX_ALLOWED_DIFFERENCE:
                    exceeded.append(f"X: {x_diff:.3f}mm")
                if y_diff > MAX_ALLOWED_DIFFERENCE:
                    exceeded.append(f"Y: {y_diff:.3f}mm")
                msg = f"Verify park position differs too much from current position. Exceeded: {', '.join(exceeded)}."
                raise gcmd.error(msg)

        # Normal verification passes
        gcmd_valid = MockGCodeCommand({'X': '35.5', 'Y': '333.0'})
        verify_park_pos(gcmd_valid)

        # Y exceeds tolerance (e.g. Y=337.0 -> diff 4.8mm)
        gcmd_y_invalid = MockGCodeCommand({'X': '35.0', 'Y': '337.0'})
        with self.assertRaises(ValueError) as ctx:
            verify_park_pos(gcmd_y_invalid)
        self.assertIn("Exceeded: Y: 4.800mm", str(ctx.exception))

        # Force move overrides tolerance check
        gcmd_y_forced = MockGCodeCommand({'X': '35.0', 'Y': '337.0', 'FORCE_MOVE': '1'})
        verify_park_pos(gcmd_y_forced)

if __name__ == '__main__':
    unittest.main()

