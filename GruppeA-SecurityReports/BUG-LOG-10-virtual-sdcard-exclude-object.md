# BUG-LOG-10: `EXCLUDE_OBJECT` Crash, Dead Code, and Hardcoded Z-Stepper Assumption in `virtual_sdcard.py`

## Summary
In `klippy/extras/virtual_sdcard.py`:
1. In `GCodeStateTracker.update_position()`, the `EXCLUDE_OBJECT` handler called `self.get(line, params, 'NAME').upper()` without providing a default value. When `EXCLUDE_OBJECT` was issued with `CURRENT=1` or `RESET=1` (omitting `NAME`), `self.get()` unconditionally raised `command_error("Error on ...: missing NAME")`. Furthermore, attempting to call `.upper()` on `None` when `default=None` was supplied resulted in `AttributeError`. As a consequence, `CURRENT` and `RESET` parameters could never be executed (dead code) and always triggered exceptions.
2. In `VirtualSD.flush_pl_z_homing_stepper_z_info()`, the Z-stepper position was hardcoded as `stepper_mcu_pos[2]` indexing the list returned by `kin.get_steppers()`. If kinematics configurations had fewer than 3 steppers or an alternate stepper ordering, this raised `IndexError: list index out of range` or captured the wrong axis stepper position.

## Component / Affected Files
- **File:** `klippy/extras/virtual_sdcard.py`
  - **Affected Classes & Methods:**
    - `VirtualSD.flush_pl_z_homing_stepper_z_info()` (lines 1615–1635)
    - `GCodeStateTracker.update_position()` (`EXCLUDE_OBJECT` and `EXCLUDE_OBJECT_START`, lines 2265–2295)

## Classification
- **Category:** Group A: Upstream Klipper Core / Virtual SDCard
- **Severity:** High (Crash / Broken Functionality / Kinematics State Corruption)

## Root Cause Analysis
- `self.get(line, params, 'NAME')` enforces required parameters when called without `default`. Because `EXCLUDE_OBJECT` syntax supports `RESET=1` and `CURRENT=1` without `NAME`, requiring `NAME` and calling `.upper()` directly on the result caused immediate failure.
- `stepper_mcu_pos[2]` relied on an assumed stepper order index `2` rather than inspecting `kin.rails[2].get_steppers()[0]` or checking stepper naming conventions.

## Steps to Reproduce
1. Feed a G-code stream containing `EXCLUDE_OBJECT CURRENT=1` into `GCodeStateTracker`.
2. Observe `command_error: missing NAME` logged as an unhandled parse error.
3. Call `flush_pl_z_homing_stepper_z_info()` on a kinematics instance with fewer than 3 steppers.
4. Observe `IndexError: list index out of range`.

## Remediation
- In `EXCLUDE_OBJECT`, retrieve `NAME` with `default=None` (`self.get(line, params, 'NAME', None)`), and apply `.upper()` only if `raw_name is not None`.
- In `flush_pl_z_homing_stepper_z_info()`, obtain the primary Z stepper via `kin.rails[2].get_steppers()[0]` or search for `stepper_z`, guarding against out-of-bounds list access.

## Verification
- Unit test implemented in `test/test_bug_log10.py` verifying `EXCLUDE_OBJECT CURRENT=1`, `RESET=1`, `NAME=cube`, and `flush_pl_z_homing_stepper_z_info()` with fewer than 3 steppers.
- Executed in `u1sim` container: 4 tests passed in 0.007s.
- `scripts/check_whitespace.py` verified with 0 warnings.

