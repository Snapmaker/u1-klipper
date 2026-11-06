# BUG-DEAD-01: Unbounded Hardware Polling Loops in MCU Drivers

## Summary
In `src/stm32/sdio.c`, `src/stm32/at32f403a.c`, `src/stm32/at32f415rc.c`, `src/stm32/n32g45x_adc.c`, and `src/generic/canserial.c`, low-level hardware routines executed unbounded `while` and `for` loops polling peripheral register flags. In the event of hardware communication stalls, disconnected media, bus saturation, or unclocked peripherals, the microcontroller remained permanently locked in tight busy loops, halting all MCU scheduling and triggering watchdog resets.

## Component / Affected Files
- **File:** `src/stm32/sdio.c`
  - **Affected Functions:** `sdio_read_data()`, `sdio_write_data()`
  - **Lines:** 304-390
- **File:** `src/stm32/at32f403a.c`
  - **Affected Functions:** `__io_putchar()`, `at32f403a_log()`
  - **Lines:** 35-55
- **File:** `src/stm32/at32f415rc.c`
  - **Affected Functions:** `at32f415_log()`
  - **Lines:** 15-30
- **File:** `src/stm32/n32g45x_adc.c`
  - **Affected Functions:** `adc_calibrate()`
  - **Lines:** 65-75
- **File:** `src/generic/canserial.c`
  - **Affected Functions:** `can_process_query_unassigned()`
  - **Lines:** 152-160

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Firmware
- **Severity:** High (MCU Lockup / Watchdog Reset / Denial of Service)

## Root Cause Analysis
1. **Missing Timeout in SDIO Data Transfer:**
   In `sdio_read_data()` and `sdio_write_data()`, the polling loops `while ((sdio->STA & ...) == 0)` depended solely on hardware status flags (`SDIO_STA_DATAEND`, `SDIO_STA_DTIMEOUT`, `SDIO_STA_DCRCFAIL`, etc.). If the SD card disconnected mid-transfer or the SDIO controller locked up, neither completion nor hardware error flags were raised, causing an infinite loop.
2. **Uninitialized Debug UART Polling in AT32 Port:**
   `at32f403a_log()` and `at32f415_log()` polled `usart_flag_get(PRINT_UART, USART_TDBE_FLAG) == RESET` indefinitely. If the debug UART clock was not initialized, this flag never set.
3. **ADC Calibration Hang:**
   `n32g45x_adc.c:adc_calibrate()` polled `adc->CTRL3 & ADC_FLAG_RDY` and `adc->CTRL2 & CTRL2_CAL_SET` without timeout.
4. **Infinite CAN Retry Loop:**
   `canserial.c:can_process_query_unassigned()` ran `for (;;)` attempting `canbus_send()`. When the CAN transmission buffer was saturated or the bus was offline, the loop locked the MCU execution thread.

## Steps to Reproduce
1. In an MCU environment, issue `sdio_read_data()` with an unresponsive SD card that never drives data or asserts transfer end flags.
2. Observe that the MCU never returns from `sdio_read_data()`.
3. The independent watchdog timer (IWDG) triggers, crashing the printer into shutdown.

## Proposed Fix / Patch
1. In `src/stm32/sdio.c`, initialize a software cycle timeout counter based on `SDIO_MAX_TIMEOUT * (SystemCoreClock / 8U / 1000U)` in `sdio_read_data()` and `sdio_write_data()`. Return `SDIO_DATA_TIMEOUT` when the counter expires.
2. In `src/stm32/at32f403a.c` and `src/stm32/at32f415rc.c`, add iteration countdown limits to USART transmit flag polling.
3. In `src/stm32/n32g45x_adc.c`, add iteration countdown limits to ADC calibration flags.
4. In `src/generic/canserial.c`, bound the retry loop to a maximum of 10000 attempts.

```diff
--- a/src/stm32/sdio.c
+++ b/src/stm32/sdio.c
@@ -308,6 +308,11 @@ sdio_read_data(struct sdio_config sdio_config, uint8_t *data,
+    uint32_t count = SDIO_MAX_TIMEOUT * (SystemCoreClock / 8U / 1000U);
     while ((sdio->STA & (SDIO_STA_RXOVERR | SDIO_STA_DCRCFAIL |
         SDIO_STA_DTIMEOUT | SDIO_STA_DATAEND)) == 0) {
+        if (count-- == 0) {
+            sdio->ICR = SDIO_STATIC_FLAGS;
+            return SDIO_DATA_TIMEOUT;
+        }
...
@@ -371,6 +376,11 @@ sdio_write_data(struct sdio_config sdio_config, uint8_t *data,
+    uint32_t count = SDIO_MAX_TIMEOUT * (SystemCoreClock / 8U / 1000U);
     while ((sdio->STA & (SDIO_STA_TXUNDERR | SDIO_STA_DCRCFAIL |
         SDIO_STA_DTIMEOUT | SDIO_STA_DATAEND)) == 0) {
+        if (count-- == 0) {
+            sdio->ICR = SDIO_STATIC_FLAGS;
+            return SDIO_DATA_TIMEOUT;
+        }
```

## Regression & Safety Verification
- **Automated C Unit Tests:**
  - `test/test_bug_dead01_sdio.c`: Verified that unasserted hardware flags in `sdio_read_data()` and `sdio_write_data()` timeout cleanly with `SDIO_DATA_TIMEOUT`, while normal transfers complete with `SDIO_OK`.
- **Whitespace Compliance:** Verified with `scripts/check_whitespace.py` (0 errors).
- **Regression:** Validated that functional hardware operations continue to transfer data with normal throughput.

