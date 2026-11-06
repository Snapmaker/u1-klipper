# BUG-LOG-05: Late-Binding Closure Bug and Missing Y-Diff Tolerance Check in `klippy/kinematics/extruder.py`

## Summary
Two logic flaws in `klippy/kinematics/extruder.py` led to incorrect hardware state transitions and unvalidated toolhead movements:
1. In `_cmd_SWITCH_EXTRUDER()`, when configuring motor Vref switch states via lookahead callbacks, `lambda print_time: extruder_list[i].vref_sw._set_pin(print_time, ...)` captured loop index `i` by reference (late binding) rather than by value. At execution time, `i` was always bound to the final index (`len(extruder_list) - 1`), causing all lookahead callbacks to switch exclusively the last extruder and leaving preceding extruders unconfigured.
2. In `cmd_MOVE_TO_PARK_CALIBRATION_POINT` and `cmd_VERIFY_PARK_POSITION`, the difference check between the target position and the configured park position only evaluated `x_diff > MAX_ALLOWED_DIFFERENCE`. The Y-axis difference (`y_diff`) was omitted from the validation condition, allowing arbitrary uncalibrated Y moves without raising a safety threshold error unless `FORCE_MOVE=1` was explicitly requested.

## Component / Affected Files
- **File:** `klippy/kinematics/extruder.py`
  - **Affected Methods:** `_cmd_SWITCH_EXTRUDER()`, `cmd_MOVE_TO_PARK_CALIBRATION_POINT()`, `cmd_VERIFY_PARK_POSITION()`
  - **Lines:** 1787-1794, 2080-2105, 2135-2155

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Host Python
- **Severity:** High (Improper Stepper Vref Configuration / Unsafe Toolhead Moves during Dock Calibration)

## Root Cause Analysis
1. **Late-Binding Closure in Lookahead Callbacks:**
   In Python, closures bind variables from an enclosing scope by name/reference, not by value. The loop:
   ```python
   for i in range(len(extruder_list)):
       if extruder_list[i].vref_sw is not None:
           if extruder_list[i].name == self.name:
               toolhead.register_lookahead_callback(lambda print_time: extruder_list[i].vref_sw._set_pin(print_time, 1))
           else:
               toolhead.register_lookahead_callback(lambda print_time: extruder_list[i].vref_sw._set_pin(print_time, 0))
   ```
   created lambdas holding a reference to `i`. Once the loop completed, `i` remained at the last index (e.g. `3`). When the planner later fired lookahead callbacks during toolhead moves, every registered callback accessed `extruder_list[3]`.
2. **Missing Y-Axis Tolerance Checks:**
   In `cmd_VERIFY_PARK_POSITION` and `cmd_MOVE_TO_PARK_CALIBRATION_POINT`, `MAX_ALLOWED_DIFFERENCE = 3.0` mm enforces that calibration commands do not command unsafe moves far from docking coordinates. However, only `x_diff` was tested against `MAX_ALLOWED_DIFFERENCE`. A commanded Y offset exceeding physical limits bypassed validation and could trigger mechanical collision against the toolhead dock.

## Steps to Reproduce
1. In a multi-extruder setup (e.g. 4 extruders), trigger an extruder switch (`ACTIVATE_EXTRUDER`).
2. Inspect lookahead callback execution on `vref_sw`: observe that all 4 callback invocations target `extruder_list[3]`, while `extruder0`, `extruder1`, and `extruder2` never receive their lookahead pin updates.
3. Call `VERIFY_PARK_POSITION EXTRUDER=extruder X=35.0 Y=340.0` (with configured park Y=332.2 mm, diff = 7.8 mm). Prior to fix, the command bypassed difference checks without error.

## Proposed Fix / Patch
```diff
diff --git a/klippy/kinematics/extruder.py b/klippy/kinematics/extruder.py
--- a/klippy/kinematics/extruder.py
+++ b/klippy/kinematics/extruder.py
@@ -1787,7 +1787,9 @@ class PrinterExtruder:
                 if extruder_list[i].vref_sw is not None:
                     if extruder_list[i].name == self.name:
-                        toolhead.register_lookahead_callback(lambda print_time: extruder_list[i].vref_sw._set_pin(print_time, 1))
+                        toolhead.register_lookahead_callback(
+                            lambda print_time, ext=extruder_list[i]: ext.vref_sw._set_pin(print_time, 1))
                     else:
-                        toolhead.register_lookahead_callback(lambda print_time: extruder_list[i].vref_sw._set_pin(print_time, 0))
+                        toolhead.register_lookahead_callback(
+                            lambda print_time, ext=extruder_list[i]: ext.vref_sw._set_pin(print_time, 0))
@@ -2080,10 +2082,18 @@ class PrinterExtruder:
         base_calibration_y = 320
         macro = self.printer.lookup_object('gcode_macro _MOVE_TO_{}_PARK_CALIBRATION_POINT'.format(self.name.upper()), None)
         if macro is not None:
             move_calibration_x = macro.variables.get('x_pos', move_calibration_x)
             base_calibration_y = macro.variables.get('y_pos', base_calibration_y)

         move_calibration_x = gcmd.get_float('X', move_calibration_x)
         move_calibration_y = gcmd.get_float('Y', base_calibration_y)

         x_diff = abs(move_calibration_x - self.xy_park_position[0])
-        if (x_diff > MAX_ALLOWED_DIFFERENCE and not force_move):
-            msg = (f"Move to park calibration position X differs too much from current position. Exceeded: X: {x_diff:.3f}mm. "
+        y_diff = abs(move_calibration_y - base_calibration_y)
+        if ((x_diff > MAX_ALLOWED_DIFFERENCE or y_diff > MAX_ALLOWED_DIFFERENCE) and not force_move):
+            exceeded = []
+            if x_diff > MAX_ALLOWED_DIFFERENCE:
+                exceeded.append(f"X: {x_diff:.3f}mm")
+            if y_diff > MAX_ALLOWED_DIFFERENCE:
+                exceeded.append(f"Y: {y_diff:.3f}mm")
+            msg = (f"Move to park calibration position differs too much from current position. "
+                   f"Exceeded: {', '.join(exceeded)}. "
@@ -2135,5 +2145,12 @@ class PrinterExtruder:
         x_diff = abs(verify_x - self.xy_park_position[0])
-        if (x_diff > MAX_ALLOWED_DIFFERENCE and not force_move):
-            msg = (f"Verify park position differs too much from current position. Exceeded: X: {x_diff:.3f}mm. "
+        y_diff = abs(verify_y - self.xy_park_position[1])
+        if ((x_diff > MAX_ALLOWED_DIFFERENCE or y_diff > MAX_ALLOWED_DIFFERENCE) and not force_move):
+            exceeded = []
+            if x_diff > MAX_ALLOWED_DIFFERENCE:
+                exceeded.append(f"X: {x_diff:.3f}mm")
+            if y_diff > MAX_ALLOWED_DIFFERENCE:
+                exceeded.append(f"Y: {y_diff:.3f}mm")
+            msg = (f"Verify park position differs too much from current position. "
+                   f"Exceeded axes: {', '.join(exceeded)}. "
```

## Regression & Safety Verification
- **Unit Tests:** `test/test_bug_log05_extruder.py` executed:
  - `test_late_binding_closure`: Confirmed each extruder `ext0`..`ext3` receives its individual lookahead callback rather than all resolving to `ext3`.
  - `test_verify_park_position_y_diff_check`: Confirmed `Y` coordinate deviations exceeding `MAX_ALLOWED_DIFFERENCE` (3.0 mm) raise validation errors, and `FORCE_MOVE=1` allows overriding.
  - Result: `Ran 2 tests in 0.000s OK`.
- **Klippy Batch Simulation:** Executed `test/klippy/bug_log05_extruder.test`:
  ```
  Starting test/klippy/bug_log05_extruder.test (bug_log05_extruder.cfg)
  Verify park position differs too much from current position. Exceeded axes: Y: 7.800mm. Max allowed: 3.000mm.
  All 1 test cases passed
  ```
- **Whitespace Check:** `scripts/check_whitespace.py` passed with 0 errors.

