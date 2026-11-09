# BUG-BUF-10: Out-of-Bounds `IndexError` in `klippy/kinematics/extruder.py`

## Summary
In `klippy/kinematics/extruder.py`, list indexing operations in `_set_nozzle_diameter()`, `_get_filament_temp()`, and `_cmd_SWITCH_EXTRUDER()` assume non-empty status lists and valid extruder indices without boundary validation. When `print_task_config` returns an empty or truncated `filament_vendor` list, or when `analyze_switch_extruder_error()` returns an empty `unknown` list, Klippy crashes with an unhandled `IndexError: list index out of range` during toolhead switching, nozzle diameter configuration (`SET_NOZZLE_DIAMETER`), or filament temperature queries (`INNER_HEAT_TO_LOADED_FILAMENT_TEMP`). A similar unguarded `unknown[0]` dereference was identified and resolved in `klippy/extras/probe_inductance_coil.py`.

## Component / Affected Files
- **File:** `klippy/kinematics/extruder.py`
  - **Affected Methods:** `_set_nozzle_diameter()`, `_get_filament_temp()`, `_cmd_SWITCH_EXTRUDER()`
  - **Lines:** 1160-1175, 1255-1275, 1475-1488, 1740-1760
- **File:** `klippy/extras/probe_inductance_coil.py`
  - **Affected Method:** `ProbeSessionHelper.check_extruder_status()`
  - **Lines:** 869-873

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Host Python
- **Severity:** High (Crash / Denial of Service during printing / Toolchange)

## Root Cause Analysis
1. **Unchecked Extruder Indexing in `_set_nozzle_diameter`:**
   In `_set_nozzle_diameter()`, `self.extruder_index` is used directly to index `status['filament_vendor'][self.extruder_index]` without verifying that `0 <= self.extruder_index < len(status['filament_vendor'])`. If the vendor list is empty (e.g. before initial task configuration) or has fewer entries than the configured extruder index, an `IndexError` is raised.
2. **Unchecked Extruder Indexing in `_get_filament_temp`:**
   In `_get_filament_temp(extruder_index)`, `extruder_index` is passed from G-Code (`T` argument) or defaults to `self.extruder_index`. If `extruder_index` is negative or greater than or equal to `len(status['filament_vendor'])`, indexing triggers `IndexError`.
3. **Empty `unknown` List Access in `_cmd_SWITCH_EXTRUDER`:**
   In `_cmd_SWITCH_EXTRUDER()`, when hall sensor state is evaluated under error condition `code = 35`, the code unconditionally dereferenced `first_unknow_state = grip_states[unknown[0]]` and `extruder_num = unknown[0]`. When `analyze_switch_extruder_error()` returns an empty `unknown = []` (e.g. when multiple extruders are active or states are unexpected), `unknown[0]` immediately raises `IndexError`.
4. **Out-of-Bounds `idx` in `grip_states` Loop:**
   In `_cmd_SWITCH_EXTRUDER()`, `for i, idx in enumerate(unknown):` indexed `grip_states[idx]` without checking `0 <= idx < len(grip_states)`.

## Steps to Reproduce
1. Run Klippy with `print_task_config` where `filament_vendor` is empty or only holds 1 entry.
2. Execute:
   ```gcode
   SET_NOZZLE_DIAMETER EXTRUDER=extruder DIAMETER=0.2
   ```
   Or call `_get_filament_temp(extruder_index=1)`.
3. An unhandled `IndexError` crashes Klippy:
   ```
   Traceback (most recent call last):
     File "klippy/kinematics/extruder.py", line 1164, in _set_nozzle_diameter
       status['filament_vendor'][self.extruder_index],
   IndexError: list index out of range
   ```
4. During an extruder switch where `unknown == []`, evaluating line 1745 crashes Klippy with:
   ```
   IndexError: list index out of range (evaluating grip_states[unknown[0]])
   ```

## Proposed Fix / Patch
1. In `_set_nozzle_diameter()`, verify `0 <= idx < len(vendors)` and `types` and `sub_types` before calling `is_allow_to_print()`.
2. In `_get_filament_temp()`, verify `0 <= extruder_index < len(vendors)` and fall back safely to returning default temperature `220`.
3. In `_cmd_SWITCH_EXTRUDER()`, verify `unknown` is non-empty (`and unknown`) and check `0 <= unknown[0] < len(grip_states)` before accessing `unknown[0]`.
4. In `probe_inductance_coil.py`, guard `unknown` and `0 <= unknown[0] < len(grip_states)`.

```diff
diff --git a/klippy/extras/probe_inductance_coil.py b/klippy/extras/probe_inductance_coil.py
index eb54084c..29364830 100644
--- a/klippy/extras/probe_inductance_coil.py
+++ b/klippy/extras/probe_inductance_coil.py
@@ -866,8 +866,9 @@ class ProbeSessionHelper:
                 result = extruder.analyze_switch_extruder_error(activate_status)
                 if result:
                     error_msg, activated, unknown, grip_states, activated_code, unknown_code = result
-                    if grab_hall_sensor_type and "multi-act" not in error_msg:
-                        grip_state = grip_states[unknown[0]]
+                    if grab_hall_sensor_type and "multi-act" not in error_msg and unknown:
+                        if 0 <= unknown[0] < len(grip_states):
+                            grip_state = grip_states[unknown[0]]
                         message = None
                         if grip_state == 'FFF':
                             info = "Probing abort: detected that extruder%d is detached. %s" % (unknown[0], error_msg)
diff --git a/klippy/kinematics/extruder.py b/klippy/kinematics/extruder.py
index 6978d8a1..20ff556f 100644
--- a/klippy/kinematics/extruder.py
+++ b/klippy/kinematics/extruder.py
@@ -1160,14 +1160,21 @@ class PrinterExtruder:
             filament_parameters = self.printer.lookup_object('filament_parameters', None)
             if print_task_config is not None and filament_parameters is not None:
                 status = print_task_config.get_status()
-                is_allow = filament_parameters.is_allow_to_print(
-                        status['filament_vendor'][self.extruder_index],
-                        status['filament_type'][self.extruder_index],
-                        status['filament_sub_type'][self.extruder_index],
-                        self.nozzle_diameter,
-                        self.nozzle_volume_type)
-                if not is_allow:
-                    print_task_config.reset_filament_info(self.extruder_index)
+                vendors = status.get('filament_vendor', [])
+                types = status.get('filament_type', [])
+                sub_types = status.get('filament_sub_type', [])
+                idx = self.extruder_index
+                if (0 <= idx < len(vendors) and
+                        0 <= idx < len(types) and
+                        0 <= idx < len(sub_types)):
+                    is_allow = filament_parameters.is_allow_to_print(
+                            vendors[idx],
+                            types[idx],
+                            sub_types[idx],
+                            self.nozzle_diameter,
+                            self.nozzle_volume_type)
+                    if not is_allow:
+                        print_task_config.reset_filament_info(idx)
 
     def _set_nozzle_volume_type(self, volume_type, save=True):
         self.nozzle_volume_type = volume_type
@@ -1257,10 +1264,18 @@ class PrinterExtruder:
             return 220
 
         status = print_task_config.get_status()
+        vendors = status.get('filament_vendor', [])
+        types = status.get('filament_type', [])
+        sub_types = status.get('filament_sub_type', [])
+        if not (0 <= extruder_index < len(vendors) and
+                0 <= extruder_index < len(types) and
+                0 <= extruder_index < len(sub_types)):
+            return 220
+
         return filament_parameters.get_print_temp(
-                status['filament_vendor'][extruder_index],
-                status['filament_type'][extruder_index],
-                status['filament_sub_type'][extruder_index],
+                vendors[extruder_index],
+                types[extruder_index],
+                sub_types[extruder_index],
                 extruder_obj.nozzle_diameter,
                 extruder_obj.nozzle_volume_type)
 
@@ -1459,14 +1474,14 @@ class PrinterExtruder:
                                     message = '{"coded": "0002-0523-%4d-%4d", "oneshot": %d, "msg":"%s", "action": "pause"}' % (self.extruder_num, activated_code + 6, 0, error_msg)
                             else:
                                 message = '{"coded": "0002-0523-%4d-0018", "oneshot": %d, "msg":"%s", "action": "pause"}' % (self.extruder_num, 0, error_msg)
-                                if self.grab_hall_sensor_type:
+                                if self.grab_hall_sensor_type and unknown:
                                     first_unknown_index = None
                                     for i, idx in enumerate(unknown):
-                                        if grip_states[idx] != 'FFT':
+                                        if 0 <= idx < len(grip_states) and grip_states[idx] != 'FFT':
                                             first_unknown_index = idx
                                             break
 
-                                    if first_unknown_index is not None:
+                                    if first_unknown_index is not None and 0 <= first_unknown_index < len(grip_states):
                                         grip_state = grip_states[first_unknown_index]
                                         if grip_state == 'FFF' or grip_state == 'FFT':
                                             info = "Extruder %s is not allowed to switch, detected that extruder%d is detached. %s" % (self.name, first_unknown_index, error_info)
@@ -1726,20 +1741,21 @@ class PrinterExtruder:
                                                 code = 23 + activated_code
                                         else:
                                             code = 35
-                                            if self.grab_hall_sensor_type:
-                                                first_unknow_state = grip_states[unknown[0]]
-                                                if first_unknow_state == 'FFT':
-                                                    code = 45
-                                                    extruder_num = unknown[0]
-                                                    error_msg = f'detected that extruder{unknown[0]} pogopin not connected. {error_msg}'
-                                                elif first_unknow_state == 'FFF':
-                                                    code = 46
-                                                    extruder_num = unknown[0]
-                                                    error_msg = f'detected that extruder{unknown[0]} is detached. {error_msg}'
-                                                elif first_unknow_state == 'TTT' or first_unknow_state == 'TTF':
-                                                    code = 47
-                                                    extruder_num = unknown[0]
-                                                    error_msg = f'detected conflicting status for extruder{unknown[0]}: both parked and picked states. {error_msg}'
+                                            if self.grab_hall_sensor_type and unknown:
+                                                if 0 <= unknown[0] < len(grip_states):
+                                                    first_unknow_state = grip_states[unknown[0]]
+                                                    if first_unknow_state == 'FFT':
+                                                        code = 45
+                                                        extruder_num = unknown[0]
+                                                        error_msg = f'detected that extruder{unknown[0]} pogopin not connected. {error_msg}'
+                                                    elif first_unknow_state == 'FFF':
+                                                        code = 46
+                                                        extruder_num = unknown[0]
+                                                        error_msg = f'detected that extruder{unknown[0]} is detached. {error_msg}'
+                                                    elif first_unknow_state == 'TTT' or first_unknow_state == 'TTF':
+                                                        code = 47
+                                                        extruder_num = unknown[0]
+                                                        error_msg = f'detected conflicting status for extruder{unknown[0]}: both parked and picked states. {error_msg}'
                                         msg = f"Extruder {self.name} pickup failed, {error_msg}"
                                 message = '{"coded": "0002-0523-%4d-%4d", "oneshot": %d, "msg":"%s", "action": "pause"}' % (extruder_num, code, 0, msg)
                                 if retry_extruder_id is not None:
```

## Regression & Safety Verification
- **Automated Unit Test:** `test/test_bug_buf10_extruder.py` verifies:
  - Empty vendor list in `print_task_config` handled safely (0 crashes).
  - Out-of-bounds extruder index handled safely (0 crashes).
  - Temperature lookup returns safe default `220` when out of range.
  - Negative extruder index returns safe default `220`.
  - Empty `unknown` list handled safely without accessing index 0.
  - All 5 test cases passed with `OK`.
- **Klippy Batch Test:** `test/klippy/bug_buf10_extruder.test` executed via `scripts/test_klippy.py` with exit code 0 (`All 1 test cases passed`).
- **Whitespace Check:** `scripts/check_whitespace.py` completed with 0 errors.

