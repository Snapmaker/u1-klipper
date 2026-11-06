# BUG-DEAD-02: Permanent Mutex Deadlocks in `filament_feed.py` and `filament_feed_fac_test.py`

## Summary
In `klippy/extras/filament_feed.py` and `klippy/extras/filament_feed_fac_test.py`, `FeedMotor.run()` and `FeedMotor.run_one_cycle()` locked `self._mutex_lock = True` without a `try...finally` block to release it on errors. If any PWM, timer, or reactor exception occurred during execution, `self._mutex_lock` remained `True` forever. Any subsequent motor command blocked indefinitely in `while self._mutex_lock:`. Furthermore, in `FilamentFeed._load_prepare()`, `self.channel_active = ch` was set prior to entering the `try` block, permanently deadlocking the filament channel if parameter calculation raised an exception before `try` began.

## Component / Affected Files
- **File:** `klippy/extras/filament_feed.py`
  - **Affected Classes & Functions:** `FeedMotor.run()`, `FeedMotor.run_one_cycle()`, `FilamentFeed._load_prepare()`
  - **Lines:** 315-385, 770-800
- **File:** `klippy/extras/filament_feed_fac_test.py`
  - **Affected Classes & Functions:** `FeedMotor.run()`, `FeedMotor.run_one_cycle()`
  - **Lines:** 80-145

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Firmware
- **Severity:** Critical (Filament Feeder Deadlock / Permanent Channel Freeze)

## Root Cause Analysis
1. **Unprotected Mutex Acquisition:**
   In `FeedMotor.run()` and `FeedMotor.run_one_cycle()`, the mutex was acquired via:
   ```python
   while self._mutex_lock:
       self.reactor.pause(self.reactor.monotonic() + 0.1)
   self._mutex_lock = True
   ...
   self._mutex_lock = False
   ```
   If an exception was raised during execution, the assignment `self._mutex_lock = False` was bypassed, permanently bricking the motor interface until Klipper restarted.
2. **Channel State Lockout Outside `try`:**
   In `FilamentFeed._load_prepare()`, `self.channel_active = ch` was set before the `try:` block. If any helper or configuration query between lines 770 and 785 threw an exception, the `finally: self.channel_active = None` at line 1606 was never reached, locking the feeder channel permanently.
3. **Missing Shutdown Abort in Polling Loop:**
   `while self._mutex_lock:` and `while self.channel_active != None:` failed to check `not self.printer.is_shutdown()`, resulting in unkillable greenlet loops during emergency stops.

## Steps to Reproduce
1. In a test environment, trigger an exception inside `FeedMotor._run()` (e.g. invalid MCU communication or motor disconnection).
2. Attempt to call `FeedMotor.run()` again.
3. Observe that the second call hangs indefinitely in `while self._mutex_lock:`.

## Proposed Fix / Patch
1. Wrap all motor movement logic in `FeedMotor.run()` and `FeedMotor.run_one_cycle()` in `try...finally: self._mutex_lock = False`.
2. Add `not self.printer.is_shutdown()` checks to all mutex wait loops.
3. In `FilamentFeed._load_prepare()`, move the `try:` block to immediately enclose `self.channel_active = ch`.

```diff
--- a/klippy/extras/filament_feed.py
+++ b/klippy/extras/filament_feed.py
@@ -315,9 +316,12 @@ class FeedMotor:
     def run(self, dir, value):
-        while self._mutex_lock:
+        while self._mutex_lock and not self.printer.is_shutdown():
             self.reactor.pause(self.reactor.monotonic() + 0.1)
+        if self.printer.is_shutdown():
+            return
         self._mutex_lock = True
+        try:
             val = max(0, min(self.max_value, value))
...
+        finally:
+            self._mutex_lock = False
```

## Regression & Safety Verification
- **Automated Unit Tests:**
  - `test/test_bug_dead02.py`: Verified `FeedMotor` releases `_mutex_lock` under exceptions in `filament_feed.py` and `filament_feed_fac_test.py`, and verified clean exit upon `printer.is_shutdown()`.
- **Whitespace Compliance:** Verified with `scripts/check_whitespace.py` (0 errors).
- **Regression:** Verified normal motor run cycles complete cleanly.

