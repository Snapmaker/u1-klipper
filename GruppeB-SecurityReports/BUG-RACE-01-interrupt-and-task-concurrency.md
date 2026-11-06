# BUG-RACE-01: Race Conditions Between Priority-0 ISR, Timer ISR, and Task Context in `src/stm32/inductance_coil.c`

## Summary
In `src/stm32/inductance_coil.c`, `update_trigger_frequencies()` and `inductance_coil_crm_tmr_init()` read and modified sensor calibration variables (`d->cal_info` and global `g_freq_cal_info`) without disabling interrupts across critical sections. Because the hardware capture interrupt `InputCapture_IRQHandler` runs at the highest NVIC priority (Priority 0) on ARM Cortex-M, it could preempt threshold updates midway through, reading inconsistent high/low frequency threshold pairs (`trg_freq_ht`, `trg_freq_lt`) or torn 64-bit `capture_pulse_sum` readings during frequency conversion. This caused false trigger events and erratic Z-probing behavior.

## Component / Affected Files
- **File:** `src/stm32/inductance_coil.c`
  - **Affected Methods:** `update_trigger_frequencies()`, `inductance_coil_crm_tmr_init()`, `command_inductance_coil_config()`
  - **Lines:** 168-237, 265-320, 460-545

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / MCU Firmware C
- **Severity:** High (Race Condition / ISR Data Corruption / Inconsistent Z-Probing Triggers)

## Root Cause Analysis
1. `update_trigger_frequencies()` can be invoked asynchronously from the task scheduler (`command_virtual_gpio_trigger`) or timer ISR (`inductance_coil_config_freq_event`). It performs multi-step calculations to compute high and low trigger counts (`cmp_trg_cnt_ht`, `cmp_trg_cnt_lt`) and reads 64-bit `capture_pulse_sum`.
2. Previously, only the `if (freq_param.force_update)` sub-block was protected by `irq_save()`. The preceding threshold modifications to `d->cal_info`, the 64-bit read of `g_freq_cal_info.capture_pulse_sum`, and non-force updates were executed with interrupts fully enabled.
3. If `InputCapture_IRQHandler` fired during this calculation, it compared the incoming frequency against partially updated thresholds, causing spurious trigger transitions (`TRIGGERED` vs `OPEN`).
4. In `inductance_coil_crm_tmr_init()`, `g_freq_cal_info` was reinitialized without explicitly disabling `INPUT_CAPTURE_CAL_IRQn` in NVIC, allowing incoming capture edges to preempt active configuration.

## Steps to Reproduce
1. Initiate frequent dynamic trigger frequency adjustments via `virtual_gpio_trigger` during continuous probe coil oscillations.
2. Observe intermittent incorrect trigger states in `InputCapture_IRQHandler` due to partially updated `trg_freq_ht` / `trg_freq_lt` comparison limits.

## Proposed Fix / Patch
```diff
diff --git a/src/stm32/inductance_coil.c b/src/stm32/inductance_coil.c
--- a/src/stm32/inductance_coil.c
+++ b/src/stm32/inductance_coil.c
@@ -268,6 +268,8 @@ inductance_coil_crm_tmr_init(struct freq_cal_info *info)
   uint32_t tmp_pr_value = 0;

+  NVIC_DisableIRQ(INPUT_CAPTURE_CAL_IRQn);
   // turn off the timer.
   tmr_counter_enable(INPUT_CAPTURE_CRM_TIM, FALSE);
   tmr_counter_enable(INPUT_CAPTURE_CAL_CRM_TIM, FALSE);
@@ -278,6 +280,7 @@ inductance_coil_crm_tmr_init(struct freq_cal_info *info)
   INPUT_CAPTURE_CAL_CRM_TIM->ists &= 0;

   // cal info init
+  irqstatus_t irq_flags = irq_save();
   g_freq_cal_info.capture_pulse_sum = 0;
   ...
+  irq_restore(irq_flags);

@@ -485,6 +491,7 @@ update_trigger_frequencies(struct timer_config_freq_param freq_param)
 {
   struct inductance_coil_dev *d = oid_lookup(freq_param.oid, command_inductance_coil_config);
+  irqstatus_t irq_flags = irq_save();
   if (freq_param.absolute_mode) {
   ...
   if (freq_param.trigger_mode == 1 && (d->cal_info.trg_freq_ht < d->cal_info.trg_freq_lt)) {
+    irq_restore(irq_flags);
     shutdown("Bidirectional Trigger mode trg_freq_ht is smaller than trg_freq_lt!!!");
   }
   ...
+  irq_restore(irq_flags);
 }
```

## Verification
- Unit test `test/test_bug_race01_inductance_coil.c` verified via GCC in container:
  - Validates atomic threshold and limit calculation under simulated IRQ-disabled critical section.
  - Verifies no partial or torn state updates are exposed to the interrupt handler.

