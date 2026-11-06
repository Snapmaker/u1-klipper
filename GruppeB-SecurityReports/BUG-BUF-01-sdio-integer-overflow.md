# BUG-BUF-01: 32-Bit Integer Overflow Bypasses Bounds Check in `src/sdiocmds.c`

## Summary
In `src/sdiocmds.c`, `command_sdio_read_data_buffer()` and `command_sdio_write_data_buffer()` handle host data transfers to and from the internal 4096-byte SDIO data buffer (`sdio->data_buffer`). In both commands, the `offset` parameter is received as an unsigned 32-bit integer (`uint32_t`), while the payload length is an 8-bit unsigned integer (`uint8_t`). The bounds verification relies on standard addition (`offset + write_data_len <= sizeof(sdio->data_buffer)`). When a malicious or corrupted host command specifies an offset close to `UINT32_MAX` (such as `0xFFFFFFF0`), the 32-bit integer addition wraps around (e.g. `0xFFFFFFF0 + 32 = 16`). Because `16 <= 4096`, the bounds check succeeds, leading to arbitrary memory overwrite (out-of-bounds write) and arbitrary memory disclosure (out-of-bounds read) before or beyond the allocated buffer on the MCU.

## Component / Affected Files
- **File:** `src/sdiocmds.c`
- **Affected Functions:** `command_sdio_read_data_buffer()`, `command_sdio_write_data_buffer()`
- **Lines:** 135-164

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Firmware
- **Severity:** Critical (Arbitrary Out-of-Bounds Memory Write & Information Leak on MCU)

## Root Cause Analysis
1. **Integer Wrap-Around Bypasses Check:**
   `sizeof(sdio->data_buffer)` is 4096.
   In `command_sdio_write_data_buffer`:
   ```c
   uint8_t *buf = &(sdio->data_buffer[offset]);
   if (offset + write_data_len <= sizeof(sdio->data_buffer)) {
       memcpy(buf, write_data, write_data_len);
   }
   ```
   If `offset = 0xFFFFFFF0` and `write_data_len = 32`, `offset + write_data_len` wraps to `16`. Since `16 <= 4096`, `memcpy` is executed.
   `buf` points to `sdio->data_buffer + 0xFFFFFFF0` (equivalent to `sdio->data_buffer - 16` on 32-bit MCU architectures).
   Looking at `struct sdiodev_s`:
   ```c
   struct sdiodev_s {
       struct sdio_config sdio_config;
       uint32_t blocksize;
       uint32_t speed;
       uint8_t data_buffer[4096];
   };
   ```
   The `memcpy` overwrites `sdio->speed`, `sdio->blocksize`, and the hardware peripheral pointer `sdio->sdio_config.sdio`.
2. **Undefined Behavior Pointer Arithmetic:**
   `uint8_t *buf = &(sdio->data_buffer[offset]);` was evaluated prior to bounds validation, invoking undefined behavior under C99 §6.5.6 when `offset` falls outside the array bounds.
3. **Out-of-Bounds Read in `command_sdio_read_data_buffer`:**
   Similarly, `if (offset + len > sizeof(sdio->data_buffer))` evaluated to false upon integer wrap-around, transmitting 32 bytes of internal MCU memory back to the host via `sendf()`.

## Steps to Reproduce
1. Allocate an SDIO device object via `config_sdio oid=1 blocksize=512`.
2. Send an `sdio_write_data_buffer` command with:
   - `oid = 1`
   - `offset = 0xFFFFFFF0` (4294967280)
   - `data = [32 bytes]`
3. Under AddressSanitizer (`-fsanitize=address`), this immediately triggers a crash:
   ```
   ==ERROR: AddressSanitizer: SEGV on unknown address 0x... (WRITE memory access)
       #0 in memcpy
       #1 in command_sdio_write_data_buffer_unpatched
   ```
4. On embedded hardware, the overwrite corrupts the heap and peripheral config structures, causing MCU hard faults or arbitrary code execution.

## Proposed Fix / Patch
1. Verify `offset >= sizeof(sdio->data_buffer)` first to prevent pointer calculation with out-of-range offsets.
2. Verify `len > sizeof(sdio->data_buffer) - offset` using subtraction to ensure no integer overflow can bypass the bounds check.
3. Only calculate the buffer pointer `&sdio->data_buffer[offset]` after bounds verification succeeds.
4. Add null pointer guards for `sdio` and `write_data`.

```diff
--- a/src/sdiocmds.c
+++ b/src/sdiocmds.c
@@ -138,11 +138,15 @@ command_sdio_read_data_buffer(uint32_t *args)
     uint32_t offset = args[1];
     uint8_t len = args[2];
     struct sdiodev_s *sdio = sdiodev_oid_lookup(oid);
-    uint8_t *buf = &(sdio->data_buffer[offset]);
+    if (!sdio) {
+        return;
+    }
 
-    if (offset + len > sizeof(sdio->data_buffer)) {
+    if (offset >= sizeof(sdio->data_buffer) ||
+        len > sizeof(sdio->data_buffer) - offset) {
         len = 0;
     }
+    uint8_t *buf = len ? &sdio->data_buffer[offset] : NULL;
     sendf("sdio_read_data_buffer_response oid=%c data=%*s", oid, len, buf);
 }
 DECL_COMMAND(command_sdio_read_data_buffer
@@ -156,11 +160,16 @@ command_sdio_write_data_buffer(uint32_t *args)
     uint8_t write_data_len = args[2];
     uint8_t *write_data = command_decode_ptr(args[3]);
     struct sdiodev_s *sdio = sdiodev_oid_lookup(oid);
-    uint8_t *buf = &(sdio->data_buffer[offset]);
+    if (!sdio || !write_data) {
+        return;
+    }
 
-    if (offset + write_data_len <= sizeof(sdio->data_buffer)) {
-        memcpy(buf, write_data, write_data_len);
+    if (offset >= sizeof(sdio->data_buffer) ||
+        write_data_len > sizeof(sdio->data_buffer) - offset) {
+        return;
     }
+    uint8_t *buf = &sdio->data_buffer[offset];
+    memcpy(buf, write_data, write_data_len);
 }
 DECL_COMMAND(command_sdio_write_data_buffer
              , "sdio_write_data_buffer oid=%c offset=%u data=%*s");
```

## Regression & Safety Verification
- Compiled and executed test harness `test/test_bug_buf01_sdio.c` with AddressSanitizer (`gcc -fsanitize=address`).
- Unpatched version: Reproducibly crashes with `SEGV on unknown address` (WRITE memory access).
- Patched version: All 6 test stages pass with zero sanitizer warnings:
  - Normal read/write within buffer bounds.
  - Exact boundary access (`offset = 4080`, `len = 16`).
  - Boundary overflow (`offset = 4080`, `len = 17`).
  - Integer overflow write exploit (`offset = 0xFFFFFFF0`, `len = 32`).
  - Integer overflow read exploit (`offset = 0xFFFFFFF0`, `len = 32`).

