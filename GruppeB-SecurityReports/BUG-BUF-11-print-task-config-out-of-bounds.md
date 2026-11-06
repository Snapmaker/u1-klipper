# BUG-BUF-11: Out-of-Bounds List Indexing in `klippy/extras/print_task_config.py`

## Summary
In `klippy/extras/print_task_config.py`, several commands and verification loops indexed lists without verifying that indices fall within `[0, PHYSICAL_EXTRUDER_NUM)` or `[0, LOGICAL_EXTRUDER_NUM)`:
1. `cmd_SET_PRINT_USED_EXTRUDERS`: parsed comma-separated integers from `EXTRUDERS` and indexed `tmp_extruders_used[used_extruders[i]]` directly, causing `IndexError: list assignment index out of range` or unintended negative index writes when index `>= PHYSICAL_EXTRUDER_NUM` (4) or `< 0`.
2. `cmd_SETUP_PRINT_TASK_CONFIG`: in `map_table` and `flow_calibrate_extruders` parsing, only upper bounds were checked, permitting negative values to write corrupt state via negative list indexing.
3. `cmd_SETUP_PRINT_TASK_CONFIG`: the nozzle diameter verification loop hardcoded index `0` (`tmp_print_task_config_2['nozzle_diameter'][0]`) when checking all physical extruders `i`, comparing every extruder against extruder 0's nozzle diameter rather than its own (`[i]`).

## Component / Affected Files
- **File:** `klippy/extras/print_task_config.py`
  - **Affected Methods:** `cmd_SET_PRINT_USED_EXTRUDERS()`, `cmd_SETUP_PRINT_TASK_CONFIG()`
  - **Lines:** 830-840, 1190-1200, 1215-1225, 1415-1425

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Host Python
- **Severity:** High (Crash / Denial of Service / False Print Abort due to Nozzle Diameter Mismatch)

## Root Cause Analysis
1. In `cmd_SET_PRINT_USED_EXTRUDERS()`, `used_extruders = [int(value) for value in extruders_str.split(',')]` did not validate whether `0 <= value < PHYSICAL_EXTRUDER_NUM`. Any value >= 4 immediately triggered an unhandled `IndexError`, aborting print task preparation.
2. In `cmd_SETUP_PRINT_TASK_CONFIG()`, `map_table_list[i][0] >= LOGICAL_EXTRUDER_NUM or map_table_list[i][1] >= PHYSICAL_EXTRUDER_NUM` omitted checks for negative values (`< 0`).
3. In `cmd_SETUP_PRINT_TASK_CONFIG()`, line 1419 checked `abs(tmp_print_task_config_2['nozzle_diameter'][0] - actual_nozzle_diameter[i]) > 0.001` with hardcoded index `[0]`. In multi-tool configurations with mixed nozzle sizes (e.g. E0=0.4 mm, E1=0.6 mm), extruder 1 was erroneously validated against extruder 0's sliced diameter, throwing a false `nozzle diameter mismatch` exception.

## Steps to Reproduce
1. Execute:
   ```gcode
   SET_PRINT_USED_EXTRUDERS EXTRUDERS=0,5
   ```
2. Observe unhandled `IndexError: list assignment index out of range`.
3. In multi-nozzle print with E0=0.4 and E1=0.6, observe erroneous task abort during `SETUP_PRINT_TASK_CONFIG`.

## Proposed Fix / Patch
```diff
diff --git a/klippy/extras/print_task_config.py b/klippy/extras/print_task_config.py
--- a/klippy/extras/print_task_config.py
+++ b/klippy/extras/print_task_config.py
@@ -834,4 +834,6 @@ class PrintTaskConfig:
                 for i in range(min(len(used_extruders), LOGICAL_EXTRUDER_NUM)):
-                    tmp_extruders_used[used_extruders[i]] = True
-                    tmp_reprint_info['extruders_used'][used_extruders[i]] = True
+                    idx = used_extruders[i]
+                    if not (0 <= idx < PHYSICAL_EXTRUDER_NUM):
+                        raise gcmd.error(f"[print_task_config] Invalid extruder index: {idx}")
+                    tmp_extruders_used[idx] = True
+                    tmp_reprint_info['extruders_used'][idx] = True
@@ -1192,2 +1194,3 @@ class PrintTaskConfig:
-                        if map_table_list[i][0] >= LOGICAL_EXTRUDER_NUM or map_table_list[i][1] >= PHYSICAL_EXTRUDER_NUM:
+                        if not (0 <= map_table_list[i][0] < LOGICAL_EXTRUDER_NUM and
+                                0 <= map_table_list[i][1] < PHYSICAL_EXTRUDER_NUM):
                             raise gcmd.error("[print_task_config] Invalid MAP_TABLE")
@@ -1216,2 +1219,2 @@ class PrintTaskConfig:
-                    if flow_calibrate_extruders_list[i] >= PHYSICAL_EXTRUDER_NUM:
+                    if not (0 <= flow_calibrate_extruders_list[i] < PHYSICAL_EXTRUDER_NUM):
                         raise gcmd.error("[print_task_config] Invalid FLOW_CALIBRATE_EXTRUDERS")
@@ -1419,4 +1422,6 @@ class PrintTaskConfig:
-                        if abs(tmp_print_task_config_2['nozzle_diameter'][0] - actual_nozzle_diameter[i]) > 0.001:
-                            exception_code = 14
-                            raise gcmd.error(f"[print_task_config] nozzle diameter mismatch:" +
-                                                f"f{i}_{tmp_print_task_config_2['nozzle_diameter'][0]} != e{i}_{actual_nozzle_diameter[i]}")
+                        if (i < len(tmp_print_task_config_2['nozzle_diameter']) and
+                                tmp_print_task_config_2['nozzle_diameter'][i] is not None):
+                            if abs(tmp_print_task_config_2['nozzle_diameter'][i] - actual_nozzle_diameter[i]) > 0.001:
+                                exception_code = 14
+                                raise gcmd.error(f"[print_task_config] nozzle diameter mismatch:" +
+                                                    f"f{i}_{tmp_print_task_config_2['nozzle_diameter'][i]} != e{i}_{actual_nozzle_diameter[i]}")
```

## Regression & Safety Verification
- **Unit Tests:** `test/test_bug_buf11_print_task_config.py` executed:
  - `test_used_extruders_out_of_bounds`: Confirmed bounds check blocks indices `< 0` and `>= 4`.
  - `test_map_table_negative_index`: Confirmed negative index validation.
  - `test_flow_calibrate_negative_index`: Confirmed negative and `>= 4` rejection.
  - `test_nozzle_diameter_index_i`: Confirmed per-extruder index matching resolves false mismatch.
  - Result: `Ran 4 tests in 0.000s OK`.
- **Klippy Batch Simulation:** Executed `test/klippy/bug_buf11_print_task_config.test`:
  ```
  Starting test/klippy/bug_buf11_print_task_config.test (bug_buf11_print_task_config.cfg)
  All 1 test cases passed
  ```
- **Whitespace Check:** `scripts/check_whitespace.py` passed with 0 errors.

