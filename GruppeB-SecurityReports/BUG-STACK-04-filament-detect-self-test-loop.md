# BUG-STACK-04: Infinite Busy Loop in Filament Detector Self Test

## Summary
In `klippy/extras/filament_detect.py`, `cmd_FILAMENT_DT_SELF_TEST()` ran an unconstrained `while (1):` loop waiting for `self._fm175xx_reader.self_test_result()` to return `finish = True`. The routine lacked any timeout mechanism and did not check `printer.is_shutdown()`. If the RFID reader stalled, failed to acknowledge the test request, was disconnected, or if the printer entered shutdown, Klippy remained locked in the polling loop indefinitely, halting gcode processing across the entire system. Furthermore, without a `try...finally` block, exceptions left `self._state[channel]` permanently in `FILAMENT_DT_STATE_SELF_TESTING`.

## Component / Affected Files
- **File:** `klippy/extras/filament_detect.py`
- **Affected Functions:** `cmd_FILAMENT_DT_SELF_TEST()`
- **Lines:** 243-288

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Firmware
- **Severity:** High (Infinite Loop / Reactor Blockade / Denial of Service)

## Root Cause Analysis
1. **Unbounded Polling Loop:**
   `while (1):` polled `self._fm175xx_reader.self_test_result()` and only broke when `finish` was true. No deadline or timeout was enforced.
2. **Missing Shutdown Verification:**
   The polling loop failed to check `self.printer.is_shutdown()`, preventing reactor termination during emergency stops.
3. **Missing State Cleanup:**
   If aborted or interrupted by an error, the channel state `self._state[channel]` remained in `FILAMENT_DT_STATE_SELF_TESTING`, blocking future filament operations on that channel.
4. **Unchecked Reader Object:**
   If `fm175xx_reader` was unavailable or failed to initialize, `self._fm175xx_reader.self_test()` caused an `AttributeError` instead of a graceful user error.

## Steps to Reproduce
1. Disconnect or simulate a stalled RFID reader where `self_test_stage` never transitions to `FM175XX_SELF_TEST_STAGE_STOP`.
2. Issue the G-code command `FILAMENT_DT_SELF_TEST CHANNEL=0 TIMES=10`.
3. Observe that Klippy enters an endless pause loop (`pause(monotonic() + 0.3)`), blocking all further G-code command processing.
4. Issue an emergency stop (`M112`), and observe that the loop fails to abort promptly.

## Proposed Fix / Patch
1. Check that `self._fm175xx_reader is not None`.
2. Introduce a configurable `TIMEOUT` parameter defaulting to `max(10.0, times * 0.2)`.
3. Loop while `not self.printer.is_shutdown()` and raise a timeout error if `monotonic() >= endtime`.
4. Wrap execution in a `try...finally` block that guarantees `self._state[channel] = FILAMENT_DT_STATE_IDLE`.

```diff
--- a/klippy/extras/filament_detect.py
+++ b/klippy/extras/filament_detect.py
@@ -243,6 +243,7 @@ class FilamentDetector:
     def cmd_FILAMENT_DT_SELF_TEST(self, gcmd):
         channel = gcmd.get_int('CHANNEL', None)
         times = gcmd.get_int('TIMES', 100)
+        timeout = gcmd.get_float('TIMEOUT', max(10.0, times * 0.2), minval=0.1)

         if (channel is None):
             raise gcmd.error("CHANNEL must be specified!")
@@ -251,29 +252,40 @@ class FilamentDetector:
             msg = ("channel[%d] is out of range[0, %d]" % (channel, self._channel_nums - 1))
             raise gcmd.error(msg)

+        if self._fm175xx_reader is None:
+            raise gcmd.error("RFID reader fm175xx_reader is not available")
+
         self._state[channel] = FILAMENT_DT_STATE_SELF_TESTING
         finish = False
         test_times = 0
         success_times = 0
         self._self_test_success_cnt = 0
         self._fm175xx_reader.self_test(channel, times)
-        while (1):
-            finish, test_times, success_times = self._fm175xx_reader.self_test_result()
-            if finish:
-                break
-            self.reactor.pause(self.reactor.monotonic() + 0.3)
-
-        msg = ("channel[%d] test times = %d, success times: %d\n" % (
-                channel, test_times, self._self_test_success_cnt))
-        gcmd.respond_info(msg, log=False)
-        msg = ("channel[%d] vendor = %s, main_type: %s, sub_type= %s, argb_color = %08X\n"
-                % (channel,
-                    self._filament_info[channel]['VENDOR'],
-                    self._filament_info[channel]['MAIN_TYPE'],
-                    self._filament_info[channel]['SUB_TYPE'],
-                    self._filament_info[channel]['ARGB_COLOR']))
-        gcmd.respond_info(msg, log=False)
-        self._state[channel] = FILAMENT_DT_STATE_IDLE
+        endtime = self.reactor.monotonic() + timeout
+        try:
+            while not self.printer.is_shutdown():
+                finish, test_times, success_times = self._fm175xx_reader.self_test_result()
+                if finish:
+                    break
+                if self.reactor.monotonic() >= endtime:
+                    raise gcmd.error("Self test timed out after %.1fs on channel %d"
+                                     % (timeout, channel))
+                self.reactor.pause(self.reactor.monotonic() + 0.3)
+            if not finish:
+                raise gcmd.error("Self test aborted due to printer shutdown")
+
+            msg = ("channel[%d] test times = %d, success times: %d\n" % (
+                    channel, test_times, self._self_test_success_cnt))
+            gcmd.respond_info(msg, log=False)
+            msg = ("channel[%d] vendor = %s, main_type: %s, sub_type= %s, argb_color = %08X\n"
+                    % (channel,
+                        self._filament_info[channel]['VENDOR'],
+                        self._filament_info[channel]['MAIN_TYPE'],
+                        self._filament_info[channel]['SUB_TYPE'],
+                        self._filament_info[channel]['ARGB_COLOR']))
+            gcmd.respond_info(msg, log=False)
+        finally:
+            self._state[channel] = FILAMENT_DT_STATE_IDLE
```

## Regression & Safety Verification
- **Automated Unit Tests:**
  - `test/test_bug_stack04.py`: Verified timeout handling, immediate shutdown abort, successful completion, and defensive reader null guard.
- **Whitespace Compliance:** Verified with `scripts/check_whitespace.py` (0 errors).
- **Regression:** Verified that normal self test execution with active RFID hardware completes as expected.

