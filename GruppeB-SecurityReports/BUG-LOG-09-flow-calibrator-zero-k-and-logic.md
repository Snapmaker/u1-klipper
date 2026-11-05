# BUG-LOG-09: Falsy `0.0` Check, Config Corruption & Implicit `None` in `flow_calibrator.py`

## Summary
In `klippy/extras/flow_calibrator.py`, the `_load_json_config()` method validates K-factors and environment variables loaded from `flow_calibrator.json`. Due to Python's truthiness evaluation (`not 0.0 == True`), any extruder configured with a legitimate K-factor of `0.0` was classified as invalid, triggering a legacy Python 2 string exception (`raise "invalid parameters in json config"`) which crashed under Python 3 and forcefully deleted `flow_calibrator.json` via `os.remove()`. Furthermore, fallback assignment `self._current_k = DEFAULT_K` shared the mutable dictionary instance with module-level constants. In `_get_next_k()`, when both `area_left` and `area_right` were zero, all conditional branches evaluated to false, implicitly returning `None` and crashing subsequent arithmetic.

## Component / Affected Files
- **File:** `klippy/extras/flow_calibrator.py`
- **Affected Functions:** `_load_json_config()`, `_save_config()`, `_get_next_k()`
- **Lines:** 305-375, 515-545

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules
- **Severity:** High (Destruction of user calibration settings and `NoneType` arithmetic aborts)

## Root Cause Analysis
1. `_load_json_config()` checked `if not k.get('extruder') ...`. If the calibration factor was `0.0`, `not 0.0` evaluated to `True`, triggering config deletion.
2. `raise "invalid parameters in json config"`: In Python 3, raising a string causes `TypeError: exceptions must derive from BaseException`.
3. `self._current_k = DEFAULT_K` assigned a shared dictionary reference rather than a clone, allowing in-place modifications to mutate the module constant.
4. In `_get_next_k()`, condition checks:
   ```python
   if area_sum > area_left and area_sum > area_right: ...
   if area_sum < area_left and area_sum < area_right: ...
   if area_sum < area_left or area_sum < area_right: ...
   ```
   did not handle `area_left == 0.0` and `area_right == 0.0`. When both areas were `0.0`, none of the conditions matched, resulting in an implicit `None` return.

## Steps to Reproduce
1. Configure `flow_calibrator` in `printer.cfg`.
2. Execute `FLOW_TEST_NEXT_K KL=0.01 KR=0.03 AL=0.0 AR=0.0`.
3. Prior to the fix, `_get_next_k()` returned `None`.
4. Storing a valid K value of `0.0` in `flow_calibrator.json` caused configuration wipeout upon restart.

## Proposed Fix / Patch
1. Use `val is None or isinstance(val, bool) or not isinstance(val, (int, float)) or val < 0` for explicit value inspection allowing `0.0`.
2. Replace string exceptions with standard `ValueError`.
3. Use `copy.deepcopy()` for default dictionary assignments.
4. Add an explicit fallback `return round(k_left + (k_right - k_left) / 2, 6)` in `_get_next_k()`.
5. Add `FLOW_TEST_NEXT_K` diagnostic G-code command.

```diff
--- a/klippy/extras/flow_calibrator.py
+++ b/klippy/extras/flow_calibrator.py
@@ -308,18 +340,32 @@ class FlowCalibrator(object):
     def _load_json_config(self, json_file):
         try:
-            params = json.load(open(json_file, 'r'))
-            if not params.get('factor') or not params.get('env'):
-                raise "invalid parameters in json config"
+            with open(json_file, 'r') as f:
+                params = json.load(f)
+            if (not isinstance(params, dict) or not params.get('factor')
+                    or not params.get('env')):
+                raise ValueError("invalid parameters in json config")
             k = params.get('factor')
             env = params.get('env')
+            if not isinstance(k, dict) or not isinstance(env, dict):
+                raise ValueError("factor and env must be dictionaries")
 
-            if not k.get('extruder') or not k.get('extruder1') or not k.get('extruder2') or not k.get('extruder3'):
-                raise
+            for ext_name in ('extruder', 'extruder1', 'extruder2', 'extruder3'):
+                val = k.get(ext_name)
+                if (val is None or isinstance(val, bool)
+                        or not isinstance(val, (int, float)) or val < 0):
+                    raise ValueError("invalid factor value for %s: %s"
+                                     % (ext_name, val))
@@ -490,4 +536,5 @@ class FlowCalibrator(object):
         if area_sum < area_left or area_sum < area_right:
             return round(k_left + (k_right - k_left) / 2, 6)
+        return round(k_left + (k_right - k_left) / 2, 6)
```

## Regression & Safety Verification
- Test case `test/klippy/bug_log09_flow_calibrator.test` executed with virtual simulator configuration `bug_log09_flow_calibrator.cfg`.
- Output: `All 1 test cases passed`.
- Verified that zero area conditions safely yield the midpoint K-factor rather than `None`.

