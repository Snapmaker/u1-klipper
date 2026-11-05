# Security & Bug Report: BUG-SEC-03 - Path Traversal / Arbitrary File Append via `LOG_FILE` in `probe_inductance_coil.py`

## 1. Summary / Description
A path traversal vulnerability exists in `klippy/extras/probe_inductance_coil.py` within `ProbeSessionHelper.get_probe_params()` and `run_probe()`. The `LOG_FILE` parameter passed to probe commands (such as `PROBE_ACCURACY`, `PROBE`, `PROBE_XYZ_OFFSET_CALIBRATE`) was accepted without filename sanitization, allowing arbitrary relative or absolute directory traversal sequences (`../`, `..\\`).

When a probe run finishes, raw probe coordinate data was appended to the attacker-controlled path under `/userdata/gcodes/calibration_data/<LOG_FILE>`, enabling arbitrary file creation, data corruption, or path escape across the host filesystem.

## 2. Component / Affected Files
- **Affected File:** `klippy/extras/probe_inductance_coil.py`
- **Affected Methods:** `ProbeSessionHelper.get_probe_params()`, `ProbeSessionHelper.run_probe()`, `ProbeCommandHelper.cmd_PROBE_XYZ_OFFSET_CALIBRATE()`
- **Lines Affected:** Lines ~510-534, ~728-745, ~999-1035

## 3. Classification
- **Category:** Path Traversal / Arbitrary File Write & Append
- **CWE:** CWE-22 (Improper Limitation of a Pathname to a Restricted Directory)
- **Group:** Group B (Snapmaker U1 Specific Extension)
- **Severity:** High

## 4. Root Cause Analysis
In `ProbeSessionHelper.get_probe_params()`:
```python
log_file = gcmd.get("LOG_FILE", None)
```
The parameter was retrieved and passed into `params['log_file']` without checking for path delimiters (`/`, `\`), parent traversal (`..`), or null bytes.

In `ProbeSessionHelper.run_probe()`:
```python
if params.get('log_file') != None:
    logdir = '/userdata/gcodes/calibration_data'
    ...
    queuefile.async_append_file(f'{logdir}/{params["log_file"]}', content)
```
The filename was joined directly with a hardcoded path string. If `params['log_file']` contained directory traversal elements like `../../etc/evil.txt`, the resulting path escaped `/userdata/gcodes/calibration_data/` and appended content into arbitrary system files. In addition, hardcoded `/userdata` directories broke portability, and modern Python 3.6+ f-strings were used, violating Klipper's Python 2.7 / 3 dual-compatibility requirement.

## 5. Steps to Reproduce
1. Configure `probe_inductance_coil` or `inductance_coil`.
2. Issue G-Code:
   `PROBE_ACCURACY SAFETY_CHECK=0 LOG_FILE=../../evil_log.txt`
3. Before fix: Path traversal is accepted; file append is scheduled outside calibration directory.
4. Deterministic batch test: `test/klippy/bug_sec03_probe_inductance_coil.test`.

## 6. Proposed Fix / Patch
The fix implements defense-in-depth:
1. Validates `LOG_FILE` in `get_probe_params()` using `os.path.basename` and rejects any path separators, traversal sequences, or null bytes immediately with a G-code error.
2. In `run_probe()`, resolves the target path dynamically via `virtual_sdcard` (or `/tmp/calibration_data`), verifies that canonical `os.path.abspath()` remains strictly inside the calibration directory, and replaces Python 3 f-strings with `%` formatting.

```diff
--- a/klippy/extras/probe_inductance_coil.py
+++ b/klippy/extras/probe_inductance_coil.py
@@ -740,7 +740,17 @@ class ProbeSessionHelper:
         # horizontal_dist = gcmd.get_float("HORIZONTAL_DIST", 2.0, minval=1.0)
         # probe_xyz_mode = gcmd.get_int("PROBE_XYZ_MODE", RECTANGLE_PROBE_MODE, minval=RECTANGLE_PROBE_MODE, maxval=CIRCLE_PROBE_MODE)
         log_file = gcmd.get("LOG_FILE", None)
+        if log_file is not None:
+            filename = log_file.strip()
+            clean_name = os.path.basename(filename)
+            is_invalid = (not clean_name or clean_name != filename
+                          or any(sep in filename
+                                 for sep in ('/', '\\', '..', '\0')))
+            if is_invalid:
+                raise gcmd.error(
+                    "probe_inductance_coil: Invalid log file name '%s' - "
+                    "path traversal not allowed" % (filename,))
         xy_start_pos = gcmd.get_float("XY_START_POS", -6)
@@ -1023,13 +1033,43 @@ class ProbeSessionHelper:
         # save result for slow speed
-        if params.get('log_file') != None:
-            logdir = '/userdata/gcodes/calibration_data'
-            if not os.path.exists(logdir):
-                os.makedirs(logdir)
-            content = ""
-            for p in filter_pos:
-                content += f'{p[0]:.6f}, {p[1]:.6f}, {p[2]:.6f}\n'
-            content += ' , , \n'
-            try:
-                queuefile.async_append_file(f'{logdir}/{params["log_file"]}', content)
-            except Exception as e:
-                logging.exception(f"Failed to append to file {params['log_file']}: {e}")
+        if params.get('log_file') is not None:
+            clean_name = os.path.basename(params['log_file'].strip())
+            is_invalid = (not clean_name or clean_name != params['log_file']
+                          or any(sep in params['log_file']
+                                 for sep in ('/', '\\', '..', '\0')))
+            if is_invalid:
+                logging.error(
+                    "probe_inductance_coil: Invalid log file '%s' - "
+                    "skipping log write" % (params['log_file'],))
+            else:
+                vsd = self.printer.lookup_object('virtual_sdcard', None)
+                if vsd is not None and vsd.sdcard_dirname:
+                    logdir = os.path.join(vsd.sdcard_dirname,
+                                          'calibration_data')
+                else:
+                    logdir = '/tmp/calibration_data'
+                if not os.path.exists(logdir):
+                    try:
+                        os.makedirs(logdir)
+                    except OSError:
+                        pass
+                logfile = os.path.abspath(os.path.join(logdir, clean_name))
+                base_dir = os.path.abspath(logdir)
+                if not logfile.startswith(base_dir + os.sep):
+                    logging.error(
+                        "probe_inductance_coil: Security violation: "
+                        "log file path escapes calibration directory: %s"
+                        % (logfile,))
+                else:
+                    content = ""
+                    for p in filter_pos:
+                        content += "%.6f, %.6f, %.6f\n" % (p[0], p[1], p[2])
+                    content += " , , \n"
+                    try:
+                        queuefile.async_append_file(logfile, content)
+                    except Exception as e:
+                        logging.exception("Failed to append to file %s: %s"
+                                          % (logfile, str(e)))
```

## 7. Regression & Safety Verification
- **Deterministic Batch Test:** Verified with `test/klippy/bug_sec03_probe_inductance_coil.test` through `scripts/test_klippy.py`.
- **Formatting & CI Check:** Verified via `scripts/check_whitespace.py` (0 errors, <= 80 chars per line, pure LF).
- **Full Suite Verification:** All 6 test cases passed cleanly.

