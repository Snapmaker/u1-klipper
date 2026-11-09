# BUG-DIV-05: Division by Zero & `date_rate` Typo in `inductance_coil.py`

## Summary
In `klippy/extras/inductance_coil.py`, the sample rate configuration parameter was read using a misspelled option name: `config.getint('date_rate', 1000)` without specifying a minimum value (`minval=1`). When starting sensor bulk measurements in `_start_measurements()`, the MCU clock period was calculated via `rest_ticks = self._mcu.seconds_to_clock(1 / self._data_rate)`. If `date_rate` was configured as 0 (or set via bad input), an immediate unhandled `ZeroDivisionError` crashed the Klippy host service. Additionally, user configurations specifying the correct spelling `data_rate` were ignored and fell back to the default 1000.

## Component / Affected Files
- **File:** `klippy/extras/inductance_coil.py`
  - **Affected Methods:** `InductanceCoil.__init__()`, `InductanceCoil._start_measurements()`
  - **Lines:** 186, 267

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Host Python
- **Severity:** High (Klippy Host Crash / Unhandled ZeroDivisionError / Config Misconfiguration)

## Root Cause Analysis
1. Typo in configuration parser: `config.getint('date_rate', 1000)` prevents printer administrators from setting the standard `data_rate` property in `printer.cfg`.
2. Absence of lower bound check: `config.getint('date_rate', 1000)` did not specify `minval=1`. Configuring `date_rate: 0` succeeded during configuration parsing.
3. Unprotected division: In `_start_measurements()`, `1 / self._data_rate` performs float division without checking whether `self._data_rate > 0`. If `self._data_rate == 0`, a `ZeroDivisionError` is raised, causing Klippy shutdown.

## Steps to Reproduce
1. In `printer.cfg`, configure an `[inductance_coil]` section with `date_rate: 0` or attempt to override rate with `data_rate: 500`.
2. Observe that `data_rate: 500` is ignored.
3. Start frequency measurement: `ZeroDivisionError: division by zero` crashes Klippy.

## Proposed Fix / Patch
```diff
diff --git a/klippy/extras/inductance_coil.py b/klippy/extras/inductance_coil.py
--- a/klippy/extras/inductance_coil.py
+++ b/klippy/extras/inductance_coil.py
@@ -184,3 +184,6 @@ class InductanceCoil:
         # setup bulk sensor helper, Process messages in batches
         FrequencyCommandHelper(config, self)
-        self._data_rate = config.getint('date_rate', 1000)
+        data_rate = config.getint('data_rate', None, minval=1)
+        if data_rate is None:
+            data_rate = config.getint('date_rate', 1000, minval=1)
+        self._data_rate = data_rate
         chip_smooth = self._data_rate * BATCH_UPDATES * 2
@@ -265,3 +268,6 @@ class InductanceCoil:
     def _start_measurements(self):
         # Start bulk reading
+        if self._data_rate <= 0:
+            raise self.printer.command_error(
+                "Invalid data_rate in inductance_coil")
-        rest_ticks = self._mcu.seconds_to_clock(1 / self._data_rate)
+        rest_ticks = self._mcu.seconds_to_clock(1.0 / self._data_rate)
```

## Verification
- Unit test `test/test_bug_div05.py` verified:
  - Correctly parses `data_rate` with `minval=1`.
  - Maintains backward compatibility with `date_rate` fallback.
  - Correctly rejects 0 and negative rates.
  - Prevents zero division in `_start_measurements()`.

