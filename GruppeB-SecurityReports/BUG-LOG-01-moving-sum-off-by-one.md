# BUG-LOG-01: Off-by-One Bug in `get_sum()` Triggers Spurious Inductance Z-Sensor Trips in `src/stm32/inductance_coil.c`

## Summary
In `src/stm32/inductance_coil.c`, `get_sum(MOVING_SUM *ms)` calculates the sliding window sum of capture pulses. The filter is intended to suppress output (returning 0) until the circular buffer is completely saturated with `ms->bufferSize` samples. However, the guard check was written as `if (ms->count + 1 < ms->bufferSize || ms->bufferSize == 0) return 0;`. With the standard Snapmaker configuration of `bufferSize = 2`, after receiving only the first sample (`count = 1`), `1 + 1 < 2` evaluates to false, causing `get_sum()` to prematurely return `ms->sum`. Because trigger comparison limits (`cmp_trg_cnt_ht`, `cmp_trg_cnt_lt`) are scaled for a complete window of `bufferSize` samples, comparing a single sample against a double-scaled threshold halved the apparent frequency, causing false probe trigger events.

## Component / Affected Files
- **File:** `src/stm32/inductance_coil.c`
  - **Affected Methods:** `get_sum()`
  - **Lines:** 128-132

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / MCU Firmware C
- **Severity:** Critical (Spurious Z-Probe Triggers / Bed Leveling Aborts / Premature Probe Stop)

## Root Cause Analysis
The structure `MOVING_SUM` tracks how many samples have been inserted into the buffer via `ms->count`, incremented on each `add_value()` call up to `ms->bufferSize`.
The unpatched check:
```c
uint64_t get_sum(MOVING_SUM *ms) {
  if (ms->count + 1 < ms->bufferSize || ms->bufferSize == 0)
    return 0;
  return ms->sum;
}
```
For `ms->bufferSize = 2`:
- At `ms->count = 0`: `0 + 1 < 2` (1 < 2) is true -> returns 0.
- At `ms->count = 1`: `1 + 1 < 2` (2 < 2) is false -> returns `ms->sum` with only 1 sample!
- Because `cmp_trg_cnt_ht` and `cmp_trg_cnt_lt` expect the sum of 2 consecutive capture periods, returning a 1-sample sum causes a 50% deviation against expected trigger limits immediately upon sensor startup or buffer resets (`reset_buffer(&g_freq_cal_info.moving_sum)`).

## Steps to Reproduce
1. Configure `inductance_coil` with standard `cal_window_size = 2`.
2. Push a single sample into the moving sum filter.
3. Observe `get_sum()` returning non-zero before the filter window has filled, causing an immediate false trigger in `InputCapture_IRQHandler`.

## Proposed Fix / Patch
```diff
diff --git a/src/stm32/inductance_coil.c b/src/stm32/inductance_coil.c
--- a/src/stm32/inductance_coil.c
+++ b/src/stm32/inductance_coil.c
@@ -128,3 +128,3 @@ uint64_t get_sum(MOVING_SUM *ms) {
-  if (ms->count + 1 < ms->bufferSize || ms->bufferSize == 0)
+  if (ms->bufferSize == 0 || ms->count < ms->bufferSize)
     return 0;
   return ms->sum;
```

## Verification
- Unit test `test/test_bug_log01_inductance_coil.c` verified via GCC in container:
  - Validates that for `bufferSize = 2`, `count = 1` yields 0, and `count = 2` yields the full sum.
  - Validates window sizes 4 and 0.
  - All assertions pass without errors.

