# BUG-NULL-06: Unhandled `NoneType` Dereferences Across Host Modules

## Summary
In multiple Snapmaker proprietary and host modules, unhandled `NoneType` references triggered fatal exceptions (`TypeError` or `AttributeError`), crashing the Klippy host daemon during error handling, temperature queries, calibration, and peripheral event handling:
1. `klippy/klippy.py`: `_handle_exception()` called `parsed_structured_code.get(...)` without checking whether `_parse_structured_code()` returned `None`, raising `AttributeError`.
2. `klippy/kinematics/extruder.py`: `cmd_MOVE_TO_XY_IDLE_POSITION()` accessed `current_extruder.xy_park_position[0]` and `current_extruder.y_idle_position` without verifying whether they were configured (`is not None`), raising `TypeError: 'NoneType' object is not subscriptable`.
3. `klippy/extras/probe_inductance_coil.py`: `_get_filament_temp()` and `_get_filament_soft()` accessed `status['filament_vendor'][extruder]` without checking `extruder is not None` or validating index bounds, causing `TypeError` or `IndexError`.
4. `klippy/extras/extruder_calibration.py`: `get_analog_output()` multiplied `last_adc_value * 3.3 * 1.5` and `cmd_CALIBRATE_EXTRUDER_PARK_POSITION()` formatted `"%.3f" % point2_voltage` when no ADC sample was available (`None`), raising `TypeError`.
5. `klippy/extras/filament_feed.py`: Unchecked accesses to `self.filament_detect.is_startup_stay()` and `self.runout_sensor[ch].get_status(0)` crashed when optional sensors or modules were omitted or uninitialized.
6. `klippy/extras/error_mcu.py`: `if "Protocol error" in msg:` raised `TypeError: argument of type 'NoneType' is not iterable` when `msg is None`.
7. `klippy/extras/park_detector.py`: `last_adc_value * 3.3` in `get_park_detector_adc_value()` raised `TypeError` when `last_adc_value` was uninitialized (`None`).

## Component / Affected Files
- `klippy/klippy.py`: Lines 277-285
- `klippy/kinematics/extruder.py`: Lines 1845-1860
- `klippy/extras/probe_inductance_coil.py`: Lines 1450-1490
- `klippy/extras/extruder_calibration.py`: Lines 230-240, 398-404
- `klippy/extras/filament_feed.py`: Lines 401-410, 584-592, 645-650, 832-836, 855-885, 1005-1040
- `klippy/extras/error_mcu.py`: Lines 170-176
- `klippy/extras/park_detector.py`: Lines 87-94

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Host Python
- **Severity:** High (Klippy daemon crash during exception recovery, probing, and calibration)

## Root Cause Analysis
Python functions that return `None` on failure or uninitialized objects were assumed to always return valid objects, dictionaries, lists, or numbers. When optional features or error branches were executed, methods like `.get()`, array subscripts `[...]`, numerical operations `*`, and string formatters `%.3f` were invoked directly on `None`, producing unhandled Python runtime exceptions that aborted the print job or prevented daemon recovery.

## Steps to Reproduce
1. In `klippy.py`: Invoke exception handling with a malformed structured error string where `_parse_structured_code()` yields `None`. Klippy crashes with `AttributeError`.
2. In `extruder.py`: Execute `MOVE_TO_XY_IDLE_POSITION_EXTRUDER` when `xy_park_position` is unconfigured. Klippy crashes with `TypeError`.
3. In `probe_inductance_coil.py`: Call `_get_filament_temp(None)`. Crashes with `TypeError: list indices must be integers or slices, not NoneType`.
4. In `error_mcu.py`: Notify MCU error with `msg=None`. Crashes with `TypeError`.

## Proposed Fix / Patch
1. In `klippy/klippy.py`: Add `if parsed_structured_code is not None:` before extracting fields.
2. In `klippy/kinematics/extruder.py`: Validate `hasattr(current_extruder, 'xy_park_position')` and `is not None` before accessing park coordinates.
3. In `klippy/extras/probe_inductance_coil.py`: Guard against non-integer, negative, or `None` extruder indices and bounds check vendor and type lists.
4. In `klippy/extras/extruder_calibration.py`: Check `last_adc_value is not None` before floating point calculations and format `v_str` defensively.
5. In `klippy/extras/filament_feed.py`: Introduce `_get_runout_detected(ch)` helper with bounds checks and `is not None` guards.
6. In `klippy/extras/error_mcu.py`: Check `if msg and "Protocol error" in msg:`.
7. In `klippy/extras/park_detector.py`: Guard `last_adc_value is not None` before computing voltage.

## Regression & Safety Verification
- **Unit Tests:** `test/test_bug_null06.py` executed:
  - `test_klippy_parsed_structured_code_none`: Passed.
  - `test_extruder_xy_park_position_none`: Passed.
  - `test_probe_filament_temp_none`: Passed.
  - `test_extruder_calibration_analog_output_none`: Passed.
  - `test_filament_feed_runout_none`: Passed.
  - `test_error_mcu_msg_none`: Passed.
  - `test_park_detector_adc_none`: Passed.
  - Result: `Ran 7 tests in 0.000s OK`.
- **Klippy Batch Simulation:** Executed `test/klippy/bug_null06_extruder.test`:
  ```
  Starting test/klippy/bug_null06_extruder.test (bug_null06_extruder.cfg)
  All 1 test cases passed
  ```
- **Whitespace Check:** `scripts/check_whitespace.py` passed with 0 errors.

