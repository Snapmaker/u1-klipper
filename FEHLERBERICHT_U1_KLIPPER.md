# Umfassender Systematischer Fehler- & Sicherheitsbericht: `u1-klipper-main`

**Projekt:** Snapmaker U1 Klipper Firmware & Host-Software (`u1-klipper-main`)  
**Methode:** `/systematic-debugging` (Vollständige statische & logische Code-Analyse aller Subsysteme: MCU C-Firmware `src/`, Host C-Erweiterung `klippy/chelper/`, Klippy Core `klippy/`, Kinematik & Probing `klippy/kinematics/` & `klippy/extras/`, sowie Hilfsskripte `scripts/`)  
**Geprüfte Fehlerklassen:**
1. Zero-Day- & Sicherheitslücken (Path Traversal, Arbitrary File Write/Delete, Command Injection, Unauthenticated IPC)
2. Buffer Overflows & Out-of-Bounds-Zugriffe (Stack/Heap/BSS Buffer Overflows, Array/Listen OOB)
3. Integer Overflows, Underflows, Truncation & Signedness-Fehler
4. Division by Zero (Hardware-Divisionsfehler in C & `ZeroDivisionError` in Python)
5. Null Pointer Dereference / Segfaults / Unaligned Memory Access / `NoneType`-Exceptions
6. Speicherlecks (Heap Memory Leaks, `alloc_chunk`-Leaks, Move-Queue-Leaks, File-Descriptor-Leaks, Flash-Lock-Leaks, Zombie-Prozesse)
7. Dangling Pointers & Use-After-Free / Use-After-Close
8. Stack Overflows (Variable Length Arrays auf MCU-Stack, Endlosschleifen)
9. Deadlocks & Unendliche Hardware-Polling-Schleifen ohne Timeout
10. Race Conditions (ISR vs. Main-Loop, Paho-MQTT-Thread vs. Reactor, RFID-Thread vs. Reactor, Greenlet-Reentrancy, Async-File-TOCTOU)
11. Unhandled Exceptions, Verschluckte Exceptions & Fehlerhafte Exception-Handler
12. Logische Fehler (Off-by-One, Kopierfehler, Late-Binding-Closures, fehlerhafte Kalibrierungsmathematik, persistente Konfigurationskorruption)

---

## Inhaltsverzeichnis & Zusammenfassung nach Fehlerklassen

| Nr. | Fehlerklasse | Anzahl verifizierter Befunde | Höchster Schweregrad | Hauptbetroffene Module |
| :--- | :--- | :---: | :---: | :--- |
| **1** | **Zero-Day- & Sicherheitslücken** | 6 | **KRITISCH** | `bed_mesh.py`, `probe_inductance_coil.py`, `flow_calibrator.py`, `chelper/__init__.py`, `webhooks.py` |
| **2** | **Buffer Overflows & Out-of-Bounds** | 12 | **KRITISCH** | `sdiocmds.c`, `buttons.c`, `tmcuart.c`, `command.c`, `serialqueue.c`, `msgblock.c`, `stepcompress.c`, `linux/i2c.c`, `linux/gpio.c`, `extruder.py`, `print_task_config.py` |
| **3** | **Integer Overflows / Underflows / Truncation** | 9 | **HOCH** | `sdiocmds.c`, `sdio.c`, `inductance_coil.c`, `hard_pwm.c`, `power_loss_check.c`, `i2c_software.c`, `i2ccmds.c`, `sched.c`, `stepcompress.c` |
| **4** | **Division by Zero** | 16 | **KRITISCH** | `sdio.c`, `inductance_coil.c`, `serialqueue.c`, `msgblock.c`, `stepcompress.c`, `kin_shaper.c`, `virtual_sdcard.py`, `bed_mesh.py`, `inductance_coil.py`, `homing_precise_corexy.py`, `homing_xyz_override.py`, `auto_screws_tilt_adjust.py`, `flow_calibrator.py`, `purifier_factory.py`, `defect_detection.py`, `power_loss_check.py`, `toolhead.py`, `mcu.py`, `clocksync.py`, `stepper.py` |
| **5** | **Null Pointer / Segfault / Unaligned / `NoneType`** | 15 | **KRITISCH** | `sdiocmds.c`, `sdio.c`, `inductance_coil.c`, `fatfs_api.c`, `serialqueue.c`, `kin_shaper.c`, `kin_idex.c`, `pollreactor.c`, `virtual_sdcard.py`, `extruder.py`, `bed_mesh.py`, `probe_inductance_coil.py`, `filament_feed.py`, `defect_detection.py`, `klippy.py`, `error_mcu.py`, `park_detector.py`, `timelapse.py` |
| **6** | **Speicher-, FD-, Lock- & Prozess-Leaks** | 10 | **HOCH** | `stepper.c`, `power_loss_check.c`, `i2c_software.c`, `fatfs_api.c`, `linux/console.c`, `serialqueue.c`, `kin_extruder.c`, `inductance_coil.py`, `flow_calibrator.py`, `fm175xx_reader.py`, `mqtt.py` |
| **7** | **Dangling Pointers & Use-After-Free** | 5 | **KRITISCH** | `power_loss_check.c`, `inductance_coil.c`, `serialqueue.c`, `trdispatch.c`, `fm175xx_reader.py` |
| **8** | **Stack Overflows & Endlosschleifen** | 6 | **HOCH** | `i2ccmds.c`, `auto_screws_tilt_adjust.py`, `heaters.py`, `filament_detect.py`, `purifier.py`, `asyncfilereader.py` |
| **9** | **Deadlocks & Hardware-Polling-Loops** | 9 | **KRITISCH** | `sdio.c`, `at32f403a.c`, `at32f415rc.c`, `n32g45x_adc.c`, `spi.c`, `canserial.c`, `filament_feed.py`, `filament_feed_fac_test.py`, `machine_state_manager.py`, `bed_mesh.py`, `flow_calibrator.py` |
| **10** | **Race Conditions & Concurrency-Fehler** | 11 | **KRITISCH** | `inductance_coil.c`, `power_loss_check.c`, `stepper.c`, `asyncfilereader.py`, `exception_manager.py`, `webhooks.py`, `gcode.py`, `heaters.py`, `fm175xx_reader.py`, `jsonrpc.py`, `mqtt.py` |
| **11** | **Unhandled / Verschluckte Exceptions** | 10 | **HOCH** | `reactor.py`, `extruder.py`, `probe_inductance_coil.py`, `probe.py`, `extruder_calibration.py`, `filament_parameters.py`, `filament_protocol.py`, `configfile.py`, `inductance_coil.py` |
| **12** | **Logische Fehler & State-Corruption** | 14 | **KRITISCH** | `inductance_coil.c`, `queuefile.py`, `extruder.py`, `virtual_sdcard.py`, `bed_mesh.py`, `probe_inductance_coil.py`, `homing_precise_corexy.py`, `filament_feed.py`, `print_task_config.py`, `flow_calibrator.py`, `defect_detection.py`, `jsonrpc.py` |

---

## 1. Zero-Day- & Sicherheitslücken (Security Vulnerabilities)

### [SEC-01] Path Traversal & Beliebiges Überschreiben/Löschen von `.json`-Dateien im `ProfileManager` (`bed_mesh.py`)
- **Datei & Zeilen:** [bed_mesh.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/bed_mesh.py#L2110-L2194)
- **Schweregrad:** KRITISCH (Zero-Day / Arbitrary File Overwrite & Delete)
- **Ursachenanalyse (Root Cause):**
  In `ProfileManager.save_profile(prof_name)`, `load_profile(prof_name)` und `remove_profile(prof_name)` wird der vom Benutzer über G-Code (`BED_MESH_PROFILE SAVE=... LOAD=... REMOVE=...`) übergebene Parameter `prof_name` direkt in `os.path.join(self.profiles_dir, prof_name + ".json")` eingesetzt, ohne `prof_name` auf Pfadtrenner (`/` oder `..`) zu prüfen. Da `os.path.join("/pfad/bed_mesh", "../../printer_data/config/print_task")` zu einem Pfad außerhalb von `self.profiles_dir` aufgelöst wird, kann über G-Code oder Makros jede beliebige `.json`-Datei des Systems überschrieben, eingelesen oder mittels `REMOVE=../../...` gelöscht werden.
- **Betroffener Code:**
  ```python
  # klippy/extras/bed_mesh.py:2131-2135 & 2178-2185
  profile_path = os.path.join(self.profiles_dir, prof_name + ".json")
  ...
  if os.path.exists(profile_path):
      os.remove(profile_path)
  ```
- **Lösungsansatz (Defensiver Fix):**
  ```python
  def _get_safe_profile_path(self, prof_name):
      safe_name = os.path.basename(prof_name)
      if not safe_name or safe_name != prof_name or safe_name in (".", ".."):
          raise self.gcode.error(f"Invalid profile name: {prof_name}")
      base_dir = os.path.realpath(self.profiles_dir)
      full_path = os.path.realpath(os.path.join(base_dir, safe_name + ".json"))
      if os.path.commonpath([base_dir, full_path]) != base_dir:
          raise self.gcode.error(f"Invalid profile path: {prof_name}")
      return full_path
  ```

---

### [SEC-02] Beliebiges Überschreiben von Systemdateien via `BED_MESH_OUTPUT_FILE` (`bed_mesh.py`)
- **Datei & Zeilen:** [bed_mesh.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/bed_mesh.py#L304-L313)
- **Schweregrad:** HOCH (Arbitrary File Write)
- **Ursachenanalyse (Root Cause):**
  `cmd_BED_MESH_OUTPUT_FILE` liest `FILE_PATH` ungeprüft aus dem G-Code-Befehl (`gcmd.get('FILE_PATH', ...)`), erstellt beliebige Elternverzeichnisse (`os.makedirs(os.path.dirname(file_path), exist_ok=True)`) und überschreibt die Zieldatei im Schreibmodus `'w'`. Zudem schlägt `os.makedirs("")` mit `FileNotFoundError` fehl, wenn ein relativer Dateiname ohne Verzeichnis übergeben wird.
- **Betroffener Code:**
  ```python
  file_path = gcmd.get('FILE_PATH', os.path.join(config_dir, 'bed_mesh.json'))
  os.makedirs(os.path.dirname(file_path), exist_ok=True)
  with open(file_path, 'w') as f:
      f.write(status_json)
  ```
- **Lösungsansatz (Defensiver Fix):**
  Den Zielpfad strikt auf das Konfigurations- oder Log-Verzeichnis mittels `os.path.realpath()` und `os.path.commonpath()` beschränken.

---

### [SEC-03] Path Traversal / Arbitrary File Append über `LOG_FILE` in `probe_inductance_coil.py`
- **Datei & Zeilen:** [probe_inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/probe_inductance_coil.py#L728), [probe_inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/probe_inductance_coil.py#L999-L1010)
- **Schweregrad:** HOCH (Path Traversal / Arbitrary File Append)
- **Ursachenanalyse (Root Cause):**
  In `cmd_CARTOGRAPHER_CALIBRATE` und `cmd_INDUCTANCE_COIL_PROBE_ACCURACY` wird der G-Code-Parameter `LOG_FILE` ungeprüft an `open(log_file, 'a', ...)` bzw. `queuefile.async_append_file(log_file, ...)` übergeben.
- **Lösungsansatz (Defensiver Fix):**
  Nur `os.path.basename(log_file)` innerhalb eines dedizierten Log-Verzeichnisses zulassen.

---

### [SEC-04] Path Traversal & Ungeprüfter Dateipfad via `AXIS` in `flow_calibrator.py`
- **Datei & Zeilen:** [flow_calibrator.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/flow_calibrator.py#L231-L241), [flow_calibrator.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/flow_calibrator.py#L1194-L1215)
- **Schweregrad:** HOCH (Path Traversal & File-Descriptor-Leak)
- **Ursachenanalyse (Root Cause):**
  In `cmd_ACCEL_TIME_MEASURE` wird `axis = gcmd.get("AXIS", None)` nicht gegen `('x', 'y')` validiert, sondern direkt in `filename = f"/tmp/accel_time_measure_{axis}.csv"` eingesetzt. Enthält `AXIS` Sequenzen wie `../../root/...`, wird außerhalb von `/tmp` geschrieben. Zudem wird in `AccelTimeQueryHelper.write_to_file()` das Dateiobjekt `f = open(self.filename, "w")` ohne `with`-Block geöffnet und niemals mittels `f.close()` geschlossen.
- **Lösungsansatz (Defensiver Fix):**
  `if axis not in ('x', 'y'): raise gcmd.error("Invalid AXIS")` prüfen und `with open(self.filename, "w") as f:` verwenden.

---

### [SEC-05] Shell Command Injection & Unsichere `sudo`-Kompilierung in `chelper/__init__.py`
- **Datei & Zeilen:** [__init__.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/__init__.py#L252-L264), [__init__.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/__init__.py#L304-L318)
- **Schweregrad:** HOCH (Command Injection / Privilege Escalation)
- **Ursachenanalyse (Root Cause):**
  `do_build_code()`, `check_gcc_option()` und `run_hub_ctrl()` übergeben unquotierte Dateipfade (`destlib`, `srcfiles`, `hubdir`) per String-Formatierung an `os.system()`. Enthält der Pfad Leerzeichen (wie `e:\KI Projekte\u1-klipper-main`) oder Shell-Metazeichen, schlägt der Aufruf fehl oder führt eingeschleuste Befehle aus. Zudem kompiliert `run_hub_ctrl()` zur Laufzeit eine Binärdatei als normaler Nutzer und führt sie anschließend direkt via `sudo %s/hub-ctrl` aus.
- **Betroffener Code:**
  ```python
  def run_hub_ctrl(enable_power):
      ...
      if check_build_code(srcfiles, destlib):
          do_build_code(HC_COMPILE_CMD % (destlib, ' '.join(srcfiles)))
      os.system(HC_CMD % (hubdir, enable_power))
  ```
- **Lösungsansatz (Defensiver Fix):**
  Alle `os.system()`-Aufrufe durch `subprocess.run([GCC_CMD, ...], check=True, shell=False)` mit Argumentlisten ersetzen.

---

### [SEC-06] Unbegrenztes Pufferwachstum (`partial_data` OOM-DoS) & Offene Unix-Socket-Berechtigungen in `webhooks.py`
- **Datei & Zeilen:** [webhooks.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/webhooks.py#L124-L129), [webhooks.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/webhooks.py#L247-L249)
- **Schweregrad:** MITTEL bis HOCH (Denial of Service / Unautorisierter lokaler IPC-Zugriff)
- **Ursachenanalyse (Root Cause):**
  1. `ClientConnection.process_received()` hängt eingehende Daten unbegrenzt an `self.partial_data += data` an, solange kein `\x03`-Terminatorbyte gesendet wird, was zum Out-of-Memory-Absturz führt.
  2. `ServerSocket` setzt beim Binden des Unix-Domain-Sockets keine restriktiven Dateirechte (`0o660`), und `_remove_socket_file()` löscht die Zieldatei via `os.remove()` ohne vorherige Prüfung mittels `stat.S_ISSOCK()`.
- **Lösungsansatz (Defensiver Fix):**
  Maximale Puffergröße für `self.partial_data` (z. B. 10 MiB) erzwingen und Dateiberechtigungen des Unix-Sockets nach `bind()` mittels `os.chmod(server_address, 0o660)` einschränken.

---

## 2. Buffer Overflows & Out-of-Bounds Speicherzugriffe

### [BUF-01] 32-Bit Integer-Overflow umgeht Bounds-Check -> Beliebiger Out-of-Bounds Write/Read in `src/sdiocmds.c`
- **Datei & Zeilen:** [sdiocmds.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/sdiocmds.c#L135-L164)
- **Schweregrad:** KRITISCH (Arbitrary Memory Write / Buffer Overflow auf MCU)
- **Ursachenanalyse (Root Cause):**
  In `command_sdio_read_data_buffer` und `command_sdio_write_data_buffer` ist `offset` ein `uint32_t` (`args[1]`) und `len` bzw. `write_data_len` ein `uint8_t` (`args[2]`).
  1. Wenn `offset >= 0xFFFFFFFFU - write_data_len + 1` (z. B. `offset = 0xFFFFFFF0`, `write_data_len = 32`), läuft die 32-Bit-Addition `offset + write_data_len` über und ergibt `16`. Die Prüfung `if (offset + write_data_len <= sizeof(sdio->data_buffer))` (`16 <= 4096`) wird **umgangen**! Anschließend schreibt `memcpy(buf, write_data, write_data_len)` an `sdio->data_buffer - 16` und überschreibt die Strukturfelder vor `data_buffer` (einschließlich des Hardware-Registerzeigers `sdio->sdio_config.sdio`!).
  2. Zudem wird der Zeiger `uint8_t *buf = &(sdio->data_buffer[offset]);` bereits **vor** der Bereichsprüfung gebildet (Undefined Behavior in C).
- **Betroffener Code:**
  ```c
  void command_sdio_write_data_buffer(uint32_t *args)
  {
      uint8_t oid = args[0];
      uint32_t offset = args[1];
      uint8_t write_data_len = args[2];
      uint8_t *write_data = command_decode_ptr(args[3]);
      struct sdiodev_s *sdio = sdiodev_oid_lookup(oid);
      uint8_t *buf = &(sdio->data_buffer[offset]);

      if (offset + write_data_len <= sizeof(sdio->data_buffer)) {
          memcpy(buf, write_data, write_data_len);
      }
  }
  ```
- **Lösungsansatz (Defensiver Fix):**
  ```c
  void command_sdio_read_data_buffer(uint32_t *args)
  {
      uint8_t oid = args[0];
      uint32_t offset = args[1];
      uint8_t len = args[2];
      struct sdiodev_s *sdio = sdiodev_oid_lookup(oid);
      if (offset > sizeof(sdio->data_buffer)
          || len > sizeof(sdio->data_buffer) - offset) {
          offset = 0;
          len = 0;
      }
      sendf("sdio_read_data_buffer_response oid=%c data=%*s",
            oid, len, &sdio->data_buffer[offset]);
  }

  void command_sdio_write_data_buffer(uint32_t *args)
  {
      uint8_t oid = args[0];
      uint32_t offset = args[1];
      uint8_t write_data_len = args[2];
      uint8_t *write_data = command_decode_ptr(args[3]);
      struct sdiodev_s *sdio = sdiodev_oid_lookup(oid);
      if (offset <= sizeof(sdio->data_buffer)
          && write_data_len <= sizeof(sdio->data_buffer) - offset) {
          memcpy(&sdio->data_buffer[offset], write_data, write_data_len);
      }
  }
  ```

---

### [BUF-02] Schwerer Buffer Overflow (192 Bytes Out-of-Bounds Write im Timer-ISR) in `src/buttons.c`
- **Datei & Zeilen:** [buttons.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/buttons.c#L17), [buttons.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/buttons.c#L49-L53), [buttons.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/buttons.c#L160-L161)
- **Schweregrad:** KRITISCH (ISR Buffer Overflow / Heap-Pool-Korruption)
- **Ursachenanalyse (Root Cause):**
  In dieser Firmware wurde `reports[16]` in `struct buttons` von `uint8_t` auf `uint32_t reports[16]` verbreitert (für bis zu 32 Buttons). In Zeile 49 (innerhalb der Timer-ISR `buttons_event`) wurde jedoch `if (b->report_count < sizeof(b->reports))` beibehalten!
  Da `sizeof(b->reports)` nun `64` Bytes beträgt, das Array aber nur `16` Elemente (`0..15`) besitzt, schreibt `b->reports[b->report_count++] = b->pressed;` für `report_count = 16..63` bis zu **48 `uint32_t`-Werte (192 Bytes) über das Ende von `b->reports` hinaus** und überschreibt `report_count`, `ack_count`, `button_count`, `pins[]` sowie nachfolgende Objekte im `dynmem_pool`!
  Zusätzlich übergibt Zeile 160 `report_count` statt `report_count * sizeof(b->reports[0])` als Byte-Länge an `%*s`.
- **Betroffener Code:**
  ```c
  struct buttons {
      ...
      uint32_t reports[16];
      uint8_t report_count;
      ...
  };
  // In buttons_event():
      if (b->report_count < sizeof(b->reports)) {
          b->reports[b->report_count++] = b->pressed;
  ```
- **Lösungsansatz (Defensiver Fix):**
  ```c
      if (b->report_count < ARRAY_SIZE(b->reports)) {
          b->reports[b->report_count++] = b->pressed;
  ```
  Und in `buttons_task()` (Zeile 160):
  ```c
      sendf("buttons_state oid=%c ack_count=%c state=%*s"
            , oid, b->ack_count, report_count * sizeof(b->reports[0]), b->reports);
  ```

---

### [BUF-03] Out-of-Bounds Read & Write auf `m->data[10]` in `src/tmcuart.c` (ISR & Task)
- **Datei & Zeilen:** [tmcuart.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/tmcuart.c#L21), [tmcuart.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/tmcuart.c#L77), [tmcuart.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/tmcuart.c#L134-L169)
- **Schweregrad:** HOCH (ISR Buffer Overflow)
- **Ursachenanalyse (Root Cause):**
  Jedes UART-Byte wird mit Start- und Stoppbit als **10-Bit-Wort** in `uint8_t data[10]` (80 Bits = maximal **8 Bytes**) gespeichert. Zeile 139 prüft jedoch `if (write > ARRAY_SIZE(m->data) || read > ARRAY_SIZE(m->data))` (`> 10` statt `> 8`). Bei `write = 9` oder `10` bzw. `read = 9` oder `10` erreicht `pos` Werte bis `99`, sodass `m->data[(pos >> 3) + 1]` auf `m->data[10..12]` außerhalb des Puffers liest und schreibt.
- **Lösungsansatz (Defensiver Fix):**
  ```c
  if (write > (ARRAY_SIZE(m->data) * 8) / 10
      || read > (ARRAY_SIZE(m->data) * 8) / 10)
      shutdown("tmcuart data too large");
  ```

---

### [BUF-04] Out-of-Bounds Buffer Read in `parse_int` & `command_parsef` (`src/command.c` & `klippy/chelper/msgblock.c`)
- **Datei & Zeilen:** [command.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/command.c#L85-L98), [command.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/command.c#L123-L163), [msgblock.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/msgblock.c#L89-L119)
- **Schweregrad:** HOCH (Out-of-Bounds Read)
- **Ursachenanalyse (Root Cause):**
  1. In `command_parsef()` (`src/command.c:129`) prüft die Schleife `if (p > maxend)` statt `if (p >= maxend)`. Wenn `p == maxend`, liest `parse_int(&p)` oder `uint_fast8_t len = *p++;` bereits über `maxend` hinaus.
  2. In `parse_int()` (sowohl in `src/command.c` als auch in `klippy/chelper/msgblock.c`) besitzt die Schleife `while (c & 0x80) { c = *p++; ... }` keinerlei Obergrenze gegen `maxend`/`end`, sodass ein korruptes VLQ-Feld mit gesetztem MSB (`0x80`) über das Pufferende hinaus liest.
- **Lösungsansatz (Defensiver Fix):**
  `maxend`/`end` an `parse_int(uint8_t **pp, uint8_t *end)` übergeben, in `command_parsef` `if (p >= maxend) goto error;` sowie `if (len > (size_t)(maxend - p)) goto error;` prüfen.

---

### [BUF-05] Stack Over-Read & `input_buf` Buffer Overflow beim Lesen von CAN-Frames in `serialqueue.c`
- **Datei & Zeilen:** [serialqueue.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/serialqueue.c#L307-L318)
- **Schweregrad:** KRITISCH (Stack Over-Read & Buffer Overflow in C)
- **Ursachenanalyse (Root Cause):**
  In `input_event()` wird im Zweig `SQT_CAN` weder geprüft, ob `ret == sizeof(cf)` (Schutz vor Partial Reads / uninitialisiertem Stack), noch ob `cf.can_dlc <= 8` oder `sq->input_pos + cf.can_dlc <= sizeof(sq->input_buf)` (`4096`).
- **Betroffener Code:**
  ```c
  if (sq->serial_fd_type == SQT_CAN) {
      struct can_frame cf;
      int ret = read(sq->serial_fd, &cf, sizeof(cf));
      if (ret <= 0) { ... }
      if (cf.can_id != sq->client_id + 1)
          return;
      memcpy(&sq->input_buf[sq->input_pos], cf.data, cf.can_dlc);
      sq->input_pos += cf.can_dlc;
  }
  ```
- **Lösungsansatz (Defensiver Fix):**
  ```c
  if (ret < (int)sizeof(cf) || cf.can_id != sq->client_id + 1)
      return;
  uint8_t dlc = cf.can_dlc > 8 ? 8 : cf.can_dlc;
  if (sq->input_pos + dlc > sizeof(sq->input_buf))
      return;
  memcpy(&sq->input_buf[sq->input_pos], cf.data, dlc);
  sq->input_pos += dlc;
  ```

---

### [BUF-06] Ungeprüfter Stack-Buffer-Copy in `retransmit_event` (`serialqueue.c`)
- **Datei & Zeilen:** [serialqueue.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/serialqueue.c#L412-L421)
- **Schweregrad:** HOCH (Stack Buffer Overflow)
- **Ursachenanalyse (Root Cause):**
  `retransmit_event()` kopiert alle Nachrichten aus `sq->sent_queue` in ein festes Stack-Array `uint8_t buf[MESSAGE_MAX * MAX_PENDING_BLOCKS + 1]`, ohne zu prüfen, ob `buflen + qm->len <= sizeof(buf)`.
- **Lösungsansatz (Defensiver Fix):**
  Vor `memcpy` prüfen: `if (qm->len < 0 || buflen + qm->len > (int)sizeof(buf)) break;`.

---

### [BUF-07] Heap Buffer Overflow in `message_fill` (`msgblock.c`)
- **Datei & Zeilen:** [msgblock.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/msgblock.c#L136-L143)
- **Schweregrad:** HOCH (Heap Buffer Overflow)
- **Ursachenanalyse (Root Cause):**
  `message_fill(uint8_t *data, int len)` kopiert `len` Bytes mittels `memcpy(qm->msg, data, len)` in das 64 Byte große Array `qm->msg[MESSAGE_MAX]`, ohne `len >= 0 && len <= MESSAGE_MAX` zu prüfen.
- **Lösungsansatz (Defensiver Fix):**
  `if (len < 0 || len > MESSAGE_MAX) { errorf("Invalid length"); len = 0; }` vor `memcpy` ergänzen.

---

### [BUF-08] Heap Out-of-Bounds Read/Write bei `move_num == 0` in `stepcompress.c` & Off-by-One in `mcu.py`
- **Datei & Zeilen:** [stepcompress.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/stepcompress.c#L755-L775), [stepcompress.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/stepcompress.c#L811-L818), [mcu.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/mcu.py#L822-L829)
- **Schweregrad:** HOCH (Heap Out-of-Bounds Read/Write)
- **Ursachenanalyse (Root Cause):**
  In `mcu.py:823` wird nur `if move_count < self._reserved_move_slots:` geprüft. Wenn `move_count == self._reserved_move_slots`, wird `steppersync_alloc` mit `move_num = 0` aufgerufen (`ss->move_clocks = malloc(0)`). Anschließend liest `steppersync_flush()` in Zeile 811 `ss->move_clocks[0]` und `heap_replace()` schreibt in Zeile 765 `mc[0] = req_clock` außerhalb des 0-Byte-Puffers.
- **Lösungsansatz (Defensiver Fix):**
  In `mcu.py:823` auf `if move_count <= self._reserved_move_slots:` ändern und in `stepcompress.c:811` `if (ss->num_move_clocks <= 0) return ERROR_RET;` prüfen.

---

### [BUF-09] Out-of-Bounds Array-Zugriffe in Linux-MCU (`src/linux/i2c.c`, `gpio.c`, `analog.c`, `hard_pwm.c`)
- **Datei & Zeilen:** [i2c.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/linux/i2c.c#L48-L65), [gpio.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/linux/gpio.c#L69-L77), [analog.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/linux/analog.c#L25-L30), [hard_pwm.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/linux/hard_pwm.c#L40-L50)
- **Schweregrad:** MITTEL bis HOCH (Out-of-Bounds Read/Write & Uninitialisierte Variable)
- **Ursachenanalyse (Root Cause):**
  1. `src/linux/i2c.c`: Prüft nicht `if (devices_count >= ARRAY_SIZE(devices))` vor dem Schreiben in `devices[devices_count]`, und ignoriert den Rückgabewert von `ioctl(fd, I2C_FUNCS, &i2c_funcs)` bei uninitialisiertem `i2c_funcs`.
  2. `src/linux/gpio.c`: Prüft nicht `if (pin >= ARRAY_SIZE(gpio_lines))` vor `&gpio_lines[pin]`.
- **Lösungsansatz (Defensiver Fix):**
  Bounds-Checks gegen `ARRAY_SIZE(devices)` bzw. `ARRAY_SIZE(gpio_lines)` und Initialisierung `unsigned long i2c_funcs = 0;` ergänzen.

---

### [BUF-10] Out-of-Bounds `IndexError` auf `unknown[0]` und `filament_vendor[extruder_index]` in `extruder.py`
- **Datei & Zeilen:** [extruder.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/kinematics/extruder.py#L1163-L1168), [extruder.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/kinematics/extruder.py#L1259-L1265), [extruder.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/kinematics/extruder.py#L1451-L1453), [extruder.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/kinematics/extruder.py#L1728-L1729)
- **Schweregrad:** HOCH (Crash während Toolchange / Park-Check)
- **Ursachenanalyse (Root Cause):**
  1. In `_check_extruder_park_status()` (Zeile 1451 & 1728) wird im `else`-Zweig auf `unknown[0]` zugegriffen, ohne zu prüfen, ob `unknown` nicht-leer ist (`len(picked) > 1` und `len(unknown) == 0` führt sofort zu `IndexError: list index out of range`).
  2. In `compression_fila()` und `flush_fila()` (Zeile 1165 & 1261) wird `print_task_config.get_status()['filament_vendor'][self.active_extruder_index]` ohne Bereichsprüfung indiziert.
- **Lösungsansatz (Defensiver Fix):**
  Vor Listenindizierung stets `if unknown:` bzw. `0 <= idx < len(vendors)` prüfen.

---

### [BUF-11] Out-of-Bounds Listen-Indizierung in `print_task_config.py`
- **Datei & Zeilen:** [print_task_config.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/print_task_config.py#L826-L836), [print_task_config.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/print_task_config.py#L1175), [print_task_config.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/print_task_config.py#L1399-L1405)
- **Schweregrad:** MITTEL bis HOCH (`IndexError`)
- **Ursachenanalyse (Root Cause):**
  1. `cmd_SET_PRINT_USED_EXTRUDERS` prüft nicht, ob `e` innerhalb von `0 <= e < self.extruder_nums` liegt (`self.print_task_config['extruder_used'][e] = True`).
  2. `cmd_SET_PRINT_FILAMENT_CONFIG` und `cmd_SET_ EXTRUDER_FILAMENT_CALI_PARAM` prüfen nur `extruder >= self.extruder_nums`, lassen aber negative Indizes (`extruder < 0`) zu.
  3. Zeile 1405 indiziert hartcodiert `tmp_print_task_config_2['nozzle_diameter'][0]` statt `[i]`.
- **Lösungsansatz (Defensiver Fix):**
  Alle Extruder-Indizes strikt mit `0 <= idx < self.extruder_nums` prüfen und in Zeile 1405 `[i]` verwenden.

---

### [BUF-12] Off-by-One Kanalprüfung & Ungeprüftes `recv_buff[0]` in `fm175xx_reader.py` & `sc7a20.py`
- **Datei & Zeilen:** [fm175xx_reader.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/fm175xx_reader.py#L808), [fm175xx_reader.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/fm175xx_reader.py#L1037), [sc7a20.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/sc7a20.py#L85-L88)
- **Schweregrad:** MITTEL (`IndexError` bei SPI-Kommunikationsstörung)
- **Ursachenanalyse (Root Cause):**
  - `fm175xx_reader.py:1037` prüft `if channel < 0 or channel > FM175XX_CHANNEL_NUMS:` (`> 4` statt `>= 4`), sodass `channel == 4` zu `IndexError` führt.
  - `fm175xx_reader.py:808` (`recv_buff[0]`) und `sc7a20.py:86` (`response[1]`) greifen ohne Längenprüfung auf SPI-Antwortarrays zu.
- **Lösungsansatz (Defensiver Fix):**
  `channel >= FM175XX_CHANNEL_NUMS` sowie `if not recv_buff:` bzw. `if len(response) < 2:` prüfen.

---

## 3. Integer Overflows, Underflows, Truncation & Vorzeichenfehler

### [INT-01] 32-Bit Integer-Overflow bei SDIO-Timeout-Berechnung & `uint8_t`-Underflow in `sdio.c` / `sdiocmds.c`
- **Datei & Zeilen:** [sdiocmds.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/sdiocmds.c#L82), [sdiocmds.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/sdiocmds.c#L112), [sdio.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/sdio.c#L408)
- **Schweregrad:** HOCH (Fehlgeschlagene SDIO-Transfers & Falsche Taktrate)
- **Ursachenanalyse (Root Cause):**
  1. In `sdiocmds.c` (Zeilen 82, 112) wird `uint32_t timeout = TIMEOUT_MSEC * sdio->speed / 1000;` (`TIMEOUT_MSEC = 500`) in 32-Bit berechnet. Sobald `sdio->speed >= 8.589.935` Hz (~8,59 MHz; Standard-SD-Karten laufen mit 24–48 MHz!), läuft `500 * sdio->speed` über `UINT32_MAX` über, was zu einem viel zu kurzen Hardware-`DTIMER`-Timeout führt.
  2. In `sdio.c:408` (`uint8_t clkdiv = (SDIO_CLK_FREQ / speed) - 2;`) führt `speed > 24000000` (`SDIO_CLK_FREQ = 48000000`) zu einem **Underflow** von `uint8_t` auf `254` bzw. `255` (langsamster Takt statt Maximaltakt!), während `speed < 186771` bei der Umwandlung in `uint8_t` abgeschnitten wird (Truncation).
- **Lösungsansatz (Defensiver Fix):**
  ```c
  // src/sdiocmds.c:
  uint32_t timeout = (uint32_t)((uint64_t)TIMEOUT_MSEC * sdio->speed / 1000);

  // src/stm32/sdio.c:
  if (speed == 0) shutdown("Invalid SDIO speed");
  uint32_t div = SDIO_CLK_FREQ / speed;
  uint8_t clkdiv = (div <= 2) ? 0 : ((div - 2 > 255) ? 255 : (uint8_t)(div - 2));
  ```

---

### [INT-02] Unerreichbares `else if` führt zu 16-Bit Prescaler-Truncation in `src/stm32/hard_pwm.c`
- **Datei & Zeilen:** [hard_pwm.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/hard_pwm.c#L294-L302)
- **Schweregrad:** HOCH (Fehlerhafte Hardware-PWM-Frequenz)
- **Ursachenanalyse (Root Cause):**
  Der Schutz vor 16-Bit-Überlauf `else if (prescaler > UINT16_MAX)` steht im `else`-Zweig von `if (prescaler > 0)`. Da `prescaler > UINT16_MAX` zwingend `prescaler > 0` impliziert, ist der `else if`-Zweig **toter Code** und wird niemals ausgeführt! Bei `prescaler > 65536` schneidet `(uint16_t)prescaler` die oberen 16 Bit kommentarlos ab.
- **Betroffener Code:**
  ```c
  uint32_t prescaler = cycle_time / (pclock_div * (MAX_PWM - 1));
  if (prescaler > 0) {
      prescaler -= 1;
  } else if (prescaler > UINT16_MAX) {
      prescaler = UINT16_MAX;
  }
  p->timer->PSC = (uint16_t) prescaler;
  ```
- **Lösungsansatz (Defensiver Fix):**
  ```c
  if (prescaler > 0) {
      prescaler -= 1;
  }
  if (prescaler > UINT16_MAX) {
      prescaler = UINT16_MAX;
  }
  ```

---

### [INT-03] Tautologischer Bounds-Check, `MOVING_SUM` 32-Bit-Overflow & Signed-Overflow in `src/stm32/inductance_coil.c`
- **Datei & Zeilen:** [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L45), [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L104-L117), [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L328-L357), [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L471-L479)
- **Schweregrad:** HOCH (Falscher Z-Trigger / Undefined Behavior)
- **Ursachenanalyse (Root Cause):**
  1. `if (tmp_pr_value > INPUT_CAPTURE_CAL_CRM_TIM_MAX_PR_VALUE)` vergleicht `uint32_t tmp_pr_value` mit `0xFFFFFFFFU` – diese Bedingung ist **immer falsch** (Tautologie). Wenn das `double`-Makro `INPUT_CAPTURE_CAL_CRM_TIM_PR(...)` größer als `4294967295.0` oder negativ ist, erzeugt der Cast nach `uint32_t` Undefined Behavior.
  2. `MOVING_SUM.sum` ist `uint32_t` und summiert bis zu `50` 32-Bit-Timerwerte (`value`), was bei großen Perioden überläuft.
  3. In `update_trigger_frequencies()` (Zeile 471) kann `freq_param.trg_freq_ht + (int)cur_freq` einen vorzeichenbehafteten 32-Bit-Integer-Overflow auslösen.
- **Lösungsansatz (Defensiver Fix):**
  Den `double`-Wert vor dem Cast nach `uint32_t` gegen `(double)0xFFFFFFFFU` prüfen, `MOVING_SUM.sum` als `uint64_t` definieren und die Frequenzaddition in `int64_t` berechnen.

---

### [INT-04] 16-Bit Timer-Underflow & `uint32_t`-Überlauf von `power_loss_trigger_time` (`power_loss_check.c` & `power_loss_check.py`)
- **Datei & Zeilen:** [power_loss_check.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/power_loss_check.c#L492-L493), [power_loss_check.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/power_loss_check.py#L30-L32), [power_loss_check.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/power_loss_check.py#L89-L92)
- **Schweregrad:** MITTEL bis HOCH (Fehlerhafte Brown-Out-Erkennung)
- **Ursachenanalyse (Root Cause):**
  In `power_loss_check.c:492` läuft `(uint16_t)(TRM_OVER_FREQ * plc->power_loss_trigger_time - 1)` bei `power_loss_trigger_time == 0` auf `0xFFFF` unter und schneidet Werte `> 6,5536 s` (`TRM_OVER_FREQ = 10000`) bei 16 Bit ab. In `power_loss_check.py:89` wird `power_loss_trigger_time` zudem ungeprüft aus einer JSON-Datei geladen.
- **Lösungsansatz (Defensiver Fix):**
  Den Wert in Python und C auf einen gültigen Bereich (`1..65535` Ticks) begrenzen.

---

### [INT-05] Timer-Wraparound-Hänger & 32-Bit-Multiplikations-Overflow in `src/i2c_software.c`
- **Datei & Zeilen:** [i2c_software.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/i2c_software.c#L48-L58)
- **Schweregrad:** HOCH (Watchdog-Reset durch 30-Sekunden-Hänger oder 0-Delay bei Timer-Wraparound)
- **Ursachenanalyse (Root Cause):**
  1. `i2c_delay` nutzt `while (t > timer_read_time());` statt `timer_is_before(timer_read_time(), t)`. Wenn der 32-Bit-Hardwaretimer nahe `0xFFFFFFFF` überläuft, ist `t > timer_read_time()` entweder sofort `false` (0 ns Delay -> korruptes I2C-Timing) oder für `~2^32` Ticks (~25–50 Sekunden) dauerhaft `true`, was die MCU bis zum Watchdog-Reset einfriert!
  2. `nsecs_to_ticks` rechnet `timer_from_us(ns * 1000) / 1000000`, wobei `(ns * 1000) * (CONFIG_CLOCK_FREQ / 1000000)` bei 168 MHz bereits ab `ns > 25565` in 32-Bit überläuft.
- **Lösungsansatz (Defensiver Fix):**
  ```c
  static uint32_t nsecs_to_ticks(uint32_t ns) {
      return (uint32_t)(((uint64_t)ns * CONFIG_CLOCK_FREQ) / 1000000000ULL);
  }
  static void i2c_delay(unsigned int ns) {
      uint32_t end = timer_read_time() + nsecs_to_ticks(ns);
      while (timer_is_before(timer_read_time(), end))
          ;
  }
  ```

---

### [INT-06] 8-Bit Längen-Truncation (`reg_len + data_len`) in `src/i2ccmds.c`
- **Datei & Zeilen:** [i2ccmds.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/i2ccmds.c#L86-L114)
- **Schweregrad:** MITTEL (Korrupte I2C-Schreibzugriffe)
- **Ursachenanalyse (Root Cause):**
  In `command_i2c_modify_bits` sind `reg_len` (`uint8_t`, bis 255) und `data_len` (`uint8_t`, bis 127) separat bis 382 groß, werden aber als Summe `reg_len + data_len` an `i2c_write(..., uint8_t write_len, ...)` übergeben, wodurch Längen `> 255` modulo 256 abgeschnitten werden.
- **Lösungsansatz (Defensiver Fix):**
  `if (reg_len > 64 || data_len > 64 || (uint16_t)reg_len + data_len > 64) shutdown("i2c transfer too large");` prüfen.

---

### [INT-07] 8-Bit Truncation der 16-Bit `static_string_id` in `src/sched.c`
- **Datei & Zeilen:** [sched.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/sched.c#L23), [sched.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/sched.c#L295-L309), [sched.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/sched.c#L321-L335)
- **Schweregrad:** MITTEL (Falsche Shutdown-Fehlermeldungen bei > 255 Strings)
- **Ursachenanalyse (Root Cause):**
  Das Protokoll versendet `static_string_id=%hu` (16 Bit), aber `SchedStatus.shutdown_reason` und `sched_shutdown(uint_fast8_t reason)` speichern nur 8 Bit (`uint8_t`). Durch die zahlreichen zusätzlichen Strings in den Custom-Modulen werden String-IDs `>= 256` modulo 256 abgeschnitten.
- **Lösungsansatz (Defensiver Fix):**
  `shutdown_reason` sowie die Funktionsparameter von `sched_shutdown` und `sched_try_shutdown` auf `uint16_t` bzw. `uint_fast16_t` erweitern.

---

### [INT-08] Signed 32-Bit Integer-Overflow (Undefined Behavior) in `compress_bisect_add` (`stepcompress.c`)
- **Datei & Zeilen:** [stepcompress.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/stepcompress.c#L132-L146), [stepcompress.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/stepcompress.c#L161-L163), [stepcompress.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/stepcompress.c#L183-L188)
- **Schweregrad:** HOCH (Step-Komprimierungsfehler / Undefined Behavior)
- **Ursachenanalyse (Root Cause):**
  In `compress_bisect_add()` können `nextmininterval` und `nextmaxinterval` bis zu `CLOCK_DIFF_MAX` (`3 << 28` = `805.306.368`) und `nextcount` bis zu `65535` betragen. Die Multiplikationen `nextmaxinterval * nextcount`, `nextmininterval * nextcount`, `minadd * nextaddfactor` und `interval * count` werden in 32-Bit `int32_t` ausgeführt und laufen bereits ab `nextcount >= 3` über `INT32_MAX` über.
- **Lösungsansatz (Defensiver Fix):**
  Zwischenprodukte (`nextaddfactor`, `c`, `(int64_t)nextmininterval * nextcount`, `(int64_t)nextmaxinterval * nextcount`, `(int64_t)minadd * nextaddfactor`) in `int64_t` berechnen.

---

### [INT-09] Nicht-ausgerichtete Größenprüfung in `alloc_chunk` (`src/basecmd.c`)
- **Datei & Zeilen:** [basecmd.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/basecmd.c#L30-L39)
- **Schweregrad:** MITTEL (Überschreitung von `dynmem_end()`)
- **Ursachenanalyse (Root Cause):**
  `alloc_chunk` prüft `if (alloc_end + size > dynmem_end())`, erhöht `alloc_end` danach aber um `ALIGN(size, __alignof__(void*))`. Wenn `size` nicht durch 4 teilbar ist, kann `alloc_end` bis zu 3 Bytes über `dynmem_end()` (Stack-Grenze!) hinausgeschoben werden.
- **Lösungsansatz (Defensiver Fix):**
  `size_t aligned = ALIGN(size, __alignof__(void*));` vor dem Bounds-Check berechnen und `if (aligned < size || aligned > (size_t)((char*)dynmem_end() - (char*)alloc_end))` prüfen.

---

## 4. Division by Zero (`ZeroDivisionError` & Hardware-Faults)

### [DIV-01] Hardware-Division-by-Zero in `sdio_set_speed` (`src/stm32/sdio.c`) und `inductance_coil.c`
- **Datei & Zeilen:** [sdio.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/sdio.c#L408), [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L335), [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L407), [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L417)
- **Schweregrad:** KRITISCH (MCU HardFault / UsageFault)
- **Ursachenanalyse (Root Cause):**
  1. `sdio.c:408`: `SDIO_CLK_FREQ / speed` dividiert durch `0`, wenn `command_sdio_set_speed` mit `speed = 0` aufgerufen wird.
  2. `inductance_coil.c:335`: `1 / (info->freq_cal_cycle * ...)` dividiert durch `0`, wenn `freq_cal_cycle == 0` oder `cal_capture_pulse_window_size == 0`.
  3. `inductance_coil.c:407 & 417`: `frequency_conversion()` dividiert durch `g_freq_cal_info.freq_cal_factor` (`0` wenn `need_capture_pulse_sum == 0`) bzw. durch `(double)freq` (`0` wenn `trg_freq_ht/lt == 0`).
- **Lösungsansatz (Defensiver Fix):**
  Explizite Prüfungen `if (speed == 0) shutdown(...);`, `if (info->freq_cal_cycle <= 0 || g_freq_cal_info.cal_capture_pulse_window_size == 0) shutdown(...);` und `if (freq == 0) return 0xFFFFFFFF;` vor jeder Division einfügen.

---

### [DIV-02] Division by Zero in `chelper` (`serialqueue.c`, `msgblock.c`, `stepcompress.c`, `kin_shaper.c`)
- **Datei & Zeilen:**
  - [serialqueue.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/serialqueue.c#L903-L913)
  - [msgblock.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/msgblock.c#L199-L202)
  - [stepcompress.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/stepcompress.c#L331), [stepcompress.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/stepcompress.c#L605-L609)
  - [kin_shaper.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/kin_shaper.c#L48-L52)
- **Schweregrad:** HOCH (`SIGFPE` / `NaN`-Propagation in C-Solver)
- **Ursachenanalyse (Root Cause):**
  1. `serialqueue_set_wire_frequency`: `1. / frequency` ohne Prüfung `frequency > 0.`.
  2. `clock_to_time`: `(clock - ce->conv_clock) / ce->est_freq` ohne Prüfung `ce->est_freq > 0.`.
  3. `stepcompress.c`: `(lsc - .5) / sc->mcu_freq` (Zeile 331) sowie Ganzzahldivision `ticks / interval` (Zeile 605, `SIGFPE` wenn `interval == 0`) und `sqrt(b*b - 4*a*c)` ohne Schutz vor negativer Diskriminante (`NaN`-Cast auf `int32_t` ist UB).
  4. `kin_shaper.c:52`: `init_shaper()` berechnet `double inv_a = 1. / sum_a;` auch dann, wenn `n == 0` (Shaper deaktiviert) oder `sum_a == 0.`.
- **Lösungsansatz (Defensiver Fix):**
  Vor jeder Division Nenner auf `<= 0` bzw. `== 0` prüfen und Diskriminante in `stepcompress_find_past_position` mit `disc > 0. ? disc : 0.` begrenzen.

---

### [DIV-03] Fünf ungeschützte Division-by-Zero-Pfade in `virtual_sdcard.py`
- **Datei & Zeilen:** [virtual_sdcard.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/virtual_sdcard.py#L1323), [virtual_sdcard.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/virtual_sdcard.py#L2040), [virtual_sdcard.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/virtual_sdcard.py#L2142), [virtual_sdcard.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/virtual_sdcard.py#L2166-L2169), [virtual_sdcard.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/virtual_sdcard.py#L2275)
- **Schweregrad:** HOCH (`ZeroDivisionError` bei Power-Loss-Save/Restore)
- **Ursachenanalyse (Root Cause):**
  - Zeilen 1323, 2142, 2275: `1. / self.gcode_move.get_status()['speed_factor']` bzw. `1. / gcode_move_status['extrude_factor']` dividieren durch `0`, wenn `M221 S0` aktiv ist oder korrupte Faktoren vorliegen.
  - Zeile 2040: `restore_print` dividiert durch `float(file_env['speed_factor'])` ohne `!= 0`-Prüfung.
  - Zeilen 2166–2169: `self.printer.lookup_object('gcode_move').max_accel / toolhead_status['max_accel']` dividiert durch `0`, wenn `max_accel == 0` (und referenziert zudem ein nicht existierendes Attribut `gcode_move.max_accel`!).
- **Lösungsansatz (Defensiver Fix):**
  Alle Faktoren vor der Division auf `> 0` prüfen.

---

### [DIV-04] Division by Zero bei `z_adj == self.fade_dist` in `bed_mesh.py`
- **Datei & Zeilen:** [bed_mesh.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/bed_mesh.py#L219-L220)
- **Schweregrad:** HOCH (`ZeroDivisionError` mitten in `move()`-Aufruf)
- **Ursachenanalyse (Root Cause):**
  In `ZMesh.calc_z()` prüft `elif (z + z_adj) >= self.fade_end:` auf das Ende des Fade-Bereichs, und berechnet im `else`-Zweig `factor = (self.fade_end - (z + z_adj)) / (self.fade_dist - z_adj)`. Wenn `z_adj == self.fade_dist` (und `z < fade_start`), ist der Nenner `0.0`!
- **Lösungsansatz (Defensiver Fix):**
  `denom = self.fade_dist - z_adj; if abs(denom) < 1e-9: return 0.` vor der Division prüfen.

---

### [DIV-05] Division by Zero & `date_rate`-Tippfehler in `inductance_coil.py`
- **Datei & Zeilen:** [inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/inductance_coil.py#L186), [inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/inductance_coil.py#L267)
- **Schweregrad:** HOCH (`ZeroDivisionError` beim Start der Frequenzmessung)
- **Ursachenanalyse (Root Cause):**
  In `__init__` wird `self._data_rate = config.getint('date_rate', 500)` gelesen (Tippfehler `'date_rate'` statt `'data_rate'` und ohne ` minval=1`). In `_start_measurements()` berechnet Zeile 267 `rest_ticks = self._mcu.seconds_to_clock(1 / self._data_rate)`, was bei `_data_rate == 0` sofort mit `ZeroDivisionError` abstürzt.
- **Lösungsansatz (Defensiver Fix):**
  `config.getint('data_rate', config.getint('date_rate', 500), minval=1)` verwenden.

---

### [DIV-06] Division by Zero in `homing_precise_corexy.py`, `homing_xyz_override.py`, `auto_screws_tilt_adjust.py`, `homing.py`
- **Datei & Zeilen:**
  - [homing_precise_corexy.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/homing_precise_corexy.py#L107-L108)
  - [homing_xyz_override.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/homing_xyz_override.py#L206-L215)
  - [auto_screws_tilt_adjust.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/auto_screws_tilt_adjust.py#L207-L208)
  - [homing.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/homing.py#L239-L240)
- **Schweregrad:** MITTEL bis HOCH (`ZeroDivisionError` beim Homing/Bettnivellieren)
- **Ursachenanalyse (Root Cause):**
  1. `homing_precise_corexy.py:107`: `int(self.cor_x_stepper.get_rotation_distance()[0] // self.cor_x_stepper.get_step_dist())` – wenn `step_dist == 0` oder `cor_x_stepper is None`, entsteht `ZeroDivisionError` bzw. `AttributeError`.
  2. `homing_xyz_override.py:206`: `(bed_mesh_max[0] - bed_mesh_min[0]) / (x_count - 1)` dividiert durch `0`, wenn `x_count == 1` oder `y_count == 1`.
  3. `auto_screws_tilt_adjust.py:207`: `sum(...) / len(positions)` dividiert durch `0`, wenn `positions` leer ist.
  4. `homing.py:239`: `abs(movepos[2] - pos[2]) / move_d` dividiert durch `0`, wenn `move_d == 0.0`.
- **Lösungsansatz (Defensiver Fix):**
  Jeweils Nenner auf `> 0` prüfen.

---

### [DIV-07] Division by Zero in `flow_calibrator.py`, `purifier_factory.py`, `defect_detection.py`, `power_loss_check.py`
- **Datei & Zeilen:**
  - [flow_calibrator.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/flow_calibrator.py#L509-L512)
  - [purifier_factory.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/purifier_factory.py#L23), [purifier_factory.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/purifier_factory.py#L33)
  - [defect_detection.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/defect_detection.py#L78), [defect_detection.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/defect_detection.py#L808)
  - [power_loss_check.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/power_loss_check.py#L189-L191)
- **Schweregrad:** HOCH (`ZeroDivisionError`)
- **Ursachenanalyse (Root Cause):**
  1. `flow_calibrator.py:511`: `_calculate_linear_fitting_zero_crossing` rechnet `zero_crossing = -intercept / slope`. Wenn alle Messpunkte identisch sind (`slope == 0.0`), wird `ZeroDivisionError` ausgelöst.
  2. `purifier_factory.py:33`: `60. * freq / self.ppr` dividiert durch `0`, da `tachometer_ppr` in Zeile 23 mit `minval=0` erlaubt wird.
  3. `defect_detection.py:808`: `int((mesh_max - mesh_min) / self.bed_detect_probe_distance)` ohne `above=0.` in Zeile 78.
  4. `power_loss_check.py:189`: `high_level_tick / (high_level_tick + low_level_tick)` dividiert durch `0`, wenn die MCU `0, 0` meldet.
- **Lösungsansatz (Defensiver Fix):**
  In `flow_calibrator.py` `if abs(slope) < 1e-12: return None` prüfen; in `purifier_factory.py` `minval=1`, in `defect_detection.py` `above=0.` und in `power_loss_check.py` `total = high_level_tick + low_level_tick; if total <= 0: return 0.` setzen.

---

### [DIV-08] Division by Zero in `toolhead.py`, `mcu.py`, `clocksync.py` und `stepper.py`
- **Datei & Zeilen:**
  - [toolhead.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/toolhead.py#L757-L786)
  - [mcu.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/mcu.py#L672-L676)
  - [clocksync.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/clocksync.py#L114)
  - [stepper.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/stepper.py#L274-L280)
- **Schweregrad:** HOCH (`ZeroDivisionError`)
- **Ursachenanalyse (Root Cause):**
  1. `ToolHead.set_accel(accel)` prüft nur `if accel < 0: return` und lässt `accel == 0` zu, was in `_calc_junction_deviation()` (`... / self.max_accel`) sofort zu `ZeroDivisionError` führt. Ebenso fehlt `above=0.` in `cmd_SET_MAX_Z_ACCEL` und `cmd_SET_MAX_Z_VELOCITY`.
  2. `MCU._handle_mcu_stats`: `1.0 / (count * self._mcu_freq)` dividiert durch `0`, falls `count == 0`.
  3. `ClockSync._handle_clock`: `self.clock_covariance / self.time_variance` dividiert durch `0.0`, falls beim ersten Clock-Sample `diff_sent_time == 0.0` ist.
  4. `stepper.parse_gear_ratio`: Erlaubt `g1 <= 0` oder `g2 == 0` in `result *= g1 / g2`.
- **Lösungsansatz (Defensiver Fix):**
  In `set_accel` `if accel <= 0: return`, in `cmd_SET_MAX_Z_*` `above=0.` und in `_handle_mcu_stats`, `_handle_clock` sowie `parse_gear_ratio` Schutzprüfungen gegen `0` ergänzen.

---

## 5. Null Pointer Dereference, Segfaults, Unaligned Access & `NoneType`-Exceptions

### [NULL-01] Unaligned 32-Bit Pointer Dereference in `src/stm32/inductance_coil.c`
- **Datei & Zeilen:** [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L628-L630)
- **Schweregrad:** HOCH (Undefined Behavior / UsageFault auf ARM Cortex-M)
- **Ursachenanalyse (Root Cause):**
  In `struct sensor_bulk` (`src/sensor_bulk.h:9-15`) liegt `uint8_t data[SENSOR_BULK_MAX_SIZE]` direkt hinter `uint32_t possible_overflows` (4 Bytes) und `uint8_t data_count` (1 Byte), also an **ungesichertem ungeradem Byte-Offset 5**. Der direkte Cast und Schreibzugriff `*(uint32_t *)d = cal_freq;` führt einen 32-Bit-Speicherzugriff auf eine ungerade Adresse (`5 + 4*k`) aus.
- **Betroffener Code:**
  ```c
  uint8_t *d = &icd->sb.data[icd->sb.data_count];
  uint32_t cal_freq = frequency_conversion(INDUCTANCE_COIL_DEV_GET_TICK(), 0, NULL);
  *(uint32_t *)d = cal_freq;
  ```
- **Lösungsansatz (Defensiver Fix):**
  ```c
  memcpy(d, &cal_freq, sizeof(cal_freq));
  ```

---

### [NULL-02] Null Pointer Dereference in `src/sdiocmds.c`, `src/stm32/sdio.c` & `scripts/spi_flash/fatfs_api.c`
- **Datei & Zeilen:** [sdiocmds.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/sdiocmds.c#L48-L132), [sdio.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/sdio.c#L205), [fatfs_api.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/scripts/spi_flash/fatfs_api.c#L142-L143)
- **Schweregrad:** HOCH (Null-Pointer-Dereferenzierung)
- **Ursachenanalyse (Root Cause):**
  1. `sdiocmds.c`: Werden SDIO-Befehle vor `sdio_set_bus` aufgerufen, ist `sdio->sdio_config.sdio == NULL`.
  2. `sdio.c:205`: `if (response_data != NULL)` dereferenziert `*response_data_len = 4;`, ohne `response_data_len != NULL` zu prüfen.
  3. `fatfs_api.c:142`: `struct fatfs_file *fhdl = malloc(sizeof(struct fatfs_file)); memset(fhdl, 0, ...);` prüft `malloc` erst **nach** `memset` in Zeile 156 (`if (fhdl)`).
- **Lösungsansatz (Defensiver Fix):**
  Null-Prüfungen vor jedem Dereferenzieren ergänzen.

---

### [NULL-03] Null Pointer Dereference (`SIGSEGV`) in `chelper` (`serialqueue.c`, `kin_shaper.c`, `kin_idex.c`, `pollreactor.c`, `stepcompress.c`)
- **Datei & Zeilen:**
  - [serialqueue.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/serialqueue.c#L458-L476)
  - [kin_shaper.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/kin_shaper.c#L208)
  - [kin_idex.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/kin_idex.c#L58)
  - [pollreactor.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/pollreactor.c#L53-L63)
  - [stepcompress.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/stepcompress.c#L472)
- **Schweregrad:** KRITISCH (`SIGSEGV` im Host-Prozess)
- **Ursachenanalyse (Root Cause):**
  1. `serialqueue.c:458-476`: In `build_and_send_command()` ist `min_clock = MAX_CLOCK`. Wenn alle Nachrichten in `ready_queue` `m->req_clock >= MAX_CLOCK` haben, bleibt `qm == NULL` und Zeile 475 dereferenziert `qm->len` (`SIGSEGV`).
  2. `kin_shaper.c:208` & `kin_idex.c:58, 67`: Dereferenzieren `is->orig_sk->active_flags` bzw. `dc->orig_sk->active_flags` ohne `if (!orig_sk) return -1;`.
  3. `pollreactor.c:53`: `pollreactor_free(NULL)` dereferenziert `pr->fds` ohne `if (!pr) return;`.
  4. `stepcompress.c:472`: `sc->queue = realloc(sc->queue, ...)` prüft nicht auf `NULL`.
- **Lösungsansatz (Defensiver Fix):**
  In `build_and_send_command` `if (!qm) { sq->ready_bytes = 0; break; }` ergänzen und alle C-Zeiger vor Dereferenzierung prüfen.

---

### [NULL-04] `NoneType`-Abstürze in `virtual_sdcard.py` (`restore_print` & `get_print_task_config`)
- **Datei & Zeilen:** [virtual_sdcard.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/virtual_sdcard.py#L830-L831), [virtual_sdcard.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/virtual_sdcard.py#L1843-L1845)
- **Schweregrad:** KRITISCH (Unbehandelter Absturz bei Power-Loss-Wiederherstellung)
- **Ursachenanalyse (Root Cause):**
  1. In `restore_print()` (Zeile 1843–1845) wird `if not file_env['env_flag']:` ausgewertet, **bevor** geprüft wird, ob `file_env is None` (was `load_pl_env()` bei fehlender/korrupter Datei zurückgibt). Dies wirft `TypeError: 'NoneType' object is not subscriptable`.
  2. In `get_print_task_config()` (Zeile 830–831) wird `self.current_file.name` im `except`-Block dereferenziert, obwohl `self.current_file` `None` sein kann.
- **Lösungsansatz (Defensiver Fix):**
  `if not file_env or not file_env.get('env_flag'):` und `getattr(self.current_file, 'name', '<none>')` verwenden.

---

### [NULL-05] Fehlende Initialisierung von `self.mqtt_jsonrpc` in `defect_detection.py` & `None`-Dereferenzierung in `timelapse.py`
- **Datei & Zeilen:** [defect_detection.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/defect_detection.py#L406), [defect_detection.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/defect_detection.py#L428), [defect_detection.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/defect_detection.py#L509), [defect_detection.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/defect_detection.py#L552), [timelapse.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/timelapse.py#L117)
- **Schweregrad:** HOCH (`AttributeError` zur Laufzeit)
- **Ursachenanalyse (Root Cause):**
  In `DefectDetection.__init__` wird `self.mqtt_jsonrpc` überhaupt nicht initialisiert, in den Zeilen 406, 428, 509 und 552 jedoch direkt via `self.mqtt_jsonrpc.send_async_request(...)` aufgerufen -> garantierter `AttributeError: 'DefectDetection' object has no attribute 'mqtt_jsonrpc'`. In `timelapse.py` bleibt `self.mqtt_jsonrpc = None`, wenn `print_task_config` nicht geladen ist, wird aber ohne `if self.mqtt_jsonrpc is not None:` aufgerufen.
- **Lösungsansatz (Defensiver Fix):**
  In `DefectDetection.__init__` `self.mqtt_jsonrpc = None` initialisieren, in `_handle_ready` via `self.printer.lookup_object('mqtt_jsonrpc', None)` auflösen und vor jedem Aufruf auf `is not None` prüfen.

---

### [NULL-06] Weitere `NoneType`-Dereferenzierungen in `klippy.py`, `extruder.py`, `bed_mesh.py`, `probe_inductance_coil.py`, `extruder_calibration.py`, `filament_feed.py`, `error_mcu.py`, `park_detector.py`
- **Datei & Zeilen:**
  - [klippy.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/klippy.py#L277-L282): `parsed_structured_code.get("id", id)` wirft `AttributeError`, wenn `_parse_structured_code()` `None` zurückgibt.
  - [extruder.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/kinematics/extruder.py#L1833-L1838): `current_extruder.xy_park_position[0]` wirft `TypeError`, wenn für `extruder0` kein `xy_park_position` konfiguriert ist (`None`).
  - [bed_mesh.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/bed_mesh.py#L1167-L1172): `machine_state_manager.get_status()` ohne Prüfung auf `None`.
  - [probe_inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/probe_inductance_coil.py#L1397-L1408): `_get_filament_temp(self, extruder=None)` übergibt `None` an `get_extruder_filament_params(None)`, was bei `extruder < 0` mit `TypeError` abstürzt.
  - [extruder_calibration.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/extruder_calibration.py#L234): `"%.3f" % (self.get_analog_output(),)` wirft `TypeError`, da `get_analog_output()` bei fehlendem Sensor `None` liefert.
  - [filament_feed.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_feed.py#L584): `self.filament_detect.register_cb_2_filament_ key_detect(...)` und `self.runout_sensor[ch]` werden ohne `is not None`-Prüfung aufgerufen.
  - [error_mcu.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/error_mcu.py#L172): `if "Protocol error" in msg:` wirft `TypeError`, wenn `msg is None`.
  - [park_detector.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/park_detector.py#L90): `adc_Status['last_adc_value'] * 3.3` wirft `TypeError`, solange noch kein ADC-Sample vorliegt (`None`).
- **Lösungsansatz (Defensiver Fix):**
  An allen genannten Stellen explizite `is not None`-Guards ergänzen.

---

## 6. Speicherlecks (Memory Leaks, FD-Leaks, Lock-Leaks & Zombie-Prozesse)

### [LEAK-01] Move-Queue Memory Leak & Fehlende IRQ-Sperre in `get_all_stepper_info` (`src/stepper.c`)
- **Datei & Zeilen:** [stepper.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stepper.c#L342-L363)
- **Schweregrad:** KRITISCH (Permanent geleakte `stepper_move`-Knoten & Race Condition mit Stepper-ISR)
- **Ursachenanalyse (Root Cause):**
  In `get_all_stepper_info()` wird bei `is_pl_save == 1` zuerst `move_queue_clear(&s->mq)` (setzt lediglich `s->mq.first = NULL`) und erst **danach** `stepper_stop(&s->stop_signal, 0)` aufgerufen!
  Da `stepper_stop()` intern über `while (!move_queue_empty(&s->mq))` iteriert, um alle `stepper_move`-Einträge mittels `move_free(m)` in die globale `move_free_list` zurückzugeben, sieht `stepper_stop()` durch das vorherige `move_queue_clear(&s->mq)` immer eine leere Queue – **sämtliche eingereihten `stepper_move`-Knoten gehen dauerhaft verloren (Memory Leak)**!
  Zudem wird `get_all_stepper_info` aus `power_loss_check.c` bei **aktivierten Interrupts** aufgerufen, obwohl sowohl `stepper_get_position()` als auch `stepper_stop()` zwingend gesperrte IRQs voraussetzen.
- **Betroffener Code:**
  ```c
  if (is_pl_save) {
      move_queue_clear(&s->mq);
      stepper_stop(&s->stop_signal, 0);
  }
  ```
- **Lösungsansatz (Defensiver Fix):**
  `move_queue_clear(&s->mq)` vor `stepper_stop` entfernen (da `stepper_stop` die Queue selbst leert und `move_free` aufruft) und die gesamte Schleife in `irqstatus_t flag = irq_save(); ... irq_restore(flag);` einschließen.

---

### [LEAK-02] MCU-Flash bleibt bei Fehlern in `flash_write` dauerhaft entsperrt (`src/stm32/power_loss_check.c`)
- **Datei & Zeilen:** [power_loss_check.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/power_loss_check.c#L146-L203)
- **Schweregrad:** HOCH (Hardware Flash-Lock-Leak während Spannungsabfall/Brown-Out)
- **Ursachenanalyse (Root Cause):**
  `flash_write()` ruft in Zeile 146 `flash_unlock()` auf, kehrt aber in vier Fehlerpfaden (Zeilen 169, 172, 178, 183) direkt mit `return ERROR;` zurück, **ohne `flash_lock()` aufzurufen**. Gerade bei instabiler Versorgungsspannung (Power-Loss) bleibt der Programm-Flash dadurch ungeschützt.
- **Lösungsansatz (Defensiver Fix):**
  Alle Fehlerpfade über ein `goto out;`-Label leiten, das vor `return status;` garantiert `flash_lock();` aufruft.

---

### [LEAK-03] Permanentes `alloc_chunk`-Speicherleck bei wiederholtem `i2c_set_software_bus` (`src/i2c_software.c` & `src/i2ccmds.c`)
- **Datei & Zeilen:** [i2c_software.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/i2c_software.c#L25-L39), [i2ccmds.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/i2ccmds.c#L35-L50)
- **Schweregrad:** MITTEL (`dynmem_pool`-Erschöpfung)
- **Ursachenanalyse (Root Cause):**
  Weder `command_i2c_set_software_bus` noch `i2cdev_set_software_bus` prüfen, ob `i2c->flags & (IF_SOFTWARE | IF_HARDWARE)` bereits gesetzt ist. Jeder erneute Aufruf alloziert einen neuen `alloc_chunk(sizeof(*is))` aus dem statischen MCU-Pool.
- **Lösungsansatz (Defensiver Fix):**
  Vor `alloc_chunk` prüfen: `if (i2c->flags & (IF_SOFTWARE | IF_HARDWARE)) shutdown("Invalid i2c config");`.

---

### [LEAK-04] Pipe-FD-Leak, Mutex/Condvar-Leak & Unjoined-Thread in `serialqueue.c`
- **Datei & Zeilen:** [serialqueue.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/serialqueue.c#L647-L752)
- **Schweregrad:** KRITISCH (File-Descriptor-Erschöpfung `EMFILE` & Use-After-Free)
- **Ursachenanalyse (Root Cause):**
  `serialqueue_alloc()` öffnet eine Pipe `pipe(sq->pipe_fds)` (2 File Descriptors) und initialisiert zwei `pthread_mutex_t` sowie eine `pthread_cond_t`. `serialqueue_free()` schließt **niemals** `sq->pipe_fds[0]` und `sq->pipe_fds[1]` und zerstört weder Mutexe noch Condition-Variablen. Bei jedem MCU-Reconnect oder CAN-Bus-Retry-Zyklus gehen 2 File Descriptors verloren.
- **Lösungsansatz (Defensiver Fix):**
  In `serialqueue_free()` `close(sq->pipe_fds[0]); close(sq->pipe_fds[1]);`, `pthread_mutex_destroy()` und `pthread_cond_destroy()` aufrufen.

---

### [LEAK-05] C-Heap Memory Leak in `extruder_set_pressure_advance` (`kin_extruder.c`)
- **Datei & Zeilen:** [kin_extruder.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/kin_extruder.c#L150-L157)
- **Schweregrad:** HOCH (Kontinuierliches C-Heap-Speicherleck bei Pressure-Advance-Änderungen)
- **Ursachenanalyse (Root Cause):**
  Beim Aufräumen abgelaufener `struct pa_params`-Knoten aus `es->pa_list` entfernt die Schleife den Knoten mittels `list_del(&first_pa->node)`, **vergisst aber den Aufruf von `free(first_pa)`**!
- **Betroffener Code:**
  ```c
  while (!list_is_last(&first_pa->node, &es->pa_list)) {
      struct pa_params *next_pa = list_next_entry(first_pa, node);
      if (next_pa->active_print_time >= cleanup_time) break;
      list_del(&first_pa->node);
      first_pa = next_pa;
  }
  ```
- **Lösungsansatz (Defensiver Fix):**
  Direkt nach `list_del(&first_pa->node);` ein `free(first_pa);` einfügen.

---

### [LEAK-06] Schweres Speicherleck & Zombie-Prozess in `FrequencyQueryHelper.write_to_file` (`inductance_coil.py`)
- **Datei & Zeilen:** [inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/inductance_coil.py#L82-L98)
- **Schweregrad:** HOCH (RAM-Leck im Hauptprozess & Zombie-Prozess)
- **Ursachenanalyse (Root Cause):**
  `write_to_file()` startet `write_proc = multiprocessing.Process(target=self._write_to_file)` **ohne** vorher `self.get_samples()` aufzurufen und **ohne** `write_proc.join()` oder `daemon=True`.
  Dadurch wird `self.get_samples()` erst **innerhalb des geforkten Kindprozesses** ausgeführt! `self.raw_samples = []` (Zeile 66) leert somit nur die Kopie im Adressraum des Kindprozesses, während `self.raw_samples` im Elternprozess (`klippy`) niemals geleert wird und unbegrenzt im RAM verbleibt! Zudem bleibt der Kindprozess ohne `join()` als Zombie-Prozess zurück.
- **Lösungsansatz (Defensiver Fix):**
  `samples = self.get_samples()` im Elternprozess vor dem Starten der asynchronen Schreiboperation aufrufen oder `queuefile.async_write_file` nutzen.

---

### [LEAK-07] FIFO-File-Descriptor-Leak & 30s Main-Reactor-Freeze in `FlowCalcClient.calc_flow_factor` (`flow_calibrator.py`)
- **Datei & Zeilen:** [flow_calibrator.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/flow_calibrator.py#L113-L149)
- **Schweregrad:** HOCH (File-Descriptor-Leak & 30 Sekunden Blockade des gesamten Druckers)
- **Ursachenanalyse (Root Cause):**
  Wenn `os.open(self.resp_fifo, ...)` fehlschlägt, wird `req_fd` nicht geschlossen. Wenn `select.select` ein Timeout erreicht (`not rlist`), kehrt die Methode mit `return None` zurück, **ohne `req_fd` und `resp_fd` zu schließen** (`os.close()` steht nicht in einem `finally`-Block!). Darüber hinaus blockiert `select.select([resp_fd], [], [], timeout)` mit `timeout = 30.0` den Haupt-Reactor-Thread von Klippy bis zu 30 Sekunden lang synchron.
- **Lösungsansatz (Defensiver Fix):**
  `req_fd` und `resp_fd` zwingend in einem `try ... finally:`-Block schließen und das Warten über den Klippy-Reactor (`reactor.pause`) statt über ein synchrones 30s-`select.select` abwickeln.

---

### [LEAK-08] GPIO-FD-Leak & Thread-Leak in `fm175xx_reader.py` sowie Thread-Leak in `mqtt.py`
- **Datei & Zeilen:** [fm175xx_reader.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/fm175xx_reader.py#L217-L237), [fm175xx_reader.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/fm175xx_reader.py#L859-L865), [mqtt.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/mqtt.py#L47-L49)
- **Schweregrad:** MITTEL bis HOCH (FD- & Thread-Leaks)
- **Ursachenanalyse (Root Cause):**
  1. `fm175xx_reader.py:217-237`: `chip_fd = os.open(gpio_chip_dev, ...)` wird nach dem `ioctl(chip_fd, GPIO_GET_LINEHANDLE_IOCTL, ...)` weder gespeichert noch geschlossen! Nur `self._fd = req.fd` wird später geschlossen, `chip_fd` leakt dauerhaft.
  2. `mqtt.py:47-49`: `self.client.loop_start()` startet den Paho-Hintergrundthread **bevor** `self.client.connect()` aufgerufen wird. Wirft `connect()` eine Exception (z. B. Broker noch nicht erreichbar), läuft der Hintergrundthread endlos weiter.
- **Lösungsansatz (Defensiver Fix):**
  `os.close(chip_fd)` unmittelbar nach dem `ioctl`-Aufruf in einem `try...finally`-Block ausführen; in `mqtt.py` `connect_async()` verwenden oder `loop_start()` erst nach erfolgreichem `connect()` aufrufen.

---

### [LEAK-09] Verzeichnis-Handle-Leak (`f_closedir` fehlt) in `scripts/spi_flash/fatfs_api.c` & PTY-FD-Leak in `src/linux/console.c` / `klippy/util.py`
- **Datei & Zeilen:** [fatfs_api.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/scripts/spi_flash/fatfs_api.c#L217-L232), [console.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/linux/console.c#L72-L112), [util.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/util.py#L71-L97)
- **Schweregrad:** MITTEL (Resource Leak)
- **Ursachenanalyse (Root Cause):**
  - `fatfs_list_dir()` ruft `f_opendir(&dir, path)` auf, schließt `dir` aber niemals mit `f_closedir(&dir)` und gibt selbst im Fehlerfall immer `FR_OK` zurück.
  - `src/linux/console.c` schließt `mfd` und `sfd` nicht, wenn ein nachfolgender Syscall fehlschlägt.
- **Lösungsansatz (Defensiver Fix):**
  `f_closedir(&dir)` vor dem Rücksprung in `fatfs_list_dir()` aufrufen und `res` statt `FR_OK` zurückgeben.

---

## 7. Dangling Pointers & Use-After-Free / Use-After-Close

### [UAF-01] Dangling Global Pointer `plc` nach `config_reset` & Aktive `TIM4_IRQHandler`-Speicherkorruption (`src/stm32/power_loss_check.c`)
- **Datei & Zeilen:** [power_loss_check.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/power_loss_check.c#L517-L521), [power_loss_check.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/power_loss_check.c#L672-L684)
- **Schweregrad:** KRITISCH (Dangling Pointer / Use-After-Free im Interrupt-Kontext)
- **Ursachenanalyse (Root Cause):**
  `static struct power_loss_check_dev *plc;` wird über `oid_alloc()` aus Klippers `dynmem_pool` alloziert. Führt Klipper ein `config_reset` (`FIRMWARE_RESTART`) aus (`src/basecmd.c`), wird `dynmem_pool` komplett zurückgesetzt (`alloc_init()`), aber der globale Zeiger `plc` bleibt ungleich `NULL` und `TIM4_IRQHandler` bleibt aktiviert!
  1. `TIM4_IRQHandler` schreibt weiterhin auf `plc->debounce_count`, `plc->voltage_type` und `plc->need_save` mitten in den wiederverwendeten Speicher neuer OIDs (Use-After-Free / Memory Corruption).
  2. Jeder erneute Aufruf von `command_config_power_loss_check_dev` nach einem Soft-Restart wird durch `if (plc) return;` abgewiesen!
- **Lösungsansatz (Defensiver Fix):**
  In `power_loss_check_shutdown()` `TMR4` und dessen NVIC-IRQ deaktivieren und in `command_config_power_loss_check_dev` über `foreach_oid` prüfen, statt den ungeprüften globalen Zeiger `plc` über `config_reset` hinweg zu verwenden.

---

### [UAF-02] Dangling Timer `config_freq_timer` & Aktiver Priority-0-IRQ bei Shutdown in `src/stm32/inductance_coil.c`
- **Datei & Zeilen:** [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L72), [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L432-L437), [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L665-L673)
- **Schweregrad:** HOCH (Dangling Timer & Rekonfigurationssperre)
- **Ursachenanalyse (Root Cause):**
  1. `inductance_coil_shutdown()` löscht nur `sched_del_timer(&d->timer)`, vergisst aber `sched_del_timer(&d->config_freq_timer)` und lässt den Hardware-Interrupt `INPUT_CAPTURE_CAL_CRM_IRQn` (Priorität 0) aktiv.
  2. `static uint8_t inductance_coil_oid_malloc` speichert `args[0]` (`oid`). Ist `oid == 0`, bleibt die Variable `0` (Singleton-Schutz wirkungslos); ist `oid != 0`, wird sie bei `config_reset` nie zurückgesetzt und blockiert jeden `FIRMWARE_RESTART`.
- **Lösungsansatz (Defensiver Fix):**
  In `inductance_coil_shutdown` beide Software-Timer löschen sowie Hardware-Timer und `INPUT_CAPTURE_CAL_CRM_IRQn` deaktivieren; Singleton-Prüfung über `foreach_oid` realisieren.

---

### [UAF-03] Use-After-Free in `serialqueue_free` bei gleichzeitigem Thread-Exit (`serialqueue.c`)
- **Datei & Zeilen:** [serialqueue.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/serialqueue.c#L635-L643), [serialqueue.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/serialqueue.c#L728-L752)
- **Schweregrad:** KRITISCH (Use-After-Free / `SIGSEGV` beim Beenden der seriellen Verbindung)
- **Ursachenanalyse (Root Cause):**
  Wenn in `input_event()` ein Lese-/CAN-Fehler auftritt, setzt der Hintergrundthread selbst `pollreactor_do_exit(sq->pr)` (`must_exit = 1`), noch **bevor** `pollreactor_run()` zurückkehrt und `background_thread()` in Zeile 638 `pthread_mutex_lock(&sq->lock)` erwirbt.
  Ruft der Hauptthread nun `serialqueue_free(sq)` auf, ist `pollreactor_is_exit(sq->pr)` bereits `1`, sodass `if (!pollreactor_is_exit(sq->pr)) serialqueue_exit(sq);` **übersprungen** wird! `serialqueue_free()` ruft kein `pthread_join(sq->tid, NULL)` auf und gibt `free(sq)` sofort frei, während `background_thread()` noch auf `sq->lock` zugreift!
- **Lösungsansatz (Defensiver Fix):**
  Ein eigenes Flag `sq->thread_running` führen, damit `serialqueue_exit()` (inklusive `pthread_join`) in `serialqueue_free()` **immer** ausgeführt wird, solange der Thread noch nicht gejoint wurde.

---

### [UAF-04] Dangling Pointers (`tdm->node` & `tdm->fr`) bei Freigabe via `ffi_lib.free` (`trdispatch.c` & `mcu.py`)
- **Datei & Zeilen:** [trdispatch.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/trdispatch.c#L132-L210), [mcu.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/mcu.py#L174-L177)
- **Schweregrad:** HOCH (Use-After-Free in `td->tdm_list` und `sq->fast_readers`)
- **Ursachenanalyse (Root Cause):**
  `trdispatch_mcu_alloc` hängt `tdm->node` in `td->tdm_list` ein, und `trdispatch_start` hängt `tdm->fr` in `sq->fast_readers` ein. In `mcu.py` werden beide Strukturen jedoch direkt mit `ffi_lib.free` an den Python-GC gebunden, ohne sie vorher aus den C-Verkettungslisten zu entfernen.
- **Lösungsansatz (Defensiver Fix):**
  Dedizierte C-Funktionen `trdispatch_free()` und `trdispatch_mcu_free()` bereitstellen, die vor `free()` `trdispatch_stop()` und `list_del(&tdm->node)` aufrufen.

---

### [UAF-05] Use-After-Close Race Condition beim Shutdown des RFID-Readers (`fm175xx_reader.py`)
- **Datei & Zeilen:** [fm175xx_reader.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/fm175xx_reader.py#L938-L961)
- **Schweregrad:** MITTEL (`OSError: Bad file descriptor` / Race beim Herunterfahren)
- **Ursachenanalyse (Root Cause):**
  In `__shutdown()` wird unmittelbar nach `self._running = False` der GPIO-/SPI-Treiber geschlossen (`self._fm175xx.deinit()`), **ohne** vorher mittels `self._thread.join(timeout=2.0)` auf das Ende von `_thread_Check_Card()` zu warten. Da der Hintergrundthread während `time.sleep(0.1)` mitten in einem Lesezyklus stecken kann, greift er nach `deinit()` auf bereits geschlossene File Descriptors zu.
- **Lösungsansatz (Defensiver Fix):**
  In `__shutdown()` zuerst `self._running = False` setzen, dann `self._thread.join(timeout=2.0)` abwarten und erst danach `self._fm175xx.deinit()` aufrufen.

---

## 8. Stack Overflows, Endlosschleifen & Endlos-Rekursion

### [STACK-01] Ungeprüfte Variable Length Arrays (VLA) auf dem MCU-Stack in `src/i2ccmds.c`
- **Datei & Zeilen:** [i2ccmds.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/i2ccmds.c#L74), [i2ccmds.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/i2ccmds.c#L99)
- **Schweregrad:** HOCH (MCU Stack Overflow)
- **Ursachenanalyse (Root Cause):**
  In `command_i2c_read` (`uint8_t data[data_len];`, bis 255 Bytes) und `command_i2c_modify_bits` (`uint8_t receive_data[reg_len + data_len];`, bis 382 Bytes) werden dynamisch große Arrays direkt auf dem engen MCU-Stack alloziert.
- **Lösungsansatz (Defensiver Fix):**
  Maximale I2C-Transfergröße auf z. B. 64 Bytes begrenzen und feste Puffergrößen verwenden.

---

### [STACK-02] Unendliche Probing-Schleife in `cmd_AUTO_SCREWS_TILT_ADJUST_MANUAL_TUNING` (`auto_screws_tilt_adjust.py`)
- **Datei & Zeilen:** [auto_screws_tilt_adjust.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/auto_screws_tilt_adjust.py#L520-L580)
- **Schweregrad:** HOCH (Unabbrechbare Endlosschleife)
- **Ursachenanalyse (Root Cause):**
  `while True:` führt wiederholt `probe.run_probe(gcmd)` aus und verlässt die Schleife ausschließlich dann, wenn alle Schrauben innerhalb von `self.Manual_thread_adjust_threshold` liegen. Es gibt weder ein `max_iter`-Limit noch eine Timeout-Prüfung.
- **Lösungsansatz (Defensiver Fix):**
  Maximale Iterationszahl (`max_attempts`) und Abbruchprüfung ergänzen.

---

### [STACK-03] Endlosschleife in `PrinterHeaters.set_temperature` bei Shutdown während Queue-Wait (`heaters.py`)
- **Datei & Zeilen:** [heaters.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/heaters.py#L733-L739)
- **Schweregrad:** HOCH (Endlosschleife bei Shutdown / M109)
- **Ursachenanalyse (Root Cause):**
  Die äußere Warteschleife auf den Queue-Slot (`while True: if heater.name in self.heater_queue[:self.max_concurrent_heaters]: break; self.reactor.pause(eventtime + 1.)`) prüft **nicht** `self.printer.is_shutdown()` und aktualisiert `eventtime` innerhalb der Schleife nicht (`eventtime = self.reactor.monotonic()`), sodass sie nach der ersten Sekunde in eine 100%-CPU-Busy-Loop (`pause` in der Vergangenheit!) übergeht und bei einem Shutdown niemals abbricht!
- **Betroffener Code:**
  ```python
  while True:
      with self.queue_lock:
          if heater.name in self.heater_queue[:self.max_concurrent_heaters]:
              break
      self.reactor.pause(eventtime + 1.)
  ```
- **Lösungsansatz (Defensiver Fix):**
  ```python
  while not self.printer.is_shutdown():
      with self.queue_lock:
          if heater.name in self.heater_queue[:self.max_concurrent_heaters]:
              break
      eventtime = self.reactor.pause(self.reactor.monotonic() + 1.)
  ```

---

### [STACK-04] Endlosschleife `while (1):` in `cmd_FILAMENT_DT_SELF_TEST` (`filament_detect.py`)
- **Datei & Zeilen:** [filament_detect.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_detect.py#L238-L244)
- **Schweregrad:** HOCH (Permanente Blockade der G-Code-Verarbeitung)
- **Ursachenanalyse (Root Cause):**
  `cmd_FILAMENT_DT_SELF_TEST` tritt in eine unendliche `while (1):`-Schleife ohne jede Abbruchbedingung ein, bis der Prozess abgeschossen wird.
- **Lösungsansatz (Defensiver Fix):**
  Schleife auf eine definierte Testdauer (`DURATION`, Standard z. B. 10 Sekunden) und `not self.printer.is_shutdown()` begrenzen.

---

### [STACK-05] Defekter Timeout (`wait_timeout_time` wird jede Sekunde überschrieben) -> Endlosschleife in `cmd_WAIT_CHAMBER_TEMP` (`purifier.py`)
- **Datei & Zeilen:** [purifier.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/purifier.py#L1158), [purifier.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/purifier.py#L1188-L1190)
- **Schweregrad:** HOCH (Endlosschleife bei nicht erreichter Kammertemperatur)
- **Ursachenanalyse (Root Cause):**
  In `cmd_WAIT_CHAMBER_TEMP` wird `wait_timeout_time = eventtime + timeout` vor der Schleife berechnet (Zeile 1158), aber **innerhalb** der `while not self.printer.is_shutdown():`-Schleife in Zeile 1188 bei jedem Durchlauf erneut mit `wait_timeout_time = eventtime` überschrieben! Dadurch ist `if eventtime > wait_timeout_time:` in Zeile 1189 (`eventtime > eventtime`) **niemals wahr** und der Timeout greift nie!
- **Betroffener Code:**
  ```python
  wait_timeout_time = eventtime + timeout
  while not self.printer.is_shutdown():
      ...
      eventtime = self.reactor.pause(eventtime + 1.)
      wait_timeout_time = eventtime
      if eventtime > wait_timeout_time:
          ...
          break
  ```
- **Lösungsansatz (Defensiver Fix):**
  Die fehlerhafte Zeile 1188 (`wait_timeout_time = eventtime`) ersatzlos entfernen.

---

### [STACK-06] Endlosschleife bei zyklischen Symlinks in `AsyncFileReader._do_listdir` (`asyncfilereader.py`)
- **Datei & Zeilen:** [asyncfilereader.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/asyncfilereader.py#L368)
- **Schweregrad:** MITTEL (Blockade des Datei-Reader-Threads)
- **Ursachenanalyse (Root Cause):**
  `os.walk(dirname, followlinks=True)` folgt symbolischen Links ohne Zykluserkennung. Ein einziger Symlink auf ein übergeordnetes Verzeichnis lässt den Hintergrundthread endlos laufen.
- **Lösungsansatz (Defensiver Fix):**
  Besuchte `os.path.realpath(root)`-Pfade in einem `set` speichern und bereits besuchte Verzeichnisse überspringen.

---

## 9. Deadlocks & Unendliche Hardware-Polling-Loops (ohne Timeout)

### [DEAD-01] Unendliche Hardware-Polling-Loops ohne Timeout in MCU-Treibern (`sdio.c`, `at32f403a.c`, `at32f415rc.c`, `n32g45x_adc.c`, `spi.c`, `canserial.c`)
- **Datei & Zeilen:**
  - [sdio.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/sdio.c#L307-L318), [sdio.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/sdio.c#L361-L372)
  - [at32f403a.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/at32f403a.c#L37-L52), [at32f415rc.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/at32f415rc.c#L17-L24)
  - [n32g45x_adc.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/n32g45x_adc.c#L65-L75)
  - [spi.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/spi.c#L218-L235)
  - [canserial.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/generic/canserial.c#L156-L160)
- **Schweregrad:** HOCH (MCU-Freeze & Watchdog-Reset)
- **Ursachenanalyse (Root Cause):**
  - `sdio_read_data` und `sdio_write_data` warten in `while ((sdio->STA & ...) == 0)` ohne Software-Timeout auf Hardware-Flags.
  - `at32f403a_log`, `at32f415_log` und `__io_putchar` warten endlos auf `USART_TDBE_FLAG`, obwohl `uart_debug_print_init` standardmäßig deaktiviert/auskommentiert ist.
  - `n32g45x_adc.c:adc_calibrate()` und `spi.c` (AT32F403A) pollen Hardware-Flags ohne Timeout.
  - `canserial.c:156` (`for (;;) { int ret = canbus_send(&send); if (ret >= 0) return; }`) blockiert die gesamte MCU-Taskschleife, wenn der CAN-TX-Puffer voll ist.
- **Lösungsansatz (Defensiver Fix):**
  Alle Hardware-Polling-Schleifen mit einem Software-Timer-Limit (`timer_is_before(timer_read_time(), end)`) bzw. maximalem Schleifenzähler absichern.

---

### [DEAD-02] Permanenter Mutex-Deadlock auf `self._mutex_lock` und `self.channel_active` in `filament_feed.py` & `filament_feed_fac_test.py`
- **Datei & Zeilen:** [filament_feed.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_feed.py#L315-L374), [filament_feed.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_feed.py#L776-L789), [filament_feed_fac_test.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_feed_fac_test.py#L82-L141)
- **Schweregrad:** KRITISCH (Permanenter Deadlock des Filament-Feeders)
- **Ursachenanalyse (Root Cause):**
  1. In `FeedMotor.run()` und `FeedMotor.run_one_cycle()` (`filament_feed.py:315-374`) wird `self._mutex_lock = True` gesetzt, aber die anschließenden Aktor-/Reaktor-Aufrufe stehen **nicht** in einem `try ... finally: self._mutex_lock = False`-Block. In `filament_feed_fac_test.py:139` fängt `except Exception:` Fehler sogar ab, ohne `self._mutex_lock = False` zurückzusetzen! Tritt eine einzige Exception auf, bleibt `_mutex_lock` dauerhaft `True` und jede weitere Motorbewegung wirft `"FeedMotor is already running"`.
  2. In `FilamentFeedModule._load_prepare()` (`filament_feed.py:776-789`) wird `self.channel_active[ch] = True` **vor** dem `try:`-Block gesetzt. Schlägt `self._check_extruder_temp(ch)` in Zeile 778 fehl, greift der `finally:`-Block noch nicht und der Kanal bleibt bis zum Neustart durch `"channel[%d] is busy"` gesperrt!
- **Lösungsansatz (Defensiver Fix):**
  `self._mutex_lock = True` und `self.channel_active[ch] = True` unmittelbar vor `try:` setzen und die Freigabe (`False`) ausnahmslos im zugehörigen `finally:`-Block garantieren.

---

### [DEAD-03] Selbst-Deadlock auf nicht-reentrantem `ReactorMutex` in `machine_state_manager.py`
- **Datei & Zeilen:** [machine_state_manager.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/machine_state_manager.py#L269-L299)
- **Schweregrad:** KRITISCH (Permanenter Reactor-Greenlet-Deadlock)
- **Ursachenanalyse (Root Cause):**
  `Klippy`s `ReactorMutex` (`self._lock`) ist **nicht reentrant** (er prüft nur `if self.is_locked:`). In `change_state()` und `set_action_code()` werden sämtliche registrierten `self._pre_hooks` und `self._post_hooks` **innerhalb** von `with self._lock:` ausgeführt! Ruft irgendein Hook-Callback seinerseits `set_action_code()` oder `change_state()` im selben Greenlet auf, wartet das Greenlet in `ReactorMutex.__enter__` endlos auf sich selbst.
- **Lösungsansatz (Defensiver Fix):**
  Einen reentranten Mutex (Prüfung auf `greenlet.getcurrent()`) verwenden oder die Hooks außerhalb des Locks ausführen.

---

### [DEAD-04] Deadlock-Risiko durch `gcode.run_script_from_command` innerhalb von `with self.lock:` in `bed_mesh.py`
- **Datei & Zeilen:** [bed_mesh.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/bed_mesh.py#L1258-L1270)
- **Schweregrad:** HOCH (Greenlet-Deadlock bei konkurrierendem G-Code)
- **Ursachenanalyse (Root Cause):**
  In `BedMeshCalibrate` wird `with self.lock:` gehalten, während `self.gcode.run_script_from_command(...)` (das `gcode_mutex` anfordert) ausgeführt wird. Hält ein anderes Greenlet bereits `gcode_mutex` und ruft eine `bed_mesh`-Funktion auf, entsteht eine klassische Lock-Order-Inversion (AB-BA-Deadlock).
- **Lösungsansatz (Defensiver Fix):**
  `gcode.run_script_from_command` außerhalb von `with self.lock:` ausführen.

---

## 10. Race Conditions & Concurrency-Fehler

### [RACE-01] Race Conditions zwischen Priority-0-ISR (`InputCapture_IRQHandler`), Timer-ISR und Task in `src/stm32/inductance_coil.c`
- **Datei & Zeilen:** [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L168-L237), [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L279-L320), [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L458-L518)
- **Schweregrad:** HOCH (Korrupte Trigger-Schwellenwerte während Z-Probing)
- **Ursachenanalyse (Root Cause):**
  `update_trigger_frequencies()` wird sowohl aus der Timer-ISR (`inductance_coil_config_freq_event`) als auch aus dem Task-Kontext (`command_virtual_gpio_trigger`) aufgerufen, modifiziert `d->cal_info` aber außerhalb von `irq_save()`. Zudem setzt `inductance_coil_crm_tmr_init()` `g_freq_cal_info` zurück, ohne zuvor den Priority-0-Interrupt `INPUT_CAPTURE_CAL_CRM_IRQn` zu sperren.
- **Lösungsansatz (Defensiver Fix):**
  Alle Schreibzugriffe auf `d->cal_info` und `g_freq_cal_info` vollständig in `irq_save()` / `irq_restore()` kapseln.

---

### [RACE-02] Fehlerhaftes `threading.local()` statt Greenlet-Local State in `GCodeDispatch._process_commands` (`gcode.py`)
- **Datei & Zeilen:** [gcode.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/gcode.py#L10), [gcode.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/gcode.py#L201-L250)
- **Schweregrad:** KRITISCH (Komplettes Verschlucken von `CommandError` und Coded Exceptions bei parallelen Greenlets)
- **Ursachenanalyse (Root Cause):**
  `_process_commands` verwendet `_thread_local = threading.local()` (`_thread_local.in_process_commands`), um zu erkennen, ob ein Aufruf der äußerste Aufruf (`is_top_level`) ist.
  Da Klippy jedoch **alle** Greenlets (G-Code, Timer, Webhooks) im **selben Betriebssystem-Thread** ausführt, bleibt `_thread_local.in_process_commands = True` gesetzt, sobald Greenlet A während eines Befehls (z. B. `G28`, `M109`, `M400`) via `reactor.pause()` pausiert!
  Startet währenddessen Greenlet B (z. B. über `webhooks.py` `gcode/script` oder einen Timer) einen G-Code-Befehl, sieht Greenlet B `_thread_local.in_process_commands == True` und setzt `is_top_level = False`! Tritt in Greenlet B ein Fehler auf, werden `_respond_error()` und `raise_coded_exception(e)` komplett übersprungen!
- **Betroffener Code:**
  ```python
  _thread_local = threading.local()
  ...
  def _process_commands(self, commands, need_ack=True):
      is_top_level = not getattr(_thread_local, 'in_process_commands', False)
      if is_top_level:
          _thread_local.in_process_commands = True
  ```
- **Lösungsansatz (Defensiver Fix):**
  Das Flag an das aktuelle **Greenlet** (`greenlet.getcurrent()`) statt an `threading.local()` binden:
  ```python
  cur_greenlet = greenlet.getcurrent()
  is_top_level = not getattr(cur_greenlet, 'in_process_commands', False)
  if is_top_level:
      cur_greenlet.in_process_commands = True
  ```

---

### [RACE-03] Reentrancy-Crash (`KeyError` / `ValueError`) in `QueryStatusHelper._do_query` (`webhooks.py`)
- **Datei & Zeilen:** [webhooks.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/webhooks.py#L504-L583)
- **Schweregrad:** KRITISCH (Unbehandelter Reactor-Absturz mitten im Druck)
- **Ursachenanalyse (Root Cause):**
  `_do_query()` pausiert bei längeren Status-Abfragen mittels `reactor.pause(reactor.NOW)` (Zeilen 535, 556). Während `_do_query` pausiert ist, kann `send_status()` den Timer erneut auf `reactor.NOW` setzen oder ein Client die Verbindung schließen. Dadurch führen `del self.clients[cconn]` (Zeile 518) zu `KeyError` und `reactor.unregister_timer(self.query_timer)` (Zeile 560, wenn `self.query_timer` bereits auf `None` gesetzt wurde) zu `ValueError`.
- **Lösungsansatz (Defensiver Fix):**
  `self.clients.pop(cconn, None)` statt `del self.clients[cconn]` nutzen und `if self.query_timer is not None:` vor `unregister_timer` prüfen.

---

### [RACE-04] TOCTOU Read-Modify-Write Datei-Race & Thread-Unsicherheit in `exception_manager.py`
- **Datei & Zeilen:** [exception_manager.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/exception_manager.py#L54), [exception_manager.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/exception_manager.py#L190-L258), [exception_manager.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/exception_manager.py#L300-L305)
- **Schweregrad:** HOCH (Datenverlust in `exception_persistent.json` & Cross-Thread-Reactor-Zugriff)
- **Ursachenanalyse (Root Cause):**
  1. `save_persistent_exception()` und `clear_persistent_exception()` lesen die Datei von der Disk und reihen den Schreibvorgang asynchron in `queuefile.async_write_file()` ein, ohne `self.file_lock` zu benutzen. Bei kurz aufeinanderfolgenden Aufrufen (z. B. in `clear_exception()`, Zeile 303 & 305) liest der zweite Aufruf den veralteten Dateistand von der Disk, bevor `queuefile` den ersten Schreibauftrag ausgeführt hat.
  2. `raise_exception_async()` wird aus Hintergrundthreads (`serialhdl.py`) aufgerufen, greift ohne Lock auf `self.async_exceptions` zu und ruft `reactor.update_timer()` direkt aus dem Fremdthread auf; zudem fehlt in `_handle_async_exception()` ein Check `if not self.async_exceptions:` vor `.pop(0)`.
- **Lösungsansatz (Defensiver Fix):**
  Einen geschützten In-Memory-Cache für persistente Exceptions führen und `raise_exception_async` über `threading.Lock()` + `reactor.register_async_callback()` synchronisieren.

---

### [RACE-05] Thread-Safety-Verletzungen & `RuntimeError` im Paho-MQTT-Hintergrundthread (`mqtt.py` & `jsonrpc.py`)
- **Datei & Zeilen:** [mqtt.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/mqtt.py#L79-L82), [mqtt.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/mqtt.py#L110-L118), [jsonrpc.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/jsonrpc.py#L122-L127)
- **Schweregrad:** HOCH (Absturz des MQTT-Netzwerkthreads)
- **Ursachenanalyse (Root Cause):**
  1. In `mqtt.py` laufen `_on_connect` und `_on_message` im Paho-Netzwerkthread und iterieren ohne Lock über `self.subscribed_topics`, während der Hauptthread Topics hinzufügt/entfernt (`RuntimeError: dictionary changed size during iteration`). Zudem sind `list.remove(h)` (Zeile 201) und `message.payload.decode()` (Zeile 112) ungeschützt gegen `ValueError` bzw. `UnicodeDecodeError`.
  2. In `jsonrpc.py:122-127` wird die MQTT-Nachricht **vor** dem Eintragen von `self.pending_requests[request_id]` publiziert. Trifft die Antwort im Paho-Thread vor Zeile 125 ein, wird sie verworfen.
- **Lösungsansatz (Defensiver Fix):**
  Zugriffe auf `self.subscribed_topics` mit einem `threading.Lock()` schützen und `self.pending_requests[request_id]` **vor** `publish_topic()` registrieren.

---

### [RACE-06] Unsynchronisierter Zugriff auf `self._gcode` & Überschreiben aktiver Leser in `asyncfilereader.py`
- **Datei & Zeilen:** [asyncfilereader.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/asyncfilereader.py#L290-L307), [asyncfilereader.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/asyncfilereader.py#L330-L345)
- **Schweregrad:** HOCH (Abruptes Ende eines laufenden Drucks / `AttributeError` im Reader-Thread)
- **Ursachenanalyse (Root Cause):**
  1. `_loop()` liest `if self._gcode is not None and not self._gcode._closed:` ohne `self._gcode_lock`, während `_handle_close()` `self._gcode = None` setzt.
  2. `_AsyncFileReaderSingleton` unterstützt nur eine einzige `self._gcode`-Instanz; wird während eines laufenden Drucks eine zweite `AsyncFileReader`-Instanz geöffnet, schließt `_register_gcode()` die erste Instanz zwangsweise, wodurch der aktive Druck beim nächsten `read()` stillschweigend mit EOF (`''`) abbricht!
- **Lösungsansatz (Defensiver Fix):**
  `self._gcode` unter `with self._gcode_lock:` in eine lokale Variable lesen und eine Menge (`set`) aktiver Reader statt eines einzelnen Slots verwalten.

---

### [RACE-07] Fehlende Synchronisation in `cmd_SET_PID_PROFILE` (`heaters.py`) & RFID-Thread (`fm175xx_reader.py`)
- **Datei & Zeilen:** [heaters.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/heaters.py#L201-L205), [heaters.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/heaters.py#L476-L499), [fm175xx_reader.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/fm175xx_reader.py#L964-L1025)
- **Schweregrad:** MITTEL bis HOCH (Race Condition auf PID-Zustand & RFID-Callbacks)
- **Ursachenanalyse (Root Cause):**
  1. `Heater.set_pid_profile()` tauscht `self.control.Kp/Ki/Kd` und `temp_integ_max` aus, **ohne** `with self.lock:` zu erwerben, während `temperature_callback()` parallel `self.control.temperature_update()` ausführt.
  2. `_thread_Check_Card()` in `fm175xx_reader.py` führt `self._card_info_callback` direkt aus dem Hintergrundthread statt über `reactor.register_async_callback()` aus und modifiziert `_channel_Trigger` ohne Lock (`|=`, `&=`).
- **Lösungsansatz (Defensiver Fix):**
  `set_pid_profile` in `with self.lock:` einschließen und RFID-Callbacks über `self.reactor.register_async_callback` auf dem Reactor-Thread dispatchen.

---

## 11. Unhandled Exceptions, Verschluckte Exceptions & Fehlerhafte Exception-Handler

### [EXC-01] `KeyError`-Crash im Haupt-Reactor bei Client-Disconnect unter Schreibblockade + `SelectReactor` / `EPollReactor` Crashes (`reactor.py`)
- **Datei & Zeilen:** [reactor.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/reactor.py#L269), [reactor.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/reactor.py#L344-L357), [reactor.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/reactor.py#L366-L409)
- **Schweregrad:** KRITISCH (Kompletter Drucker-Absturz bei Webhook-Disconnect)
- **Ursachenanalyse (Root Cause):**
  1. **`PollReactor._dispatch_loop` (Zeilen 344–357):** Wenn ein Webhook-Client bei vollem Sendepuffer (`POLLHUP | POLLOUT` registriert) die Verbindung trennt, liefert `poll()` ein Event mit **beiden** Bits (`POLLHUP` und `POLLOUT`). Der erste Block `if event & (select.POLLIN | select.POLLHUP):` ruft `read_callback` auf, welcher EOF erkennt und `unregister_fd()` aufruft (`del self._fds[fd]`). Direkt danach prüft Zeile 352 `if event & select.POLLOUT:` und greift auf `self._fds[fd].write_callback` zu -> **unbehandelter `KeyError` im Haupt-Reactor-Loop**!
  2. **`SelectReactor._dispatch_loop` (Zeile 269):** Übergibt `self.write_fds` statt `self._write_fds` (`AttributeError`).
  3. **`EPollReactor.register_fd` (Zeile 369):** Speichert `fds[fd] = read_callback` (Funktion) statt `file_handler`, ruft in Zeile 398 aber `self._fds[fd].read_callback(eventtime)` auf (`AttributeError`).
- **Betroffener Code:**
  ```python
  # klippy/reactor.py:344-354
  for fd, event in res:
      busy = True
      if event & (select.POLLIN | select.POLLHUP):
          self._fds[fd].read_callback(eventtime)
          ...
      if event & select.POLLOUT:
          self._fds[fd].write_callback(eventtime)
  ```
- **Lösungsansatz (Defensiver Fix):**
  ```python
  if event & (select.POLLIN | select.POLLHUP):
      fh = self._fds.get(fd)
      if fh is not None:
          fh.read_callback(eventtime)
      ...
  if event & select.POLLOUT:
      fh = self._fds.get(fd)
      if fh is not None:
          fh.write_callback(eventtime)
  ```

---

### [EXC-02] `EINTR` beendet permanent den C-Hintergrundthread in `pollreactor.c`
- **Datei & Zeilen:** [pollreactor.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/pollreactor.c#L136-L148)
- **Schweregrad:** KRITISCH (Abbruch der MCU-Kommunikation bei jedem POSIX-Signal)
- **Ursachenanalyse (Root Cause):**
  Wenn `poll()` durch ein beliebiges POSIX-Signal unterbrochen wird (`ret < 0` mit `errno == EINTR`), setzt `pollreactor_run()` sofort `pr->must_exit = 1` und beendet dauerhaft den `serialqueue`-Thread der MCU!
- **Lösungsansatz (Defensiver Fix):**
  ```c
  } else if (ret < 0) {
      if (errno == EINTR)
          continue;
      report_errno("poll", ret);
      pr->must_exit = 1;
  }
  ```

---

### [EXC-03] `UnboundLocalError` (`message`, `probe_session`, `need_save`) & Leeres `raise` außerhalb von `except`
- **Datei & Zeilen:**
  - [extruder.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/kinematics/extruder.py#L1456-L1484), [extruder.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/kinematics/extruder.py#L1731-L1748)
  - [probe_inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/probe_inductance_coil.py#L1183-L1190)
  - [purifier.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/purifier.py#L877-L944)
  - [filament_feed.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_feed.py#L838), [filament_feed.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_feed.py#L943)
  - [filament_feed_fac_test.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_feed_fac_test.py#L256)
- **Schweregrad:** HOCH (`UnboundLocalError` & `RuntimeError: No active exception to reraise`)
- **Ursachenanalyse (Root Cause):**
  1. `extruder.py`: Wenn `self.Switching_Tool` weder `'T0'..'T3'` noch `None` ist (z. B. `""`), bleibt `message` ungebunden und `raise self.printer.command_error(message)` wirft `UnboundLocalError`.
  2. `probe_inductance_coil.py`: Schlägt `start_probe_session` in `run_single_probe` fehl, wirft `probe_session.end_probe_session()` im `finally:`-Block `UnboundLocalError`.
  3. `purifier.py`: Tritt in `_handle_control_purifier` vor Zeile 914 ein Fehler auf, wirft `if need_save:` im `finally:`-Block `UnboundLocalError`.
  4. `filament_feed.py` & `filament_feed_fac_test.py`: Führen ein nacktes `raise` außerhalb eines `except`-Blocks aus (`RuntimeError: No active exception to reraise`).
- **Lösungsansatz (Defensiver Fix):**
  Lokale Variablen (`message = "Park status error"`, `probe_session = None`, `need_save = False`) vor dem `try`-Block initialisieren und `raise Exception(...)` statt eines nackten `raise` außerhalb von `except` verwenden.

---

### [EXC-04] Fehlende `try ... finally:`-Wiederherstellung nach Probing / Kalibrierung (`extruder_calibration.py`, `probe.py`, `probe_inductance_coil.py`, `flow_calibrator.py`)
- **Datei & Zeilen:**
  - [extruder_calibration.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/extruder_calibration.py#L196), [extruder_calibration.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/extruder_calibration.py#L301-L302)
  - [probe.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/probe.py#L130-L141), [probe.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/probe.py#L454-L468)
  - [probe_inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/probe_inductance_coil.py#L537-L541)
  - [flow_calibrator.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/flow_calibrator.py#L1323-L1361)
- **Schweregrad:** KRITISCH (Zerstörtes Z-Probing / Eingeschaltete Heizung nach Fehler)
- **Ursachenanalyse (Root Cause):**
  1. **`extruder_calibration.py`:** Überschreibt `probe_obj.set_mcu_probe(self.mcu_probe)` (setzt den optischen/analogen Kalibriersensor als globalen Drucker-Probe!), stellt den originalen Induktions-Z-Probe aber bei einer Exception niemals in einem `finally:`-Block wieder her! Jedes nachfolgende `G28 Z` oder `BED_MESH_CALIBRATE` nutzt dann den falschen Sensor und fährt die Düse ungebremst ins Druckbett!
  2. **`probe.py`:** `run_single_probe`, `cmd_PROBE_ACCURACY` und `cmd_PROBE_CALIBRATE` rufen `probe_session.end_probe_session()` nicht in einem `finally:`-Block auf (`multi_probe_pending` bleibt dauerhaft `True`).
  3. **`probe_inductance_coil.py:537-541`:** Im `finally:`-Block steht `self._move(...)` **vor** `toolhead.set_accel(cur_accel)`. Wirft `_move` einen Fehler, bleibt die Beschleunigung verstellt.
  4. **`flow_calibrator.py:1323-1361`:** `cmd_FLOW_MEASURE_K` schaltet die Extruderheizung bei einem Fehler während der Messung nicht in einem `finally:`-Block auf `0` zurück (und stürzt bei `K_STEP=0` in `range(..., 0)` mit `ValueError` ab).
- **Lösungsansatz (Defensiver Fix):**
  Alle Zustandsänderungen (`orig_mcu_probe`, `probe_session`, `cur_accel`, Heizungstemperatur) zwingend in `finally:`-Blöcken zurücksetzen.

---

### [EXC-05] Unbehandelte `UnicodeDecodeError`, `ValueError`, `KeyError` & Verschlucktes `gcmd.error(e)`
- **Datei & Zeilen:**
  - [inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/inductance_coil.py#L146-L147): Ruft `gcmd.error(e)` **ohne `raise`** auf (Exception wird konstruiert und sofort verworfen!).
  - [filament_protocol.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_protocol.py#L369-L375): Unbehandelter `UnicodeDecodeError` in `m1_proto_data_parse` bei korrupten RFID-Tag-Daten.
  - [virtual_sdcard.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/virtual_sdcard.py#L1156-L1230): Unbehandelter `UnicodeDecodeError` und implizites `return None` (führt zu `TypeError: cannot unpack non-iterable NoneType object`) in `parse_power_loss_move_env`.
  - [filament_parameters.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_parameters.py#L1580-L1607): Unbehandelter `ValueError`/`AttributeError` in `_version_to_tuple`.
  - [extruder_config_bak.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/extruder_config_bak.py#L78-L80): `TypeError`, wenn JSON-Datei `null` oder eine Liste enthält.
  - [heaters.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/heaters.py#L327-L334): `KeyError: 'default'` in `ControlPID.__init__`, wenn keine Standard-PID-Parameter vorhanden sind.
  - [configfile.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/configfile.py#L408-L415): `cmd_SAVE_CONFIG` fängt `configparser.Error` nicht ab.
- **Lösungsansatz (Defensiver Fix):**
  `raise gcmd.error(str(e))` verwenden, `.decode('utf-8', errors='replace')` nutzen und Eingabeformate defensiv validieren.

---

## 12. Schwerwiegende Logische Fehler & State-Corruption Bugs

### [LOG-01] Off-by-One-Bug in `get_sum()` löst Fehlauslösungen des Induktions-Z-Sensors aus (`src/stm32/inductance_coil.c`)
- **Datei & Zeilen:** [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L128-L132)
- **Schweregrad:** KRITISCH (Falsche Frequenzberechnung & Spurious Z-Endstop-Trigger)
- **Ursachenanalyse (Root Cause):**
  `get_sum(MOVING_SUM *ms)` soll `0` zurückgeben, solange das gleitende Fenster (`ms->bufferSize`, Standard `2`) noch nicht vollständig mit Samples gefüllt ist. Die Bedingung lautet jedoch `if (ms->count + 1 < ms->bufferSize || ms->bufferSize == 0) return 0;`.
  Bei `bufferSize = 2` ist nach dem **ersten** Sample `ms->count == 1`, sodass `1 + 1 < 2` (`2 < 2`) bereits `false` ergibt! `get_sum()` gibt daher schon beim `(bufferSize - 1)`-ten Sample die Teilsumme zurück, obwohl `freq_cal_factor` und die Trigger-Schwellen `cmp_trg_cnt_ht/lt` für `bufferSize` Samples skaliert sind! Dies halbiert/verdoppelt den Messwert beim `(bufferSize - 1)`-ten Sample nach jedem Reset.
- **Betroffener Code:**
  ```c
  uint32_t get_sum(MOVING_SUM *ms) {
    if (ms->count + 1 < ms->bufferSize || ms->bufferSize == 0)
      return 0;
    return ms->sum;
  }
  ```
- **Lösungsansatz (Defensiver Fix):**
  ```c
  uint32_t get_sum(MOVING_SUM *ms) {
    if (ms->bufferSize == 0 || ms->count < ms->bufferSize)
      return 0;
    return ms->sum;
  }
  ```

---

### [LOG-02] Unerreichbarer `elif os.path.isdir`-Zweig verhindert Verzeichnislöschung in `queuefile.py`
- **Datei & Zeilen:** [queuefile.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/queuefile.py#L105-L109)
- **Schweregrad:** HOCH (`IsADirectoryError` & Toter Code)
- **Ursachenanalyse (Root Cause):**
  Für jedes existierende Verzeichnis gibt `os.path.exists(op.filename)` `True` zurück! Dadurch betritt `op.op_type == "delete"` immer den ersten Zweig (`os.remove(op.filename)` -> wirft `IsADirectoryError`), und der Zweig `elif os.path.isdir(op.filename): shutil.rmtree(op.filename)` wird **niemals erreicht**. Zudem sind in `safe_write` (Zeilen 87–88, 128–129) `f.flush()` und `os.fdatasync()` auskommentiert.
- **Betroffener Code:**
  ```python
  elif op.op_type == "delete":
      if os.path.exists(op.filename):
          os.remove(op.filename)
      elif os.path.isdir(op.filename):
          shutil.rmtree(op.filename)
  ```
- **Lösungsansatz (Defensiver Fix):**
  ```python
  elif op.op_type == "delete":
      if os.path.isdir(op.filename) and not os.path.islink(op.filename):
          shutil.rmtree(op.filename)
      elif os.path.lexists(op.filename):
          os.remove(op.filename)
  ```

---

### [LOG-03] 8-stellige RGBA-Farocodes zerstören `print_task.json` beim nächsten Neustart (`print_task_config.py`)
- **Datei & Zeilen:** [print_task_config.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/print_task_config.py#L223), [print_task_config.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/print_task_config.py#L681-L692), [print_task_config.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/print_task_config.py#L750-L759)
- **Schweregrad:** KRITISCH (Selbstzerstörung der persistenten Konfiguration beim Reboot)
- **Ursachenanalyse (Root Cause):**
  1. In `set_filament_Slot()` (Zeile 681–692) wird der **8-stellige RGBA-String** (`f"#{color_rgba[:6]}FF"`, 9 Zeichen inkl. `#`) in `self.filament_color_multi['colors'][channel]` gespeichert und in `print_task.json` persistiert. Beim nächsten Start prüft `_early_check()` in Zeile 223 `self._is_valid_rgb_color(c)` (erlaubt ausschließlich **6-stellige RGB-Strings** `#RRGGBB`!), stuft die Datei als korrupt ein und **setzt die gesamte `print_task.json` auf Werkseinstellungen zurück**!
  2. In `cmd_SET_PRINT_PREFERENCES` (Zeile 750–759) wird `'flow_calib_extruders'` statt `'flow_calibrate_extruders'` geschrieben, sodass die Einstellung wirkungslos bleibt.
- **Lösungsansatz (Defensiver Fix):**
  In Zeile 685 `f"#{color_rgba[:6]}"` (6-stelliges RGB) in `self.filament_color_multi['colors'][channel]` speichern und in Zeile 752/756 den Schlüsselnamen `'flow_calibrate_extruders'` korrigieren.

---

### [LOG-04] `self.pending_requests.pop(0)` wirft immer `KeyError: 0` und löscht alle 100 offenen RPC-Requests (`jsonrpc.py`)
- **Datei & Zeilen:** [jsonrpc.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/jsonrpc.py#L105-L113)
- **Schweregrad:** HOCH (Massenverlust aller laufenden JSON-RPC-Anfragen)
- **Ursachenanalyse (Root Cause):**
  `self.pending_requests` ist ein `dict`, dessen Schlüssel `request_id` bei `1` beginnen (`1, 2, 3, ...`). Wenn `len(self.pending_requests) >= 100` erreicht wird, versucht Zeile 109 das älteste Element mittels `self.pending_requests.pop(0)` (wie bei einer Liste!) zu entfernen. Da der Schlüssel `0` im `dict` nicht existiert, wirft `.pop(0)` **immer `KeyError: 0`**, springt in den `except Exception:`-Block und führt `self.pending_requests.clear()` aus – wodurch **alle 100 aktiven Anfragen gleichzeitig gelöscht werden**!
- **Betroffener Code:**
  ```python
  if len(self.pending_requests) >= self.max_pending_requests:
      try:
          self.pending_requests.pop(0)
      except Exception:
          self.pending_requests.clear()
  ```
- **Lösungsansatz (Defensiver Fix):**
  ```python
  if len(self.pending_requests) >= self.max_pending_requests:
      oldest_key = next(iter(self.pending_requests), None)
      if oldest_key is not None:
          self.pending_requests.pop(oldest_key, None)
  ```

---

### [LOG-05] Late-Binding-Closure-Bug (`i` ist immer `3`), fehlende `y_diff`-Prüfung in Park-Kalibrierung (`extruder.py`)
- **Datei & Zeilen:** [extruder.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/kinematics/extruder.py#L1770-L1776), [extruder.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/kinematics/extruder.py#L2065-L2071), [extruder.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/kinematics/extruder.py#L2110-L2116)
- **Schweregrad:** HOCH (Falscher Extruder-Vref-Schalter & Ungeprüfte Y-Abweichung)
- **Ursachenanalyse (Root Cause):**
  1. In Zeile 1770–1776 erzeugt eine Schleife `for i in range(len(extruder_list)):` verzögerte Callbacks `lambda e, s=state: extruder_list[i].vref_sw.set_sw(s)`. Da `i` nicht als Default-Argument gebunden wird, schalten alle Callbacks nach Schleifenende ausschließlich den **letzten Extruder** (`extruder_list[3]`)!
  2. In `cmd_MOVE_TO_PARK_CALIBRATION_POINT` (Zeile 2069) und `cmd_VERIFY_PARK_POSITION` (Zeile 2114) wird `y_diff = abs(cur_pos[1] - park_detector.calibration_point[1])` berechnet, in der `if`-Bedingung `if x_diff > 0.1:` jedoch komplett vergessen!
- **Lösungsansatz (Defensiver Fix):**
  `lambda e, s=state, idx=i: extruder_list[idx].vref_sw.set_sw(s)` sowie `if x_diff > 0.1 or y_diff > 0.1:` verwenden.

---

### [LOG-06] Fehlerhafte Mittelwertbildung über Teilmenge (`/ 9`) in `homing_precise_corexy.py`
- **Datei & Zeilen:** [homing_precise_corexy.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/homing_precise_corexy.py#L282-L303)
- **Schweregrad:** KRITISCH (Massiver Positionsfehler bei CoreXY-Präzisions-Homing)
- **Ursachenanalyse (Root Cause):**
  In `perform_multi_point_diagonal_probing()` wird bei Ausreißern (`need_probe_point_index`, z. B. 1 oder 2 von 9 Punkten) `avg = 0` gesetzt, in der Schleife **nur über die nachgemessenen Punkte** summiert (`avg += temp_position`), und am Ende in Zeile 303 durch `9` geteilt (`avg = avg / 9`)! Wenn nur 1 Punkt nachgemessen wurde, beträgt `avg` nur **1/9 der tatsächlichen Position**!
- **Betroffener Code:**
  ```python
  if len(need_probe_point_index):
      avg = 0
      for i in need_probe_point_index:
          ...
          avg += temp_position
  avg = avg / 9
  ```
- **Lösungsansatz (Defensiver Fix):**
  In der Nachmessschleife `probe_Trigger_position[i] = temp_position` aktualisieren und danach über **alle 9 Elemente** mitteln: `avg = sum(probe_Trigger_position) / len(probe_Trigger_position)`.

---

### [LOG-07] Kopierfehler `hole_z` mit Fallback `hole_x`, invertierte Determinantenformel & ungeschütztes `lstsq` in `probe_inductance_coil.py`
- **Datei & Zeilen:** [probe_inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/probe_inductance_coil.py#L50-L86), [probe_inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/probe_inductance_coil.py#L316-L330), [probe_inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/probe_inductance_coil.py#L1520)
- **Schweregrad:** KRITISCH (Düsencrash bei Düsenkalibrierung, weil X-Koordinate ~150 mm als Z-Höhe verwendet wird!)
- **Ursachenanalyse (Root Cause):**
  1. In Zeile 1520 steht `hole_z = macro.variables.get('hole_z', hole_x)` statt `macro.variables.get('hole_z', hole_z)`! Fehlt `'hole_z'` im Makro, wird die X-Koordinate (`hole_x`) als Z-Koordinate übernommen!
  2. In `find_circle_center()` (Zeilen 50–86) haben `center_x` und `center_y` umgekehrte Vorzeichen im Zähler und einen ungeschützten `Decimal`-Nenner (`DivisionByZero` bei kollinearen Punkten).
  3. In `_find_circle_center()` (Zeilen 316–330 & 493–505) wird das Ergebnis von `np.linalg.lstsq` bei kollinearen Punkten nicht auf Plausibilität geprüft, bevor der Druckkopf dorthin verfährt.
- **Lösungsansatz (Defensiver Fix):**
  Zeile 1520 in `hole_z = macro.variables.get('hole_z', hole_z)` ändern und den berechneten Kreismittelpunkt vor dem Verfahren auf maximalen Abstand zum Startpunkt prüfen.

---

### [LOG-08] Vertauschte LED-Pins (`white_pin` / `red_pin`) und `max()` statt `min()` beim Ramp-Up in `filament_feed.py`
- **Datei & Zeilen:** [filament_feed.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_feed.py#L137), [filament_feed.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_feed.py#L411-L418), [filament_feed.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_feed.py#L1219-L1222)
- **Schweregrad:** MITTEL (Vertauschte Fehler-/Status-LEDs & Sofortiger Sprung auf Maximal-PWM)
- **Ursachenanalyse (Root Cause):**
  1. `FeedLight.__init__` erwartet `(printer, white_pin, red_pin)`, wird in Zeile 416 aber mit `(self.printer, self.light_red_pin[i], self.light_white_pin[i])` aufgerufen (Weiß und Rot vertauscht).
  2. In Zeile 1219 & 1221 wird beim schrittweisen Hochrammen `duty = max(duty + duty_step, max_duty)` statt `min(...)` verwendet, was den Wert bereits im ersten Schritt sofort auf `max_duty` setzt.
- **Lösungsansatz (Defensiver Fix):**
  Argumentreihenfolge bei `FeedLight(...)` korrigieren und `min(duty + duty_step, max_duty)` verwenden.

---

### [LOG-09] Falsy-`0.0`-Bug löscht `flow_calibrator.json`, mutiert `DEFAULT_K` und liefert `None` in `flow_calibrator.py`
- **Datei & Zeilen:** [flow_calibrator.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/flow_calibrator.py#L260), [flow_calibrator.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/flow_calibrator.py#L305-L327), [flow_calibrator.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/flow_calibrator.py#L478-L491)
- **Schweregrad:** HOCH (Löschung gültiger Kalibrierdaten & `TypeError` bei `k = 0.0`)
- **Ursachenanalyse (Root Cause):**
  1. `_load_flow_calibrate_param()` prüft `if not val or not isinstance(val, (int, float)) or val < 0:`. Da `not 0.0` in Python `True` ist, wird ein gültiger K-Faktor von `0.0` als korrupt gewertet, `raise "invalid flow_calibrator.json"` (String-Exception!) ausgelöst und die gesamte `flow_calibrator.json`-Datei gelöscht! Zudem teilt `self.flow_Queue_param = DEFAULT_K` dieselbe Dictionary-Referenz, sodass Änderungen `DEFAULT_K` in-place mutieren.
  2. `_get_next_k()` gibt implizit `None` zurück, wenn `area_left == 0` und `area_right == 0` sind.
- **Lösungsansatz (Defensiver Fix):**
  `if val is None or isinstance(val, bool) or not isinstance(val, (int, float)) or val < 0:` prüfen, `DEFAULT_K.copy()` verwenden und in `_get_next_k` `elif area_right >= area_left:` nutzen.

---

### [LOG-10] `EXCLUDE_OBJECT`-Crash & Toter Code sowie falsche Z-Stepper-Annahme in `virtual_sdcard.py`
- **Datei & Zeilen:** [virtual_sdcard.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/virtual_sdcard.py#L1606-L1616), [virtual_sdcard.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/virtual_sdcard.py#L2246-L2264)
- **Schweregrad:** HOCH (`AttributeError` bei `EXCLUDE_OBJECT` während Power-Loss-Parsing)
- **Ursachenanalyse (Root Cause):**
  1. In Zeile 2248 ruft `_parse_line_env` `self.get(params, 'NAME').upper()` auf. Da `VirtualSD` keine Methode `self.get()` besitzt (und `NAME` fehlen kann), stürzt die Methode mit `AttributeError` ab. Zudem steht `if 'END' in params:` als `elif` unter `if 'START' in params:`, was nur ausgeführt wird, wenn `'START'` **nicht** in `params` ist.
  2. In Zeile 1609 nimmt `get_pl_stepper_pos()` fest an, dass `stepper_mcu_pos[2]` immer der Z-Stepper ist, statt den Namen `stepper_name.startswith('stepper_z')` zu prüfen.
- **Lösungsansatz (Defensiver Fix):**
  `params.get('NAME', '').upper()` verwenden und den Z-Stepper anhand seines Namens statt über den festen Index `2` ermitteln.

---

### [LOG-11] Fehlerhafte Index-Prüfung `sorted_sub_idx[idx] == idx` in `bed_mesh.py`
- **Datei & Zeilen:** [bed_mesh.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/bed_mesh.py#L1460-L1462)
- **Schweregrad:** MITTEL (Falsche Zuordnung von Sub-Mesh-Punkten)
- **Ursachenanalyse (Root Cause):**
  In `substitute_points()` wird `if idx < len(sorted_sub_idx) and sorted_sub_idx[idx] == idx:` geprüft statt `if idx in sorted_sub_idx:`. Sobald `sorted_sub_idx` nicht exakt `[0, 1, 2, ...]` ab Index 0 ist, schlägt `sorted_sub_idx[idx] == idx` für alle nachfolgenden Indizes fehl!
- **Lösungsansatz (Defensiver Fix):**
  `sub_idx_set = set(sorted_sub_idx)` vorab bilden und `if idx in sub_idx_set:` prüfen.

---

### [LOG-12] Unbedingter Z-Move & Zurücksetzen auf `PRINTING` im `finally:`-Block nach Druckabbruch (`defect_detection.py`)
- **Datei & Zeilen:** [defect_detection.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/defect_detection.py#L942-L961)
- **Schweregrad:** HOCH (Unerwartete Z-Fahrt & Falscher Druckerstatus nach Abbruch/Shutdown)
- **Ursachenanalyse (Root Cause):**
  Im `finally:`-Block von `cmd_FOREIGN_OBJECT_DETECT` wird der Druckerstatus bedingungslos auf `PRINTING` gesetzt und `toolhead.manual_move([None, None, z_pos], ...)` ausgeführt – selbst dann, wenn die Erkennung durch einen Shutdown, Not-Aus oder Benutzerabbruch beendet wurde.
- **Lösungsansatz (Defensiver Fix):**
  Im `finally:`-Block prüfen, ob `not self.printer.is_shutdown()` und der vorherige Status tatsächlich wiederhergestellt werden darf.

---

### [LOG-13] Korrupte Fehlercode-Formatierung in `klippy.py`, `serialhdl.py`, `homing.py` und `"serial: None"` in `printer_device_scan.py`
- **Datei & Zeilen:**
  - [klippy.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/klippy.py#L581): `coded = f"{level:04d}-{id:04d}-{code:04d}-{level:04d}"` schreibt `code` an die Position von `index` und `level` an die Position von `code`.
  - [serialhdl.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/serialhdl.py#L323-L324) & [homing.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/homing.py#L96): Verwenden `"%4d"` (Leerzeichen-Padding `"   0"`) statt `"%04d"` (Null-Padding `"0000"`).
  - [printer_device_scan.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/printer_device_scan.py#L74-L88): Schreibt den Literal-String `"serial: None"` in `printer.cfg`, wenn ein MCU-Gerät beim Scan nicht gefunden wurde (`info_list[index] is None`).
- **Lösungsansatz (Defensiver Fix):**
  In `klippy.py:581` `f"{level:04d}-{id:04d}-{index:04d}-{code:04d}"` nutzen, `"%4d"` durch `"%04d"` ersetzen und in `printer_device_scan.py` Einträge mit `info_list[index] is None` überspringen.

---

### [LOG-14] Konfigurations-Tippfehler & Fehlende Sektionspräfixe in `extruder_calibration.py`, `filament_entangle_detect.py`, `mqtt.py`
- **Datei & Zeilen:**
  - [extruder_calibration.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/extruder_calibration.py#L79-L85), [extruder_calibration.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/extruder_calibration.py#L223-L224): Zeile 79 liest `config.getint('_probe_mode', ...)` ohne `section +`-Präfix; Zeile 84 initialisiert `extruder_y_cal_second_positions` nur wenn `section == 'x'`, während Zeile 224 auf den Tippfehler-Key `self.cal_params['extruder_y_cal_second_posiions']` (fehlendes `t`) zugreift -> garantierter `KeyError`.
  - [filament_entangle_detect.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_entangle_detect.py#L148-L151): Prüft `self.extruder_name + "0"`, was für `extruder1` zu `"extruder10"` wird.
  - [mqtt.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/mqtt.py#L155), [mqtt.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/mqtt.py#L212): `qos = qos or self.qos` überschreibt ein explizit übergebenes `qos=0` mit `self.qos`.
- **Lösungsansatz (Defensiver Fix):**
  Tippfehler `'extruder_y_cal_second_positions'` und `section + '_probe_mode'` korrigieren, in `filament_entangle_detect.py` `"extruder0"` direkt prüfen und in `mqtt.py` `qos = self.qos if qos is None else qos` verwenden.
