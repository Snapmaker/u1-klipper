# BUG-INT-04: 16-Bit Timer Underflow & `uint32_t` Overflow of `power_loss_trigger_time` in `power_loss_check.c` & `power_loss_check.py`

## Summary
In `src/stm32/power_loss_check.c` and `klippy/extras/power_loss_check.py`, `power_loss_trigger_time` sets the hardware timeout period for TMR4 on the MCU to detect brown-out / AC power drops. In `src/stm32/power_loss_check.c:493`, the timer period reload value was calculated using `(uint16_t)(TRM_OVER_FREQ * plc->power_loss_trigger_time - 1)`. If `power_loss_trigger_time == 0` or negative, this caused a floating-point underflow and undefined cast to `uint16_t`. Furthermore, because TMR4 is a 16-bit timer (`max 65535`), values above `6.5535` seconds (`TRM_OVER_FREQ = 10000`) caused integer truncation modulo 65536, configuring an unintended tiny timeout and premature power-loss halts. In `klippy/extras/power_loss_check.py`, `power_loss_trigger_time` was loaded unvalidated from `power_loss_check.json`.

## Component / Affected Files
- **Files:**
  - `src/stm32/power_loss_check.c` (Lines 486-500)
  - `klippy/extras/power_loss_check.py` (Lines 21-35, 93-97)

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / MCU Firmware & Host Python
- **Severity:** High (16-Bit Integer Underflow/Overflow / Brown-Out Detection Failure)

## Root Cause Analysis
1. Unbounded 16-bit hardware timer reload: `TRM_OVER_FREQ` is 10,000 Hz. The timer reload register (PR / ARR) on AT32 TMR4 is 16 bits (`0..65535`). Any timeout beyond `6.5535` seconds (`70000 ticks`) truncates to `(70000 - 1) & 0xFFFF = 4463 ticks` (`0.446s`), triggering premature brownout alerts.
2. Underflow on zero/negative values: If `power_loss_trigger_time == 0.0`, `10000 * 0.0 - 1.0 = -1.0`, triggering undefined float-to-unsigned conversion and underflow.
3. Unvalidated JSON config load: `val = json.load(f).get('power_loss_trigger_time')` in `power_loss_check.py` did not check `minval` or `maxval`.

## Steps to Reproduce
1. In `printer.cfg` or `power_loss_check.json`, specify `power_loss_trigger_time: 7.0`.
2. Start Klippy and observe MCU timer ARR value truncated to 4463 ticks (0.446s) instead of 7.0 seconds.
3. In `power_loss_check.json`, specify `power_loss_trigger_time: 0.0`. Observe timer underflow to 0xFFFF (6.55s) instead of an immediate alert or validation error.

## Proposed Fix / Patch
```diff
diff --git a/src/stm32/power_loss_check.c b/src/stm32/power_loss_check.c
--- a/src/stm32/power_loss_check.c
+++ b/src/stm32/power_loss_check.c
@@ -490,4 +490,9 @@ void power_loss_check_init(void)
     /* tmr4 counter mode configuration */
-    tmr_base_init(TMR4, 0xFFFF, TRM_PR_DIV_VALUE);
-    tmr_base_init(TMR4, (uint16_t)(TRM_OVER_FREQ*plc->power_loss_trigger_time - 1), TRM_PR_DIV_VALUE);
+    double calc_ticks = (double)TRM_OVER_FREQ * plc->power_loss_trigger_time - 1.0;
+    if (calc_ticks < 0.0 || calc_ticks > 65535.0) {
+        shutdown("Invalid power loss trigger time");
+    }
+    uint16_t pr_val = (uint16_t)calc_ticks;
+    tmr_base_init(TMR4, pr_val, TRM_PR_DIV_VALUE);
     tmr_counter_value_set(TMR4, 0);

diff --git a/klippy/extras/power_loss_check.py b/klippy/extras/power_loss_check.py
--- a/klippy/extras/power_loss_check.py
+++ b/klippy/extras/power_loss_check.py
@@ -21,3 +21,4 @@ class PowerLossCheck:
         self._mcu = pin_params['chip']
-        cfg_trigger_time = config.getfloat('power_loss_trigger_time', 0.0109, above=0.)
+        cfg_trigger_time = config.getfloat('power_loss_trigger_time', 0.0109,
+                                           minval=0.0001, maxval=6.5535)
         self.power_loss_trigger_time = cfg_trigger_time
@@ -28,4 +29,9 @@ class PowerLossCheck:
                 with open(self._config_path, 'r', encoding='utf-8') as f:
                     val = json.load(f).get('power_loss_trigger_time')
-                if val is not None and val > 0:
-                    self.power_loss_trigger_time = float(val)
+                if val is not None:
+                    val = float(val)
+                    if 0.0001 <= val <= 6.5535:
+                        self.power_loss_trigger_time = val
+                        trigger_source = "json config"
```

## Verification
- Unit tests:
  - C test `test/test_bug_int04_power_loss_check.c`: Validates rejection of underflow and overflow conditions.
  - Python test `test/test_bug_int04.py`: Validates parser range checks and JSON validation.
- Both test suites pass cleanly with 0 errors.

