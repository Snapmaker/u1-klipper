# BUG-LEAK-02: MCU Flash Controller Remains Unlocked on Error in `flash_write` (`src/stm32/power_loss_check.c`)

## Summary
In `src/stm32/power_loss_check.c`, `flash_write()` unlocks the AT32 on-chip flash memory controller via `flash_unlock()` before writing power-loss recovery markers. However, upon encountering an operation timeout, sector erase error, or write verification error, four separate error exit paths executed `return ERROR;` directly without calling `flash_lock()`. During power degradation or brown-out conditions, leaving the Flash controller unlocked exposes the MCU's firmware to accidental corruption or unauthorized modification if spurious instructions or voltage spikes occur.

## Component / Affected Files
- **File:** `src/stm32/power_loss_check.c`
  - **Affected Methods:** `flash_write()`
  - **Lines:** 146-203

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / MCU Firmware C
- **Severity:** High (Hardware Security & Firmware Integrity / Permanent Hardware Lock Leak)

## Root Cause Analysis
AT32 flash memory writing requires unlocking the flash control register. Once unlocked, all sectors in flash are writable.
In `flash_write`:
```c
flash_unlock();
...
while(1) {
    ...
    else if(status == FLASH_OPERATE_TIMEOUT)
        return ERROR; // Flash remains unlocked!
    ...
    if(status != FLASH_OPERATE_DONE)
        return ERROR; // Flash remains unlocked!
    ...
    if(flash_write_nocheck(...) != SUCCESS)
        return ERROR; // Flash remains unlocked!
    ...
    if(flash_write_nocheck(...) != SUCCESS)
        return ERROR; // Flash remains unlocked!
}
flash_lock();
return SUCCESS;
```
If any hardware error occurred during the write or erase operation, execution exited immediately without reaching `flash_lock()`.

## Steps to Reproduce
1. Introduce a flash operation timeout or simulated write error in `flash_write()`.
2. Inspect the Flash Control Register (`FLASH->ctrl`): the lock bit `FLASH_CTRL_LOCK` remains cleared (0), indicating that flash remains permanently write-enabled.

## Proposed Fix / Patch
```diff
diff --git a/src/stm32/power_loss_check.c b/src/stm32/power_loss_check.c
--- a/src/stm32/power_loss_check.c
+++ b/src/stm32/power_loss_check.c
@@ -165,18 +165,18 @@ uint8_t flash_write(uint32_t write_addr, uint16_t *p_buffer, uint16_t num_write
             else if(status == FLASH_OPERATE_TIMEOUT)
-                return ERROR;
+                goto err_exit;
             status = flash_sector_erase(sector_position * FLASH_SECTOR_SIZE + FLASH_BASE);
             if(status != FLASH_OPERATE_DONE)
-                return ERROR;
+                goto err_exit;
             for(i = 0; i < sector_remain; i++)
             {
                 flash_buf[i + sector_offset] = p_buffer[i];
             }
             if(flash_write_nocheck(sector_position * FLASH_SECTOR_SIZE + FLASH_BASE, flash_buf, FLASH_SECTOR_SIZE / 2) != SUCCESS)
-                return ERROR;
+                goto err_exit;
         }
         else
         {
             if(flash_write_nocheck(write_addr, p_buffer, sector_remain) != SUCCESS)
-                return ERROR;
+                goto err_exit;
         }
@@ -200,3 +200,7 @@ uint8_t flash_write(uint32_t write_addr, uint16_t *p_buffer, uint16_t num_write
     flash_lock();
     return SUCCESS;
+
+err_exit:
+    flash_lock();
+    return ERROR;
 }
```

## Verification
- Unit test `test/test_bug_leak02_power_loss_check.c` compiled and verified with GCC in container:
  - Confirms unpatched code leaks unlocked flash on error.
  - Confirms patched code relocks flash on all error paths (timeout, erase, and write failure).
  - All assertions pass without errors.

