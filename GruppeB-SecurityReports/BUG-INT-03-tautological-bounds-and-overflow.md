# BUG-INT-03: Tautological Bounds Check, Moving Sum 32-Bit Overflow, and Signed Overflow in `src/stm32/inductance_coil.c`

## Summary
In `src/stm32/inductance_coil.c`, three related integer and type-conversion bugs threatened the numerical integrity and hardware safety of the inductive probe Z-trigger mechanism:
1. **Tautological Bounds Check:** `if (tmp_pr_value > INPUT_CAPTURE_CAL_CRM_TIM_MAX_PR_VALUE)` compared a `uint32_t` variable against `0xFFFFFFFFU`. Since an unsigned 32-bit integer can never exceed `UINT32_MAX`, this condition was tautologically false. If `INPUT_CAPTURE_CAL_CRM_TIM_PR(...)` produced a value greater than `4294967295.0` or a negative value, casting to `uint32_t` invoked undefined behavior without triggering the intended `shutdown()`.
2. **Moving Sum 32-Bit Accumulator Overflow:** `MOVING_SUM.sum` was typed as `uint32_t` and accumulated up to 50 timer tick readings. For high periods or high timer values, the cumulative sum wrapped around modulo $2^{32}$, corrupting the moving average calculation and leading to invalid trigger state evaluations.
3. **Signed 32-Bit Overflow in Frequency Addition:** In `update_trigger_frequencies()`, relative mode calculated target trigger frequencies via `freq_param.trg_freq_ht + (int)cur_freq`. If the sum exceeded `INT32_MAX`, signed 32-bit overflow wrapped the expression into a negative value, causing the firmware to reset the high trigger frequency to `0` and suppressing probe triggering.

## Component / Affected Files
- **File:** `src/stm32/inductance_coil.c`
  - **Affected Methods:** `inductance_coil_crm_tmr_init()`, `add_value()`, `get_sum()`, `frequency_conversion()`, `update_trigger_frequencies()`
  - **Lines:** 25-31, 42, 128-132, 328-355, 403-418, 471-480

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / MCU Firmware C
- **Severity:** High (Crash / Spurious Probe Trigger / Arithmetic Undefined Behavior / Bed Crash Risk)

## Root Cause Analysis
1. In `inductance_coil_crm_tmr_init()`:
   ```c
   tmp_pr_value = INPUT_CAPTURE_CAL_CRM_TIM_PR(g_freq_cal_info.freq_cal_cycle);
   if (tmp_pr_value > INPUT_CAPTURE_CAL_CRM_TIM_MAX_PR_VALUE) { // Always false!
       shutdown("input capture calculation cycle is too long!!!");
   }
   ```
   The macro `INPUT_CAPTURE_CAL_CRM_TIM_PR` evaluates as `double`. By truncating to `uint32_t tmp_pr_value` before checking, any out-of-range floating point value was wrapped into an in-range 32-bit integer before the check executed.
2. In `MOVING_SUM`:
   ```c
   typedef struct {
       uint32_t buffer[MAX_BUFFER_SIZE];
       uint32_t bufferSize;
       uint32_t head;
       uint32_t count;
       uint32_t sum; // 32-bit accumulator
   } MOVING_SUM;
   ```
   With `MAX_BUFFER_SIZE = 50`, accumulating up to 50 32-bit timer pulse counts easily exceeds $2^{32}-1 \approx 4.29 \times 10^9$.
3. In `update_trigger_frequencies()`:
   ```c
   if (freq_param.trg_freq_ht + (int)cur_freq < 0)
       d->cal_info.trg_freq_ht = 0;
   else
       d->cal_info.trg_freq_ht = freq_param.trg_freq_ht + cur_freq;
   ```
   `freq_param.trg_freq_ht` is `int32_t`. When `(int)cur_freq` is added and the mathematical sum exceeds `2,147,483,647`, signed integer overflow yields a negative value, falsely hitting the `< 0` branch and resetting `trg_freq_ht` to `0`.

## Steps to Reproduce
1. Configure an input capture calculation cycle larger than 25.5s at 168 MHz. Observe that `tmp_pr_value > 0xFFFFFFFF` fails to detect the overflow.
2. Feed 50 sample periods of `200,000,000` into `add_value()`. Observe `ms->sum` wraps from `10,000,000,000` to `1,410,065,408`.
3. Call `update_trigger_frequencies()` with `trg_freq_ht = 1,500,000,000` and `cur_freq = 1,000,000,000`. Observe `trg_freq_ht` is set to `0`.

## Proposed Fix / Patch
```diff
diff --git a/src/stm32/inductance_coil.c b/src/stm32/inductance_coil.c
--- a/src/stm32/inductance_coil.c
+++ b/src/stm32/inductance_coil.c
@@ -25,7 +25,7 @@ typedef struct {
   uint32_t buffer[MAX_BUFFER_SIZE];
   uint32_t bufferSize;
   uint32_t head;
   uint32_t count;
-  uint32_t sum;
+  uint64_t sum;
 } MOVING_SUM;
 
 struct freq_cal_info {
@@ -42,1 +42,1 @@ struct freq_cal_info {
-  volatile uint32_t capture_pulse_sum;
+  volatile uint64_t capture_pulse_sum;
@@ -128,4 +128,4 @@ void reset_buffer(MOVING_SUM *ms) {
-uint32_t get_sum(MOVING_SUM *ms) {
+uint64_t get_sum(MOVING_SUM *ms) {
   if (ms->count + 1 < ms->bufferSize || ms->bufferSize == 0)
     return 0;
   return ms->sum;
@@ -328,6 +328,8 @@ inductance_coil_crm_tmr_init(struct freq_cal_info *info)
   if (g_freq_cal_info.freq_cal_mode == FIXED_TIME_CAL_MODE) {
-    tmp_pr_value = INPUT_CAPTURE_CAL_CRM_TIM_PR(g_freq_cal_info.freq_cal_cycle);
-    if (tmp_pr_value > INPUT_CAPTURE_CAL_CRM_TIM_MAX_PR_VALUE) {
+    double calc_pr = INPUT_CAPTURE_CAL_CRM_TIM_PR(g_freq_cal_info.freq_cal_cycle);
+    if (calc_pr < 0.0 || calc_pr > (double)INPUT_CAPTURE_CAL_CRM_TIM_MAX_PR_VALUE) {
       shutdown("input capture calculation cycle is too long!!!");
     }
+    tmp_pr_value = (uint32_t)calc_pr;
@@ -350,1 +352,5 @@ inductance_coil_crm_tmr_init(struct freq_cal_info *info)
-    tmp_pr_value = INPUT_CAPTURE_CAL_CRM_TIM_PR(g_freq_cal_info.freq_cal_timeout_cycle);
+    double timeout_pr = INPUT_CAPTURE_CAL_CRM_TIM_PR(g_freq_cal_info.freq_cal_timeout_cycle);
+    if (timeout_pr < 0.0 || timeout_pr > (double)INPUT_CAPTURE_CAL_CRM_TIM_MAX_PR_VALUE) {
+      shutdown("input capture timeout cycle is invalid!!!");
+    }
+    tmp_pr_value = (uint32_t)timeout_pr;
@@ -471,9 +477,17 @@ update_trigger_frequencies(struct timer_config_freq_param freq_param)
-    if (freq_param.trg_freq_ht + (int)cur_freq < 0)
-      d->cal_info.trg_freq_ht = 0;
-    else
-      d->cal_info.trg_freq_ht = freq_param.trg_freq_ht + cur_freq;
+    int64_t calc_ht = (int64_t)freq_param.trg_freq_ht + (int64_t)cur_freq;
+    if (calc_ht < 0)
+      d->cal_info.trg_freq_ht = 0;
+    else if (calc_ht > (int64_t)UINT32_MAX)
+      d->cal_info.trg_freq_ht = UINT32_MAX;
+    else
+      d->cal_info.trg_freq_ht = (uint32_t)calc_ht;
 
-    if (freq_param.trg_freq_lt + (int)cur_freq < 0)
-      d->cal_info.trg_freq_lt = 0;
-    else
-      d->cal_info.trg_freq_lt = freq_param.trg_freq_lt + cur_freq;
+    int64_t calc_lt = (int64_t)freq_param.trg_freq_lt + (int64_t)cur_freq;
+    if (calc_lt < 0)
+      d->cal_info.trg_freq_lt = 0;
+    else if (calc_lt > (int64_t)UINT32_MAX)
+      d->cal_info.trg_freq_lt = UINT32_MAX;
+    else
+      d->cal_info.trg_freq_lt = (uint32_t)calc_lt;
```

## Verification & Automated Tests
- Test harness implemented in `test/test_bug_int03_inductance_coil.c`:
  - `check_pr_patched`: Verifies that cycles exceeding 32-bit limits or negative values are intercepted before cast.
  - `add_value_patched`: Verifies that `MOVING_SUM` accumulation does not wrap modulo $2^{32}$.
  - `calc_freq_ht_patched`: Verifies that frequency addition does not overflow signed integers or wrap to zero.
- Test execution:
  - Compiled and executed with GCC in `u1sim` container: All tests passed with 0 errors.
  - `python3 scripts/check_whitespace.py` passed with 0 errors.

