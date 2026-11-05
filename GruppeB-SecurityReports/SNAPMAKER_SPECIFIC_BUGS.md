# Snapmaker U1 Specific Bugs (Gruppe B)

Zentrale Übersicht aller Befunde der **Gruppe B (Snapmaker U1 Proprietary)** aus dem Referenzbericht `FEHLERBERICHT_U1_KLIPPER.md`.

## Statusübersicht & Metriken

- **Gesamtanzahl Befunde:** 53
- **Kritisch (KRITISCH):** 12
- **Hoch (HOCH):** 36
- **Mittel (MITTEL):** 5
- **Bearbeitungsstatus:** 1 Behoben (Geprueft), 52 Offen

---

## Tabellarische Übersicht

| ID | Modul / Datei | Zeilen | Schweregrad | Status | Titel / Kurzbeschreibung |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **[SEC-01](BUG-SEC-01-bed-mesh-path-traversal.md)** | `bed_mesh.py` | `2110-2194` | **KRITISCH** | Behoben (Geprueft) | Path Traversal & Beliebiges Überschreiben/Löschen von `.json`-Dateien im `ProfileManager` (`bed_mesh.py`) |
| **[SEC-02](BUG-SEC-02-bed-mesh-output-file-path-traversal.md)** | `bed_mesh.py` | `304-313` | **HOCH** | Behoben (Geprueft) | Beliebiges Überschreiben von Systemdateien via `BED_MESH_OUTPUT_FILE` (`bed_mesh.py`) |
| **[SEC-03](BUG-SEC-03-probe-inductance-coil-path-traversal.md)** | `probe_inductance_coil.py` | `728, 999-1010` | **HOCH** | Behoben (Geprueft) | Path Traversal / Arbitrary File Append über `LOG_FILE` in `probe_inductance_coil.py` |
| **[SEC-04](BUG-SEC-04-flow-calibrator-path-traversal.md)** | `flow_calibrator.py` | `231-241, 1194-1215` | **HOCH** | Behoben (Geprueft) | Path Traversal & Ungeprüfter Dateipfad via `AXIS` in `flow_calibrator.py` |
| **[BUF-01](BUG-BUF-01.md)** | `sdiocmds.c` | `135-164` | **KRITISCH** | Offen | 32-Bit Integer-Overflow umgeht Bounds-Check -> Beliebiger Out-of-Bounds Write/Read in `src/sdiocmds.c` |
| **[BUF-10](BUG-BUF-10.md)** | `extruder.py` | `1163-1168, 1259-1265, 1451-1453, 1728-1729` | **HOCH** | Offen | Out-of-Bounds `IndexError` auf `unknown[0]` und `filament_vendor[extruder_index]` in `extruder.py` |
| **[BUF-11](BUG-BUF-11.md)** | `print_task_config.py` | `826-836, 1175, 1399-1405` | **HOCH** | Offen | Out-of-Bounds Listen-Indizierung in `print_task_config.py` |
| **[BUF-12](BUG-BUF-12.md)** | `fm175xx_reader.py, sc7a20.py` | `808, 1037, 85-88` | **MITTEL** | Offen | Off-by-One Kanalprüfung & Ungeprüftes `recv_buff[0]` in `fm175xx_reader.py` & `sc7a20.py` |
| **[INT-01](BUG-INT-01.md)** | `sdiocmds.c, sdio.c` | `82, 112, 408` | **HOCH** | Offen | 32-Bit Integer-Overflow bei SDIO-Timeout-Berechnung & `uint8_t`-Underflow in `sdio.c` / `sdiocmds.c` |
| **[INT-03](BUG-INT-03.md)** | `inductance_coil.c` | `45, 104-117, 328-357, 471-479` | **HOCH** | Offen | Tautologischer Bounds-Check, `MOVING_SUM` 32-Bit-Overflow & Signed-Overflow in `src/stm32/inductance_coil.c` |
| **[INT-04](BUG-INT-04.md)** | `power_loss_check.py, power_loss_check.c` | `492-493, 30-32, 89-92` | **HOCH** | Offen | 16-Bit Timer-Underflow & `uint32_t`-Überlauf von `power_loss_trigger_time` (`power_loss_check.c` & `power_loss_check.py`) |
| **[DIV-01](BUG-DIV-01.md)** | `inductance_coil.c, sdio.c` | `408, 335, 407, 417` | **KRITISCH** | Offen | Hardware-Division-by-Zero in `sdio_set_speed` (`src/stm32/sdio.c`) und `inductance_coil.c` |
| **[DIV-04](BUG-DIV-04-bed-mesh-zero-division.md)** | `bed_mesh.py` | `219-220` | **HOCH** | Behoben (Geprueft) | Division by Zero bei `z_adj == self.fade_dist` in `bed_mesh.py` |
| **[DIV-05](BUG-DIV-05.md)** | `inductance_coil.py` | `186, 267` | **HOCH** | Offen | Division by Zero & `date_rate`-Tippfehler in `inductance_coil.py` |
| **[DIV-06](BUG-DIV-06.md)** | `homing_precise_corexy.py` | `107-108` | **HOCH** | Offen | Division by Zero in `homing_precise_corexy.py`, `homing_xyz_override.py`, `auto_screws_tilt_adjust.py`, `homing.py` |
| **[DIV-07](BUG-DIV-07-flow-calibrator-zero-division.md)** | `flow_calibrator.py` | `509-512` | **HOCH** | Teilweise behoben (`flow_calibrator.py` geprueft) | Division by Zero in `flow_calibrator.py`, `purifier_factory.py`, `defect_detection.py`, `power_loss_check.py` |
| **[NULL-01](BUG-NULL-01.md)** | `inductance_coil.c` | `628-630` | **HOCH** | Offen | Unaligned 32-Bit Pointer Dereference in `src/stm32/inductance_coil.c` |
| **[NULL-02](BUG-NULL-02.md)** | `fatfs_api.c, sdiocmds.c, sdio.c` | `48-132, 205, 142-143` | **HOCH** | Offen | Null Pointer Dereference in `src/sdiocmds.c`, `src/stm32/sdio.c` & `scripts/spi_flash/fatfs_api.c` |
| **[NULL-04](BUG-NULL-04.md)** | `virtual_sdcard.py` | `830-831, 1843-1845` | **KRITISCH** | Offen | `NoneType`-Abstürze in `virtual_sdcard.py` (`restore_print` & `get_print_task_config`) |
| **[NULL-05](BUG-NULL-05.md)** | `timelapse.py, defect_detection.py` | `406, 428, 509, 552, 117` | **HOCH** | Offen | Fehlende Initialisierung von `self.mqtt_jsonrpc` in `defect_detection.py` & `None`-Dereferenzierung in `timelapse.py` |
| **[NULL-06](BUG-NULL-06.md)** | `klippy.py` | `277-282` | **HOCH** | Offen | Weitere `NoneType`-Dereferenzierungen in `klippy.py`, `extruder.py`, `bed_mesh.py`, `probe_inductance_coil.py`, `extruder_calibration.py`, `filament_feed.py`, `error_mcu.py`, `park_detector.py` |
| **[LEAK-02](BUG-LEAK-02.md)** | `power_loss_check.c` | `146-203` | **HOCH** | Offen | MCU-Flash bleibt bei Fehlern in `flash_write` dauerhaft entsperrt (`src/stm32/power_loss_check.c`) |
| **[LEAK-06](BUG-LEAK-06.md)** | `inductance_coil.py` | `82-98` | **HOCH** | Offen | Schweres Speicherleck & Zombie-Prozess in `FrequencyQueryHelper.write_to_file` (`inductance_coil.py`) |
| **[LEAK-07](BUG-LEAK-07-flow-calibrator-fifo-leak.md)** | `flow_calibrator.py` | `113-149` | **HOCH** | Behoben (Geprueft) | FIFO-File-Descriptor-Leak & 30s Main-Reactor-Freeze in `FlowCalcClient.calc_flow_factor` (`flow_calibrator.py`) |
| **[LEAK-08](BUG-LEAK-08.md)** | `fm175xx_reader.py, mqtt.py` | `217-237, 859-865, 47-49` | **HOCH** | Offen | GPIO-FD-Leak & Thread-Leak in `fm175xx_reader.py` sowie Thread-Leak in `mqtt.py` |
| **[LEAK-09](BUG-LEAK-09.md)** | `fatfs_api.c, console.c, util.py` | `217-232, 72-112, 71-97` | **MITTEL** | Offen | Verzeichnis-Handle-Leak (`f_closedir` fehlt) in `scripts/spi_flash/fatfs_api.c` & PTY-FD-Leak in `src/linux/console.c` / `klippy/util.py` |
| **[UAF-01](BUG-UAF-01.md)** | `power_loss_check.c` | `517-521, 672-684` | **KRITISCH** | Offen | Dangling Global Pointer `plc` nach `config_reset` & Aktive `TIM4_IRQHandler`-Speicherkorruption (`src/stm32/power_loss_check.c`) |
| **[UAF-02](BUG-UAF-02.md)** | `inductance_coil.c` | `72, 432-437, 665-673` | **HOCH** | Offen | Dangling Timer `config_freq_timer` & Aktiver Priority-0-IRQ bei Shutdown in `src/stm32/inductance_coil.c` |
| **[UAF-05](BUG-UAF-05.md)** | `fm175xx_reader.py` | `938-961` | **MITTEL** | Offen | Use-After-Close Race Condition beim Shutdown des RFID-Readers (`fm175xx_reader.py`) |
| **[STACK-02](BUG-STACK-02.md)** | `auto_screws_tilt_adjust.py` | `520-580` | **HOCH** | Offen | Unendliche Probing-Schleife in `cmd_AUTO_SCREWS_TILT_ADJUST_MANUAL_TUNING` (`auto_screws_tilt_adjust.py`) |
| **[STACK-04](BUG-STACK-04.md)** | `filament_detect.py` | `238-244` | **HOCH** | Offen | Endlosschleife `while (1):` in `cmd_FILAMENT_DT_SELF_TEST` (`filament_detect.py`) |
| **[STACK-05](BUG-STACK-05.md)** | `purifier.py` | `1158, 1188-1190` | **HOCH** | Offen | Defekter Timeout (`wait_timeout_time` wird jede Sekunde überschrieben) -> Endlosschleife in `cmd_WAIT_CHAMBER_TEMP` (`purifier.py`) |
| **[DEAD-01](BUG-DEAD-01.md)** | `sdio.c` | `307-318, 361-372` | **HOCH** | Offen | Unendliche Hardware-Polling-Loops ohne Timeout in MCU-Treibern (`sdio.c`, `at32f403a.c`, `at32f415rc.c`, `n32g45x_adc.c`, `spi.c`, `canserial.c`) |
| **[DEAD-02](BUG-DEAD-02.md)** | `filament_feed_fac_test.py, filament_feed.py` | `315-374, 776-789, 82-141` | **KRITISCH** | Offen | Permanenter Mutex-Deadlock auf `self._mutex_lock` und `self.channel_active` in `filament_feed.py` & `filament_feed_fac_test.py` |
| **[DEAD-03](BUG-DEAD-03.md)** | `machine_state_manager.py` | `269-299` | **KRITISCH** | Offen | Selbst-Deadlock auf nicht-reentrantem `ReactorMutex` in `machine_state_manager.py` |
| **[DEAD-04](BUG-DEAD-04-bed-mesh-abort-probe-deadlock.md)** | `bed_mesh.py` | `1258-1270` | **HOCH** | Behoben (Geprueft) | Deadlock-Risiko durch `gcode.run_script_from_command` innerhalb von `with self.lock:` in `bed_mesh.py` |
| **[RACE-01](BUG-RACE-01.md)** | `inductance_coil.c` | `168-237, 279-320, 458-518` | **HOCH** | Offen | Race Conditions zwischen Priority-0-ISR (`InputCapture_IRQHandler`), Timer-ISR und Task in `src/stm32/inductance_coil.c` |
| **[RACE-04](BUG-RACE-04.md)** | `exception_manager.py` | `54, 190-258, 300-305` | **HOCH** | Offen | TOCTOU Read-Modify-Write Datei-Race & Thread-Unsicherheit in `exception_manager.py` |
| **[RACE-07](BUG-RACE-07.md)** | `fm175xx_reader.py, heaters.py` | `201-205, 476-499, 964-1025` | **HOCH** | Offen | Fehlende Synchronisation in `cmd_SET_PID_PROFILE` (`heaters.py`) & RFID-Thread (`fm175xx_reader.py`) |
| **[EXC-03](BUG-EXC-03.md)** | `extruder.py` | `1456-1484, 1731-1748` | **HOCH** | Offen | `UnboundLocalError` (`message`, `probe_session`, `need_save`) & Leeres `raise` außerhalb von `except` |
| **[EXC-04](BUG-EXC-04-flow-calibrator-heater-cleanup.md)** | `extruder_calibration.py` | `196, 301-302` | **KRITISCH** | Teilweise behoben (`flow_calibrator.py` geprueft) | Fehlende `try ... finally:`-Wiederherstellung nach Probing / Kalibrierung (`extruder_calibration.py`, `probe.py`, `probe_inductance_coil.py`, `flow_calibrator.py`) |
| **[EXC-05](BUG-EXC-05.md)** | `inductance_coil.py` | `146-147` | **HOCH** | Offen | Unbehandelte `UnicodeDecodeError`, `ValueError`, `KeyError` & Verschlucktes `gcmd.error(e)` |
| **[LOG-01](BUG-LOG-01.md)** | `inductance_coil.c` | `128-132` | **KRITISCH** | Offen | Off-by-One-Bug in `get_sum()` löst Fehlauslösungen des Induktions-Z-Sensors aus (`src/stm32/inductance_coil.c`) |
| **[LOG-02](BUG-LOG-02.md)** | `queuefile.py` | `105-109` | **HOCH** | Offen | Unerreichbarer `elif os.path.isdir`-Zweig verhindert Verzeichnislöschung in `queuefile.py` |
| **[LOG-03](BUG-LOG-03.md)** | `print_task_config.py` | `223, 681-692, 750-759` | **KRITISCH** | Offen | 8-stellige RGBA-Farocodes zerstören `print_task.json` beim nächsten Neustart (`print_task_config.py`) |
| **[LOG-05](BUG-LOG-05.md)** | `extruder.py` | `1770-1776, 2065-2071, 2110-2116` | **HOCH** | Offen | Late-Binding-Closure-Bug (`i` ist immer `3`), fehlende `y_diff`-Prüfung in Park-Kalibrierung (`extruder.py`) |
| **[LOG-06](BUG-LOG-06.md)** | `homing_precise_corexy.py` | `282-303` | **KRITISCH** | Offen | Fehlerhafte Mittelwertbildung über Teilmenge (`/ 9`) in `homing_precise_corexy.py` |
| **[LOG-07](BUG-LOG-07.md)** | `probe_inductance_coil.py` | `50-86, 316-330, 1520` | **KRITISCH** | Offen | Kopierfehler `hole_z` mit Fallback `hole_x`, invertierte Determinantenformel & ungeschütztes `lstsq` in `probe_inductance_coil.py` |
| **[LOG-08](BUG-LOG-08.md)** | `filament_feed.py` | `137, 411-418, 1219-1222` | **MITTEL** | Offen | Vertauschte LED-Pins (`white_pin` / `red_pin`) und `max()` statt `min()` beim Ramp-Up in `filament_feed.py` |
| **[LOG-09](BUG-LOG-09-flow-calibrator-zero-k-and-logic.md)** | `flow_calibrator.py` | `260, 305-327, 478-491` | **HOCH** | Behoben (Geprueft) | Falsy-`0.0`-Bug löscht `flow_calibrator.json`, mutiert `DEFAULT_K` und liefert `None` in `flow_calibrator.py` |
| **[LOG-11](BUG-LOG-11-bed-mesh-substitute-points-index.md)** | `bed_mesh.py` | `1460-1462` | **MITTEL** | Behoben (Geprueft) | Fehlerhafte Index-Prüfung `sorted_sub_idx[idx] == idx` in `bed_mesh.py` |
| **[LOG-12](BUG-LOG-12.md)** | `defect_detection.py` | `942-961` | **HOCH** | Offen | Unbedingter Z-Move & Zurücksetzen auf `PRINTING` im `finally:`-Block nach Druckabbruch (`defect_detection.py`) |
| **[LOG-14](BUG-LOG-14.md)** | `extruder_calibration.py` | `79-85, 223-224` | **HOCH** | Offen | Konfigurations-Tippfehler & Fehlende Sektionspräfixe in `extruder_calibration.py`, `filament_entangle_detect.py`, `mqtt.py` |
