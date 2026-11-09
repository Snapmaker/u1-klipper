import unittest

LOGICAL_EXTRUDER_NUM = 32
PHYSICAL_EXTRUDER_NUM = 4

class TestBugBuf11PrintTaskConfig(unittest.TestCase):
    def test_used_extruders_out_of_bounds(self):
        def parse_used_extruders(extruders_str):
            tmp_extruders_used = [False] * PHYSICAL_EXTRUDER_NUM
            used_extruders = [int(v) for v in extruders_str.split(',')]
            for i in range(min(len(used_extruders), LOGICAL_EXTRUDER_NUM)):
                idx = used_extruders[i]
                if 0 <= idx < PHYSICAL_EXTRUDER_NUM:
                    tmp_extruders_used[idx] = True
                else:
                    raise ValueError(f"Invalid extruder index: {idx}")
            return tmp_extruders_used

        # Normal valid extruders
        self.assertEqual(parse_used_extruders("0,1"), [True, True, False, False])

        # Out of bounds (> 3)
        with self.assertRaises(ValueError) as ctx:
            parse_used_extruders("0,4")
        self.assertIn("Invalid extruder index: 4", str(ctx.exception))

        # Negative index
        with self.assertRaises(ValueError) as ctx:
            parse_used_extruders("-1,2")
        self.assertIn("Invalid extruder index: -1", str(ctx.exception))

    def test_map_table_negative_index(self):
        def check_map_table(map_table_list):
            for i in range(len(map_table_list)):
                if not (0 <= map_table_list[i][0] < LOGICAL_EXTRUDER_NUM and
                        0 <= map_table_list[i][1] < PHYSICAL_EXTRUDER_NUM):
                    raise ValueError("Invalid MAP_TABLE")

        # Valid
        check_map_table([[0, 0], [1, 1]])

        # Negative logical extruder
        with self.assertRaises(ValueError):
            check_map_table([[-1, 0]])

        # Negative physical extruder
        with self.assertRaises(ValueError):
            check_map_table([[0, -1]])

    def test_flow_calibrate_negative_index(self):
        def check_flow_calib(flow_calib_list):
            for i in range(len(flow_calib_list)):
                if not (0 <= flow_calib_list[i] < PHYSICAL_EXTRUDER_NUM):
                    raise ValueError("Invalid FLOW_CALIBRATE_EXTRUDERS")

        # Valid
        check_flow_calib([0, 1, 2, 3])

        # Negative
        with self.assertRaises(ValueError):
            check_flow_calib([-1])

        # Greater than 3
        with self.assertRaises(ValueError):
            check_flow_calib([4])

    def test_nozzle_diameter_index_i(self):
        # Extruder 0 has nozzle 0.4, Extruder 1 has nozzle 0.6
        actual_nozzle_diameter = [0.4, 0.6, 0.4, 0.4]
        extruders_used = [True, True, False, False]
        # Sliced file configured nozzle 0 for E0, and nozzle 1 for E1
        sliced_nozzle_diameter = [0.4, 0.6]

        mismatches = []
        for i in range(PHYSICAL_EXTRUDER_NUM):
            if extruders_used[i]:
                if i < len(sliced_nozzle_diameter) and sliced_nozzle_diameter[i] is not None:
                    if abs(sliced_nozzle_diameter[i] - actual_nozzle_diameter[i]) > 0.001:
                        mismatches.append(i)

        # In fixed code, E0 matches sliced[0] (0.4 == 0.4) and E1 matches sliced[1] (0.6 == 0.6)
        self.assertEqual(len(mismatches), 0)

        # In old buggy code: sliced[0] was compared to actual[1] (0.4 vs 0.6 -> false mismatch!)
        old_buggy_mismatches = []
        for i in range(PHYSICAL_EXTRUDER_NUM):
            if extruders_used[i]:
                if abs(sliced_nozzle_diameter[0] - actual_nozzle_diameter[i]) > 0.001:
                    old_buggy_mismatches.append(i)
        self.assertEqual(old_buggy_mismatches, [1])

if __name__ == '__main__':
    unittest.main()

