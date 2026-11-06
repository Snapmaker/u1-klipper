# BUG-EXC-05: Swallowed `gcmd.error()` Exception in `inductance_coil.py`

## Summary
In `klippy/extras/inductance_coil.py`, `FrequencyCommandHelper.cmd_FREQUENCY_MEASURE()` caught all runtime exceptions during directory creation and sample data writing with `except Exception as e:` and invoked `gcmd.error(e)` without the `raise` keyword. In Klipper's command architecture, `gcmd.error(msg)` does not raise an exception itself; it acts as a constructor returning a `CommandError` instance. Calling `gcmd.error(e)` without `raise` caused errors (such as disk full, permission denied, or invalid paths) to be silently discarded. Klippy indicated to the user and caller that the measurement file had been saved successfully despite write operations failing completely.

## Component / Affected Files
- **File:** `klippy/extras/inductance_coil.py`
  - **Affected Methods:** `FrequencyCommandHelper.cmd_FREQUENCY_MEASURE()`
  - **Lines:** 152-153

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Host Python
- **Severity:** High (Silent Failure / Swallowed Exception / False Success Reporting)

## Root Cause Analysis
Klipper's `GCodeDispatch.error()` / `gcmd.error()` is an exception factory:
```python
def error(self, message):
    return self.command_error(message)
```
In `cmd_FREQUENCY_MEASURE`:
```python
try:
    ...
    bg_client.write_to_file(filename)
    gcmd.respond_info("Writing raw frequency data to %s file" % (str(filename),))
except Exception as e:
    gcmd.error(e)  # Creates CommandError object and drops it on the floor!
```
Because `raise` was omitted, Python did not propagate the error. Execution exited normally, masking severe filesystem errors and misleading automation scripts into expecting generated frequency log files.

## Steps to Reproduce
1. Trigger `FREQUENCY_MEASURE` on a read-only filesystem or with a permission-restricted path for `frequency_data`.
2. Observe `cmd_FREQUENCY_MEASURE` finishing without throwing any error or signaling failure.
3. Check the target directory: no file was created, yet the G-Code console reported success.

## Proposed Fix / Patch
```diff
diff --git a/klippy/extras/inductance_coil.py b/klippy/extras/inductance_coil.py
--- a/klippy/extras/inductance_coil.py
+++ b/klippy/extras/inductance_coil.py
@@ -152,2 +152,2 @@ class FrequencyCommandHelper:
         except Exception as e:
-            gcmd.error(e)
+            raise gcmd.error(str(e))
```

## Verification
- Unit test `test/test_bug_exc05.py` verified:
  - Confirms that calling `gcmd.error(e)` without `raise` silently swallows errors.
  - Confirms that `raise gcmd.error(str(e))` correctly halts execution and raises a `CommandError` with the failure message.

