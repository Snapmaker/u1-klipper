# Unit test for BUG-STACK-02: Infinite probing loop in auto_screws_tilt_adjust
import unittest
from unittest.mock import MagicMock
from extras import auto_screws_tilt_adjust


class CommandError(Exception):
    pass


class TestBugStack02(unittest.TestCase):
    def _create_adjuster(self):
        config = MagicMock()
        printer = MagicMock()
        printer.is_shutdown.return_value = False
        toolhead = MagicMock()
        probe = MagicMock()
        gcode = MagicMock()
        webhooks = MagicMock()

        printer.lookup_object.side_effect = lambda name, default=None: {
            'toolhead': toolhead,
            'probe': probe,
            'gcode': gcode,
            'webhooks': webhooks,
            'machine_state_manager': None
        }.get(name, default)

        config.get_printer.return_value = printer
        config.get.side_effect = (
            lambda k, default=None: '10,10'
            if k.startswith('screw') and not k.endswith('_name')
            else default
        )
        config.getfloatlist.side_effect = lambda k, count=2: (10.0, 10.0)
        config.getintlist.side_effect = (
            lambda k, default=None, count=4: default or [1, 2, 3, 4]
        )
        config.getfloat.side_effect = (
            lambda k, default=None, **kwargs: default
            if default is not None else 0.1
        )
        config.getint.side_effect = (
            lambda k, default=None, **kwargs: default
            if default is not None else 1
        )

        adjuster = auto_screws_tilt_adjust.AutoScrewsTiltAdjust(config)
        adjuster.state = (
            auto_screws_tilt_adjust.AutoScrewsTiltAdjustStep
            .PROBING_REFPOINT_COMPLETED
        )
        adjuster.base_points = [0.1, 0.2, 0.3, 0.4]
        adjuster.target_z = 0.25

        toolhead.get_status.return_value = {'homed_axes': ['x', 'y', 'z']}
        probe.get_status.return_value = {'last_z_result': 0.2}

        return adjuster, printer, gcode

    def test_manual_tuning_max_verify_attempts_limit(self):
        adjuster, printer, gcode = self._create_adjuster()

        # Simulate user advancing screws
        def mock_run_script(cmd):
            if 'PROBE SAMPLES=1' in cmd:
                adjuster.state = (
                    auto_screws_tilt_adjust.AutoScrewsTiltAdjustStep
                    .NEXT_POINT_ADJUST
                )
        gcode.run_script_from_command.side_effect = mock_run_script

        adjuster._verify_level = MagicMock(return_value=False)

        gcmd = MagicMock()
        gcmd.error = CommandError
        gcmd.get_int.side_effect = (
            lambda name, default=None, **kw: 2
            if name == 'MAX_VERIFY_ATTEMPTS' else 5
        )

        with self.assertRaises(CommandError) as ctx:
            adjuster.cmd_AUTO_SCREWS_TILT_ADJUST_MANUAL_TUNING(gcmd)

        self.assertIn("exceeded max verification attempts (2)", str(ctx.exception))
        self.assertEqual(
            adjuster.state,
            auto_screws_tilt_adjust.AutoScrewsTiltAdjustStep.SCREWS_TILT_ADJUST_FAIL
        )

    def test_manual_tuning_screw_adjust_max_times_limit(self):
        adjuster, printer, gcode = self._create_adjuster()

        gcmd = MagicMock()
        gcmd.error = CommandError
        gcmd.get_int.side_effect = (
            lambda name, default=None, **kw: 3
            if name == 'ADJUST_MAX_TIMES' else 10
        )

        with self.assertRaises(CommandError) as ctx:
            adjuster.cmd_AUTO_SCREWS_TILT_ADJUST_MANUAL_TUNING(gcmd)

        self.assertIn("exceeded max limit (3 times)", str(ctx.exception))
        self.assertEqual(
            adjuster.state,
            auto_screws_tilt_adjust.AutoScrewsTiltAdjustStep.SCREWS_TILT_ADJUST_FAIL
        )

    def test_probe_abort_check_on_shutdown(self):
        adjuster, printer, gcode = self._create_adjuster()
        printer.is_shutdown.return_value = True

        gcmd = MagicMock()
        gcmd.error = CommandError
        gcmd.get_int.side_effect = lambda name, default=None, **kw: default or 10

        adjuster.cmd_AUTO_SCREWS_TILT_ADJUST_MANUAL_TUNING(gcmd)
        self.assertEqual(
            adjuster.state,
            auto_screws_tilt_adjust.AutoScrewsTiltAdjustStep.PROBING_ABORTED
        )


if __name__ == '__main__':
    unittest.main()
