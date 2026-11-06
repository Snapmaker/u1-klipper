# BUG-UAF-05: Use-After-Close Race Condition during RFID Reader Shutdown in `fm175xx_reader.py`

## Summary
In `klippy/extras/fm175xx_reader.py`, `__shutdown()` initiated shutdown by signalling `self.__stop_event.set()` and immediately proceeded to release GPIO pin handles (`pin.release()`) and close the SPI bus file descriptor (`self.__spi.close()`). Because it never joined or waited for the background polling thread (`__bg_thread`), the active thread continued executing SPI transfers (`spi.xfer2`, `spi.writebytes`) and GPIO toggles against closed file descriptors, triggering unhandled `OSError: [Errno 9] Bad file descriptor` crashes during firmware restart or printer shutdown.

## Component / Affected Files
- **File:** `klippy/extras/fm175xx_reader.py`
  - **Affected Methods:** `__shutdown()`, `__ready()`, `__hard_reset()`
  - **Lines:** 252-274, 301-305

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Host Python
- **Severity:** Medium (Race Condition / Use-After-Close / `OSError: Bad file descriptor` on System Shutdown)

## Root Cause Analysis
1. When Klippy shuts down or restarts (via `FIRMWARE_RESTART`, `klippy:shutdown`, or `gcode:request_restart`), all registered shutdown callbacks run sequentially on the main reactor thread.
2. In `FM175XXReader`, the RFID card polling loop runs in a separate thread `__bg_thread`. When `__shutdown()` was called, it set `self.__stop_event.set()` but immediately tore down the underlying hardware objects:
   - `self.__soc_rst_pin.release()`
   - `self.__extra_rst_pin.release()`
   - `self.__rf_1_pin.release()`
   - `self.__rf_2_pin.release()`
   - `self.__spi.close()`
3. If `__bg_thread` was in the middle of a card communication cycle (such as `__reader_a_init()`, `__select_channel()`, or `__reader_a_activate()`), it attempted to communicate over the now closed SPI or GPIO handles, raising `OSError: [Errno 9] Bad file descriptor`.

## Steps to Reproduce
1. Start Klippy with `fm175xx_reader` enabled and active RFID card polling.
2. Execute `RESTART` or `FIRMWARE_RESTART` while a card detection cycle is in progress.
3. Observe background thread traceback with `OSError: [Errno 9] Bad file descriptor` originating from `spidev` or `gpiod`.

## Proposed Fix / Patch
```diff
diff --git a/klippy/extras/fm175xx_reader.py b/klippy/extras/fm175xx_reader.py
--- a/klippy/extras/fm175xx_reader.py
+++ b/klippy/extras/fm175xx_reader.py
@@ -252,6 +252,9 @@ class FM175XXReader:
     def __shutdown(self, eventtime=None):
         self.__stop_event.set()
+        if self.__bg_thread is not None and self.__bg_thread.is_alive():
+            self.__bg_thread.join(timeout=2.0)
+            self.__bg_thread = None
         for pin in (self.__soc_rst_pin, self.__extra_rst_pin,
                     self.__rf_1_pin, self.__rf_2_pin):
             if pin is not None:
@@ -301,3 +304,4 @@ class FM175XXReader:
     # hardware reset
     def __hard_reset(self):
-        self.__rst_pin.set_value(0)
+        if self.__rst_pin is not None:
+            self.__rst_pin.set_value(0)
```

## Verification & Automated Tests
- Test harness implemented in `test/test_bug_uaf05.py`:
  - `test_shutdown_avoids_use_after_close`: Verifies that stop signalling followed by `join(timeout=2.0)` guarantees the background thread has exited cleanly before hardware descriptors are closed.
  - `test_uncoordinated_shutdown_triggers_bad_fd`: Verifies that the previous shutdown order triggers `OSError: Bad file descriptor`.
- Test execution:
  - `python3 test/test_bug_uaf05.py` passes 2/2 tests cleanly.
  - `python3 scripts/check_whitespace.py` passes with 0 errors.

