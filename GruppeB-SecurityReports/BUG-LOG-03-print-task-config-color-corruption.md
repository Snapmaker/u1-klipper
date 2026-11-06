# BUG-LOG-03: 8-Digit RGBA String Corrupting `print_task.json` on Reboot

## Summary
Two configuration schema discrepancies in `klippy/extras/print_task_config.py` caused persistent state corruption and ineffective preference settings:
1. In `set_filament_slot()`, `dest_filament_color_multi['colors'] = [dest_filament_color_rgba]` stored an 8-digit hex string (e.g. `RRGGBBAA`) into `print_task.json`. On subsequent daemon restarts, `_early_check()` evaluated `len(tmp_print_task_config['filament_color_multi'][i]['colors'][j]) != 6` (which requires strictly 6-digit `RRGGBB` strings) and raised `ValueError("print_task_config invalid")`. This caused Klippy to flag `print_task.json` as corrupt and reset the configuration file back to factory defaults on every reboot.
2. In `cmd_SET_PRINT_PREFERENCES()`, the parser initialized `tmp_print_task_config['flow_calibrate_extruders']` rather than `flow_calib_extruders`, causing key mismatches with `DEFAULT_PRINT_TASK_CONFIG` and leaving per-extruder flow calibration settings unpersisted.

## Component / Affected Files
- **File:** `klippy/extras/print_task_config.py`
  - **Affected Methods:** `set_filament_slot()`, `cmd_SET_PRINT_PREFERENCES()`
  - **Lines:** 685-695, 750-760

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Host Python
- **Severity:** Critical (Persistent State Corruption / Automatic Factory Reset of `print_task.json`)

## Root Cause Analysis
1. **RGBA vs RGB Length Mismatch:**
   In `set_filament_slot()`:
   ```python
   dest_filament_color_rgba = f'{red:02X}' + f'{green:02X}' + f'{blue:02X}' + f'{alpha:02X}'
   dest_filament_color_multi['nums'] = 1
   dest_filament_color_multi['alpha'] = alpha
   dest_filament_color_multi['colors'] = [dest_filament_color_rgba]
   ```
   `dest_filament_color_rgba` is an 8-character hex string representing RGBA. However, `_early_check()` validates multi-color arrays using:
   ```python
   for j in range(tmp_print_task_config['filament_color_multi'][i]['nums']):
       if not isinstance(tmp_print_task_config['filament_color_multi'][i]['colors'][j], str) or \
                   len(tmp_print_task_config['filament_color_multi'][i]['colors'][j]) != 6:
           raise ValueError(f"print_task_config invalid")
   ```
   Because length was 8 instead of 6, `_early_check()` failed during Klippy initialization.
2. **Key Name Inconsistency:**
   The standard configuration dictionary specifies `flow_calib_extruders`. In `cmd_SET_PRINT_PREFERENCES()`, the code initialized `tmp_print_task_config['flow_calibrate_extruders']`, resulting in a phantom key that did not update the real extruder list in `reprint_info`.

## Steps to Reproduce
1. Configure filament color using:
   ```gcode
   SET_PRINT_FILAMENT_CONFIG CONFIG_EXTRUDER=0 FILAMENT_COLOR=4279312179 FORCE=1
   ```
2. Restart Klippy daemon.
3. Observe Klippy logging `config file not exits: /root/print_task_2.json` / `[print_task_config] reset print info` because `_early_check()` rejected the saved configuration file.

## Proposed Fix / Patch
```diff
diff --git a/klippy/extras/print_task_config.py b/klippy/extras/print_task_config.py
--- a/klippy/extras/print_task_config.py
+++ b/klippy/extras/print_task_config.py
@@ -690,1 +690,1 @@ class PrintTaskConfig:
-                    dest_filament_color_multi['colors'] = [dest_filament_color_rgba]
+                    dest_filament_color_multi['colors'] = [dest_filament_color_rgba[0:6]]
@@ -750,2 +750,2 @@ class PrintTaskConfig:
-                tmp_print_task_config['flow_calibrate_extruders'] = [True for i in range(PHYSICAL_EXTRUDER_NUM)]
-                tmp_print_task_config['reprint_info'].update({'flow_calibrate_extruders': [True for i in range(PHYSICAL_EXTRUDER_NUM)]})
+                tmp_print_task_config['flow_calib_extruders'] = [True for i in range(PHYSICAL_EXTRUDER_NUM)]
+                tmp_print_task_config['reprint_info'].update({'flow_calib_extruders': [True for i in range(PHYSICAL_EXTRUDER_NUM)]})
```

## Regression & Safety Verification
- **Unit Tests:** `test/test_bug_log03_print_task_config.py` executed:
  - `test_filament_color_rgb_length`: Verified `colors[0]` string length is 6 and passes `_early_check()` validation.
  - `test_flow_calib_extruders_key`: Verified key `flow_calib_extruders` is updated without polluting config schema.
  - Result: `Ran 2 tests in 0.000s OK`.
- **Klippy Batch Simulation:** Executed `test/klippy/bug_log03_print_task_config.test`:
  ```
  Starting test/klippy/bug_log03_print_task_config.test (bug_log03_print_task_config.cfg)
  All 1 test cases passed
  ```
- **Whitespace Check:** `scripts/check_whitespace.py` passed with 0 errors.

