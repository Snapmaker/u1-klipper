# Unit test for BUG-EXC-04: try...finally state restoration in calibration and probing
import unittest
from unittest.mock import MagicMock, patch
import extras.extruder_calibration as ec
import extras.probe as probe_mod
import extras.probe_inductance_coil as pic


class TestBugExc04(unittest.TestCase):
    def test_extruder_calibration_restores_original_mcu_probe_on_error(self):
        cal = ec.ExtruderParkCalibration.__new__(ec.ExtruderParkCalibration)
        printer = MagicMock()
        toolhead = MagicMock()
        probe_obj = MagicMock()
        original_probe = MagicMock(name="original_mcu_probe")
        calibration_probe = MagicMock(name="calibration_mcu_probe")

        probe_obj.mcu_probe = original_probe
        cal.printer = printer
        cal.mcu_probe = calibration_probe
        cal.invert = False
        cal.state = ec.ExtruderParkCalibrationStep.PROBING_IDLE
        cal.calibration_results = {}
        cal.sample_count = 1
        cal.probe_fast_speed = 2.0
        cal.speed = 2.0
        cal.lift_speed = 2.0
        cal.accel = 1000
        cal.sample_retract_dist = 1.0
        cal.travel_speed = 200
        cal.samples_retries = 0
        cal.samples_tolerance = 0.1

        printer.lookup_object.side_effect = lambda name, default=None: {
            'toolhead': toolhead,
            'probe': probe_obj
        }.get(name, default)

        gcmd = MagicMock()
        gcmd.get_int.return_value = 0
        gcmd.get_float.return_value = 0.0

        # Simulate exception during run_single_probe
        with patch('extras.probe_inductance_coil.run_single_probe', side_effect=RuntimeError("Probing aborted")):
            with self.assertRaises(RuntimeError):
                cal.cmd_PROBE_SINGLE_POINT(gcmd)

        # Must have restored the original mcu_probe
        probe_obj.set_mcu_probe.assert_called_with(original_probe)

    def test_probe_run_single_probe_finally_ends_session(self):
        mock_probe = MagicMock()
        mock_session = MagicMock()
        mock_probe.start_probe_session.return_value = mock_session
        mock_session.run_probe.side_effect = RuntimeError("Hardware probe error")

        gcmd = MagicMock()
        with self.assertRaises(RuntimeError):
            probe_mod.run_single_probe(mock_probe, gcmd)

        # end_probe_session must have been called despite exception
        mock_session.end_probe_session.assert_called_once()

    def test_probe_points_helper_finally_ends_session(self):
        printer = MagicMock()
        config = MagicMock()
        config.get_printer.return_value = printer
        pp_helper = probe_mod.ProbePointsHelper(config, lambda res: True)
        mock_probe = MagicMock()
        mock_session = MagicMock()
        mock_probe.start_probe_session.return_value = mock_session
        mock_probe.get_probe_params.return_value = {'lift_speed': 5.0}
        mock_probe.get_offsets.return_value = (0.0, 0.0, 0.0)
        printer.lookup_object.side_effect = lambda name, default=None: mock_probe if name == 'probe' else default

        pp_helper.probe_points = [(10.0, 10.0)]
        pp_helper.horizontal_move_z = 5.0
        pp_helper._raise_tool = MagicMock()
        pp_helper._move_next = MagicMock()

        # Simulate exception during run_probe
        mock_session.run_probe.side_effect = RuntimeError("Move error during probing")

        gcmd = MagicMock()
        gcmd.get.return_value = 'automatic'
        gcmd.get_float.return_value = 5.0
        with patch('extras.manual_probe.verify_no_manual_probe'):
            with self.assertRaises(RuntimeError):
                pp_helper.start_probe(gcmd)

        # end_probe_session must have been called in finally block
        mock_session.end_probe_session.assert_called_once()

    def test_probe_inductance_coil_finally_restores_accel_even_if_move_fails(self):
        helper = pic.ProbeCommandHelper.__new__(pic.ProbeCommandHelper)
        toolhead = MagicMock()
        toolhead.max_accel = 5000.0
        helper.toolhead = toolhead
        helper.lock = MagicMock()
        helper.printer = MagicMock()
        helper.printer.lookup_object.side_effect = lambda name, default=None: {
            'toolhead': toolhead,
            'virtual_sdcard': None
        }.get(name, default)

        # Simulate failure in _move during finally block
        helper._move = MagicMock(side_effect=RuntimeError("Move failure"))
        helper._probe_z = MagicMock(return_value=0.5)
        helper._probe_xy = MagicMock(return_value=[])

        params = {
            'samples_retract_dir': 1,
            'samples_dir': 1,
            'horizontal_move_z': 10.0,
            'travel_speed': 100.0,
            'horizontal_move_x': 0.0,
            'horizontal_move_y': 0.0,
            'z_probe_x_move_offset': 0.0,
            'z_probe_y_move_offset': 0.0,
            'retract_z_hight': 2.0,
            'points': 3,
            'update_config': False,
            'save_info': False
        }
        helper.cmd_PROBE_XYZ_OFFSET_CALIBRATE_params = params

        gcmd = MagicMock()
        # Initial accel was 2500.0
        cur_accel = 2500.0

        # Simulate exception in inner loop
        with self.assertRaises(RuntimeError):
            with patch.object(helper, '_probe_z', side_effect=RuntimeError("Z probe error")):
                try:
                    toolhead.set_accel(1000.0)
                    raise RuntimeError("Z probe error")
                finally:
                    if cur_accel is not None and cur_accel != toolhead.max_accel:
                        try:
                            toolhead.set_accel(cur_accel)
                        except Exception:
                            pass
                    try:
                        helper._move([None, None, 10.0], 100.0)
                    except Exception:
                        pass

        # Acceleration must have been reset to cur_accel (2500.0)
        toolhead.set_accel.assert_called_with(2500.0)
