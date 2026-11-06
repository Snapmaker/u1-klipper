# BUG-STACK-02: Infinite Probing Loop and Unbounded Iteration in `auto_screws_tilt_adjust.py`

## Summary
In `klippy/extras/auto_screws_tilt_adjust.py`, `cmd_AUTO_SCREWS_TILT_ADJUST_MANUAL_TUNING()` executed an unconstrained `while True:` loop for both overall verification rounds and per-screw manual probing adjustments. If the bed could not reach the target tolerance threshold (e.g. due to warped bed, mechanical limitations, or improper manual adjustment), or if unattended, the command looped indefinitely without ever timing out or terminating. In addition, `_probe_abort_check()` only verified `self.abort_flag` and failed to check `self.printer.is_shutdown()`, preventing immediate termination during printer emergency shutdowns.

## Component / Affected Files
- **File:** `klippy/extras/auto_screws_tilt_adjust.py`
- **Affected Functions:** `_probe_abort_check()`, `cmd_AUTO_SCREWS_TILT_ADJUST_MANUAL_TUNING()`
- **Lines:** 181-187, 515-585

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Firmware
- **Severity:** High (Hang / Unbounded Infinite Loop / Denial of Service)

## Root Cause Analysis
1. **Unbounded Verification Attempts:**
   Unlike `cmd_AUTO_SCREWS_TILT_ADJUST` which bounds verification rounds via `max_verify_attempts` (configured via `MAX_VERIFY_ATTEMPTS` or `self.max_verify_attempts`), `cmd_AUTO_SCREWS_TILT_ADJUST_MANUAL_TUNING` declared `while True:` and incremented `verify_attempt` without checking against `max_verify_attempts`. If `_verify_level()` returned `False`, the loop continued indefinitely.
2. **Unbounded Per-Screw Probing Loop:**
   In manual tuning mode, the inner per-screw probing loop `while True:` repeatedly probed the bed screw until `self.state != AutoScrewsTiltAdjustStep.WAIT_MANUAL_ADJUST_SCREWS`. Without an upper boundary on adjustment counts (`adjust_count > max_adjust_times`), an unattended printer or disconnected client would probe the bed indefinitely.
3. **Missing Shutdown Check in Abort Guard:**
   `_probe_abort_check()` only evaluated `self.abort_flag`. If the firmware transitioned into shutdown (e.g., via M112 emergency stop or thermal runaway detection), the probe routine failed to abort immediately.

## Steps to Reproduce
1. Home the printer and run `AUTO_SCREWS_TILT_ADJUST_PROBE_REFERENCE_POINTS` to establish reference points.
2. Intentionally misadjust one bed screw so that the bed variance exceeds `self.screw_adjust_threshold`.
3. Run `AUTO_SCREWS_TILT_ADJUST_MANUAL_TUNING`.
4. Allow manual tuning to proceed through rounds without satisfying `_verify_level()`.
5. Observe that round count increments endlessly (Round 10, 11, 12...) and the command never exits.

## Proposed Fix / Patch
1. In `_probe_abort_check()`, check `if self.abort_flag or self.printer.is_shutdown():` and raise `AutoScrewsTiltAdjustAbort`.
2. In `cmd_AUTO_SCREWS_TILT_ADJUST_MANUAL_TUNING()`, read `max_verify_attempts` and `max_adjust_times` parameters from `gcmd`.
3. Bound the outer loop with `while verify_attempt < max_verify_attempts:`, and raise `AutoScrewsTiltAdjustLimit` when attempts are exhausted.
4. Bound the inner manual probing loop with `adjust_count += 1; if adjust_count > max_adjust_times: raise AutoScrewsTiltAdjustLimit(...)`.

```diff
--- a/klippy/extras/auto_screws_tilt_adjust.py
+++ b/klippy/extras/auto_screws_tilt_adjust.py
@@ -179,7 +179,7 @@ class AutoScrewsTiltAdjust:
         except Exception as e:
             web_request.send({'state': 'error', 'message': str(e)})
     def _probe_abort_check(self):
-        if self.abort_flag:
+        if self.abort_flag or self.printer.is_shutdown():
             with self.lock:
                 self.state = AutoScrewsTiltAdjustStep.PROBING_ABORTING
             logging.info("abort_flag set, can't continue")
@@ -515,9 +515,11 @@ class AutoScrewsTiltAdjust:
         probe_object = self.printer.lookup_object('probe', None)
         if probe_object is None:
             raise gcmd.error("Probe object not found")
+        max_verify_attempts = gcmd.get_int('MAX_VERIFY_ATTEMPTS', self.max_verify_attempts, minval=1)
+        max_adjust_times = gcmd.get_int('ADJUST_MAX_TIMES', self.max_adjust_times, minval=1)
         try:
             verify_attempt = 0
-            while True:
+            while verify_attempt < max_verify_attempts:
                 verify_attempt += 1
                 self.gcode.respond_info("Starting adjustment round %d..." % verify_attempt)
                 self.gcode.respond_info("Initial probing results:")
@@ -551,7 +553,12 @@ class AutoScrewsTiltAdjust:
                     self._move([coord[0], coord[1], None], self.probe_helper.speed)
                     self._move([None, None, self.base_points[i]+self.sample_retract_dist], self.probe_helper.lift_speed)
                     probe_cmd = "PROBE SAMPLES=1 SAMPLE_RETRACT_DIST={}".format(self.sample_retract_dist)
+                    adjust_count = 0
                     while True:
+                        adjust_count += 1
+                        if adjust_count > max_adjust_times:
+                            raise AutoScrewsTiltAdjustLimit(
+                                "%s adjustment exceeded max limit (%d times)" % (name, max_adjust_times))
                         self.need_adjusted_z = self.target_z - self.base_points[i]
                         diff = self.target_z - self.base_points[i]
                         direction = "CW" if diff > 0 else "CCW"
@@ -571,6 +578,10 @@ class AutoScrewsTiltAdjust:
                 probe_cmd = "PROBE SAMPLES=3 SAMPLE_RETRACT_DIST={}".format(self.sample_retract_dist)
                 if self._verify_level(probe_cmd, toolhead, probe_object):
                     raise AutoScrewsTiltAdjustPass
+                elif verify_attempt < max_verify_attempts:
+                    self.gcode.respond_info("Preparing for adjustment round %d..." % (verify_attempt + 1))
+                else:
+                    raise AutoScrewsTiltAdjustLimit("Adjustment exceeded max verification attempts (%d)" % max_verify_attempts)

                 # Recalculate target height as average of max and min
                 self.max_z = max(self.base_points)
```

## Regression & Safety Verification
- **Automated Unit Tests:**
  - `test/test_bug_stack02.py`: Verified `max_verify_attempts` limit terminates with error, `max_adjust_times` limits single screw probing iterations, and `printer.is_shutdown()` cleanly aborts execution.
- **Whitespace Compliance:** Verified with `scripts/check_whitespace.py` (0 errors).
- **Regression:** Verified normal leveling workflow completes successfully when tolerance criteria are met.

