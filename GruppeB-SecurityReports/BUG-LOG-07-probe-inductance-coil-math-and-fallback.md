# BUG-LOG-07: Copy-Paste Coordinate Fallback and Degenerate Circle Center Math in `probe_inductance_coil.py`

## Summary
In `klippy/extras/probe_inductance_coil.py`, plate detection and nozzle offset calibration contained critical mathematical and logical defects:
1. In `_cmd_DETECT_BUILD_PLATE()`, when retrieving macro coordinates, `macro.variables.get('hole_z', hole_x)` erroneously specified `hole_x` (~150 mm) as the default fallback for `hole_z` (~0-2 mm). Omitting `hole_z` from the macro triggered a severe head crash.
2. `find_circle_center(A, B, C)` evaluated perpendicular bisector slopes using heuristics that divided by zero or failed on horizontal/vertical chords, and lacked collinearity validation.
3. `find_circle_center_least_squares(points)` called `np.linalg.lstsq` without verifying rank or output sanity. Collinear probe samples caused singular solutions, producing `NaN`, `inf`, or extreme coordinates that caused rapid collision moves.

## Component / Affected Files
- **File:** `klippy/extras/probe_inductance_coil.py`
  - **Affected Classes & Functions:** `find_circle_center()`, `ProbeCommandHelper.find_circle_center_least_squares()`, `ProbeCommandHelper.cmd_PROBE_XYZ_OFFSET_CALIBRATE()`, `ProbeCommandHelper._cmd_DETECT_BUILD_PLATE()`
  - **Lines:** 49-86, 298-330, 488-501, 1600-1605

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Firmware
- **Severity:** Critical (Physical Hardware Crash / Nozzle Crash into Bed)

## Root Cause Analysis
1. **Typo in Coordinate Fallback:**
   In `_cmd_DETECT_BUILD_PLATE()`:
   ```python
   hole_position = [
       macro.variables.get('hole_x', hole_x),
       macro.variables.get('hole_y', hole_y),
       macro.variables.get('hole_z', hole_x)
   ]
   ```
   Passing `hole_x` as the default for `hole_z` substituted the X bed position (~150 mm) for the Z probing height (~0-2.5 mm).
2. **Fragile Circle Fit Formulas:**
   In `find_circle_center()`, midpoint and slope calculations suffered from division by zero for horizontal/vertical point pairings and lacked a unified determinant solver.
3. **Unchecked Least Squares Rank and Plausibility:**
   `find_circle_center_least_squares()` fit a 3-parameter circle equation ($2 c_x x + 2 c_y y + c = x^2 + y^2$) without checking `rank < 3`. Collinear points generated wild coefficients. Furthermore, `cmd_PROBE_XYZ_OFFSET_CALIBRATE()` moved directly to the calculated coordinates without bounding maximum deviation from the starting position.

## Steps to Reproduce
1. In `klippy`, call `cmd_DETECT_BUILD_PLATE` with a `_DETECT_PLATE` macro that does not specify `hole_z`.
2. Observe `hole_position[2]` evaluate to ~150 mm, commanding a crash into the build plate.
3. Supply collinear points `[(0,0), (1,1), (2,2)]` to `find_circle_center` or `find_circle_center_least_squares`.
4. Observe unhandled division or uncontrolled motion coordinates.

## Proposed Fix / Patch
1. Correct line 1603 fallback to `macro.variables.get('hole_z', hole_z)`.
2. Rewrite `find_circle_center()` using the standard 3-point determinant formulation with non-zero determinant validation (`|D| >= 1e-9`).
3. Require `rank == 3`, finite coordinates, and minimum 3 points in `find_circle_center_least_squares()`.
4. Validate that calculated circle center does not exceed `max_center_deviation` (default 20.0 mm) before executing moves.

## Regression & Safety Verification
- **Automated Unit Tests:**
  - `test/test_bug_log07.py`: Verified exact mathematical center resolution, collinear point rejection in both analytical and least squares algorithms, underdetermined sample rejection, and correct `hole_z` fallback behavior.
- **Whitespace Compliance:** Verified with `scripts/check_whitespace.py` (0 errors).
- **Regression:** Verified normal probe offset calibration and plate detection remain fully functional.

