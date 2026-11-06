# BUG-INT-01: 32-Bit Integer Overflow in SDIO Timeout and `uint8_t` Underflow in Clock Divider

## Summary
In the Snapmaker U1 SDIO peripheral driver, two integer boundary vulnerabilities caused communication failures and timing faults:
1. In `src/sdiocmds.c`, `command_sdio_read_data()` and `command_sdio_write_data()` computed transfer timeout cycles using 32-bit math: `uint32_t timeout = TIMEOUT_MSEC * sdio->speed / 1000;`. For SD clock speeds of 8.59 MHz and higher (standard SD runs at 24-50 MHz), `500 * speed` overflows `UINT32_MAX`, truncating hardware timeouts by up to 88% and causing premature `DTIMEOUT` aborts.
2. In `src/stm32/sdio.c`, `sdio_set_speed()` computed clock divider registers via `uint8_t clkdiv = (SDIO_CLK_FREQ / speed) - 2;`. When `speed` exceeded 24 MHz with `SDIO_CLK_FREQ = 48000000`, `div <= 1` caused an unsigned 8-bit underflow to `255`, dropping the SD clock to its slowest rate (~186 kHz) instead of maximum speed. Conversely, low clock frequencies (< 187 kHz) caused divider truncation.

## Component / Affected Files
- **Files:**
  - `src/sdiocmds.c` (lines 80-84, 110-114)
  - `src/stm32/sdio.c` (lines 420-435)
- **Affected Functions:** `command_sdio_read_data()`, `command_sdio_write_data()`, `sdio_set_speed()`

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Firmware
- **Severity:** High (Premature transfer timeout aborts & severe clock rate underflow)

## Root Cause Analysis
1. **Timeout Calculation Overflow (`src/sdiocmds.c`):**
   ```c
   #define TIMEOUT_MSEC 500
   uint32_t timeout = TIMEOUT_MSEC * sdio->speed / 1000;
   ```
   At 25 MHz: `500 * 25,000,000 = 12,500,000,000`. Overflows 32-bit unsigned integer to `3,910,065,408 / 1000 = 3,910,065` cycles (expected `12,500,000`, 68.7% truncation).
   At 50 MHz: `500 * 50,000,000 = 25,000,000,000`. Overflows to `3,525,163,808 / 1000 = 3,525,163` cycles (expected `25,000,000`, 85.9% truncation).
2. **Clock Divider Underflow and Truncation (`src/stm32/sdio.c`):**
   ```c
   uint8_t clkdiv = (SDIO_CLK_FREQ / speed) - 2;
   ```
   At 25 MHz or 48 MHz, `SDIO_CLK_FREQ / speed` is `1`. Subtracting `2` in unsigned 8-bit arithmetic yields `(uint8_t)(1 - 2) = 255`, inadvertently configuring the maximum prescaler and reducing clock speed from 24/48 MHz to ~186 kHz. Furthermore, when `speed < 186771 Hz`, `div > 257`, so `div - 2` exceeds 255 and silently truncates its upper bits.

## Steps to Reproduce
1. Configure SDIO transfer clock at 25 MHz or 50 MHz.
2. Observe timeout value wrapped around in `command_sdio_read_data` or `command_sdio_write_data`.
3. Call `sdio_set_speed(cfg, 48000000)` on unpatched code; observe `clkdiv` evaluated to `255` instead of `0`.

## Proposed Fix / Patch
1. In `src/sdiocmds.c`:
   Cast `TIMEOUT_MSEC` to `uint64_t` prior to multiplication:
   ```c
   uint32_t timeout = (uint32_t)((uint64_t)TIMEOUT_MSEC * sdio->speed / 1000);
   ```
2. In `src/stm32/sdio.c`:
   Check for zero speed and bound `clkdiv` within `[0, 255]`:
   ```c
   if (!speed)
       shutdown("Invalid SDIO speed: 0");
   uint32_t div = SDIO_CLK_FREQ / speed;
   uint8_t clkdiv = (div <= 2) ? 0 : ((div - 2 > 255) ? 255 : (uint8_t)(div - 2));
   ```

## Regression & Safety Verification
- **Automated Unit Tests:**
  - `test/test_bug_int01_sdio.c`: Compiled with GCC `-Wall -Wextra -O2`. Verified full 64-bit precision across speeds from 400 kHz to 50 MHz with zero truncation, and verified clkdiv underflow prevention at 48 MHz, 25 MHz, 400 kHz, and low frequency saturation at 100 kHz.
- **Whitespace Compliance:** Verified with `scripts/check_whitespace.py` (0 errors).
- **Regression:** Confirmed normal SD card initialization, block transfers, and high-speed clock operation execute reliably.
