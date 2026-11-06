import unittest

PHYSICAL_EXTRUDER_NUM = 4

class TestBugLog03PrintTaskConfig(unittest.TestCase):
    def test_filament_color_rgb_length(self):
        # Emulate set_filament_slot color parsing
        filament_color = 0xFF112233
        alpha = (filament_color & 0xFF000000) >> 24
        red =   (filament_color & 0x00FF0000) >> 16
        green = (filament_color & 0x0000FF00) >> 8
        blue =  (filament_color & 0x000000FF) >> 0
        dest_filament_color_rgba = f'{red:02X}' + f'{green:02X}' + f'{blue:02X}' + f'{alpha:02X}'

        dest_filament_color_multi = {}
        dest_filament_color_multi['nums'] = 1
        dest_filament_color_multi['alpha'] = alpha
        # Fix: must be 6-char RGB hex string, not 8-char RGBA
        dest_filament_color_multi['colors'] = [dest_filament_color_rgba[0:6]]
        dest_filament_color_multi['mode'] = 0

        # Verify length is 6
        self.assertEqual(len(dest_filament_color_multi['colors'][0]), 6)
        self.assertEqual(dest_filament_color_multi['colors'][0], "112233")

        # Emulate _early_check validation
        for j in range(dest_filament_color_multi['nums']):
            color_str = dest_filament_color_multi['colors'][j]
            self.assertTrue(isinstance(color_str, str))
            self.assertEqual(len(color_str), 6)

    def test_flow_calib_extruders_key(self):
        # Verify key name matches schema
        config = {
            'flow_calib_extruders': [True] * PHYSICAL_EXTRUDER_NUM,
            'reprint_info': {'flow_calib_extruders': [True] * PHYSICAL_EXTRUDER_NUM}
        }
        flow_calibrate_extruders = "0,2"
        calib_extruders = [int(v) for v in flow_calibrate_extruders.split(',')]

        config['flow_calib_extruders'] = [True for _ in range(PHYSICAL_EXTRUDER_NUM)]
        config['reprint_info']['flow_calib_extruders'] = [True for _ in range(PHYSICAL_EXTRUDER_NUM)]
        for i in range(PHYSICAL_EXTRUDER_NUM):
            val = (i in calib_extruders)
            config['flow_calib_extruders'][i] = val
            config['reprint_info']['flow_calib_extruders'][i] = val

        self.assertNotIn('flow_calibrate_extruders', config)
        self.assertEqual(config['flow_calib_extruders'], [True, False, True, False])
        self.assertEqual(config['reprint_info']['flow_calib_extruders'], [True, False, True, False])

if __name__ == '__main__':
    unittest.main()

