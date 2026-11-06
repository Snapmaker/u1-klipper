# BUG-LEAK-08: GPIO File Descriptor Leak and Background Thread Leaks in `fm175xx_reader.py` and `mqtt.py`

## Summary
In `klippy/extras/fm175xx_reader.py` and `klippy/extras/mqtt.py`, multiple resource lifecycle management issues caused persistent file descriptor leaks and unjoined/dangling background threads:
1. In `fm175xx_reader.py`, `chip = gpiod.Chip('gpiochip1')` was instantiated as a local variable in `__init__()`. Although requested GPIO lines were released on shutdown, the underlying chip file descriptor (`/dev/gpiochip1`) was never tracked or closed with `chip.close()`, causing permanent descriptor leaks.
2. In `fm175xx_reader.py`, `__ready()` started a background thread `threading.Thread(target=self.__bg_thread)` without assigning it to an instance variable. During Klippy shutdowns or restarts (`__shutdown()`), this thread was never joined, leaving an active thread running against tear-down hardware resources.
3. In `mqtt.py`, `self.client.loop_start()` was called before `self.client.connect()`. If `connect()` failed or threw an unhandled network error, the paho-mqtt background network loop remained running indefinitely in the background, consuming CPU and sockets.

## Component / Affected Files
- **File:** `klippy/extras/fm175xx_reader.py`
  - **Affected Methods:** `__init__()`, `__ready()`, `__shutdown()`
  - **Lines:** 217-274
- **File:** `klippy/extras/mqtt.py`
  - **Affected Methods:** `__init__()`, `_handle_shutdown()`, `_handle_request_restart()`
  - **Lines:** 47-64

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Host Python
- **Severity:** High (Resource Leaks / File Descriptor Exhaustion / Dangling Threads across Host Lifecycle)

## Root Cause Analysis
1. In `fm175xx_reader.py`, the libgpiod `Chip` object holds an open file descriptor to the Linux character device `/dev/gpiochip1`. Since `chip` was only stored in a local stack variable during `__init__()`, garbage collection could not guarantee immediate reclamation, and `chip.close()` was never invoked upon system shutdown.
2. In `fm175xx_reader.py`, `background_thread` was created as a local variable in `__ready()`. When `__shutdown()` executed, it set `self.__stop_event.set()` but had no handle to join the thread, immediately continuing to release pins and SPI bus descriptors.
3. In `mqtt.py`, starting the event loop via `loop_start()` before establishing a connection left the thread unmanaged if `connect()` failed. Additionally, `_handle_shutdown()` and `_handle_request_restart()` lacked defensive error handling around disconnection and loop stopping.

## Steps to Reproduce
1. In `fm175xx_reader.py`:
   - Initialize `FM175XXReader`. Check open file descriptors (`ls -l /proc/$PID/fd`).
   - Trigger `FIRMWARE_RESTART`. Notice `/dev/gpiochip1` descriptor count increments continuously without release.
2. In `mqtt.py`:
   - Configure an unreachable MQTT broker IP or simulate connection drop during startup.
   - Observe that `self.client.loop_start()` thread remains alive and detached.

## Proposed Fix / Patch
```diff
diff --git a/klippy/extras/fm175xx_reader.py b/klippy/extras/fm175xx_reader.py
--- a/klippy/extras/fm175xx_reader.py
+++ b/klippy/extras/fm175xx_reader.py
@@ -216,13 +216,23 @@ class FM175XXReader:
         # Pins
-        chip = gpiod.Chip('gpiochip1')
-        self.__soc_rst_pin = chip.get_line(25)
+        self.__gpio_chip = None
+        self.__soc_rst_pin = None
+        self.__extra_rst_pin = None
+        self.__rf_1_pin = None
+        self.__rf_2_pin = None
+        try:
+            self.__gpio_chip = gpiod.Chip('gpiochip1')
+            self.__soc_rst_pin = self.__gpio_chip.get_line(25)
+            self.__soc_rst_pin.request(consumer='soc_rst_pin',
+                                       type=gpiod.LINE_REQ_DIR_OUT, default_val=0)
+            self.__extra_rst_pin = self.__gpio_chip.get_line(28)
+            self.__extra_rst_pin.request(consumer='extra_rst_pin',
+                                         type=gpiod.LINE_REQ_DIR_OUT, default_val=0)
+            self.__rf_1_pin = self.__gpio_chip.get_line(27)
+            self.__rf_1_pin.request(consumer='rf_1_pin',
+                                    type=gpiod.LINE_REQ_DIR_OUT, default_val=0)
+            self.__rf_2_pin = self.__gpio_chip.get_line(24)
+            self.__rf_2_pin.request(consumer='rf_2_pin',
+                                    type=gpiod.LINE_REQ_DIR_OUT, default_val=0)
+        except Exception:
+            logging.exception("Failed to initialize GPIO lines for FM175XX")
@@ -234,2 +244,3 @@ class FM175XXReader:
         self.__picc_a = Fm175xxPiccMetaData()
+        self.__bg_thread = None
@@ -248,3 +259,3 @@ class FM175XXReader:
         # Threading
-        background_thread = threading.Thread(target=self.__bg_thread)
-        background_thread.start()
+        self.__bg_thread = threading.Thread(target=self.__bg_thread)
+        self.__bg_thread.start()
@@ -253,2 +264,5 @@ class FM175XXReader:
         self.__stop_event.set()
+        if self.__bg_thread is not None and self.__bg_thread.is_alive():
+            self.__bg_thread.join(timeout=2.0)
+            self.__bg_thread = None
+        for pin in (self.__soc_rst_pin, self.__extra_rst_pin,
+                    self.__rf_1_pin, self.__rf_2_pin):
+            if pin is not None:
+                try:
+                    pin.release()
+                except Exception:
+                    pass
@@ -273,2 +287,7 @@ class FM175XXReader:
+        try:
+            if self.__gpio_chip is not None:
+                self.__gpio_chip.close()
+                self.__gpio_chip = None
+        except Exception:
+            pass
diff --git a/klippy/extras/mqtt.py b/klippy/extras/mqtt.py
--- a/klippy/extras/mqtt.py
+++ b/klippy/extras/mqtt.py
@@ -47,3 +47,10 @@ class MQTT:
-        self.client.loop_start()
         self.client.reconnect_delay_set(min_delay=1, max_delay=120)
-        self.client.connect(self.address, self.port)
+        try:
+            self.client.connect_async(self.address, self.port)
+            self.client.loop_start()
+        except Exception:
+            try:
+                self.client.loop_stop()
+            except Exception:
+                pass
+            raise
```

## Verification & Automated Tests
- Test harness implemented in `test/test_bug_leak08.py`:
  - `test_fm175xx_gpio_and_thread_cleanup`: Verifies that `chip.close()` and thread joining execute cleanly during shutdown.
  - `test_mqtt_connection_failure_no_thread_leak`: Verifies that connection failures do not leak the network background loop thread.
  - `test_mqtt_successful_connection_and_shutdown`: Verifies normal connection and graceful shutdown.
- Test execution:
  - `python3 test/test_bug_leak08.py` passes 3/3 tests cleanly.
  - `python3 scripts/check_whitespace.py` passes with 0 errors.

