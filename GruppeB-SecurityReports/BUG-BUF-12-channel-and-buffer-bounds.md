# BUG-BUF-12: Off-by-One Channel Boundary and Unchecked SPI Buffer Indexing in `fm175xx_reader.py` & `sc7a20.py`

## Summary
In `klippy/extras/fm175xx_reader.py` and `klippy/extras/sc7a20.py`, multiple boundary and buffer length checks were omitted or improperly formulated:
1. In `fm175xx_reader.py`, `self_test()` checked `if (channel < 0 or channel > FM175XX_CHANNEL_NUMS):`. Because `FM175XX_CHANNEL_NUMS = 4` (valid channels are `0, 1, 2, 3`), using `> 4` rather than `>= 4` allowed `channel == 4` to pass through, causing out-of-bounds bitwise shift and indexing errors.
2. In `fm175xx_reader.py`, `request_read_card_info()` and `request_clear_card_info()` lacked any bounds validation on `channel`, allowing negative values or values `>= 4` to corrupt internal channel flag masks.
3. In `fm175xx_reader.py`, `_read_card_anticollision()` accessed `result.out_param.recv_buff[0]` without checking if `recv_buff` contained elements, risking an unhandled `IndexError` during SPI communication anomalies.
4. In `sc7a20.py`, `read_reg()` assumed the SPI transaction returned at least 2 bytes and directly accessed `response[1]`. If the SPI bus returned an empty or truncated response, an unhandled `IndexError` crashed Klippy instead of raising a descriptive `command_error`.

## Component / Affected Files
- **File:** `klippy/extras/fm175xx_reader.py`
  - **Affected Methods:** `_read_card_anticollision()`, `request_read_card_info()`, `request_clear_card_info()`, `self_test()`
  - **Lines:** 797-815, 1044-1065
- **File:** `klippy/extras/sc7a20.py`
  - **Affected Methods:** `read_reg()`
  - **Lines:** 84-93

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Host Python
- **Severity:** Medium (Unhandled `IndexError` / Crash / Denial of Service upon SPI / RFID communication fault)

## Root Cause Analysis
1. In `fm175xx_reader.py`, `FM175XX_CHANNEL_NUMS` is defined as `4`. The four physical RFID reader channels are indexed `0, 1, 2, 3`. The check `channel > FM175XX_CHANNEL_NUMS` permitted index `4` (off-by-one error). Furthermore, `request_read_card_info()` and `request_clear_card_info()` performed no validation prior to bit shifting `(1 << channel)`.
2. In `_read_card_anticollision()`, `result.out_param.recv_buff` is a list that can be empty if an error or incomplete packet was received. Accessing index `[0]` without `not result.out_param.recv_buff` resulted in an unhandled `IndexError`.
3. In `sc7a20.py`, `read_reg()` read `response = bytearray(params['response'])` and returned `response[1]`. On communication timeouts or corrupted SPI transfers where fewer than 2 bytes were returned, an `IndexError` occurred rather than a structured Klipper error.

## Steps to Reproduce
1. In `fm175xx_reader.py`:
   - Call `self_test(channel=4, times=1)`. Observe channel 4 is mistakenly accepted.
   - Inject an empty `recv_buff = []` on a transmission error. Observe unhandled `IndexError` at line 797/809.
2. In `sc7a20.py`:
   - Simulate a SPI transfer returning an empty bytearray `b""` or `b"\x00"`.
   - Observe `IndexError: bytearray index out of range` in `read_reg()`.

## Proposed Fix / Patch
```diff
diff --git a/klippy/extras/fm175xx_reader.py b/klippy/extras/fm175xx_reader.py
--- a/klippy/extras/fm175xx_reader.py
+++ b/klippy/extras/fm175xx_reader.py
@@ -794,7 +794,8 @@ class FM175XXReader:
         result = self.__command_exe(cmd)
         ret = result.err_code
 
-        if ((result.err_code != FM175XX_OK) or (result.out_param.bits_recved != 4) or (result.out_param.recv_buff[0] & 0x0F != 0x0A)):
+        if ((result.err_code != FM175XX_OK) or (result.out_param.bits_recved != 4) or
+                not result.out_param.recv_buff or (result.out_param.recv_buff[0] & 0x0F != 0x0A)):
             if (result.err_code == FM175XX_OK):
                 ret = FM175XX_CARD_COMM_ERR
         else:
@@ -806,7 +807,8 @@ class FM175XXReader:
             result = self.__command_exe(cmd)
             ret = result.err_code
 
-            if ((result.out_param.bits_recved != 4) or (result.out_param.recv_buff[0] & 0x0F != 0x0A)):
+            if ((result.out_param.bits_recved != 4) or not result.out_param.recv_buff or
+                    (result.out_param.recv_buff[0] & 0x0F != 0x0A)):
                 ret = FM175XX_CARD_COMM_ERR
 
         return ret
@@ -1042,15 +1044,21 @@ class FM175XXReader:
             logging.error("Param[cb] is not a callable function")
 
     def request_read_card_info(self, channel):
+        if (channel < 0 or channel >= FM175XX_CHANNEL_NUMS):
+            logging.error("invalid channel[%d]", channel)
+            return
         self.__card_info_clear_flag &= ~(1 << channel) & 0xFFFFFFFF
         self.__card_info_read_flag |= (1 << channel)
 
     def request_clear_card_info(self, channel):
+        if (channel < 0 or channel >= FM175XX_CHANNEL_NUMS):
+            logging.error("invalid channel[%d]", channel)
+            return
         self.__card_info_read_flag &= ~(1 << channel) & 0xFFFFFFFF
         self.__card_info_clear_flag |= (1 << channel)
 
     def self_test(self, channel, times):
-        if (channel < 0 or channel > FM175XX_CHANNEL_NUMS):
+        if (channel < 0 or channel >= FM175XX_CHANNEL_NUMS):
             logging.error("invalid channel[%d]", channel)
             return

diff --git a/klippy/extras/sc7a20.py b/klippy/extras/sc7a20.py
--- a/klippy/extras/sc7a20.py
+++ b/klippy/extras/sc7a20.py
@@ -84,7 +84,12 @@ class SC7A20:
 
     def read_reg(self, reg):
         params = self.spi.spi_transfer([reg | REG_MOD_READ, 0x00])
-        response = bytearray(params['response'])
+        response = bytearray(params.get('response', b''))
+        if len(response) < 2:
+            msg = ("Failed to read SC7A20 register [0x%x]: response too short (%d bytes)" % (
+                reg, len(response)))
+            err_msg = '{"coded": "0003-0522-0000-0009", "oneshot": 1, "msg":"%s"}' % msg
+            raise self.printer.command_error(err_msg)
         return response[1]
```

## Verification & Automated Tests
- Test harness implemented in `test/test_bug_buf12.py`:
  - `test_fm175xx_channel_bounds`: Validates channel bounds `0 <= channel < 4` and confirms `channel == 4` is correctly rejected.
  - `test_fm175xx_empty_recv_buff`: Validates that empty buffer does not crash with `IndexError`.
  - `test_sc7a20_empty_spi_response`: Validates that empty or single-byte SPI responses raise a handled `command_error` instead of crashing.
- Test execution:
  - `python3 test/test_bug_buf12.py` passes 3/3 tests cleanly.
  - `python3 scripts/check_whitespace.py` passes with 0 errors.

