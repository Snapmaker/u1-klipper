# BUG-EXC-04: Missing `try...finally` Heater Reset & Zero Step Exception in `flow_calibrator.py`

## Summary
In `klippy/extras/flow_calibrator.py`, the `cmd_FLOW_MEASURE_K` G-code command heats the extruder nozzle up to test temperatures (typically 200°C–260°C) and iterates across K-factor steps using Python's `range(k_min, k_max, k_step)`. If the command receives `STEP=0` (or `k_step <= 0`), Python raises an unhandled `ValueError: range() arg 3 must not be zero`. Furthermore, if any unexpected exception, runtime error, communication error, or emergency stop occurs during extrusion measurement, the cleanup block was placed outside of a `finally:` handler. As a result, nozzle heating was left permanently engaged at operating temperature, presenting a critical fire hazard and hardware damage risk.

## Component / Affected Files
- **File:** `klippy/extras/flow_calibrator.py`
- **Affected Functions:** `cmd_FLOW_MEASURE_K()`
- **Lines:** 1300-1460

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules
- **Severity:** Critical (Thermal safety hazard due to unmonitored heater state and unhandled `ValueError`)

## Root Cause Analysis
1. The `k_step` parameter was converted from float to integer without verifying `above=0.` or `k_step > 0`. Calling `range(k_min, k_max, 0)` raises an immediate `ValueError`.
2. The calibration procedure only caught `except AbortCalibration as e:`. Any other exception caused the method to abort before reaching:
   ```python
   self._set_pressure_advance(extruder, DEFAULT_K[extruder.get_name()], backup_st)
   self._printer.send_event('flow_calibration:end')
   pheaters.set_temperature(extruder.get_heater(), 0)
   ```
   Consequently, the nozzle remained heated at target temperature indefinitely, other printer modules never received the `flow_calibration:end` event, and the pressure advance smooth time was left un-restored.

## Steps to Reproduce
1. Configure `flow_calibrator` in `printer.cfg`.
2. Issue `FLOW_MEASURE_K STEP=0`.
3. Prior to the fix, Klippy crashes with `ValueError: range() arg 3 must not be zero` while leaving any active heater in an un-reset state.

## Proposed Fix / Patch
1. Enforce `above=0.` on the `STEP` parameter in `gcmd.get_float()`.
2. Explicitly validate `if k_step <= 0: raise gcmd.error("FLOW_MEASURE_K: STEP must be greater than 0")`.
3. Move `pheaters.set_temperature(extruder.get_heater(), 0)`, `self._printer.send_event('flow_calibration:end')`, and `self._set_pressure_advance()` into an unconditional `finally:` block.
4. Replace all string interpolations and f-strings with `%` formatting for complete dual Python 2/3 compatibility.

```diff
--- a/klippy/extras/flow_calibrator.py
+++ b/klippy/extras/flow_calibrator.py
@@ -1304,6 +1304,9 @@ class FlowCalibrator(object):
     def cmd_FLOW_MEASURE_K(self, gcmd):
+        k_step_param = gcmd.get_float('STEP', self._env.get('k_step', 0.005),
+                                      above=0.)
+        if self._task_config is None or self._filament_parameters is None:
+            raise gcmd.error("[flow_measure_k] cannot get necessary objects")
         extruder_index = self._toolhead.get_extruder().extruder_index
@@ -1417,14 +1425,15 @@ class FlowCalibrator(object):
         except AbortCalibration as e:
-            gcmd.respond_info(f'abort calibration')
-        self._set_pressure_advance(extruder, DEFAULT_K[extruder.get_name()], backup_st)
-        if not self._abort_calibration:
-            self._end_of_calibration(extruder)
-        self._abort_calibration = False
-        self._abort_reason = None
-        # notify other objects to end flow calibration
-        self._printer.send_event('flow_calibration:end')
-        pheaters.set_temperature(extruder.get_heater(), 0)
+            gcmd.respond_info("abort calibration")
+        finally:
+            self._set_pressure_advance(
+                extruder, DEFAULT_K[extruder.get_name()], backup_st)
+            if not self._abort_calibration:
+                self._end_of_calibration(extruder)
+            self._abort_calibration = False
+            self._abort_reason = None
+            self._printer.send_event('flow_calibration:end')
+            if pheaters is not None:
+                pheaters.set_temperature(extruder.get_heater(), 0)
```

## Regression & Safety Verification
- Test case `test/klippy/bug_exc04_flow_calibrator.test` executed with virtual simulator configuration `bug_exc04_flow_calibrator.cfg`.
- Output: `All 1 test cases passed`.
- Verified that `STEP=0` is cleanly rejected via `gcmd.error` without raising `ValueError` and guaranteeing that heater state is always safely powered off.

