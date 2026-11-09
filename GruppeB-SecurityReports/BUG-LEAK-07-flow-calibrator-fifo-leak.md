# BUG-LEAK-07: Flow Calculator FIFO File Descriptor Leak in `flow_calibrator.py`

## Summary
In `klippy/extras/flow_calibrator.py`, the `FlowCalcClient` handles communication with the external flow calculation server over Unix named pipes (FIFOs: `/tmp/flow_calculator_req` and `/tmp/flow_calculator_resp`). When I/O errors, parsing failures, protocol timeouts, or missing server conditions occur, file descriptors opened via `os.open()` are left open without guaranteed closure in `finally:` blocks. Over repeated calibration runs or network/daemon interruptions, this leaks file descriptors until the host process exhausts its descriptor limit, leading to system resource starvation and printer crashes.

## Component / Affected Files
- **File:** `klippy/extras/flow_calibrator.py`
- **Affected Functions:** `FlowCalcClient.calc_flow_factor()`, `FlowCalcClient._write_request()`
- **Lines:** 70-155

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules
- **Severity:** High (Resource leak of OS file descriptors and unhandled communication failure)

## Root Cause Analysis
In `FlowCalcClient.calc_flow_factor()`, `req_fd` and `resp_fd` were opened and then closed sequentially:
```python
req_fd = os.open(self.REQ_PIPE, os.O_WRONLY)
self._write_request(...)
os.close(req_fd)

resp_fd = os.open(self.RESP_PIPE, os.O_RDONLY)
response = self._read_response(resp_fd)
os.close(resp_fd)
```
If `self._write_request()` raised any exception (e.g., broken pipe, write buffer error), `req_fd` was never closed. Similarly, if `self._read_response()` threw an exception (e.g. invalid JSON, EOF on EOF before 4 bytes read), `resp_fd` remained leaked.
Furthermore, f-strings in logging calls broke dual Python 2/3 compatibility.

## Steps to Reproduce
1. Configure `flow_calibrator` in `printer.cfg`.
2. Trigger flow calculator check or calculation when FIFOs are unpopulated or severed.
3. Prior to the fix, any exception leaves opened descriptors dangling without explicit cleanup.

## Proposed Fix / Patch
1. Enclose both `req_fd` and `resp_fd` operations in strict nested `try ... finally:` blocks ensuring `os.close()` is always invoked.
2. Replace f-strings with `%` formatting in logger invocations.
3. Add `FLOW_CALCULATOR_CHECK` diagnostic G-code command that catches `FlowCalcError` and reports failures cleanly via `gcmd.error`.

```diff
--- a/klippy/extras/flow_calibrator.py
+++ b/klippy/extras/flow_calibrator.py
@@ -114,14 +120,24 @@ class FlowCalcClient:
         result = [None]
         error = [None]
 
         def _do_io():
+            req_fd = None
+            resp_fd = None
             try:
-                req_fd = os.open(self.REQ_PIPE, os.O_WRONLY)
-                self._write_request(req_fd, pt, freq, accel_time,
-                                    loop, slowv, fastv, drop1, drop2,
-                                    calc_mode, calc_mode_params)
-                os.close(req_fd)
-
-                resp_fd = os.open(self.RESP_PIPE, os.O_RDONLY)
-                response = self._read_response(resp_fd)
-                os.close(resp_fd)
-                result[0] = response
+                try:
+                    req_fd = os.open(self.REQ_PIPE, os.O_WRONLY)
+                    self._write_request(req_fd, pt, freq, accel_time,
+                                        loop, slowv, fastv, drop1, drop2,
+                                        calc_mode, calc_mode_params)
+                finally:
+                    if req_fd is not None:
+                        try:
+                            os.close(req_fd)
+                        except OSError:
+                            pass
+
+                try:
+                    resp_fd = os.open(self.RESP_PIPE, os.O_RDONLY)
+                    response = self._read_response(resp_fd)
+                    result[0] = response
+                finally:
+                    if resp_fd is not None:
+                        try:
+                            os.close(resp_fd)
+                        except OSError:
+                            pass
             except Exception as e:
                 error[0] = e
```

## Regression & Safety Verification
- Test case `test/klippy/bug_leak07_flow_calibrator.test` executed with virtual simulator configuration `bug_leak07_flow_calibrator.cfg`.
- Output: `All 1 test cases passed`.
- Verified that missing FIFOs are cleanly caught and reported as `gcmd.error` without leaks.

