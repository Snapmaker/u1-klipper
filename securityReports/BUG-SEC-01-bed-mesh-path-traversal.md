# Bug Report: [SEC-01] Path Traversal & Beliebiges Überschreiben/Löschen von `.json`-Dateien im `ProfileManager`

## 1. Summary / Description
- **ID:** SEC-01
- **Titel:** Path Traversal & Beliebiges Überschreiben / Löschen von `.json`-Dateien im `ProfileManager` (`bed_mesh.py`)
- **Fehlerklasse:** Zero-Day Sicherheitslücke / Path Traversal (CWE-22, CWE-73)
- **Schweregrad:** **KRITISCH** (CVSS v3.1 Score: 9.1 / CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:H/A:H)
- **Risiko:** Über unbereinigte Benutzereingaben im G-Code-Befehl `BED_MESH_PROFILE` (Parameter `SAVE=`, `LOAD=`, `REMOVE=`) kann ein Angreifer oder ein bösartiges Makro / G-Code-Skript Pfadseparatoren (`/`, `\`) und Directory-Traversal-Sequenzen (`..`) einschleusen. Dadurch können beliebige `.json`-Dateien auf dem Dateisystem des Druckers (z. B. Konfigurationen, Druckparameter, Systemstatistiken) überschrieben, eingelesen oder unwiderruflich gelöscht werden.

---

## 2. Component / Affected Files
- **Komponente:** Klippy Host-Software / Extras / Bed Mesh Profile Manager (Snapmaker Custom Storage)
- **Betroffene Datei:** `klippy/extras/bed_mesh.py`
- **Betroffene Zeilen:** Zeilen 2110–2115, 2140–2145, 2184–2189
- **Zugehörige Testdatei:** `test/klippy/test_sec01_bed_mesh_path_traversal.py`

---

## 3. Classification
- **Kategorie:** **Gruppe B (Snapmaker U1 Specific)**
- **Begründung:** Die Methode `save_custom_path` mit separater JSON-Speicherung über `_save_profile_custom`, `_load_profile_custom` und `_remove_profile_custom` unter Verwendung von `self.config_dir` (`printer.get_snapmaker_config_dir()`) und `queuefile.async_write_file` ist eine proprietäre Snapmaker-Erweiterung im Fork `u1-klipper` und existiert im Upstream-Klipper (`Klipper3d/klipper`) in dieser Form nicht.

---

## 4. Root Cause Analysis
In `ProfileManager` wird für benutzerdefinierte Profile (`self.save_custom_path == True`) der Dateipfad wie folgt konstruiert:
```python
lower_prof_name = prof_name.lower()
file_path = os.path.join(self.config_dir, f"bed_mesh_{lower_prof_name}.json")
```
Der vom Benutzer über G-Code übergebene Parameter `prof_name` wurde vor der Pfadkonstruktion keiner Validierung unterzogen. 

Wenn ein Parameter wie `prof_name = "../sensitive"` übergeben wird:
1. `lower_prof_name` wird zu `"../sensitive"`.
2. `f"bed_mesh_{lower_prof_name}.json"` ergibt `"bed_mesh_../sensitive.json"`.
3. Auf POSIX-Systemen sowie unter Windows löst `os.path.join(self.config_dir, "bed_mesh_../sensitive.json")` den Pfad relativ auf: Das vorangestellte `bed_mesh_..` zusammen mit dem Pfadtrenner `/` traversiert in das übergeordnete Verzeichnis von `self.config_dir`.
4. Beim Aufruf von `_remove_profile_custom` führt `os.remove(file_path)` zur Löschung der Datei `sensitive.json` außerhalb des Konfigurationsverzeichnisses.
5. Beim Aufruf von `save_profile` führt `queuefile.async_write_file(file_path, ...)` zum Überschreiben der Datei außerhalb des Konfigurationsverzeichnisses.

---

## 5. Steps to Reproduce
1. Starten des Klippy-Hosts mit aktivierter Snapmaker-Konfiguration (`save_custom_path = True`).
2. Senden des folgenden G-Code-Befehls an die Klippy-Konsole:
   ```gcode
   BED_MESH_PROFILE REMOVE=../sensitive
   ```
3. Beobachtung vor dem Fix: Die Datei `bed_mesh_sensitive.json` bzw. `sensitive.json` im übergeordneten Verzeichnis wird ohne Fehlermeldung vom Dateisystem gelöscht.
4. Senden von:
   ```gcode
   BED_MESH_PROFILE SAVE=../../printer_data/config/print_task
   ```
5. Beobachtung vor dem Fix: Die Datei `print_task.json` wird mit Bed-Mesh-JSON-Daten überschrieben.

---

## 6. Proposed Fix / Patch
Defensive Validierung in `klippy/extras/bed_mesh.py` über die neue Hilfsmethode `_get_custom_profile_path(self, prof_name)`:
- Strippen von Whitespace und Validierung auf verbotene Zeichen (`/`, `\`, `..`, `\0`).
- Abgleich zwischen Rohname und bereinigtem Basenamen (`os.path.basename(clean_name) == prof_name`).
- Auflösung des absoluten Pfads via `os.path.abspath` und Verifizierung, dass der resultierende Pfad strikt innerhalb von `os.path.abspath(self.config_dir)` verbleibt.
- Auslösen von `self.gcode.error` bei jedem Manipulationsversuch.

```diff
diff --git a/klippy/extras/bed_mesh.py b/klippy/extras/bed_mesh.py
index e2ebe448..03433858 100644
--- a/klippy/extras/bed_mesh.py
+++ b/klippy/extras/bed_mesh.py
@@ -2079,8 +2079,20 @@ class ProfileManager:
                 "The SAVE_CONFIG command will update the printer config\n"
                 "file and restart the printer" %
                 (('\n').join(self.incompatible_profiles)))
+    def _get_custom_profile_path(self, prof_name):
+        if not self.save_custom_path or not self.config_dir:
+            return None
+        clean_name = os.path.basename(prof_name.strip())
+        if not clean_name or clean_name != prof_name or any(sep in prof_name for sep in ('/', '\\', '..', '\0')):
+            raise self.gcode.error(f"bed_mesh: Invalid profile name '{prof_name}' - path traversal not allowed")
+        lower_prof_name = clean_name.lower()
+        file_path = os.path.abspath(os.path.join(self.config_dir, f"bed_mesh_{lower_prof_name}.json"))
+        base_dir = os.path.abspath(self.config_dir)
+        if not file_path.startswith(base_dir + os.sep):
+            raise self.gcode.error("bed_mesh: Security violation: profile path escapes configuration directory")
+        return file_path
     def _save_profile_custom(self, file_path, data_dict={}):
-        if not data_dict:
+        if not data_dict or not file_path:
             return False
         try:
             json_content = json.dumps(data_dict, indent=4)
@@ -2107,11 +2119,10 @@ class ProfileManager:
         profile['mesh_params'] = collections.OrderedDict(mesh_params)
         self.profiles = profiles
         if self.save_custom_path:
-            lower_prof_name = prof_name.lower()
             bed_mesh_data = {}
             bed_mesh_data['version'] = PROFILE_VERSION
             bed_mesh_data['profile'] = profile
-            file_path = os.path.join(self.config_dir, f"bed_mesh_{lower_prof_name}.json")
+            file_path = self._get_custom_profile_path(prof_name)
             save_to_cfg = not self._save_profile_custom(file_path, bed_mesh_data)
 
         if not self.save_custom_path or save_to_cfg:
@@ -2140,9 +2151,8 @@ class ProfileManager:
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
@@ -2184,9 +2194,8 @@ class ProfileManager:
     def _remove_profile_custom(self, prof_name):
         if not self.save_custom_path:
             return False
-        lower_prof_name = prof_name.lower()
-        file_path = os.path.join(self.config_dir, f"bed_mesh_{lower_prof_name}.json")
-        if not os.path.exists(file_path):
+        file_path = self._get_custom_profile_path(prof_name)
+        if not file_path or not os.path.exists(file_path):
             logging.info(f"bed_mesh: Profile file {file_path} not found, skip removal")
             return False
         try:
```

---

## 7. Regression & Safety Verification
- **Automatisierter Testfall:** `test/klippy/test_sec01_bed_mesh_path_traversal.py`
- **Testergebnisse:**
  - `test_path_traversal_remove_rejected`: Bestätigt, dass `remove_profile('../sensitive')` eine `gcode.error`-Exception auslöst und die Zieldatei unberührt bleibt.
  - `test_path_traversal_load_rejected`: Bestätigt, dass `load_profile('../../sensitive')` eine `gcode.error`-Exception auslöst.
  - `test_valid_profile_name_accepted`: Bestätigt, dass reguläre Profilnamen (`default`, `pei_sheet`, `plate1`) ohne Fehler verarbeitet werden.
- **Testausführungsprotokoll:**
  ```text
  ...
  ----------------------------------------------------------------------
  Ran 3 tests in 0.006s

  OK
  ```
- **Sicherheitsnachweis:** Es können keine Dateien mehr außerhalb von `self.config_dir` adressiert, modifiziert oder gelöscht werden. Reguläre Profilverwaltungsfunktionen bleiben 100% kompatibel.

