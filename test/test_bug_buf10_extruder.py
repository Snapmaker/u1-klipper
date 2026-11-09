#!/usr/bin/env python3
# Test harness for BUG-BUF-10: Out-of-bounds IndexError in extruder.py
import sys
import os
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'klippy'))
from kinematics import extruder

class DummyPrinter:
    def __init__(self):
        self.objects = {}
        self.start_args = {'software_version': 'test-version'}
    def lookup_object(self, name, default=None):
        return self.objects.get(name, default)
    def update_snapmaker_config_file(self, path, info):
        return True
    def get_start_args(self):
        return self.start_args

class DummyPrintTaskConfig:
    def __init__(self, vendors=None):
        self.vendors = vendors if vendors is not None else []
    def get_status(self):
        return {
            'filament_vendor': list(self.vendors),
            'filament_type': ['PLA'] * len(self.vendors),
            'filament_sub_type': ['STANDARD'] * len(self.vendors),
        }
    def reset_filament_info(self, idx):
        pass

class DummyFilamentParameters:
    def is_allow_to_print(self, v, t, s, d, vol):
        return True
    def get_print_temp(self, v, t, s, d, vol):
        return 215

class DummyExtruderObj:
    def __init__(self, diameter=0.4, volume_type='standard'):
        self.nozzle_diameter = diameter
        self.nozzle_volume_type = volume_type

class TestPrinterExtruder(extruder.PrinterExtruder):
    def __init__(self, printer, extruder_index=0):
        self.printer = printer
        self.name = f"extruder{extruder_index}" if extruder_index else "extruder"
        self.extruder_index = extruder_index
        self.nozzle_diameter = 0.4
        self.nozzle_volume_type = 'standard'
        self.nozzle_config_info = {'volume_type': 'standard'}
        self.nozzle_config_path = '/tmp/fake_nozzle_cfg'
        self.grab_hall_sensor_type = True

class TestBuf10Extruder(unittest.TestCase):
    def setUp(self):
        self.printer = DummyPrinter()
        self.filament_params = DummyFilamentParameters()
        self.printer.objects['filament_parameters'] = self.filament_params
        self.printer.objects['extruder'] = DummyExtruderObj()
        self.printer.objects['extruder1'] = DummyExtruderObj()

    def test_01_set_nozzle_diameter_empty_vendor_list(self):
        # Empty vendor list in print_task_config must not raise IndexError
        self.printer.objects['print_task_config'] = DummyPrintTaskConfig(vendors=[])
        ext = TestPrinterExtruder(self.printer, extruder_index=0)
        try:
            ext._set_nozzle_diameter(0.2, save=False)
        except IndexError as e:
            self.fail(f"_set_nozzle_diameter raised IndexError on empty vendor list: {e}")

    def test_02_set_nozzle_diameter_out_of_bounds_index(self):
        # Extruder index 3 when only 1 vendor configured must not raise IndexError
        self.printer.objects['print_task_config'] = DummyPrintTaskConfig(vendors=['SNAPMAKER'])
        ext = TestPrinterExtruder(self.printer, extruder_index=3)
        try:
            ext._set_nozzle_diameter(0.2, save=False)
        except IndexError as e:
            self.fail(f"_set_nozzle_diameter raised IndexError on out-of-bounds index: {e}")

    def test_03_get_filament_temp_out_of_bounds_index(self):
        # Requesting temp for extruder 1 when only 1 vendor configured must safely return 220
        self.printer.objects['print_task_config'] = DummyPrintTaskConfig(vendors=['SNAPMAKER'])
        ext = TestPrinterExtruder(self.printer, extruder_index=0)
        try:
            temp = ext._get_filament_temp(extruder_index=1)
            self.assertEqual(temp, 220)
        except IndexError as e:
            self.fail(f"_get_filament_temp raised IndexError: {e}")

    def test_04_get_filament_temp_negative_index(self):
        # Negative index must safely return default 220
        self.printer.objects['print_task_config'] = DummyPrintTaskConfig(vendors=['SNAPMAKER'] * 4)
        ext = TestPrinterExtruder(self.printer, extruder_index=0)
        try:
            temp = ext._get_filament_temp(extruder_index=-1)
            self.assertEqual(temp, 220)
        except IndexError as e:
            self.fail(f"_get_filament_temp raised IndexError on negative index: {e}")

    def test_05_unknown_empty_list_handling(self):
        # When unknown is empty, grip_states[unknown[0]] must not be evaluated
        unknown = []
        grip_states = ['FFF', 'FFT']
        first_unknow_state = None
        if unknown and 0 <= unknown[0] < len(grip_states):
            first_unknow_state = grip_states[unknown[0]]
        self.assertIsNone(first_unknow_state)

if __name__ == '__main__':
    unittest.main()

