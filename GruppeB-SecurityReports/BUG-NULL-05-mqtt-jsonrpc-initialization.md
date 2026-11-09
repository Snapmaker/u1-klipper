# BUG-NULL-05: Missing Initialization of `self.mqtt_jsonrpc` in `defect_detection.py` & `None` Dereference in `timelapse.py`

## Summary
In `klippy/extras/defect_detection.py`, the attribute `self.mqtt_jsonrpc` was never initialized in `DefectDetection.__init__()`. When ready handler or MQTT initialization was skipped or delayed, any subsequent call to defect detection methods (`request_detect`, `_request_detect_noodle_first_sync`, `request_detect_clean_bed_sync`, `request_detect_nozzle_sync`, or their associated G-code commands) unconditionally attempted to dereference `self.mqtt_jsonrpc`, raising `AttributeError: 'DefectDetection' object has no attribute 'mqtt_jsonrpc'`.
Furthermore, in `klippy/extras/timelapse.py`, `self.mqtt_jsonrpc` was set to `None` in `__init__()`, but if `print_task_config` or `mqtt` was absent, `_handle_ready` returned early without initializing JSONRPC. Calls in `cmd_TIMELAPSE_START`, `cmd_TIMELAPSE_STOP`, and `cmd_TIMELAPSE_TAKE_FRAME` failed to verify `self.mqtt_jsonrpc is not None`, causing an unhandled `AttributeError: 'NoneType' object has no attribute 'send_request_with_response'`.

## Component / Affected Files
- **Files:**
  - `klippy/extras/defect_detection.py`
    - Lines: 89, 130-144, 375-408, 411-436, 477-512, 532-556, 717-769, 980-983
  - `klippy/extras/timelapse.py`
    - Lines: 52-65, 84-85, 124-128, 154-168, 193-195, 225-226

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Host Python
- **Severity:** High (Uncaught Exception / G-code Command Failure / Service Denial)

## Root Cause Analysis
1. In `defect_detection.py`:
   `DefectDetection.__init__()` initialized `self.mqtt_client = None` but omitted initializing `self.mqtt_jsonrpc = None`. In `_handle_ready()`, `self.mqtt_jsonrpc` was only instantiated if `self.printer.lookup_object("mqtt", None)` succeeded. Because `self.mqtt_jsonrpc` was not defined as an attribute on `self`, attempting to inspect or use it prior to or in absence of MQTT raised an `AttributeError`.
2. In `timelapse.py`:
   In `cmd_TIMELAPSE_START()` and `cmd_TIMELAPSE_STOP()`, checks were made for `self.mqtt_client is None`, but `self.mqtt_jsonrpc is None` was not checked. If JSONRPC initialization failed or was skipped due to missing `print_task_config`, dereferencing `self.mqtt_jsonrpc.send_request_with_response()` triggered an unhandled `AttributeError`.

## Steps to Reproduce
1. Configure printer without `print_task_config` or without `mqtt` client active.
2. Trigger `TIMELAPSE_START` or `TIMELAPSE_STOP` G-code command.
3. Observe unhandled `AttributeError: 'NoneType' object has no attribute 'send_request_with_response'`.
4. Trigger `DEFECT_DETECTION_DETECT` or `DEFECT_DETECTION_DETECT_BED`.
5. Observe crash `AttributeError: 'DefectDetection' object has no attribute 'mqtt_jsonrpc'`.

## Remediation
1. In `defect_detection.py`:
   - Initialize `self.mqtt_jsonrpc = None` in `__init__()`.
   - Wrap JSONRPC initialization in `_handle_ready()` in a defensive `try...except` block, setting `self.mqtt_jsonrpc = None` upon failure.
   - Add explicit guards `if self.mqtt_client is None or self.mqtt_jsonrpc is None:` across `request_detect()`, `_request_detect_noodle_first_sync()`, `request_detect_clean_bed_sync()`, `request_detect_nozzle_sync()`, and G-code commands (`cmd_DEFECT_DETECTION_START`, `cmd_DEFECT_DETECTION_DETECT`, `cmd_DEFECT_DETECT_NOODLE_FIRST`, `cmd_DEFECT_DETECTION_DETECT_BED`, `cmd_DEFECT_DETECTION_DETECT_NOZZLE`).
2. In `timelapse.py`:
   - Wrap JSONRPC creation in `_handle_ready()` in a `try...except` block.
   - Check `self.mqtt_jsonrpc is None` in `cmd_TIMELAPSE_START()`, `cmd_TIMELAPSE_STOP()`, and `cmd_TIMELAPSE_TAKE_FRAME()`.
   - Guard all call sites before sending requests.

## Verification
- Unit test implemented in `test/test_bug_null05.py`.
- Verified in Docker test environment `u1sim`:
  `python3 /app/klipper/test/test_bug_null05.py` executed with 3 tests passing.
- Whitespace validation `scripts/check_whitespace.py` verified with 0 warnings.

