# BUG-DIV-03: Five Unprotected Division-by-Zero Paths in `virtual_sdcard.py`

## Summary
In `klippy/extras/virtual_sdcard.py`, multiple calculations performed floating-point division using factors or acceleration parameters (`speed_factor`, `extrude_factor`, and `max_accel`) without validating that the denominator was strictly positive (`> 0.0`). When zero factors were loaded from corrupted power-loss state, calculated from edge-case G-code inputs (e.g. `M221 S0`), or uninitialized, the host process crashed with an unhandled `ZeroDivisionError`.

## Component / Affected Files
- **File:** `klippy/extras/virtual_sdcard.py`
  - **Affected Classes & Methods:**
    - `VirtualSD.save_pause_state()` (line 1330)
    - `GCodeStateTracker._get_gcode_speed()` (line 2055)
    - `GCodeStateTracker.update_position()` (`M221` line 2158, `SET_VELOCITY_LIMIT` line 2182 & 2185)
    - `GCodeStateTracker.set_factors()` (line 2295)

## Classification
- **Category:** Group A: Upstream Klipper Core / Virtual SDCard
- **Severity:** High (Crash / Denial of Service / Print Recovery Abortion)

## Root Cause Analysis
1. In `save_pause_state()`:
   `_pl_save_data['speed'] = state_copy['speed'] / state_copy['speed_factor']`
   When `state_copy['speed_factor']` was `0.0`, division triggered `ZeroDivisionError`.
2. In `GCodeStateTracker._get_gcode_speed()`:
   `return self.speed / self.speed_factor`
   If `self.speed_factor <= 0.0`, division failed immediately.
3. In `GCodeStateTracker.update_position()` handling `M221`:
   `e_value = (last_e_pos - self.base_position[3]) / self.extrude_factor`
   A zero `extrude_factor` resulted in an unhandled zero division.
4. In `SET_VELOCITY_LIMIT`:
   `min_cruise_ratio = 1. - min(1., (req_accel_to_decel / self.max_accel))`
   If `self.max_accel` was zero, division by zero was raised.
5. In `set_factors()`:
   `self.speed = speed_factor * self.speed / self.speed_factor`
   If the existing `self.speed_factor` was zero, division by zero was raised.

## Steps to Reproduce
1. Feed a power-loss state file containing `speed_factor: 0.0` or `extrude_factor: 0.0`.
2. Execute `update_position("M221 S100")` or query speed via `_get_gcode_speed()`.
3. Observe unhandled `ZeroDivisionError: float division by zero`.

## Remediation
- Across all five division sites, defensively validate that the divisor is strictly positive (`> 0.0`).
- If zero or non-positive, clamp/fallback to standard operational defaults (`1.0` or `1. / 60.`).

## Verification
- Unit test implemented in `test/test_bug_div03.py` verifying all 5 division sites with zero and negative values.
- Executed in `u1sim` container: 5 tests passed in 0.001s.
- `scripts/check_whitespace.py` verified with 0 warnings.

