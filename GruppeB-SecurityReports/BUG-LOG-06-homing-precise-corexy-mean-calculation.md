# BUG-LOG-06: Erroneous Mean Calculation Over Subset (`/ 9`) in `homing_precise_corexy.py`

## Summary
In `klippy/extras/homing_precise_corexy.py`, the precision CoreXY homing algorithm performs diagonal multi-point probing across a grid of 9 points (`len(point_sequence) == 9`). In the retry loop (`for revcount in range(...)`), points detected as unstable are re-probed. However, the accumulator `c_acc = [0.0, 0.0]` was cleared at the beginning of each retry round, and only newly re-probed points (`data['revalidate'] == True`) were added to `c_acc`. `origin` was subsequently calculated as `origin = [c_acc[0] / 9.0, c_acc[1] / 9.0]`. When only 1 or 2 points were re-probed, dividing the partial sum of 1 or 2 points by 9 collapsed the calculated origin coordinate to approximately 1/9th of its true physical position, causing catastrophic CoreXY calibration failures or immediate command aborts.

## Component / Affected Files
- **File:** `klippy/extras/homing_precise_corexy.py`
  - **Affected Methods:** `perform_multi_point_diagonal_probing()`
  - **Lines:** 300-335

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Host Python
- **Severity:** Critical (Severe Physical Position Error / CoreXY Calibration Failure / False Aborts)

## Root Cause Analysis
During point revalidation in `perform_multi_point_diagonal_probing`:
```python
for revcount in range(len(point_sequence) // 2):
    c_acc = [0.0, 0.0]
    new_rev_cnt = 0
    for i in range(len(point_sequence)):
        seq = point_sequence[i]
        data = points[i]
        if data['revalidate']:
            ...
            c_acc[0] += data['c_dist'][0]
            c_acc[1] += data['c_dist'][1]
    origin = [c_acc[0] / float(len(point_sequence)), c_acc[1] / float(len(point_sequence))]
```
If only point index 3 had `revalidate == True`, `c_acc` only received `points[3]['c_dist']`. Points 0, 1, 2, 4, 5, 6, 7, 8 (which retained their valid measurements from round 0) were completely omitted from `c_acc`. The subsequent division by `len(point_sequence)` (9) divided the single measurement by 9, introducing an ~89% error in homing origin calculation.

## Steps to Reproduce
1. Initiate CoreXY precision homing (`HOMING_PRECISE_COREXY`).
2. Simulate a slight sensor flutter on 1 of the 9 probe points so that it is marked for revalidation (`data['revalidate'] = True`).
3. In round 1, observe `origin` calculated as 1/9th of the true coordinate, immediately triggering error `"Home calibration point error: dx=... dy=... with origin x=... y=..."`.

## Proposed Fix / Patch
```diff
diff --git a/klippy/extras/homing_precise_corexy.py b/klippy/extras/homing_precise_corexy.py
--- a/klippy/extras/homing_precise_corexy.py
+++ b/klippy/extras/homing_precise_corexy.py
@@ -313,4 +313,4 @@ class HomingPreciseCorexy:
                     if probe_success == True:
                         data['c_dist'][0], data['c_dist'][1], c_a_raw, c_b_raw = self.cal_diagonal_dist_selected(recv_steps, True)
-                        c_acc[0] += data['c_dist'][0]
-                        c_acc[1] += data['c_dist'][1]
                         self.gcode.respond_info("c_a_raw: {}, c_b_raw: {}".format(data['c_dist'][0], data['c_dist'][1]))
@@ -321,2 +321,4 @@ class HomingPreciseCorexy:
+            c_acc[0] = sum(p['c_dist'][0] for p in points)
+            c_acc[1] = sum(p['c_dist'][1] for p in points)
             origin = [c_acc[0] / float(len(point_sequence)), c_acc[1] / float(len(point_sequence))]
```

## Verification
- Unit test `test/test_bug_log06.py` verified:
  - Demonstrates that the unpatched logic reduces the calculated origin from ~104 to ~11.5 when 1 point is re-probed.
  - Confirms that the patched logic sums all 9 points, yielding the exact mathematical average.
  - Test passes cleanly.

