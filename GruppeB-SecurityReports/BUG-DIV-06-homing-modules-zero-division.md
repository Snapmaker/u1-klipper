# BUG-DIV-06: Division by Zero in `homing_precise_corexy.py`, `homing_xyz_override.py`, `auto_screws_tilt_adjust.py`, and `homing.py`

## Summary
Several homing and bed alignment modules contained unguarded divisions susceptible to `ZeroDivisionError: float division by zero`:
1. In `klippy/extras/homing_precise_corexy.py`, `phase_backoff_steps()` computed `(1024 / self.x_tmc_module.get_phase_offset()[1])`. If the TMC driver returned 0 phases, a zero-division exception aborted precision homing.
2. In `klippy/extras/homing_xyz_override.py`, `x_step = (max_x - min_x) / (x_count - 1)` threw a `ZeroDivisionError` when `x_count` or `y_count` was 1.
3. In `klippy/extras/auto_screws_tilt_adjust.py`, `probe_finalize()` divided by `len(z_values)` with an empty list of positions.
4. In `klippy/extras/homing.py`, `retract_r = min(1., hi.retract_dist / move_d)` divided by `move_d` when total travel distance was `0.0`.

## Component / Affected Files
- **Files:**
  - `klippy/extras/homing_precise_corexy.py` (Lines 105-125)
  - `klippy/extras/homing_xyz_override.py` (Lines 210-212)
  - `klippy/extras/auto_screws_tilt_adjust.py` (Lines 205-210)
  - `klippy/extras/homing.py` (Lines 238-241)

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules & Upstream Overrides / Host Python
- **Severity:** High (Klippy Service Crash / Homing Move Abort)

## Root Cause Analysis
- In `homing_precise_corexy.py`: TMC phase offset tuple indexing `get_phase_offset()[1]` was inverted without checking `> 0`.
- In `homing_xyz_override.py`: Mesh grid step size calculation did not handle 1D or single-point meshes (`x_count - 1 == 0`).
- In `auto_screws_tilt_adjust.py`: Calling `probe_finalize()` when probe points were aborted or empty resulted in `0` length list division.
- In `homing.py`: Calculating axis retraction ratio when the start and home positions coincided (`move_d == 0.0`) triggered zero division.

## Steps to Reproduce
1. In `homing_precise_corexy.py`, trigger `phase_backoff_steps` when TMC returns `phase_offset = (0, 0)`.
2. In `homing_xyz_override.py`, configure a single-point bed mesh (`x_count=1`).
3. In `homing.py`, execute a second homing move when `homepos == startpos` (`move_d = 0.0`).
4. All result in unhandled `ZeroDivisionError` crashing Klippy.

## Proposed Fix / Patch
```diff
diff --git a/klippy/extras/homing_precise_corexy.py b/klippy/extras/homing_precise_corexy.py
--- a/klippy/extras/homing_precise_corexy.py
+++ b/klippy/extras/homing_precise_corexy.py
@@ -106,2 +106,12 @@ class HomingPreciseCorexy:
-        x_backoff_step = (([1, -1][x_backoff_dir == 1]*self.x_tmc_module.query_phase()) % 1024) / (1024 / self.x_tmc_module.get_phase_offset()[1])
-        y_backoff_step = (([1, -1][y_backoff_dir == 1]*self.y_tmc_module.query_phase()) % 1024) / (1024 / self.y_tmc_module.get_phase_offset()[1])
+        x_phase_offset = self.x_tmc_module.get_phase_offset()
+        x_phases = x_phase_offset[1] if len(x_phase_offset) > 1 else 0
+        if x_phases <= 0:
+            raise self.printer.command_error("Invalid TMC phase configuration for stepper_x")
+        x_scale = 1024.0 / x_phases
+        x_backoff_step = (([1, -1][x_backoff_dir == 1]*self.x_tmc_module.query_phase()) % 1024) / x_scale

diff --git a/klippy/extras/homing_xyz_override.py b/klippy/extras/homing_xyz_override.py
--- a/klippy/extras/homing_xyz_override.py
+++ b/klippy/extras/homing_xyz_override.py
@@ -210,2 +210,2 @@ class HomingXYZOverride:
-            x_step = (max_x - min_x) / (x_count - 1)
-            y_step = (max_y - min_y) / (y_count - 1)
+            x_step = (max_x - min_x) / (x_count - 1) if x_count > 1 else 0.0
+            y_step = (max_y - min_y) / (y_count - 1) if y_count > 1 else 0.0

diff --git a/klippy/extras/auto_screws_tilt_adjust.py b/klippy/extras/auto_screws_tilt_adjust.py
--- a/klippy/extras/auto_screws_tilt_adjust.py
+++ b/klippy/extras/auto_screws_tilt_adjust.py
@@ -206,3 +206,3 @@ class AutoScrewsTiltAdjust:
-        self.target_z = sum(z_values) / len(z_values)
-        self.min_z = min(z_values)
-        self.max_z = max(z_values)
+        self.target_z = sum(z_values) / len(z_values) if z_values else 0.0
+        self.min_z = min(z_values) if z_values else 0.0
+        self.max_z = max(z_values) if z_values else 0.0

diff --git a/klippy/extras/homing.py b/klippy/extras/homing.py
--- a/klippy/extras/homing.py
+++ b/klippy/extras/homing.py
@@ -239,1 +239,1 @@ class HomingMove:
-                retract_r = min(1., hi.retract_dist / move_d)
+                retract_r = min(1., hi.retract_dist / move_d) if move_d > 0. else 0.
```

## Verification
- Unit test `test/test_bug_div06.py` verified:
  - Validates `homing_precise_corexy` with 0 and 1024 TMC phases.
  - Validates `homing_xyz_override` with single point mesh.
  - Validates `auto_screws_tilt_adjust` with empty position list.
  - Validates `homing` with 0.0 travel distance.
- All 5 test cases pass cleanly.

