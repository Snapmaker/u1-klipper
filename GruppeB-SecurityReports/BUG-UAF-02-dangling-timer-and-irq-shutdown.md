# BUG-UAF-02: Dangling Timer `config_freq_timer` and Active Priority-0 IRQ on Shutdown in `src/stm32/inductance_coil.c`

## Summary
In `src/stm32/inductance_coil.c`, the shutdown handler `inductance_coil_shutdown()` only unregistered `d->timer` via `sched_del_timer(&d->timer);`, omitting the secondary calibration timer `d->config_freq_timer`. Furthermore, hardware capture counters (TMR2, TMR5), overflow/capture interrupts, and the NVIC line (`INPUT_CAPTURE_CAL_IRQn`) were left running. If an MCU shutdown or emergency stop occurs while calibration is active, the active hardware timer interrupt continues firing, mutating `g_freq_cal_info` or dereferencing freed/reset memory, leading to use-after-free (UAF) crashes or unexpected task wakeups during reset.

## Component / Affected Files
- **File:** `src/stm32/inductance_coil.c`
  - **Affected Methods:** `inductance_coil_shutdown()`, `command_inductance_coil_config()`
  - **Lines:** 72, 445-455, 688-705

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / MCU Firmware C
- **Severity:** High (Use-After-Free / Dangling Interrupt Handler / Resource Leak / MCU HardFault)

## Root Cause Analysis
1. `struct inductance_coil_dev` registers two timers: `d->timer` (sampling timer) and `d->config_freq_timer` (frequency calibration reconfig timer). Upon shutdown, only `d->timer` was deleted from the scheduler queue. If `config_freq_timer` was scheduled, its timer callback (`timer_config_freq_event`) would fire on stale memory.
2. Hardware timers (`INPUT_CAPTURE_CRM_TIM` and `INPUT_CAPTURE_CAL_CRM_TIM`) and the priority-0 interrupt `InputCapture_IRQHandler` were not stopped or disabled in the NVIC during shutdown. The interrupt continued processing pulses and attempting to wake Klipper scheduler tasks even after shutdown.
3. `command_inductance_coil_config()` checked a global variable `inductance_coil_oid_malloc` without checking active OIDs via `foreach_oid`, which could lead to conflicts across re-initialization if shutdown failed to reset it.

## Steps to Reproduce
1. Configure the inductance coil device and start a frequency calibration with `config_freq_timer` active.
2. Trigger an MCU emergency shutdown (e.g. M112).
3. Observe `config_freq_timer` remaining queued in the scheduler list or `InputCapture_IRQHandler` continuing to service timer events into uninitialized memory.

## Proposed Fix / Patch
```diff
diff --git a/src/stm32/inductance_coil.c b/src/stm32/inductance_coil.c
--- a/src/stm32/inductance_coil.c
+++ b/src/stm32/inductance_coil.c
@@ -691,6 +691,14 @@ inductance_coil_shutdown(void)
   uint8_t i;
   struct inductance_coil_dev *d;
   foreach_oid(i, d, command_inductance_coil_config) {
     sched_del_timer(&d->timer);
+    sched_del_timer(&d->config_freq_timer);
   }
+#if CONFIG_MACH_AT32F4x
+  tmr_interrupt_enable(INPUT_CAPTURE_CAL_CRM_TIM, TMR_OVF_INT | TMR_C1_INT, FALSE);
+  tmr_counter_enable(INPUT_CAPTURE_CAL_CRM_TIM, FALSE);
+  tmr_counter_enable(INPUT_CAPTURE_CRM_TIM, FALSE);
+  NVIC_DisableIRQ(INPUT_CAPTURE_CAL_IRQn);
+#endif
+  inductance_coil_oid_malloc = 0;
 }
```

## Verification
- Unit test `test/test_bug_uaf02_inductance_coil.c` verified using GCC:
  - Both `timer` and `config_freq_timer` are cleanly deleted upon shutdown.
  - TMR2 and TMR5 counters are disabled.
  - TMR5 interrupts and NVIC IRQ lines are disabled.
  - `inductance_coil_oid_malloc` is reset to 0.
- All checks pass cleanly.

