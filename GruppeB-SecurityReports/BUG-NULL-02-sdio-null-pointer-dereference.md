# BUG-NULL-02: Null Pointer Dereference in SDIO and FatFS Subsystems

## Summary
In `src/sdiocmds.c`, `src/stm32/sdio.c`, and `scripts/spi_flash/fatfs_api.c`, pointers were dereferenced without prior null checks.
In `src/sdiocmds.c`, command dispatch handlers dereferenced `sdio` and peripheral hardware pointers (`sdio->sdio_config.sdio`) without null validation when called before `sdio_set_bus` or with an invalid OID, causing HardFault MCU crashes.
In `src/stm32/sdio.c`, `sdio_send_command()` checked `response_data != NULL` but unconditionally wrote `*response_data_len = 4;` and `*response_data_len = 16;`, dereferencing a potential null pointer.
In `scripts/spi_flash/fatfs_api.c`, `fatfs_open()` called `memset(fhdl, 0, ...)` before checking if `malloc()` returned `NULL`, and file/buffer pointers across `fatfs_close()`, `fatfs_read()`, `fatfs_write()`, `fatfs_remove()`, `fatfs_get_fstats()`, `fatfs_get_disk_info()`, and `fatfs_list_dir()` were accessed without null parameter validation.

## Component / Affected Files
- **File:** `src/sdiocmds.c`
  - **Affected Functions:** `command_config_sdio()`, `command_sdio_set_bus()`, `command_sdio_set_speed()`, `command_sdio_send_command()`, `command_sdio_read_data()`, `command_sdio_write_data()`
  - **Lines:** 25-135
- **File:** `src/stm32/sdio.c`
  - **Affected Functions:** `sdio_send_command()`
  - **Lines:** 199-230
- **File:** `scripts/spi_flash/fatfs_api.c`
  - **Affected Functions:** `fatfs_open()`, `fatfs_close()`, `fatfs_read()`, `fatfs_write()`, `fatfs_remove()`, `fatfs_get_fstats()`, `fatfs_get_disk_info()`, `fatfs_list_dir()`
  - **Lines:** 139-245

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Firmware
- **Severity:** High (MCU Crash / Host CFFI Segfault / Null Pointer Exception)

## Root Cause Analysis
1. **Unchecked OID Lookup and Bus Initialization in `src/sdiocmds.c`:**
   In SDIO command handlers, `sdio = sdiodev_oid_lookup(oid)` returns `NULL` if the OID was not configured. Furthermore, before `command_sdio_set_bus()` runs, `sdio->sdio_config.sdio` is null. Dereferencing these uninitialized pointers triggered immediate HardFault crashes on the microcontroller.
2. **Unchecked Output Length Pointer in `src/stm32/sdio.c`:**
   `sdio_send_command()` accepted `uint8_t *response_data_len` but directly wrote `*response_data_len = 4;` or `*response_data_len = 16;` without verifying `if (response_data_len != NULL)`.
3. **Unchecked Allocation and Null Arguments in `scripts/spi_flash/fatfs_api.c`:**
   In `fatfs_open()`, `malloc(sizeof(*fhdl))` was followed immediately by `memset(fhdl, 0, sizeof(*fhdl))` without verifying `fhdl != NULL`. If host memory was exhausted, this caused a null pointer write segfault. Similarly, public CFFI functions lacked defensive validation for null input paths and buffers.

## Steps to Reproduce
1. Establish communication with the MCU.
2. Send an `sdio_set_speed` command with `oid=1` before sending `sdio_set_bus`:
   ```
   config_sdio oid=1 blocksize=512
   sdio_set_speed oid=1 speed=25000000
   ```
3. Under AddressSanitizer (`-fsanitize=address`), this reproduces an immediate crash:
   ```
   AddressSanitizer:DEADLYSIGNAL
   =================================================================
   ==164==ERROR: AddressSanitizer: SEGV on unknown address 0x000000000000 (pc 0x63975a9ef2e4 bp 0x7ffee8259d40 sp 0x7ffee8259ce0 T0)
   ==164==The signal is caused by a WRITE memory access.
   ==164==Hint: address points to the zero page.
       #0 in sdio_set_speed
       #1 in command_sdio_set_speed_unpatched
       #2 in main
   ```
4. For FatFS, call `fatfs_read(NULL, buf, 10)` or `fatfs_open(NULL, 0)` from CFFI, triggering a segmentation fault.

## Proposed Fix / Patch
1. In `src/sdiocmds.c`, zero initialize `sdio->sdio_config` and check `!sdio || !sdio->sdio_config.sdio` before accessing hardware registers, returning error responses (`error=1`) to the host.
2. In `src/stm32/sdio.c`, wrap response length writes in `if (response_data_len != NULL)`.
3. In `scripts/spi_flash/fatfs_api.c`, validate pointer arguments and verify `fhdl != NULL` before calling `memset()`.

```diff
--- a/src/sdiocmds.c
+++ b/src/sdiocmds.c
@@ -25,6 +25,7 @@ command_config_sdio(uint32_t *args)
 {
     struct sdiodev_s *sdio = oid_alloc(args[0], command_config_sdio
                                        , sizeof(*sdio));
+    memset(&sdio->sdio_config, 0, sizeof(sdio->sdio_config));
     sdio->blocksize = args[1];
     sdio->speed = 400000; // Initial speed set to ~400khz
 }
@@ -40,6 +41,9 @@ void
 command_sdio_set_bus(uint32_t *args)
 {
     struct sdiodev_s *sdio = sdiodev_oid_lookup(args[0]);
+    if (!sdio) {
+        return;
+    }
     sdio->sdio_config = sdio_setup(args[1]);
 }
 DECL_COMMAND(command_sdio_set_bus, "sdio_set_bus oid=%c sdio_bus=%u");
@@ -48,6 +52,9 @@ void
 command_sdio_set_speed(uint32_t *args)
 {
     struct sdiodev_s *sdio = sdiodev_oid_lookup(args[0]);
+    if (!sdio || !sdio->sdio_config.sdio) {
+        return;
+    }
     sdio->speed = args[1];
     sdio_set_speed(sdio->sdio_config, sdio->speed);
 }
@@ -61,6 +68,11 @@ command_sdio_send_command(uint32_t *args)
     uint32_t argument = args[2];
     uint8_t wait = args[3];
     struct sdiodev_s *sdio = sdiodev_oid_lookup(oid);
+    if (!sdio || !sdio->sdio_config.sdio) {
+        sendf("sdio_send_command_response oid=%c error=%c response=%*s"
+              , oid, 1, 0, "");
+        return;
+    }
     uint8_t response[16];
     uint8_t response_len = 0;
     uint8_t err = sdio_send_command(sdio->sdio_config, cmd, argument, wait
--- a/src/stm32/sdio.c
+++ b/src/stm32/sdio.c
@@ -202,7 +202,9 @@ sdio_send_command(struct sdio_config sdio_config, uint8_t cmd,
             response_data[1] = (uint8_t) ((sdio->RESP1 >> 16) & 0xFF);
             response_data[2] = (uint8_t) ((sdio->RESP1 >> 8) & 0xFF);
             response_data[3] = (uint8_t) ((sdio->RESP1) & 0xFF);
-            *response_data_len = 4;
+            if (response_data_len != NULL) {
+                *response_data_len = 4;
+            }
         } else if (wait == SDIO_WAIT_LONG_RESPONSE) {
             // TODO Inverse?
             response_data[0] =  (uint8_t) ((sdio->RESP1 >> 24) & 0xFF);
@@ -221,7 +223,9 @@ sdio_send_command(struct sdio_config sdio_config, uint8_t cmd,
             response_data[13] = (uint8_t) ((sdio->RESP4 >> 16) & 0xFF);
             response_data[14] = (uint8_t) ((sdio->RESP4 >> 8) & 0xFF);
             response_data[15] = (uint8_t) ((sdio->RESP4) & 0xFF);
-            *response_data_len = 16;
+            if (response_data_len != NULL) {
+                *response_data_len = 16;
+            }
         }
     }
--- a/scripts/spi_flash/fatfs_api.c
+++ b/scripts/spi_flash/fatfs_api.c
@@ -139,7 +139,11 @@ struct ff_file* __visible
 fatfs_open(const char* path, uint8_t mode)
 {
     FRESULT res;
+    if (!path)
+        return NULL;
     struct ff_file* fhdl = malloc(sizeof(*fhdl));
+    if (!fhdl)
+        return NULL;
     memset(fhdl, 0, sizeof(*fhdl));
     res = f_open(&(fhdl->fobj), path, mode);
     if (res != FR_OK) {
@@ -153,6 +157,8 @@ uint8_t __visible
 fatfs_close(struct ff_file* fhdl)
 {
     FRESULT res;
+    if (!fhdl)
+        return FR_INVALID_OBJECT;
     res = f_close(&(fhdl->fobj));
     free(fhdl);
     return res;
@@ -163,6 +169,8 @@ fatfs_read(struct ff_file* fhdl, void* rbuf, uint16_t btr)
 {
     FRESULT res;
     UINT bytes_read;
+    if (!fhdl || !rbuf)
+        return -FR_INVALID_OBJECT;
     res = f_read(&(fhdl->fobj), rbuf, btr, &bytes_read);
     if (res != FR_OK) {
         return -res;
```

## Regression & Safety Verification
- **Automated ASan & C Unit Tests:**
  - `test/test_bug_null02_sdio.c`: Validated pre-fix crash and post-fix defensive behavior with AddressSanitizer.
  - `test/test_bug_null02_fatfs.c`: Validated `scripts/spi_flash/fatfs_api.c` null argument handling and `src/stm32/sdio.c` null `response_data_len` protection without crashing.
- **Whitespace Compliance:** Verified with `scripts/check_whitespace.py` (0 errors).
- **Regression:** Verified that valid FatFS and SDIO operations function normally according to hardware protocol specifications.
