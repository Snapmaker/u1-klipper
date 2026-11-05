# Bug Report: [DIV-04] Division by Zero in Bed Mesh Fade Position Calculation

## 1. Summary / Description
- **ID:** DIV-04
- **Title:** Division by Zero in Bed Mesh Fade Position Calculation (`bed_mesh.py`)
- **Vulnerability Type:** Denial of Service / Unhandled Arithmetic Exception (CWE-369: Divide By Zero)
- **Severity:** **HIGH** (CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H - Base Score: 5.5)
- **Description:** 
  In `BedMesh.get_position()`, when calculating the fading adjustment factor within the transition range (`max(...) >= self.fade_start`), the calculation formula computes `factor = ((self.fade_end + self.fade_target - fade_z_pos) / (self.fade_dist - z_adj))`. If the mesh adjustment value `z_adj` (`max_adj - self.fade_target`) equals the configured fade distance `self.fade_dist`, the denominator becomes `0.0`. This triggers an unhandled `ZeroDivisionError`, immediately terminating the Klippy host process during coordinate queries or move calculations.

---

## 2. Component / Affected Files
- **Component:** Klippy Host Daemon / Extras / Bed Mesh
- **Affected File:** `klippy/extras/bed_mesh.py`
- **Affected Functions:** `BedMesh.get_position()`, `BedMesh.get_z_factor()`
- **Test Files:**
  - `test/klippy/bug_div04_bed_mesh.cfg`
  - `test/klippy/bug_div04_bed_mesh.test`

---

## 3. Classification
- **Category:** **Group B (Snapmaker U1 Specific)**
- **Rationale:** Tracked under Group B for `u1-klipper` integration and regression testing on the U1 toolhead coordinate pipeline.

---

## 4. Root Cause Analysis
In `BedMesh.get_position()`:
```python
x, y, z, e = self.toolhead.get_position()
max_adj = self.z_mesh.calc_z(x, y)
factor = 1.
z_adj = max_adj - self.fade_target
fade_z_pos = z + self.tool_offset
if min(fade_z_pos, (fade_z_pos - max_adj)) >= self.fade_end:
    factor = 0.
elif max(fade_z_pos, (fade_z_pos - max_adj)) >= self.fade_start:
    factor = ((self.fade_end + self.fade_target - fade_z_pos) /
              (self.fade_dist - z_adj))
```
1. While `BedMesh.set_mesh()` verifies `max(abs(min_z), abs(max_z)) < self.fade_dist`, the value of `z_adj` is computed as `max_adj - self.fade_target`.
2. When `self.fade_target` is non-zero (or negative), `z_adj` can equal `self.fade_dist` even if individual points lie within bounds.
3. When `z_adj == self.fade_dist`, `(self.fade_dist - z_adj)` evaluates to `0.0`.
4. Python raises `ZeroDivisionError: float division by zero`, crashing Klippy during active print moves or `M114` status queries.
5. In addition, `get_z_factor()` divides by `self.fade_dist` without zero guards if `fade_dist` approaches zero.

---

## 5. Steps to Reproduce
1. Configure `fade_start: 1.0`, `fade_end: 2.0` (`fade_dist: 1.0`) and `fade_target: -0.4`.
2. Load a mesh profile containing measured points of `0.6` (`z_adj = 0.6 - (-0.4) = 1.0`).
3. Query position via `M114` or execute a move within the fade transition zone.
4. **Behavior before fix:** Klippy crashes with `ZeroDivisionError: float division by zero`.
5. **Behavior after fix:** Klippy guards against denominators within `abs(denom) < 1e-9`, clamping `factor` safely to `0.` without error.

---

## 6. Proposed Fix / Patch
```diff
--- a/klippy/extras/bed_mesh.py
+++ b/klippy/extras/bed_mesh.py
@@ -191,8 +191,10 @@ class BedMesh:
     def get_z_factor(self, z_pos):
         z_pos += self.tool_offset
         if z_pos >= self.fade_end:
             return 0.
         elif z_pos >= self.fade_start:
+            if abs(self.fade_dist) < 1e-9:
+                return 0.
             return (self.fade_end - z_pos) / self.fade_dist
         else:
             return 1.
@@ -215,8 +217,12 @@ class BedMesh:
             elif max(fade_z_pos, (fade_z_pos - max_adj)) >= self.fade_start:
                 # Likely in the process of fading out adjustment.
                 # Because we don't yet know the gcode z position, use
                 # algebra to calculate the factor from the toolhead pos
-                factor = ((self.fade_end + self.fade_target - fade_z_pos) /
-                          (self.fade_dist - z_adj))
-                factor = constrain(factor, 0., 1.)
+                denom = self.fade_dist - z_adj
+                if abs(denom) < 1e-9:
+                    factor = 0.
+                else:
+                    factor = ((self.fade_end + self.fade_target - fade_z_pos) /
+                              denom)
+                    factor = constrain(factor, 0., 1.)
```

---

## 7. Regression & Safety Verification
- **Automated Deterministic Test:**
  - Configuration: `test/klippy/bug_div04_bed_mesh.cfg`
  - Test Script: `test/klippy/bug_div04_bed_mesh.test`
  - Test Execution:
    ```bash
    python scripts/test_klippy.py -d test/klippy -t /tmp -v test/klippy/bug_div04_bed_mesh.test
    ```
- **Test Result:**
  - Test successfully executed without arithmetic exceptions (`All 1 test cases passed`).

