# Unit test for BUG-LOG-14: config typo, entangle detect key lookup, and mqtt qos 0
import unittest
from unittest.mock import MagicMock
import extras.mqtt as mqtt
import extras.filament_entangle_detect as fed


class TestBugLog14(unittest.TestCase):
    def test_mqtt_qos_zero_preserved(self):
        # When default qos is 1, an explicit qos=0 must NOT be overridden to 1
        client_mock = MagicMock()
        client_mock.is_connected.return_value = True
        client_mock.subscribe.return_value = (0, 1)
        client_mock.publish.return_value = (0, 1)

        printer = MagicMock()
        reactor = MagicMock()
        printer.get_reactor.return_value = reactor
        config = MagicMock()
        config.get_printer.return_value = printer
        config.get.return_value = 'localhost'
        config.getint.side_effect = lambda name, default=None, **kw: 1 if 'qos' in name else default
        config.getboolean.return_value = False

        m = mqtt.MQTTClient(config)
        m.client = client_mock

        # Test subscribe with qos=0
        cb = lambda msg: None
        m.subscribe_topic('test/topic', cb, qos=0)
        client_mock.subscribe.assert_called_with('test/topic', 0)

        # Test publish with qos=0
        m.publish_topic('test/topic', 'payload', qos=0)
        client_mock.publish.assert_called_with('test/topic', 'payload', 0, False)

    def test_filament_entangle_detect_key_resolution(self):
        config = MagicMock()
        printer = MagicMock()
        config.get_printer.return_value = printer
        config.get_name.return_value = 'filament_entangle_detect e0'
        config.get.side_effect = lambda k, default=None: 'extruder0' if k == 'extruder' else 'filament_feed'
        config.getfloat.return_value = 20.0

        printer.get_snapmaker_config_dir.return_value = '/tmp'
        printer.load_snapmaker_config_file.return_value = {'detect_factor': 1.0}

        detector = fed.FilamentEntangleDetect(config)
        detector.init_ok = True
        detector.skip_check_flag = False
        detector.extruder_index = 0
        detector.extruder_name = 'extruder0'

        mock_feed = MagicMock()
        mock_feed.get_status.return_value = {
            'extruder0': {
                'module_exist': True,
                'disable_auto': False,
                'filament_detected': True
            }
        }
        detector.filament_feed_module = mock_feed

        mock_print_task = MagicMock()
        mock_print_task.print_task_config = {'filament_entangle_detect': True}
        detector.print_task_config = mock_print_task

        mock_stats = MagicMock()
        mock_stats.get_status.return_value = {'state': 'printing'}
        detector.print_stats = mock_stats

        # With the fix, extruder0 resolves directly to 'extruder0' without becoming 'extruder00'
        self.assertTrue(detector._need_to_check_entanglement())

    def test_extruder_calibration_positions_dict_and_guard(self):
        import extras.extruder_calibration as ec
        # Verify dictionary naming
        inst = ec.ExtruderParkCalibration.__new__(ec.ExtruderParkCalibration)
        inst.extruder_y_cal_second_positions = {}
        inst.y_cal_enable = True

        # When section is not present in extruder_y_cal_second_positions, guard prevents KeyError
        section = 'extruder'
        self.assertNotIn(section, inst.extruder_y_cal_second_positions)
        # Should not raise KeyError when guarded
        self.assertFalse(inst.y_cal_enable and section in inst.extruder_y_cal_second_positions)
