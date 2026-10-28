# Tests for klippy/extras/print_temperature_guard.py
#
# Copyright (C) 2026  Gilberto Moraes
#                     <7747175+MoraesGil@users.noreply.github.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# The real module against synthetic printer objects; no MCU, no printer.
# Run from the repository root:
#   python3 -m unittest discover -s test/klippy_extras -p '*_test.py'

from copy import deepcopy
import importlib.util
import os
from types import SimpleNamespace
import unittest


import sys

KLIPPY = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', 'klippy'
)
sys.path.insert(0, KLIPPY)  # heaters.py imports queuefile


def load_module(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(KLIPPY, 'extras', name + '.py')
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HEATERS = load_module('heaters')


class FakeHeater:
    def __init__(self, name):
        self.name = name
        self.target_temp = 210.0
        self.smoothed_temp = 210.0
        self.is_shutdown = False
        self.min_temp, self.max_temp, self.min_extrude_temp = 0.0, 300.0, 170.0
        self.writes = []

    def get_name(self):
        return self.name

    def set_temp(self, target):
        self.writes.append(target)
        self.target_temp = target


class FakeGcmd:
    def __init__(self, params, line=None):
        self.params, self.responses = params, []
        self.line = (
            line
            if line is not None
            else ' '.join(
                ['SET_GUARDED_PRINT_TEMPERATURE']
                + ['%s=%s' % item for item in params.items()]
            )
        )

    def get_commandline(self):
        return self.line

    def get_command_parameters(self):
        return self.params

    def respond_info(self, message):
        self.responses.append(message)


class PrintTemperatureGuardTests(unittest.TestCase):
    def setUp(self):
        module = load_module('print_temperature_guard')
        self.clock = 100.0
        self.callbacks, self.commands = {}, {}
        self.stats = SimpleNamespace(
            state='printing',
            filename='synthetic.gcode',
            print_start_time=20.0,
            exception_details={},
            error_message='',
        )
        self.file = SimpleNamespace(
            name='/synthetic/synthetic.gcode', closed=False
        )
        self.sd = SimpleNamespace(
            current_file=self.file,
            must_pause_work=False,
            is_active=lambda: True,
        )
        self.inventory = dict(
            filament_exist=[True] * 4,
            extruder_map_table=[0, 1, 2, 3],
            filament_color_rgba=[
                'FF0000FF',
                '00FF00FF',
                '0000FFFF',
                'FFFFFFFF',
            ],
            filament_color_multi=[{} for _ in range(4)],
            filament_type=['PLA'] * 4,
            filament_sub_type=['generic'] * 4,
            filament_vendor=['generic'] * 4,
            filament_sku=[0] * 4,
            filament_official=[False] * 4,
        )
        self.config = SimpleNamespace(
            get_status=lambda now: deepcopy(self.inventory),
            print_task_config_2={'nozzle_temp': [210, 210, 210, 210]},
            is_exec_print_end_action=False,
        )
        self.pause = SimpleNamespace(is_paused=False, pause_command_sent=False)
        self.exceptions = SimpleNamespace(exceptions=[], async_exceptions=[])
        self.machine = SimpleNamespace(main_state=1, action_code=0)
        self.heaters = [
            FakeHeater('extruder' + (str(i) if i else '')) for i in range(4)
        ]
        self.extruders = [
            SimpleNamespace(
                get_name=lambda i=i: self.heaters[i].name,
                get_heater=lambda i=i: self.heaters[i],
            )
            for i in range(4)
        ]
        self.active = self.extruders[0]
        self.grab_complete = True
        self.park_states = ['ACTIVATE', 'PARKED', 'PARKED', 'PARKED']
        for i, extruder in enumerate(self.extruders):
            extruder.get_park_detector_status = lambda i=i: {
                'state': self.park_states[i]
            }
        self.power = SimpleNamespace(
            active_heating_extruders=[h.name for h in self.heaters],
            pending_extruders=[],
            max_heating_extruders=4,
        )

        # The real native admission method, bound to the synthetic lists.
        def admit(heater, temp):
            return HEATERS.PrinterHeaters.try_set_extruder_temperature(
                self.power, heater, temp
            )

        self.power.try_set_extruder_temperature = admit
        self.power.is_extruder_pending = (
            lambda name: HEATERS.PrinterHeaters.is_extruder_pending(
                self.power, name
            )
        )
        self.ready = 'ready'
        self.objects = dict(
            print_stats=self.stats,
            virtual_sdcard=self.sd,
            print_task_config=self.config,
            pause_resume=self.pause,
            exception_manager=self.exceptions,
            machine_state_manager=self.machine,
            heaters=self.power,
            toolhead=SimpleNamespace(
                get_extruder=lambda: self.active,
                get_grab_complete=lambda: self.grab_complete,
            ),
            gcode=SimpleNamespace(
                register_command=lambda name, handler, **kw: (
                    self.commands.update({name: handler})
                )
            ),
        )
        self.objects.update(
            {h.name: e for h, e in zip(self.heaters, self.extruders)}
        )
        self.sensors = [
            dict(enabled=True, filament_detected=True) for _ in range(4)
        ]
        self.objects.update(
            {
                'filament_motion_sensor e%d_filament'
                % i: SimpleNamespace(
                    get_status=lambda now, i=i: self.sensors[i]
                )
                for i in range(4)
            }
        )
        self.printer = SimpleNamespace(
            lookup_object=lambda name, default=None: self.objects.get(
                name, default
            ),
            get_reactor=lambda: SimpleNamespace(monotonic=lambda: self.clock),
            get_state_message=lambda: ('synthetic state', self.ready),
            register_event_handler=lambda name, callback: (
                self.callbacks.update({name: callback})
            ),
        )
        self.options = {}
        self.module = module
        self.setUp_guard()

    def setUp_guard(self):
        self.guard = self.module.load_config(
            SimpleNamespace(
                get_printer=lambda: self.printer,
                getfloat=lambda name, default, **kw: self.options.get(
                    name, default
                ),
            )
        )

    def status(self):
        return self.guard.get_status(self.clock)

    def body(self, **updates):
        status = self.status()
        params = dict(
            TOOL='1',
            TARGET='215',
            EXPECTED='210',
            JOB=status['job_token'],
            FILAMENT=status['filament_tokens'][0],
            NONCE='a' * 32,
            ACTIVATION=status.get('activation_token'),
            POLICY='b' * 32,
        )
        params.update(updates)
        return params

    def execute(self, params, line=None):
        self.commands['SET_GUARDED_PRINT_TEMPERATURE'](FakeGcmd(params, line))
        return self.status()['last_result']

    def assert_no_heat(self):
        self.assertEqual([h.writes for h in self.heaters], [[], [], [], []])

    def test_safe_command_applies_only_selected_active_heater(self):
        before = self.status()
        self.assertEqual(before['protocol'], 1)
        self.assertEqual(
            before['implementation'], 'u1-print-temperature-guard-v1'
        )
        self.assertRegex(before['job_token'], r'^[0-9a-f]{64}$')
        result = self.execute(self.body())
        self.assertEqual(
            result,
            dict(
                nonce='a' * 32,
                applied=True,
                replayed=False,
                reason='applied',
                toolhead=1,
                target=215,
            ),
        )
        self.assertEqual([h.writes for h in self.heaters], [[215], [], [], []])

    def test_firmware_async_reader_with_only_private_closed_flag(self):
        # virtual_sdcard.current_file is an AsyncFileReader: no public
        # "closed", only "_closed". A real job must still get a token.
        self.file = SimpleNamespace(
            name='/synthetic/synthetic.gcode', _closed=False
        )
        self.sd.current_file = self.file
        self.assertRegex(self.status()['job_token'], r'^[0-9a-f]{64}$')
        self.assertTrue(self.execute(self.body())['applied'])
        self.file._closed = True
        self.assertIsNone(self.status()['job_token'])

    def test_target_limits_relative_to_print_and_heater_maximum(self):
        # Default max_delta 30 and max_temp_margin 10 (max_temp 300).
        self.assertFalse(self.execute(self.body(TARGET='241'))['applied'])
        self.assertFalse(
            self.execute(self.body(TARGET='179', NONCE='c' * 32))['applied']
        )
        self.assert_no_heat()
        self.assertTrue(
            self.execute(self.body(TARGET='240', NONCE='d' * 32))['applied']
        )
        self.setUp()
        self.options.update(max_delta=100.0)
        self.setUp_guard()
        self.config.print_task_config_2['nozzle_temp'] = [280, 210, 210, 210]
        self.heaters[0].target_temp = 280
        self.assertFalse(
            self.execute(self.body(TARGET='291', EXPECTED='280'))['applied']
        )
        self.assertTrue(
            self.execute(
                self.body(TARGET='290', EXPECTED='280', NONCE='c' * 32)
            )['applied']
        )

    def test_status_never_raises_on_unexpected_native_state(self):
        def broken(now):
            raise RuntimeError('synthetic native failure')

        self.config.get_status = broken
        with self.assertLogs(level='ERROR'):
            status = self.status()
        self.assertEqual(status['filament_tokens'], [None] * 4)
        self.objects['toolhead'] = SimpleNamespace(get_extruder=broken)
        # Still failing: null tokens again, logged only on the first failure.
        with self.assertNoLogs(level='ERROR'):
            self.assertIsNone(self.status()['activation_token'])
        self.config.get_status = lambda now: deepcopy(self.inventory)
        self.objects['toolhead'] = SimpleNamespace(
            get_extruder=lambda: self.active,
            get_grab_complete=lambda: self.grab_complete,
        )
        self.assertIsNotNone(self.status()['activation_token'])
        self.config.get_status = broken
        with self.assertLogs(level='ERROR'):
            self.status()  # A new failure after recovery is logged again

    def test_repeated_parameter_and_malformed_nonce_are_not_trusted(self):
        params = self.body()
        line = 'SET_GUARDED_PRINT_TEMPERATURE TOOL=2 ' + ' '.join(
            '%s=%s' % item for item in params.items()
        )
        result = self.execute(params, line)
        self.assertEqual(result['reason'], 'invalid_parameters')
        self.assert_no_heat()
        result = self.execute(self.body(NONCE='X' * 100000))
        self.assertIsNone(result['nonce'])
        self.assertFalse(result['applied'])

    def test_quoted_parameter_is_refused(self):
        params = self.body()
        line = 'SET_GUARDED_PRINT_TEMPERATURE ' + ' '.join(
            '%s=%s' % item for item in params.items()
        )
        result = self.execute(params, line + ' "TARGET"=240')
        self.assertEqual(result['reason'], 'invalid_parameters')
        self.assert_no_heat()

    def test_pending_native_target_blocks_even_an_equal_target(self):
        self.heaters[0].target_temp = 215
        self.power.pending_extruders.append(('extruder', 230.0))
        result = self.execute(self.body())
        self.assertEqual(result['reason'], 'power_budget')
        self.assertFalse(result['applied'])

    def test_pending_head_is_never_admitted_and_budget_is_native(self):
        self.power.pending_extruders.append(('extruder', 230.0))
        self.assertEqual(self.execute(self.body())['reason'], 'power_budget')
        self.assert_no_heat()
        self.assertEqual(self.power.pending_extruders, [('extruder', 230.0)])

    def test_enqueue_execute_races_never_heat_changed_state(self):
        changes = [
            lambda: setattr(self.pause, 'is_paused', True),
            lambda: setattr(self.stats, 'state', 'paused'),
            lambda: setattr(self.active, 'get_name', lambda: 'extruder2'),
            lambda: setattr(self.heaters[0], 'target_temp', 140),
            lambda: setattr(self.heaters[0], 'target_temp', 0),
            lambda: setattr(
                self.sd,
                'current_file',
                SimpleNamespace(name=self.file.name, closed=False),
            ),
            lambda: setattr(self.stats, 'print_start_time', 21.0),
            lambda: self.inventory['filament_color_rgba'].__setitem__(
                0, 'FFFF00FF'
            ),
            lambda: self.inventory['filament_type'].__setitem__(0, 'PETG'),
        ]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                self.setUp()
                queued = self.body()
                change()
                self.assertFalse(self.execute(queued)['applied'])
                self.assert_no_heat()

    def test_same_file_new_job_event_revokes_old_token(
        self,
    ):
        queued = self.body()
        self.callbacks['print_stats:new_task_start']()
        self.assertNotEqual(self.status()['job_token'], queued['JOB'])
        self.assertFalse(self.execute(queued)['applied'])
        self.assert_no_heat()

    def test_job_identity_survives_pause_but_not_missing_file_or_boot(self):
        token = self.status()['job_token']
        self.stats.state, self.pause.is_paused = 'paused', True
        self.assertEqual(self.status()['job_token'], token)
        self.sd.current_file = None
        self.assertIsNone(self.status()['job_token'])
        self.sd.current_file = self.file
        self.assertNotEqual(self.status()['job_token'], token)
        self.setUp()
        self.assertNotEqual(self.status()['job_token'], token)

    def test_unknown_filament_and_unloaded_slot_cannot_receive_token(self):
        for field, value in [
            ('filament_exist', False),
            ('filament_exist', None),
            ('filament_color_rgba', ''),
            ('filament_color_rgba', 'bogus'),
            ('filament_type', 'NONE'),
            ('filament_type', None),
        ]:
            with self.subTest(field=field, value=value):
                self.setUp()
                self.inventory[field][0] = value
                self.assertIsNone(self.status()['filament_tokens'][0])
                self.assert_no_heat()

    def test_fault_unknown_state_and_power_queue_block_heating(self):
        mutations = [
            lambda: setattr(self, 'ready', 'shutdown'),
            lambda: self.exceptions.exceptions.append({'code': 523}),
            lambda: self.exceptions.async_exceptions.append((523,)),
            lambda: setattr(self.stats, 'exception_details', {'code': 523}),
            lambda: setattr(self.stats, 'error_message', 'fault'),
            lambda: setattr(self.machine, 'main_state', 7),
            lambda: setattr(self.machine, 'action_code', 130),
            lambda: setattr(self.pause, 'is_paused', None),
            lambda: setattr(self.pause, 'pause_command_sent', True),
            lambda: setattr(self.sd, 'must_pause_work', True),
            lambda: setattr(self.sd, 'is_active', lambda: False),
            lambda: setattr(self.config, 'is_exec_print_end_action', True),
            lambda: setattr(self.power, 'try_set_extruder_temperature', None),
            lambda: self.power.pending_extruders.append(('extruder', 230)),
            lambda: self.objects.pop('exception_manager'),
        ]
        for mutate in mutations:
            with self.subTest(case=mutations.index(mutate)):
                self.setUp()
                queued = self.body()
                mutate()
                self.assertFalse(self.execute(queued)['applied'])
                self.assert_no_heat()

    def test_power_admission_uses_available_slot_without_queueing(self):
        self.power.active_heating_extruders = ['extruder1']
        self.power.max_heating_extruders = 2
        self.assertTrue(self.execute(self.body())['applied'])
        self.assertEqual(
            self.power.active_heating_extruders, ['extruder1', 'extruder']
        )
        self.assertEqual(self.power.pending_extruders, [])

    def test_power_budget_defers_cold_head_but_allows_already_hot_head(self):
        self.power.active_heating_extruders = ['extruder1']
        self.power.max_heating_extruders = 1
        self.assertEqual(self.execute(self.body())['reason'], 'power_budget')
        self.assert_no_heat()
        self.assertEqual(self.power.pending_extruders, [])
        self.heaters[0].smoothed_temp = 213
        self.assertTrue(self.execute(self.body(NONCE='d' * 32))['applied'])
        self.assertEqual(self.power.active_heating_extruders, ['extruder1'])
        self.assertEqual(self.power.pending_extruders, [])

    def test_zero_nonworking_and_invalid_requested_targets_never_heat(self):
        for value in [
            '0',
            '40',
            '169',
            '301',
            'nan',
            'inf',
            '215.1',
            '-1',
            True,
        ]:
            with self.subTest(value=value):
                result = self.execute(self.body(TARGET=value, NONCE='b' * 32))
                self.assertFalse(result['applied'])
                self.assert_no_heat()
        self.assertFalse(
            self.execute(self.body(EXPECTED='40', NONCE='c' * 32))['applied']
        )

    def test_malformed_protocol_is_rejected_without_heating(self):
        for update in [
            dict(TOOL='0'),
            dict(TOOL='5'),
            dict(JOB='x' * 64),
            dict(FILAMENT='f' * 63),
            dict(NONCE='n' * 32),
            dict(EXTRA='1'),
        ]:
            with self.subTest(update=update):
                self.assertFalse(self.execute(self.body(**update))['applied'])
        self.assert_no_heat()

    def test_identical_retry_returns_result_without_reapplying_after_pause(
        self,
    ):
        command = self.body()
        first = self.execute(command)
        self.pause.is_paused = True
        self.heaters[0].target_temp = 40
        replay = self.execute(command)
        self.assertTrue(replay.pop('replayed'))
        self.assertFalse(first.pop('replayed'))
        self.assertEqual(replay, first)
        self.assertEqual(self.heaters[0].writes, [215])
        self.assertEqual(self.heaters[0].target_temp, 40)

    def test_nonce_cannot_be_reused_for_a_different_command(self):
        command = self.body()
        self.execute(command)
        result = self.execute(dict(command, TARGET='220'))
        self.assertFalse(result['applied'])
        self.assertEqual(result['reason'], 'nonce_conflict')
        self.assertEqual(self.heaters[0].writes, [215])

    def test_already_matching_target_needs_no_heater_write(self):
        self.heaters[0].target_temp = 215
        result = self.execute(self.body())
        self.assertTrue(result['applied'])
        self.assertEqual(result['reason'], 'already_at_target')
        self.assert_no_heat()

    def test_nonce_cache_is_bounded_and_evicted_requests_are_rechecked(self):
        old = self.body()
        self.execute(old)
        for i in range(300):
            self.execute(self.body(NONCE=format(i, '032x')))
        self.assertLessEqual(len(self.guard.results), 256)
        self.pause.is_paused = True
        self.heaters[0].target_temp = 40
        self.assertFalse(self.execute(old)['applied'])
        self.assertEqual(self.heaters[0].writes, [215])

    def test_status_is_detached_from_internal_last_result(self):
        self.execute(self.body())
        returned = self.status()
        returned['last_result']['applied'] = False
        self.assertTrue(self.status()['last_result']['applied'])

    def test_each_physical_tool_requires_its_own_filament_and_active_identity(
        self,
    ):
        for index in range(4):
            with self.subTest(tool=index + 1):
                self.setUp()
                self.active = self.extruders[index]
                self.park_states = [
                    'ACTIVATE' if i == index else 'PARKED' for i in range(4)
                ]
                command = self.body(
                    TOOL=str(index + 1),
                    FILAMENT=self.status()['filament_tokens'][index],
                )
                self.assertTrue(self.execute(command)['applied'])
                self.assertEqual(self.heaters[index].writes, [215])
                self.assertEqual(sum(len(h.writes) for h in self.heaters), 1)

    def test_unknown_limits_or_temperature_and_shutdown_fail_closed(self):
        for field, value in [
            ('min_temp', None),
            ('max_temp', float('nan')),
            ('min_extrude_temp', None),
            ('target_temp', float('nan')),
            ('is_shutdown', True),
            ('is_shutdown', None),
        ]:
            with self.subTest(field=field):
                self.setUp()
                command = self.body()
                setattr(self.heaters[0], field, value)
                self.assertFalse(self.execute(command)['applied'])
                self.assert_no_heat()

    def test_native_setter_error_is_not_retried_and_admission_is_rolled_back(
        self,
    ):
        self.power.active_heating_extruders = []

        def fail(target):
            raise RuntimeError('synthetic setter failure')

        self.heaters[0].set_temp = fail
        command = self.body()
        with self.assertLogs(level='ERROR'):
            result = self.execute(command)
        self.assertEqual(result['reason'], 'native_state_or_setter_error')
        self.assertEqual(self.power.active_heating_extruders, [])
        self.heaters[0].set_temp = lambda target: self.heaters[
            0
        ].writes.append(target)
        self.assertFalse(self.execute(command)['applied'])
        self.assert_no_heat()

    def test_unseen_same_name_file_replacement_is_detected(
        self,
    ):
        command = self.body()
        # Intentionally no status read between replacement and execution.
        self.sd.current_file = SimpleNamespace(
            name=self.file.name, closed=False
        )
        self.assertEqual(
            self.execute(command)['reason'], 'job_changed_or_unknown'
        )
        self.assert_no_heat()

    def test_expected_target_must_match_unambiguous_native_print_parameters(
        self,
    ):
        for temps, mapping in [
            ([140, 210, 210, 210], [0, 1, 2, 3]),
            ([210, 220, 210, 210], [0, 0, 2, 3]),
            ([], [0, 1, 2, 3]),
            ([210, 210], None),
        ]:
            with self.subTest(temps=temps, mapping=mapping):
                self.setUp()
                command = self.body()
                self.config.print_task_config_2['nozzle_temp'] = temps
                self.inventory['extruder_map_table'] = mapping
                self.assertFalse(self.execute(command)['applied'])
                self.assert_no_heat()

    def test_one_application_per_policy_activation_even_with_a_fresh_nonce(
        self,
    ):
        self.execute(self.body())
        self.heaters[0].target_temp = 210
        result = self.execute(self.body(NONCE='c' * 32))
        self.assertFalse(result['applied'])
        self.assertEqual(result['reason'], 'activation_already_applied')
        self.assertEqual(self.heaters[0].target_temp, 210)
        self.assertEqual(self.heaters[0].writes, [215])
        self.assertTrue(
            self.execute(self.body(NONCE='d' * 32, POLICY='c' * 32))['applied']
        )

    def test_activation_and_resume_events_require_fresh_token(
        self,
    ):
        for event in ('extruder:activate_extruder', 'print_stats:start'):
            with self.subTest(event=event):
                self.setUp()
                old = self.body()
                self.execute(old)
                self.heaters[0].target_temp = 210
                self.callbacks[event]()
                self.assertNotEqual(
                    old['ACTIVATION'], self.status()['activation_token']
                )
                self.assertFalse(
                    self.execute(dict(old, NONCE='c' * 32))['applied']
                )
                self.assertTrue(
                    self.execute(self.body(NONCE='d' * 32))['applied']
                )
                self.assertEqual(self.heaters[0].writes, [215, 215])

    def test_observed_color_change_and_revert_does_not_restore_old_token(self):
        old = self.status()['filament_tokens']
        self.inventory['filament_color_rgba'][0] = 'FFFF00FF'
        self.status()
        self.inventory['filament_color_rgba'][0] = 'FF0000FF'
        new = self.status()['filament_tokens']
        self.assertNotEqual(old[0], new[0])
        self.assertEqual(old[1:], new[1:])

    def test_native_filament_events_revoke_only_affected_head(
        self,
    ):
        for event in ('filament_switch_sensor:runout', 'filament_feed:port'):
            with self.subTest(event=event):
                self.setUp()
                old = self.status()['filament_tokens']
                command = self.body()
                self.callbacks[event](0, False)
                self.callbacks[event](0, True)
                self.assertFalse(self.execute(command)['applied'])
                new = self.status()['filament_tokens']
                self.assertNotEqual(old[0], new[0])
                self.assertEqual(old[1:], new[1:])
                self.assert_no_heat()

    def test_missing_disabled_or_unknown_sensor_cannot_prove_filament_presence(
        self,
    ):
        for mode in ('missing', 'disabled', 'unknown'):
            with self.subTest(mode=mode):
                self.setUp()
                before = self.status()['filament_tokens']
                command = self.body()
                if mode == 'missing':
                    self.objects.pop('filament_motion_sensor e0_filament')
                else:
                    self.sensors[0]['enabled'] = (
                        False if mode == 'disabled' else None
                    )
                after = self.status()['filament_tokens']
                self.assertIsNone(after[0])
                self.assertEqual(before[1:], after[1:])
                self.assertFalse(self.execute(command)['applied'])
                self.assert_no_heat()

    def test_park_keeps_active_pointer_but_cannot_heat_even_with_a_new_policy(
        self,
    ):
        self.execute(self.body())
        self.heaters[0].writes.clear()
        self.heaters[0].target_temp = 210
        queued = self.body(NONCE='c' * 32, POLICY='d' * 32)
        self.grab_complete = False
        self.park_states[0] = 'PARKED'
        self.assertEqual(self.active, self.extruders[0])
        self.assertFalse(self.execute(queued)['applied'])
        self.assert_no_heat()

    def test_physical_activation_unknown_or_ambiguous_fails_closed(self):
        for grab, states in [
            (None, ['ACTIVATE', 'PARKED', 'PARKED', 'PARKED']),
            (False, ['ACTIVATE', 'PARKED', 'PARKED', 'PARKED']),
            (True, ['PARKED', 'PARKED', 'PARKED', 'PARKED']),
            (True, ['UNKNOWN', 'PARKED', 'PARKED', 'PARKED']),
            (True, ['ACTIVATE', 'ACTIVATE', 'PARKED', 'PARKED']),
        ]:
            with self.subTest(grab=grab, states=states):
                self.setUp()
                queued = self.body()
                self.grab_complete, self.park_states = grab, states
                self.assertFalse(self.execute(queued)['applied'])
                self.assert_no_heat()
        self.setUp()
        queued = self.body()
        self.extruders[0].get_park_detector_status = lambda: None
        self.assertFalse(self.execute(queued)['applied'])
        self.assert_no_heat()
