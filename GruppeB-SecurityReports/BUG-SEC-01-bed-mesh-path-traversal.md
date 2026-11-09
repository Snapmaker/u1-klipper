# Bug Report: [SEC-01] Path Traversal and Arbitrary File Overwrite/Deletion in `ProfileManager`

## 1. Summary / Description
- **ID:** SEC-01
- **Title:** Path Traversal and Arbitrary File Overwrite/Deletion in `ProfileManager` (`bed_mesh.py`)
- **Vulnerability Type:** Path Traversal (CWE-22, CWE-73)
- **Severity:** **CRITICAL** (CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:H/A:H - Base Score: 9.1)
- **Description:** 
  The Snapmaker custom storage implementation in `ProfileManager` (`klippy/extras/bed_mesh.py`) accepts user supplied profile names via G-code commands (`BED_MESH_PROFILE SAVE=...`, `LOAD=...`, `REMOVE=...`) without sanitization or directory boundary validation. By supplying directory traversal sequences (`../`, `..\`) or path separators, an attacker or untrusted print job G-code script can traverse outside the intended configuration directory. This allows overwriting, reading, or permanently deleting arbitrary `.json` files on the host filesystem with the privileges of the Klippy daemon.

---

## 2. Component / Affected Files
- **Component:** Klippy Host Daemon / Extras / Bed Mesh Profile Manager (Snapmaker Custom Storage)
- **Affected File:** `klippy/extras/bed_mesh.py`
- **Affected Functions:** `ProfileManager._save_profile_custom()`, `ProfileManager._load_profile_custom()`, `ProfileManager._remove_profile_custom()`
- **Test Files:**
  - `test/klippy/bug_sec01_bed_mesh.cfg`
  - `test/klippy/bug_sec01_bed_mesh.test`

---

## 3. Classification
- **Category:** **Group B (Snapmaker U1 Specific)**
- **Rationale:** The `save_custom_path` feature utilizing separate JSON file persistence via `_save_profile_custom`, `_load_profile_custom`, and `_remove_profile_custom` in conjunction with `printer.get_snapmaker_config_dir()` and `queuefile.async_write_file` is a proprietary Snapmaker fork enhancement not present in upstream `Klipper3d/klipper`.

---

## 4. Root Cause Analysis
When `save_custom_path` is enabled in configuration, `ProfileManager` constructs disk paths by directly formatting the unvalidated parameter:
```python
lower_prof_name = prof_name.lower()
file_path = os.path.join(self.config_dir, f"bed_mesh_{lower_prof_name}.json")
```
No validation or sanitization was performed against `prof_name`. When a path traversal sequence such as `../../evil_path` is provided:
1. `lower_prof_name` resolves to `../../evil_path`.
2. `f"bed_mesh_{lower_prof_name}.json"` produces `"bed_mesh_../../evil_path.json"`.
3. In both POSIX and Windows environments, `os.path.join()` treats `..` components by moving up the directory tree relative to `self.config_dir`.
4. In `_remove_profile_custom()`, `os.remove(file_path)` deletes the targeted file outside the configuration directory.
5. In `_save_profile_custom()`, the JSON payload is written to `file_path`, clobbering existing configuration or state files outside the sandbox directory.

---

## 5. Steps to Reproduce
1. Start Klippy with `save_custom_path: True` configured under `[bed_mesh]`.
2. Execute the following G-code command via the batch test runner or terminal:
   ```gcode
   BED_MESH_PROFILE LOAD=../../evil_path
   ```
3. **Behavior before fix:** Klippy attempts to open `/evil_path.json` or traverses out of the configuration directory, logging file access errors or mutating files outside `config_dir`.
4. **Behavior after fix:** Klippy intercepts the input, rejects traversal characters, emits `!! bed_mesh: Invalid profile name '../../evil_path' - path traversal not allowed`, and safely terminates execution without touching any filesystem resources outside `config_dir`.

---

## 6. Proposed Fix / Patch
Introduce strict input validation via a helper `_get_custom_profile_path(prof_name)`. The helper ensures:
1. The profile name does not contain path separators (`/`, `\`), null bytes (`\0`), or parent directory references (`..`).
2. The sanitized basename matches the input string exactly.
3. The resolved canonical path (`os.path.abspath`) resides strictly inside `self.config_dir`.

```diff
diff --git a/klippy/extras/bed_mesh.py b/klippy/extras/bed_mesh.py
index e2ebe448..8f251572 100644
--- a/klippy/extras/bed_mesh.py
+++ b/klippy/extras/bed_mesh.py
@@ -2079,15 +2079,37 @@ class ProfileManager:
                 "The SAVE_CONFIG command will update the printer config\n"
                 "file and restart the printer" %
                 (('\n').join(self.incompatible_profiles)))
+    def _get_custom_profile_path(self, prof_name):
+        if not self.save_custom_path or not self.config_dir:
+            return None
+        clean_name = os.path.basename(prof_name.strip())
+        is_invalid = (not clean_name or clean_name != prof_name
+                      or any(sep in prof_name
+                             for sep in ('/', '\\', '..', '\0')))
+        if is_invalid:
+            raise self.gcode.error(
+                "bed_mesh: Invalid profile name '%s' - "
+                "path traversal not allowed" % (prof_name,))
+        lower_prof_name = clean_name.lower()
+        fname = "bed_mesh_%s.json" % (lower_prof_name,)
+        file_path = os.path.abspath(os.path.join(self.config_dir, fname))
+        base_dir = os.path.abspath(self.config_dir)
+        if not file_path.startswith(base_dir + os.sep):
+            raise self.gcode.error(
+                "bed_mesh: Security violation: profile path escapes "
+                "configuration directory")
+        return file_path
     def _save_profile_custom(self, file_path, data_dict={}):
-        if not data_dict:
+        if not data_dict or not file_path:
             return False
         try:
             json_content = json.dumps(data_dict, indent=4)
-            queuefile.async_write_file(file_path, json_content, safe_write=True)
+            queuefile.async_write_file(file_path, json_content,
+                                       safe_write=True)
             return True
         except Exception as e:
-            logging.exception(f"Failed to write bed_mesh_data file: {file_path}")
+            logging.exception("Failed to write bed_mesh_data file: %s"
+                              % (file_path,))
             return False
     def save_profile(self, prof_name):
         save_to_cfg = False
@@ -2107,12 +2129,12 @@ class ProfileManager:
         profile['mesh_params'] = collections.OrderedDict(mesh_params)
         self.profiles = profiles
         if self.save_custom_path:
-            lower_prof_name = prof_name.lower()
             bed_mesh_data = {}
             bed_mesh_data['version'] = PROFILE_VERSION
             bed_mesh_data['profile'] = profile
-            file_path = os.path.join(self.config_dir, f"bed_mesh_{lower_prof_name}.json")
-            save_to_cfg = not self._save_profile_custom(file_path, bed_mesh_data)
+            file_path = self._get_custom_profile_path(prof_name)
+            save_to_cfg = not self._save_profile_custom(file_path,
+                                                        bed_mesh_data)
 
         if not self.save_custom_path or save_to_cfg:
             configfile = self.printer.lookup_object('configfile')
@@ -2140,9 +2162,8 @@ class ProfileManager:
     def _load_profile_custom(self, prof_name):
         if not self.save_custom_path:
             return None
-        lower_prof_name = prof_name.lower()
-        file_path = os.path.join(self.config_dir, f"bed_mesh_{lower_prof_name}.json")
-        if not os.path.exists(file_path):
+        file_path = self._get_custom_profile_path(prof_name)
+        if not file_path or not os.path.exists(file_path):
             return None
         try:
             with open(file_path, 'r') as f:
@@ -2184,17 +2205,18 @@ class ProfileManager:
     def _remove_profile_custom(self, prof_name):
         if not self.save_custom_path:
             return False
-        lower_prof_name = prof_name.lower()
-        file_path = os.path.join(self.config_dir, f"bed_mesh_{lower_prof_name}.json")
-        if not os.path.exists(file_path):
-            logging.info(f"bed_mesh: Profile file {file_path} not found, skip removal")
+        file_path = self._get_custom_profile_path(prof_name)
+        if not file_path or not os.path.exists(file_path):
+            logging.info("bed_mesh: Profile file %s not found, skip removal"
+                         % (file_path,))
             return False
         try:
             os.remove(file_path)
-            logging.info(f"bed_mesh: Removed profile file {file_path}")
+            logging.info("bed_mesh: Removed profile file %s" % (file_path,))
             return True
         except Exception as e:
-            logging.error(f"bed_mesh: Failed to remove profile file {file_path}, error: {str(e)}")
+            logging.error("bed_mesh: Failed to remove profile file %s: %s"
+                          % (file_path, str(e)))
             return False
     def remove_profile(self, prof_name):
         self._remove_profile_custom(prof_name)
```

---

## 7. Regression & Safety Verification
- **Automated Deterministic Test:**
  - Configuration: `test/klippy/bug_sec01_bed_mesh.cfg`
  - Test Script: `test/klippy/bug_sec01_bed_mesh.test`
  - Test Execution Command:
    ```bash
    python scripts/test_klippy.py -d test/klippy -t /tmp -v test/klippy/bug_sec01_bed_mesh.test
    ```
- **Test Result:**
  - Traversal attempt `BED_MESH_PROFILE LOAD=../../evil_path` is caught and logged:
    `WARNING:root:bed_mesh: Invalid profile name '../../evil_path' - path traversal not allowed`
  - Output message: `!! bed_mesh: Invalid profile name '../../evil_path' - path traversal not allowed`
  - Batch runner result: `All 1 test cases passed`.
  - Legitimate alphanumeric profile names (e.g. `default`, `high_temp`, `pei_sheet_1`) continue to function without disruption.
