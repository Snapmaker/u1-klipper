# Guarded change of one extruder's working temperature during a print
#
# Copyright (C) 2026  Gilberto Moraes
#                     <7747175+MoraesGil@users.noreply.github.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# Opt-in module. An external client (a print farm manager, a dashboard)
# asks for a new working temperature of one physical extruder; the change
# is applied only if, at execution time, the job, the filament, the active
# head and the firmware state are still those the client observed. Every
# check and the heater write run synchronously in one reactor turn: no
# run_script, no reactor pause, no lookahead callback and no queued
# heating. It never wraps M104/M109 and never changes the native pause or
# standby program; a later native command can still change the target.
#
# The private interfaces used here were inspected at U1 firmware 1.6.0.
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
import logging
import math
import re
import secrets

EXTRUDERS = ('extruder', 'extruder1', 'extruder2', 'extruder3')
FIELDS = frozenset(('TOOL', 'TARGET', 'EXPECTED', 'JOB', 'FILAMENT',
                    'NONCE', 'ACTIVATION', 'POLICY'))
HEX_FIELDS = (('JOB', 64), ('FILAMENT', 64), ('NONCE', 32),
              ('ACTIVATION', 64), ('POLICY', 32))
FILAMENT_EXTRA = ('filament_color_multi', 'filament_vendor',
                  'filament_sub_type', 'filament_sku', 'filament_official')
MAX_RESULTS = 256

def finite(value):
    return type(value) in (int, float) and math.isfinite(value)

def digest(value):
    data = json.dumps(value, sort_keys=True, separators=(',', ':'),
                      allow_nan=False)
    return hashlib.sha256(data.encode('utf-8')).hexdigest()

class PrintTemperatureGuard:
    def __init__(self, config):
        self.printer = config.get_printer()
        # TARGET may differ from the print's own temperature by max_delta at
        # most, and stays max_temp_margin below the heater's max_temp (the
        # shutdown threshold sits just above max_temp).
        self.max_delta = config.getfloat('max_delta', 30., minval=0.)
        self.max_temp_margin = config.getfloat('max_temp_margin', 10.,
                                               minval=0.)
        self.boot = secrets.token_hex(32)
        self.generation = 0
        self.file = self.identity = self.job_token = None
        self.activation_generation = 0
        self.active = None
        self.applied_policies = set()
        self.filament_generations = [0] * 4
        self.filament_signatures = [None] * 4
        self.last_result = None
        self.results = OrderedDict()
        self.status_failing = False
        handlers = (('print_stats:new_task_start', self._new_job),
                    ('print_stats:stop', self._new_job),
                    ('print_stats:start', self._new_activation),
                    ('extruder:activate_extruder', self._new_activation),
                    ('filament_switch_sensor:runout', self._filament_event),
                    ('filament_feed:port', self._filament_event))
        for event, handler in handlers:
            self.printer.register_event_handler(event, handler)
        gcode = self.printer.lookup_object('gcode')
        gcode.register_command(
            'SET_GUARDED_PRINT_TEMPERATURE',
            self.cmd_SET_GUARDED_PRINT_TEMPERATURE,
            desc=self.cmd_SET_GUARDED_PRINT_TEMPERATURE_help)
    def _new_job(self, *args):
        self.generation += 1
        self.file = self.identity = self.job_token = None
        self._new_activation()
    def _new_activation(self, *args):
        self.activation_generation += 1
        self.active = None
        self.applied_policies.clear()
    def _activation(self):
        toolhead = self.printer.lookup_object('toolhead', None)
        active = toolhead.get_extruder() if toolhead is not None else None
        if (self.job_token is None or active is None
                or active.get_name() not in EXTRUDERS):
            return None
        if self.active is not active:
            self._new_activation()
            self.active = active
        return digest((self.boot, self.job_token, self.activation_generation,
                       active.get_name()))
    def _filament_event(self, index=None, present=None, *args):
        # Both native events carry the physical zero-based extruder index.
        # Invalidate even if no client observed an unload followed by reload.
        indices = (index,) if type(index) is int and 0 <= index <= 3 \
            else range(4)
        for slot in indices:
            self.filament_generations[slot] += 1
    def _job(self):
        stats = self.printer.lookup_object('print_stats', None)
        sd = self.printer.lookup_object('virtual_sdcard', None)
        current = getattr(sd, 'current_file', None)
        filename = getattr(stats, 'filename', None)
        start = getattr(stats, 'print_start_time', None)
        # virtual_sdcard holds an AsyncFileReader, which only exposes the
        # private _closed flag; a plain file object exposes closed.
        closed = getattr(current, 'closed', getattr(current, '_closed', None))
        if (getattr(stats, 'state', None) not in ('printing', 'paused')
                or not isinstance(filename, str) or not filename
                or not finite(start) or current is None
                or closed is not False):
            if self.identity is not None:
                self._new_job()
            return None
        identity = (start, filename, getattr(current, 'name', None))
        if not isinstance(identity[2], str) or not identity[2]:
            self._new_job()
            return None
        # Keep the file object itself, so an address cannot be recycled
        # between unobserved same-filename jobs. new_task_start covers reuse.
        if self.file is not current or self.identity != identity:
            self.generation += 1
            self._new_activation()
            self.file, self.identity = current, identity
            self.job_token = digest((self.boot, self.generation, identity))
        return self.job_token
    def _filament_raw(self, eventtime):
        signatures = [None] * 4
        config = self.printer.lookup_object('print_task_config', None)
        if config is None:
            return signatures
        try:
            # Native get_status refreshes presence from the filament sensors
            # without I/O or yield; the stored config alone may be stale.
            inventory = config.get_status(eventtime)
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            return signatures
        for index in range(4):
            try:
                sensor = self.printer.lookup_object(
                    'filament_motion_sensor e%d_filament' % (index,), None)
                # The inventory defaults to present when this sensor is
                # missing or disabled; that default cannot authorize a change.
                if (sensor is None or
                        sensor.get_status(eventtime).get('enabled')
                        is not True):
                    continue
                raw = {key: inventory[key][index] for key in (
                    'filament_exist', 'filament_color_rgba', 'filament_type')}
                color = raw['filament_color_rgba']
                material = raw['filament_type']
                if (raw['filament_exist'] is not True
                        or not isinstance(color, str)
                        or not re.fullmatch(r'[0-9A-Fa-f]{8}', color)
                        or not isinstance(material, str)
                        or material.strip().upper() in (
                            '', 'NONE', 'UNKNOWN')):
                    continue
                for key in FILAMENT_EXTRA:
                    raw[key] = inventory[key][index] \
                        if key in inventory else None
                signatures[index] = digest(raw)
            except (AttributeError, IndexError, KeyError, TypeError,
                    ValueError):
                continue  # A malformed slot never invalidates other heads.
        return signatures
    def _filaments(self, eventtime):
        signatures = self._filament_raw(eventtime)
        result = []
        for index, signature in enumerate(signatures):
            if signature != self.filament_signatures[index]:
                self.filament_generations[index] += 1
                self.filament_signatures[index] = signature
            token = None
            if signature is not None:
                token = digest((self.boot, index,
                                self.filament_generations[index], signature))
            result.append(token)
        return result
    def get_status(self, eventtime):
        # Polled by status subscriptions: an exception here would shut the
        # printer down, so any unexpected native state yields null tokens.
        try:
            job_token = self._job()
            activation = self._activation()
            filaments = self._filaments(eventtime)
            self.status_failing = False
        except Exception:
            if not self.status_failing:  # Log once, not on every poll
                logging.exception("print_temperature_guard: status error")
            self.status_failing = True
            job_token = activation = None
            filaments = [None] * 4
        return {'protocol': 1,
                'implementation': 'u1-print-temperature-guard-v1',
                'job_token': job_token,
                'activation_token': activation,
                'filament_tokens': filaments,
                'last_result': deepcopy(self.last_result)}
    @staticmethod
    def _parse(params):
        if set(params) != FIELDS:
            raise ValueError('invalid_parameters')
        for key, length in HEX_FIELDS:
            value = params[key]
            if (not isinstance(value, str)
                    or not re.fullmatch('[0-9a-f]{%d}' % (length,), value)):
                raise ValueError('invalid_parameters')
        parsed = dict(params)
        for key in ('TOOL', 'TARGET', 'EXPECTED'):
            value = params[key]
            if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,5}',
                                                              value):
                raise ValueError('invalid_parameters')
            parsed[key] = int(value)
        if not 1 <= parsed['TOOL'] <= 4:
            raise ValueError('invalid_parameters')
        return parsed
    def _check_firmware(self):
        stats = self.printer.lookup_object('print_stats', None)
        pause = self.printer.lookup_object('pause_resume', None)
        sd = self.printer.lookup_object('virtual_sdcard', None)
        exceptions = self.printer.lookup_object('exception_manager', None)
        machine = self.printer.lookup_object('machine_state_manager', None)
        config = self.printer.lookup_object('print_task_config', None)
        is_active = getattr(sd, 'is_active', None)
        if (getattr(stats, 'state', None) != 'printing'
                or not callable(is_active) or is_active() is not True):
            return 'print_not_running'
        if getattr(config, 'is_exec_print_end_action', None) is not False:
            return 'print_ending_or_unknown'
        # A pause already requested but not yet reached counts as paused.
        if (getattr(pause, 'is_paused', None) is not False
                or getattr(pause, 'pause_command_sent', None) is not False
                or getattr(sd, 'must_pause_work', None) is not False):
            return 'paused_or_unknown'
        if self.printer.get_state_message()[1] != 'ready':
            return 'firmware_not_ready'
        fault = getattr(stats, 'exception_details', None)
        clean_fault = (isinstance(fault, dict) and not fault.get('message')
                       and all(fault.get(k, 0) == 0
                               for k in ('id', 'index', 'code', 'level')))
        if (getattr(exceptions, 'exceptions', None) != []
                or getattr(exceptions, 'async_exceptions', None) != []
                or not clean_fault
                or getattr(stats, 'error_message', None) != ''):
            return 'firmware_exception_or_unknown'
        main = getattr(machine, 'main_state', None)
        action = getattr(machine, 'action_code', None)
        if (type(main) is bool or type(action) is bool
                or main not in (1, 'PRINTING') or action not in (0, 'IDLE')):
            return 'firmware_busy_or_unknown'
        return None
    def _check_head(self, index):
        toolhead = self.printer.lookup_object('toolhead', None)
        extruder = self.printer.lookup_object(EXTRUDERS[index], None)
        if (toolhead is None or extruder is None
                or toolhead.get_extruder() is not extruder
                or extruder.get_name() != EXTRUDERS[index]):
            return 'toolhead_inactive'
        # PARK_EXTRUDER can keep the logical active pointer. Require the
        # completed grab and a unique physically active head, using only
        # the cached detector accessors.
        grab = getattr(toolhead, 'get_grab_complete', None)
        if not callable(grab) or grab() is not True:
            return 'toolhead_not_physically_active'
        for slot, name in enumerate(EXTRUDERS):
            physical = self.printer.lookup_object(name, None)
            detector = getattr(physical, 'get_park_detector_status', None)
            detected = detector() if callable(detector) else None
            required = 'ACTIVATE' if slot == index else 'PARKED'
            if (not isinstance(detected, dict)
                    or detected.get('state') != required):
                return 'toolhead_not_physically_active'
        return None
    def _check_temperatures(self, index, heater, command, eventtime):
        target, expected = command['TARGET'], command['EXPECTED']
        low, high, extrusion = (getattr(heater, k, None) for k in (
            'min_temp', 'max_temp', 'min_extrude_temp'))
        if (not all(finite(v) for v in (low, high, extrusion))
                or low > extrusion or extrusion > high
                or not max(1, low, extrusion) <= expected <= high
                or not max(1, low, extrusion) <= target
                or target > high - self.max_temp_margin
                or abs(target - expected) > self.max_delta):
            return 'temperature_out_of_bounds'
        config = self.printer.lookup_object('print_task_config', None)
        settings = getattr(config, 'print_task_config_2', None)
        values = settings.get('nozzle_temp') \
            if isinstance(settings, dict) else None
        inventory = config.get_status(eventtime) if config is not None else {}
        mapping = inventory.get('extruder_map_table')
        if (not isinstance(values, list) or not 1 <= len(values) <= 64
                or not isinstance(mapping, list)
                or not len(values) <= len(mapping) <= 64
                or any(type(item) is not int or not 0 <= item <= 3
                       for item in mapping)
                or any(not finite(value) or value < 0 for value in values)):
            return 'native_working_target_unknown'
        native_targets = {value for i, value in enumerate(values)
                          if mapping[i] == index and value > 0}
        if native_targets != {expected}:
            return 'native_working_target_mismatch'
        current = getattr(heater, 'target_temp', None)
        if (not finite(current) or current <= 0
                or current not in (expected, target)):
            return 'standby_or_other_firmware_target'
        return None
    def _check(self, command, eventtime):
        if self._job() != command['JOB']:
            return 'job_changed_or_unknown', None
        if self._activation() != command['ACTIVATION']:
            return 'activation_changed_or_unknown', None
        if command['POLICY'] in self.applied_policies:
            return 'activation_already_applied', None
        if len(self.applied_policies) >= MAX_RESULTS:
            return 'activation_policy_capacity', None
        index = command['TOOL'] - 1
        if self._filaments(eventtime)[index] != command['FILAMENT']:
            return 'filament_changed_or_unknown', None
        reason = self._check_firmware() or self._check_head(index)
        if reason is not None:
            return reason, None
        heater = self.printer.lookup_object(EXTRUDERS[index]).get_heater()
        if (heater.get_name() != EXTRUDERS[index]
                or getattr(heater, 'is_shutdown', None) is not False):
            return 'heater_unavailable', None
        reason = self._check_temperatures(index, heater, command, eventtime)
        if reason is not None:
            return reason, None
        heaters = self.printer.lookup_object('heaters', None)
        pending = getattr(heaters, 'is_extruder_pending', None)
        if not callable(pending) or pending(EXTRUDERS[index]) is not False:
            # A queued native target would replace this one shortly.
            return 'power_budget', None
        if heater.target_temp == command['TARGET']:
            return 'already_at_target', None
        return None, heater
    def _apply(self, heater, target):
        # The native concurrent heating budget decides, without queueing.
        heaters = self.printer.lookup_object('heaters', None)
        apply = getattr(heaters, 'try_set_extruder_temperature', None)
        if not callable(apply):
            return 'power_state_unknown'
        if apply(heater, float(target)) is not True:
            return 'power_budget'
        return None
    cmd_SET_GUARDED_PRINT_TEMPERATURE_help = (
        "Set one extruder's working temperature only if the observed print"
        " state still holds")
    def cmd_SET_GUARDED_PRINT_TEMPERATURE(self, gcmd):
        params = gcmd.get_command_parameters()
        nonce = params.get('NONCE')
        if not isinstance(nonce, str) or not re.fullmatch('[0-9a-f]{32}',
                                                          nonce):
            nonce = None  # Only a well-formed nonce is echoed back.
        result = {'nonce': nonce, 'applied': False, 'replayed': False,
                  'reason': 'invalid_parameters', 'toolhead': None,
                  'target': None}
        try:
            # The parser keeps the last of repeated parameters and strips
            # quotes: refuse both, so each parameter is the one written.
            line = gcmd.get_commandline()
            keys = re.findall(r'(?:^|\s)([A-Za-z_][A-Za-z0-9_]*)=', line)
            if ('"' in line or "'" in line
                    or len(keys) != len(set(key.upper() for key in keys))):
                raise ValueError('invalid_parameters')
            command = self._parse(params)
        except ValueError:
            self.last_result = result
            gcmd.respond_info(json.dumps(result, sort_keys=True))
            return
        result.update(nonce=command['NONCE'], toolhead=command['TOOL'],
                      target=command['TARGET'])
        nonce = command['NONCE']
        prior = self.results.get(nonce)
        if prior is not None:
            if prior[0] == command:
                result = deepcopy(prior[1])
                result['replayed'] = True
            else:
                result['reason'] = 'nonce_conflict'
        else:
            try:
                # Every accessor and set_temp below is synchronous. Never
                # add run_script, a reactor pause, lookahead callbacks, disk
                # writes or queued heating here.
                eventtime = self.printer.get_reactor().monotonic()
                reason, heater = self._check(command, eventtime)
                if reason is None:
                    reason = self._apply(heater, command['TARGET'])
                if reason is None:
                    result.update(applied=True, reason='applied')
                else:
                    result.update(applied=reason == 'already_at_target',
                                  reason=reason)
                if result['applied']:
                    self.applied_policies.add(command['POLICY'])
            except Exception:
                # An unknown native interface or setter outcome is reported,
                # never retried.
                logging.exception("print_temperature_guard: native state or"
                                  " setter error")
                result['reason'] = 'native_state_or_setter_error'
            self.results[nonce] = (command, deepcopy(result))
            if len(self.results) > MAX_RESULTS:
                self.results.popitem(last=False)
        self.last_result = result
        # Respond only after the guarded section; transports may yield here.
        gcmd.respond_info(json.dumps(result, sort_keys=True))

def load_config(config):
    return PrintTemperatureGuard(config)
