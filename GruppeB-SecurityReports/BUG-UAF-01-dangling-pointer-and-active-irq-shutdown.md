# BUG-UAF-01: Dangling Global Pointer `plc` and Active `TIM4_IRQHandler` on Shutdown in `src/stm32/power_loss_check.c`

## Summary
In `src/stm32/power_loss_check.c`, `command_config_power_loss_check_dev()` allocated memory for `plc` using Klipper's dynamic allocator `oid_alloc()`. Upon an MCU shutdown or firmware restart (`config_reset`), the global pointer `plc` was never set to `NULL`, and `power_loss_check_shutdown()` failed to stop hardware timer TMR4 or disable the NVIC line `TMR4_GLOBAL_IRQn`. As a result, `TIM4_IRQHandler` continued executing during and after soft reset, mutating `plc->debounce_count`, `plc->voltage_type`, and `plc->need_save` in memory that had been reset and reallocated for other objects (Use-After-Free and memory corruption). In addition, re-configuration was blocked on restart by a stale check `if (plc) return;`.

## Component / Affected Files
- **File:** `src/stm32/power_loss_check.c`
  - **Affected Methods:** `command_config_power_loss_check_dev()`, `power_loss_check_shutdown()`
  - **Lines:** 517-526, 672-689

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / MCU Firmware C
- **Severity:** Critical (Use-After-Free / ISR Memory Corruption / Blocked Firmware Restart)

## Root Cause Analysis
1. Dynamic memory reset: `src/basecmd.c` implements `config_reset` (`FIRMWARE_RESTART`), which reinitializes the allocator (`alloc_init()`). Global variables in C modules are not re-zeroed by Klipper's soft-restart.
2. Dangling pointer: `static struct power_loss_check_dev *plc;` retained the stale memory address pointing into the now-reused heap.
3. Unstopped interrupt: `TMR4` and `TIM4_IRQHandler` continued firing. In `TIM4_IRQHandler`, writes to `plc->...` operated on reallocated memory.
4. Blocked restart: On the next config phase, `if (plc)` evaluated to true, prematurely returning before allocating or configuring the new power-loss check device.

## Steps to Reproduce
1. Configure power-loss detection on AT32.
2. Issue `FIRMWARE_RESTART`.
3. Observe that `command_config_power_loss_check_dev` prints `power_loss_check_dev: Already configured` and fails to reinitialize, while `TIM4_IRQHandler` continues servicing interrupts on deallocated heap pointers.

## Proposed Fix / Patch
```diff
diff --git a/src/stm32/power_loss_check.c b/src/stm32/power_loss_check.c
--- a/src/stm32/power_loss_check.c
+++ b/src/stm32/power_loss_check.c
@@ -522,5 +522,7 @@ command_config_power_loss_check_dev(uint32_t *args)
 {
-    if (plc) {
+    uint8_t existing_oid;
+    struct power_loss_check_dev *existing_dev;
+    foreach_oid(existing_oid, existing_dev, command_config_power_loss_check_dev) {
         output("power_loss_check_dev: Already configured");
         return;
     }
@@ -675,5 +677,13 @@ power_loss_check_shutdown(void)
     uint8_t oid;
     struct power_loss_check_dev *p;
     foreach_oid(oid, p, command_config_power_loss_check_dev) {
-        if (!power_loss_saved && plc->print_act) {
+        sched_del_timer(&p->timer);
+        if (!power_loss_saved && p->print_act) {
             power_loss_saved = 1;
             power_loss_rotate_sector();
             output("Power loss info saved during shutdown");
         }
     }
+#if CONFIG_MACH_AT32F4x
+    tmr_counter_enable(TMR4, FALSE);
+    tmr_interrupt_enable(TMR4, TMR_OVF_INT | TMR_C2_INT, FALSE);
+    NVIC_DisableIRQ(TMR4_GLOBAL_IRQn);
+#endif
+    plc = NULL;
 }
```

## Verification
- Unit test `test/test_bug_uaf01_power_loss_check.c` compiled and verified with GCC in container:
  - Validates timer deletion from scheduler.
  - Validates TMR4 counter, interrupts, and NVIC line disabled on shutdown.
  - Validates `plc` reset to NULL, preventing UAF and allowing clean re-allocation after reset.

