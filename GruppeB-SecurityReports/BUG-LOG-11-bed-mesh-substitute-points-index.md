# Security & Bug Report: BUG-LOG-11 - Erroneous Index Comparison in `_gen_faulty_path()`

## 1. Summary / Description
A logic indexing error exists in `klippy/extras/bed_mesh.py` within the `_gen_faulty_path()` generator of `ProbeManager`. The code checked `sorted_sub_idx[idx] == idx` to determine if the currently evaluated point index corresponds to the first corner of a faulty region.

Because `sorted_sub_idx` is a list of substituted grid indices, indexing `sorted_sub_idx[idx]` using the global mesh grid point index `idx` raises an `IndexError` whenever `idx >= len(sorted_sub_idx)` or produces an incorrect boolean result, causing faulty region corner substitution calculations to behave incorrectly.

## 2. Component / Affected Files
- **Affected File:** `klippy/extras/bed_mesh.py`
- **Affected Method:** `ProbeManager._gen_faulty_path()`
- **Lines Affected:** Lines ~1458-1463

## 3. Classification
- **Category:** Logic Bug / Out of Bounds Indexing
- **Group:** Group B (Snapmaker U1 Specific Extension)
- **Severity:** Medium

## 4. Root Cause Analysis
In `ProbeManager._gen_faulty_path()`:
```python
sorted_sub_idx = sorted(self.substitutes.keys())
if sub_cnt == 2 and idx < len(sorted_sub_idx):
    first_corner = sorted_sub_idx[idx] == idx
```
The intention is to check whether the current point `idx` is the first corner among the substitute points (`sorted_sub_idx[0]`). By indexing `sorted_sub_idx[idx]`, the code treated `idx` as an index into the list of keys instead of comparing `idx` against the key value itself. When `idx` exceeds the number of substitute points (which is almost always true on a mesh with many points and few faulty regions), `first_corner` defaulted to `False` incorrectly or evaluated garbage logic.

## 5. Steps to Reproduce
1. Configure a `bed_mesh` with `faulty_region_1_min` and `faulty_region_1_max`.
2. Generate probe points or run `BED_MESH_OUTPUT PGP=1`.
3. Deterministic batch test: `test/klippy/bug_log11_bed_mesh.test`.

## 6. Proposed Fix / Patch
The fix checks whether `idx` matches the first corner index directly (`idx == sorted_sub_idx[0]`):

```diff
--- a/klippy/extras/bed_mesh.py
+++ b/klippy/extras/bed_mesh.py
@@ -1458,8 +1458,8 @@ class ProbeManager:
         # Check to see if this is the first corner
         first_corner = False
         sorted_sub_idx = sorted(self.substitutes.keys())
-        if sub_cnt == 2 and idx < len(sorted_sub_idx):
-            first_corner = sorted_sub_idx[idx] == idx
+        if sub_cnt == 2 and sorted_sub_idx:
+            first_corner = (idx == sorted_sub_idx[0])
         yield subs[0], True
         if sub_cnt == 1:
             return
```

## 7. Regression & Safety Verification
- **Deterministic Test:** Executed `test/klippy/bug_log11_bed_mesh.test` with `scripts/test_klippy.py`.
- **Formatting & CI Check:** Verified via `scripts/check_whitespace.py` (0 errors, max line length <= 80 characters, LF line endings).
- **Result:** Test completed with exit code 0 (`All test cases passed`).

