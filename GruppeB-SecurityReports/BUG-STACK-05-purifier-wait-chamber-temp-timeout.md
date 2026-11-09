# BUG-STACK-05: Broken Timeout in `cmd_WAIT_CHAMBER_TEMP` in `purifier.py`

## Summary
In `klippy/extras/purifier.py`, `cmd_WAIT_CHAMBER_TEMP()` allowed users to wait until the chamber reached a target temperature with a specified timeout. Although `wait_timeout_time` was computed prior to the loop, lines 1187-1189 checked if `timer_execution_counter != self.timer_execution_counter` and continually overwrote `wait_timeout_time = self.reactor.monotonic() + 5*self.check_interval + 2`. Because the periodic check timer continuously incremented `self.timer_execution_counter`, the deadline was repeatedly pushed into the future, causing the command to hang indefinitely if the desired chamber temperature was never reached.

## Component / Affected Files
- **File:** `klippy/extras/purifier.py`
- **Affected Functions:** `cmd_WAIT_CHAMBER_TEMP()`
- **Lines:** 1156-1193

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Firmware
- **Severity:** High (Infinite Loop / Print Pipeline Freeze / Denial of Service)

## Root Cause Analysis
1. **Perpetual Deadline Reset:**
   In `cmd_WAIT_CHAMBER_TEMP`:
   ```python
   wait_timeout_time = cur_time + timeout + 5
   ...
   while self.preheat_wait_enabled and self.reactor.monotonic() < wait_timeout_time and not self.printer.is_shutdown() and self._power_detected:
       ...
       if timer_execution_counter != self.timer_execution_counter:
           wait_timeout_time = self.reactor.monotonic() + 5*self.check_interval + 2
           timer_execution_counter = self.timer_execution_counter
   ```
   Every invocation of `_periodic_status_check` incremented `self.timer_execution_counter`. This triggered the reset condition, resetting the timeout relative to current time rather than the initial user requested duration.
2. **Discard of User-Specified Parameter:**
   The `TIMEOUT` argument passed to `cmd_WAIT_CHAMBER_TEMP` was effectively discarded after the first periodic timer tick, locking Klippy into an unbounded wait.

## Steps to Reproduce
1. Ensure the printer has a purifier module configured.
2. Execute `WAIT_CHAMBER_TEMP TEMPERATURE=70 TIMEOUT=10` on a cool bed/chamber that cannot reach 70°C within 10 seconds.
3. Observe that after 15 seconds, the printer remains in the waiting state indefinitely.
4. G-code execution cannot proceed to subsequent print steps until cancelled or shut down.

## Proposed Fix / Patch
Remove lines 1187-1189 and the unused local `timer_execution_counter` initialization, preserving the user-specified `wait_timeout_time` as the true hard timeout deadline.

```diff
--- a/klippy/extras/purifier.py
+++ b/klippy/extras/purifier.py
@@ -1156,7 +1155,6 @@ class Purifier:

         # Calculate wait timeout based on user-specified timeout
         wait_timeout_time = cur_time + timeout + 5  # Adding small buffer
-        timer_execution_counter = self.timer_execution_counter
         last_info_time = cur_time

         self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=PREHEAT_CHAMBER")
@@ -1185,9 +1183,6 @@ class Purifier:
                 last_info_time = current_time

             self.reactor.pause(self.reactor.monotonic() + 0.5)
-            if timer_execution_counter != self.timer_execution_counter:
-                wait_timeout_time = self.reactor.monotonic() + 5*self.check_interval + 2
-                timer_execution_counter = self.timer_execution_counter
         self._reset_preheat_state()
         self.reactor.pause(self.reactor.monotonic() + 0.5)
         self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=IDLE")
```

## Regression & Safety Verification
- **Automated Unit Tests:**
  - `test/test_bug_stack05.py`: Verified `cmd_WAIT_CHAMBER_TEMP` successfully terminates when the specified timeout expires despite continuous `timer_execution_counter` increments.
  - Verified immediate termination when `printer.is_shutdown()` is asserted or when `preheat_wait_enabled` is cleared.
- **Whitespace Compliance:** Verified with `scripts/check_whitespace.py` (0 errors).
- **Regression:** Verified normal chamber preheating logic functions correctly when temperature targets are satisfied before timeout.

