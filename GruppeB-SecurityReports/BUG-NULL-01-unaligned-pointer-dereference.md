# BUG-NULL-01: Unaligned 32-Bit Pointer Dereference in `src/stm32/inductance_coil.c`

## Summary
In `src/stm32/inductance_coil.c`, `inductance_coil_query()` wrote 32-bit frequency values into a sensor data buffer via direct type casting: `*(uint32_t *)d = cal_freq;`. Because the `data` array in `struct sensor_bulk` resides immediately following a 1-byte field (`uint8_t data_count`), the write address is offset by an odd number of bytes (`5 + 4*k`). On ARM Cortex-M processors, performing a 32-bit load or store to an address that is not a multiple of 4 can trigger an immediate hardware `UsageFault` (UNALIGN_TRP) or data corruption.

## Component / Affected Files
- **File:** `src/stm32/inductance_coil.c`
  - **Affected Methods:** `inductance_coil_query()`
  - **Lines:** 648-656

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / MCU Firmware C
- **Severity:** High (ARM Cortex-M UsageFault / Unaligned Memory Access / MCU HardFault)

## Root Cause Analysis
In `src/sensor_bulk.h`:
```c
struct sensor_bulk {
    uint32_t possible_overflows; // Offset 0-3 (4 bytes)
    uint8_t data_count;          // Offset 4 (1 byte)
    uint8_t data[SENSOR_BULK_MAX_SIZE]; // Offset 5
};
```
Because `data_count` increments by `BYTES_PER_SAMPLE` (4), `d = &icd->sb.data[icd->sb.data_count]` points to odd memory offsets. Casting `d` to `uint32_t *` and assigning `*(uint32_t *)d = cal_freq;` forces the CPU to execute an unaligned word store instruction (e.g. `STR`). When unaligned access trapping is enabled in the ARM Cortex-M System Control Block (`CCR.UNALIGN_TRP`), this immediately generates a `UsageFault` exception.

## Steps to Reproduce
1. Query inductance coil sensor samples with bulk reporting enabled on Cortex-M hardware.
2. If unaligned trap is enabled in hardware (`CCR.UNALIGN_TRP = 1`), execution traps into `UsageFault_Handler` upon the first `inductance_coil_query()` invocation.

## Proposed Fix / Patch
```diff
diff --git a/src/stm32/inductance_coil.c b/src/stm32/inductance_coil.c
--- a/src/stm32/inductance_coil.c
+++ b/src/stm32/inductance_coil.c
@@ -652,3 +652,3 @@ inductance_coil_query(struct inductance_coil_dev *icd, uint64_t capture_sum, ui
   uint8_t *d = &icd->sb.data[icd->sb.data_count];
-  *(uint32_t *)d = cal_freq;
+  memcpy(d, &cal_freq, sizeof(cal_freq));
   icd->sb.data_count += BYTES_PER_SAMPLE;
```

## Verification & Automated Tests
- Test harness implemented in `test/test_bug_null01_inductance_coil.c`:
  - `write_sample_safe`: Verifies that `memcpy` safely and accurately copies 32-bit sample words to unaligned byte offsets (1, 5, 9, etc.) without faults.
- Test execution:
  - Compiled and executed with GCC in `u1sim`: All tests passed with 0 errors.
  - `python3 scripts/check_whitespace.py` passed with 0 errors.

