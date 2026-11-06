# BUG-EXC-03: `UnboundLocalError` on Local Variables and Invalid Bare `raise` Statements

## Summary
In multiple Snapmaker proprietary modules, variable scope mismanagement and improper exception syntax caused runtime crashes:
1. In `klippy/kinematics/extruder.py`, in `_cmd_SWITCH_EXTRUDER()`, local variable `message` was referenced in conditional exception formatting branches without being initialized across all execution paths. Additionally, if `activated_code + 6 >= 18`, formatting `0002-0523-%4d-%4d` failed with unexpected values.
2. In `klippy/extras/probe_inductance_coil.py`, `run_single_probe()` referenced `probe_session.end_probe_session()` in its `finally:` block without guaranteeing that `probe_session` was assigned before an exception in `start_probe_session()`, raising `UnboundLocalError`.
3. In `klippy/extras/purifier.py`, `_handle_control_purifier()` initialized `need_save = False` after potential early exceptions in `web_request.get()`, leading to an `UnboundLocalError` if accessed in error handlers.
4. In `klippy/extras/filament_feed.py` (lines 835, 935) and `klippy/extras/filament_feed_fac_test.py` (lines 251, 267), bare `raise` statements were executed outside of `except:` blocks, which raises `RuntimeError: No active exception to reraise` in Python 3.

## Component / Affected Files
- **File:** `klippy/kinematics/extruder.py`
  - **Affected Methods:** `_cmd_SWITCH_EXTRUDER()`
  - **Lines:** 1475-1510
- **File:** `klippy/extras/probe_inductance_coil.py`
  - **Affected Function:** `run_single_probe()`
  - **Lines:** 1238-1248
- **File:** `klippy/extras/purifier.py`
  - **Affected Method:** `_handle_control_purifier()`
  - **Lines:** 874-885
- **File:** `klippy/extras/filament_feed.py`
  - **Affected Methods:** `_check_residual_filament()`, `_preload_filament()`
  - **Lines:** 832-838, 930-938
- **File:** `klippy/extras/filament_feed_fac_test.py`
  - **Affected Method:** `_run_fac_test()`
  - **Lines:** 248-270

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Host Python
- **Severity:** High (Klippy daemon crash during exception recovery, probing, and filament feed)

## Root Cause Analysis
1. **UnboundLocalError in `run_single_probe` (`probe_inductance_coil.py`):**
   ```python
   def run_single_probe(probe, gcmd):
       try:
           probe_session = probe.start_probe_session(gcmd)
           ...
       finally:
           probe_session.end_probe_session()
   ```
   If `probe.start_probe_session(gcmd)` raises any exception, `probe_session` is never assigned in local scope. Entering `finally:` triggers `UnboundLocalError: local variable 'probe_session' referenced before assignment`, masking the original exception and crashing Klippy.
2. **Invalid Bare `raise` Statements Outside Exception Handlers (`filament_feed.py`, `filament_feed_fac_test.py`):**
   In Python 3, a bare `raise` statement without an active exception raises `RuntimeError: No active exception to reraise`. In `filament_feed.py` and `filament_feed_fac_test.py`, bare `raise` was used inside an `if` condition within a `try:` block (not in an `except:` clause).
3. **Unbound Variable in `_handle_control_purifier` (`purifier.py`):**
   `need_save = False` was placed after parameter retrieval (`web_request.get()`) that could throw an exception. Moving it before the `try:` block guarantees it is always defined.
4. **Unbound Variable `message` in `_cmd_SWITCH_EXTRUDER` (`extruder.py`):**
   In nested branches handling `activate_status`, `message` was only defined in certain `if/else` paths. If an unhandled error code was encountered, `message` remained uninitialized when passed to logging or error reporting.

## Steps to Reproduce
1. In `probe_inductance_coil.py`: Mock `start_probe_session()` to raise an exception. Observe that Klippy terminates with `UnboundLocalError` instead of handling the original error.
2. In `filament_feed.py`: Trigger residual filament detection in `_check_residual_filament()`. Python terminates with `RuntimeError: No active exception to reraise`.

## Proposed Fix / Patch
```diff
diff --git a/klippy/extras/filament_feed.py b/klippy/extras/filament_feed.py
--- a/klippy/extras/filament_feed.py
+++ b/klippy/extras/filament_feed.py
@@ -835,3 +835,3 @@ class FilamentFeed:
                         self.exception_code[ch] = 15
-                        raise
+                        raise Exception("Residual filament detected")
@@ -935,3 +935,3 @@ class FilamentFeed:
                     if self.channel_error[ch] != FEED_OK:
-                        raise
+                        raise Exception(f"Channel error: {self.channel_error[ch]}")
diff --git a/klippy/extras/filament_feed_fac_test.py b/klippy/extras/filament_feed_fac_test.py
--- a/klippy/extras/filament_feed_fac_test.py
+++ b/klippy/extras/filament_feed_fac_test.py
@@ -251,3 +251,3 @@ class FeedFacTest:
             if self._output_pin_state != self._input_pin_state:
-                raise
+                raise Exception("Output and input pin state mismatch")
@@ -267,3 +267,3 @@ class FeedFacTest:
             if self._output_pin_state != self._input_pin_state:
-                raise
+                raise Exception("Output and input pin state mismatch")
diff --git a/klippy/extras/probe_inductance_coil.py b/klippy/extras/probe_inductance_coil.py
--- a/klippy/extras/probe_inductance_coil.py
+++ b/klippy/extras/probe_inductance_coil.py
@@ -1236,5 +1236,7 @@ def run_single_probe(probe, gcmd):
+    probe_session = None
     try:
         probe_session = probe.start_probe_session(gcmd)
         ...
     finally:
-        probe_session.end_probe_session()
+        if probe_session is not None:
+            probe_session.end_probe_session()
diff --git a/klippy/extras/purifier.py b/klippy/extras/purifier.py
--- a/klippy/extras/purifier.py
+++ b/klippy/extras/purifier.py
@@ -874,2 +874,3 @@ class Purifier:
     def _handle_control_purifier(self, web_request):
+        need_save = False
         try:
diff --git a/klippy/kinematics/extruder.py b/klippy/kinematics/extruder.py
--- a/klippy/kinematics/extruder.py
+++ b/klippy/kinematics/extruder.py
@@ -1480,5 +1480,6 @@ class PrinterExtruder:
                             if activated_code + 6 < 18:
-                                message = '{"coded": "0002-0523-%4d-%4d", "oneshot": %d, "msg":"%s", "action": "pause"}' % (self.extruder_num, activated_code + 6, 0, error_msg)
+                                code = activated_code + 6
                             else:
-                                message = '{"coded": "0002-0523-%4d-0018", "oneshot": %d, "msg":"%s", "action": "pause"}' % (self.extruder_num, 0, error_msg)
+                                code = 18
+                            message = '{"coded": "0002-0523-%4d-%4d", "oneshot": %d, "msg":"%s", "action": "pause"}' % (self.extruder_num, code, 0, error_msg)
```

## Regression & Safety Verification
- **Unit Tests:** `test/test_bug_exc03.py` executed:
  - `test_bare_raise_in_filament_feed`: Verified explicit exception is raised rather than `RuntimeError: No active exception to reraise`.
  - `test_bare_raise_in_filament_feed_fac_test`: Verified explicit exception is raised.
  - `test_probe_session_unbound_local_error`: Verified original exception propagates without `UnboundLocalError` in `finally:`.
  - `test_purifier_need_save_initialization`: Verified `need_save` is safely defined before `try:`.
  - Result: `Ran 4 tests in 0.193s OK`.
- **Klippy Batch Simulation:** Executed `test/klippy/bug_exc03_extruder.test`:
  ```
  Starting test/klippy/bug_exc03_extruder.test (bug_exc03_extruder.cfg)
  All 1 test cases passed
  ```
- **Whitespace Check:** `scripts/check_whitespace.py` passed with 0 errors.

