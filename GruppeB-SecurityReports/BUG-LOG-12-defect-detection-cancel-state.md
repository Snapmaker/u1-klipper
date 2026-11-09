# BUG-LOG-12: Unconditional Z-Move and Reset to `PRINTING` in `finally:` Block After Print Cancellation (`defect_detection.py`)

## Summary
In `klippy/extras/defect_detection.py`, the bed defect detection handler `cmd_DEFECT_DETECTION_DETECT_BED` executes an iterative probing routine enclosed in a `try...finally` block. If a print was cancelled (e.g. `pause_resume:cancel` setting `self._request_cancel_print = True`) or if the printer was shut down (`self.printer.is_shutdown()`), early returns were executed from within the probe loop. However, the subsequent `finally:` block unconditionally commanded physical toolhead movements via `toolhead.manual_move([None, None, ...], 30)` and executed `SET_MAIN_STATE MAIN_STATE=PRINTING ACTION=IDLE`, overwriting the cancelled state and restoring active printing status while moving the printhead unexpectedly.

## Component / Affected Files
- **File:** `klippy/extras/defect_detection.py`
  - **Affected Methods:** `cmd_DEFECT_DETECTION_DETECT_BED()`
  - **Lines:** 800-809, 828-854, 888-965

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Host Python
- **Severity:** High (State Corruption / Physical Collision / Post-Abort Movement)

## Root Cause Analysis
In `cmd_DEFECT_DETECTION_DETECT_BED`:
```python
try:
    ...
    for probe_times in range(probe_max_times):
        if self._request_cancel_print == True:
            return
        ...
finally:
    current_pos = list(toolhead.get_position())
    toolhead.manual_move([None, None, max(0, min(current_pos[2] + 5, start_pos[2]))], 30)
    toolhead.wait_moves()
    ...
    if machine_state_manager is not None:
        machine_sta = machine_state_manager.get_status()
        if str(machine_sta["main_state"]) == "PRINTING":
            self.gcode.run_script_from_command("SET_MAIN_STATE MAIN_STATE=PRINTING ACTION=IDLE")
```
When `_request_cancel_print` became `True` or when the printer entered a shutdown state, returning early from the loop triggered the `finally:` block. Inside `finally:`, physical movement (`manual_move`) was initiated regardless of whether the print was cancelled or aborted. Furthermore, `machine_state_manager` status was reset to `ACTION=IDLE` under `MAIN_STATE=PRINTING`, masking the cancellation state and causing inconsistent machine state transitions.

## Steps to Reproduce
1. Start bed defect detection via `DEFECT_DETECTION_DETECT_BED`.
2. Issue a print cancellation (`CANCEL_PRINT` or triggering `pause_resume:cancel` event).
3. The probe loop detects `self._request_cancel_print == True` and returns.
4. Observe the `finally:` block executing physical toolhead moves and issuing `SET_MAIN_STATE MAIN_STATE=PRINTING ACTION=IDLE`, resetting the printer state back to `PRINTING`.

## Remediation
1. Inside the `try:` block and throughout the iterative probe loop, check both `self._request_cancel_print` and `self.printer.is_shutdown()`.
2. Inside `finally:`, evaluate `is_aborted = self._request_cancel_print or self.printer.is_shutdown()`.
3. Guard physical toolhead movements, machine state updates (`SET_MAIN_STATE`), and `defect_event_handler(CONFIRM_DIRTY_BED)` with `if not is_aborted:`.
4. Guard kinematics notifications (`toolhead.get_kinematics().note_z_not_homed()`) with `if not self.printer.is_shutdown():`.

## Verification
- Unit test created in `test/test_bug_log12.py` verifying normal completion, print cancellation, and printer shutdown scenarios.
- Executed inside the `u1sim` Docker container:
  `python3 /app/klipper/test/test_bug_log12.py` passing with 3 tests.
- Code validated with `scripts/check_whitespace.py` (0 warnings).

