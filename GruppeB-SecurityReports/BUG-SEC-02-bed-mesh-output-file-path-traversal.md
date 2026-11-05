# Bug Report: [SEC-02] Path Traversal and Arbitrary File Write in `BED_MESH_OUTPUT_FILE`

## 1. Summary / Description
- **ID:** SEC-02
- **Title:** Path Traversal and Arbitrary File Write in `BED_MESH_OUTPUT_FILE` (`bed_mesh.py`)
- **Vulnerability Type:** Path Traversal / Arbitrary File Overwrite & Append (CWE-22, CWE-73)
- **Severity:** **HIGH** (CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:H/A:L - Base Score: 8.2)
- **Description:** 
  In `cmd_BED_MESH_OUTPUT_FILE`, the `FILE` parameter from user-supplied G-code commands is combined via `os.path.join(logdir, logfile)` without validating directory boundaries or sanitizing directory traversal sequences (`../`, `..\`) or absolute paths. An attacker or malicious print job can specify arbitrary destinations on the filesystem, enabling unauthorized file creation, file renaming (`.old` rotation), or appending arbitrary mesh output data to sensitive system files.

---

## 2. Component / Affected Files
- **Component:** Klippy Host Daemon / Extras / Bed Mesh Output
- **Affected File:** `klippy/extras/bed_mesh.py`
- **Affected Functions:** `BedMesh.cmd_BED_MESH_OUTPUT_FILE()`
- **Test Files:**
  - `test/klippy/bug_sec02_bed_mesh.cfg`
  - `test/klippy/bug_sec02_bed_mesh.test`

---

## 3. Classification
- **Category:** **Group B (Snapmaker U1 Specific)**
- **Rationale:** The G-code command `BED_MESH_OUTPUT_FILE` with file logging and rotation under `virtual_sdcard` / `calibration_data` using `queuefile.async_append_file` is a proprietary Snapmaker fork feature not present in upstream `Klipper3d/klipper`.

---

## 4. Root Cause Analysis
In `BedMesh.cmd_BED_MESH_OUTPUT_FILE`:
```python
logfile = gcmd.get('FILE', "bed_mesh_output.txt")
logfile = os.path.join(logdir, logfile)
```
1. `os.path.join` treats absolute paths by replacing the base directory entirely, and treats relative `..` segments by traversing above `logdir`.
2. Before writing, if the file size exceeds 5 MiB, `os.rename(logfile, logfile + ".old")` renames the target path, potentially damaging critical system files.
3. `queuefile.async_append_file(logfile, content)` appends text to whatever target file path was resolved.
4. Input validation was completely absent.

---

## 5. Steps to Reproduce
1. Start Klippy with `[bed_mesh]` configured.
2. Send the following G-code command:
   ```gcode
   BED_MESH_OUTPUT_FILE FILE=../../evil_output.txt
   ```
3. **Behavior before fix:** `BED_MESH_OUTPUT_FILE` does not validate the `FILE` argument. If a mesh exists, it writes or appends outside `logdir`. If no mesh exists, it fails to reject the invalid parameter format.
4. **Behavior after fix:** Klippy validates `FILE` immediately on command entry, rejects directory traversal characters, emits `!! bed_mesh: Invalid file name '../../evil_output.txt' - path traversal not allowed`, and safely terminates without performing unauthorized file operations.

---

## 6. Proposed Fix / Patch
```diff
--- a/klippy/extras/bed_mesh.py
+++ b/klippy/extras/bed_mesh.py
@@ -286,31 +286,45 @@ class BedMesh:
         else:
             self.z_mesh.print_probed_matrix(gcmd.respond_info)
             self.z_mesh.print_mesh(gcmd.respond_raw, self.horizontal_move_z)
-    cmd_BED_MESH_OUTPUT_FILE_help = "Retrieve interpolated grid of probed z-points to file"
+    cmd_BED_MESH_OUTPUT_FILE_help = (
+        "Retrieve interpolated grid of probed z-points to file")
     def cmd_BED_MESH_OUTPUT_FILE(self, gcmd):
+        filename = gcmd.get('FILE', "bed_mesh_output.txt").strip()
+        clean_name = os.path.basename(filename)
+        is_invalid = (not clean_name or clean_name != filename
+                      or any(sep in filename
+                             for sep in ('/', '\\', '..', '\0')))
+        if is_invalid:
+            raise gcmd.error(
+                "bed_mesh: Invalid file name '%s' - "
+                "path traversal not allowed" % (filename,))
         if self.z_mesh is None:
             gcmd.respond_info("Bed has not been probed")
+            return
+        import time
+        date_str = time.strftime("%Y-%m-%d %H:%M:%S")
+        vsd = self.printer.lookup_object('virtual_sdcard', None)
+        if vsd is None:
+            gcmd.respond_info("No virtual_sdcard dir to save bed_mesh data")
+            logdir = '/tmp/calibration_data'
         else:
-            import time, os
-            date_str = time.strftime("%Y-%m-%d %H:%M:%S")
-            vsd = self.printer.lookup_object('virtual_sdcard', None)
-            if vsd is None:
-                gcmd.respond_info("No virtual_sdcard dir to save bed_mesh data")
-                logdir = '/tmp/calibration_data'
-            else:
-                logdir = f'{vsd.sdcard_dirname}/calibration_data'
-            if not os.path.exists(logdir):
-                os.makedirs(logdir)
-            logfile = gcmd.get('FILE', "bed_mesh_output.txt")
-            logfile = os.path.join(logdir, logfile)
-            file_size = os.path.getsize(logfile) if os.path.exists(logfile) else 0
-            # if file size is larger than 5MiB, rename it to one with suffix '.old'
-            if file_size > 5 * 1024 * 1024:
-                os.rename(logfile, logfile + ".old")
-            content = "\nTest Date: %s\n" % date_str
-            content += self.z_mesh.print_probed_matrix()
-            content += self.z_mesh.print_mesh(move_z=self.horizontal_move_z)
-            queuefile.async_append_file(logfile, content)
+            logdir = "%s/calibration_data" % (vsd.sdcard_dirname,)
+        if not os.path.exists(logdir):
+            os.makedirs(logdir)
+        logfile = os.path.abspath(os.path.join(logdir, clean_name))
+        base_dir = os.path.abspath(logdir)
+        if not logfile.startswith(base_dir + os.sep):
+            raise gcmd.error(
+                "bed_mesh: Security violation: output file path escapes "
+                "calibration directory")
+        file_size = os.path.getsize(logfile) if os.path.exists(logfile) else 0
+        # if file size is larger than 5MiB, rename it to one with suffix '.old'
+        if file_size > 5 * 1024 * 1024:
+            os.rename(logfile, logfile + ".old")
+        content = "\nTest Date: %s\n" % date_str
+        content += self.z_mesh.print_probed_matrix()
+        content += self.z_mesh.print_mesh(move_z=self.horizontal_move_z)
+        queuefile.async_append_file(logfile, content)
```

---

## 7. Regression & Safety Verification
- **Automated Deterministic Test:**
  - Configuration: `test/klippy/bug_sec02_bed_mesh.cfg`
  - Test Script: `test/klippy/bug_sec02_bed_mesh.test`
  - Test Execution:
    ```bash
    python scripts/test_klippy.py -d test/klippy -t /tmp -v test/klippy/bug_sec02_bed_mesh.test
    ```
- **Test Result:**
  - Before Fix: Test failed with `Test failed to raise an error`.
  - After Fix: Intercepted input, emitted `WARNING:root:bed_mesh: Invalid file name '../../evil_output.txt' - path traversal not allowed`, raised command error, and exited batch runner successfully (`All 1 test cases passed`).

