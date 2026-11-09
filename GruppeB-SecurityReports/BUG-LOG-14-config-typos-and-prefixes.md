# BUG-LOG-14: Configuration Key Typos, Missing Section Prefixes, and Overridden MQTT QoS 0

## Summary
Across three modules in `klippy/extras/`, configuration resolution and parameter handling contained defects:
1. In `extruder_calibration.py`, `_probe_mode` was queried without the `section +` prefix, and `self.extruder_y_cal_second_positions` was misspelled as `posiions` (missing `t`), leading to `KeyError` when Y calibration was enabled.
2. In `filament_entangle_detect.py`, `feed_module_status[self.extruder_name + "0"]` was used when `self.extruder_index == 0`. When `self.extruder_name` was configured as `'extruder0'`, this generated `'extruder00'`, causing status lookup failures.
3. In `mqtt.py`, `qos = qos or self.qos` in `subscribe_topic()` and `publish_topic()` evaluated `0` as falsy, overriding explicit `qos=0` requests with `self.qos` (typically `1`).

## Component / Affected Files
- **Files:**
  - `klippy/extras/extruder_calibration.py` (lines 27, 79, 85, 224)
  - `klippy/extras/filament_entangle_detect.py` (lines 147-151)
  - `klippy/extras/mqtt.py` (lines 168, 225)

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Firmware
- **Severity:** High (`KeyError` during calibration, status lookup failures & protocol QoS violations)

## Root Cause Analysis
1. **Missing Section Prefix and Typo in Extruder Calibration:**
   `config.getint('_probe_mode', ...)` failed to prepend `section +` like neighboring parameters (`section + '_probe_dist'`, etc.). In addition, `extruder_y_cal_second_posiions` omitted the letter `t`, and accessing it without a key existence check triggered runtime `KeyError`.
2. **Key Synthesis Bug in Entangle Detection:**
   Assuming `self.extruder_name` always lacks a numerical suffix resulted in appending `"0"` to an already numbered name (`'extruder0' + '0' -> 'extruder00'`).
3. **Falsy QoS 0 Bug in MQTT Client:**
   In Python, `0 or 1` yields `1`. An explicit argument `qos=0` was discarded in favor of default `self.qos`.

## Steps to Reproduce
1. In `extruder_calibration.py`, configure Y calibration and observe `KeyError: 'extruder'`.
2. In `filament_entangle_detect.py`, configure `extruder = extruder0` and observe failed module status resolution.
3. In `mqtt.py`, call `publish_topic("test", "msg", qos=0)` with `self.qos = 1`; observe outgoing packet published with QoS 1 instead of 0.

## Proposed Fix / Patch
1. Correct `section + '_probe_mode'` and rename `extruder_y_cal_second_posiions` to `extruder_y_cal_second_positions` with key membership check in `extruder_calibration.py`.
2. Resolve entangle detection status key using `f"extruder{self.extruder_index}"` with fallback to `self.extruder_name`.
3. Use `qos = self.qos if qos is None else qos` in `mqtt.py`.

## Regression & Safety Verification
- **Automated Unit Tests:**
  - `test/test_bug_log14.py`: Verified `MQTTClient` QoS 0 preservation on publish/subscribe, verified `FilamentEntangleDetect` key resolution for `extruder0`, and verified `ExtruderParkCalibration` dictionary structure.
- **Whitespace Compliance:** Verified with `scripts/check_whitespace.py` (0 errors).
- **Regression:** Verified calibration routines, entanglement monitoring, and MQTT message dispatching remain operational.

