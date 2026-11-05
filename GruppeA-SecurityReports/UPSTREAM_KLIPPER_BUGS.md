# Upstream Klipper Core Bugs (Gruppe A)

Zentrale Übersicht aller Befunde der **Gruppe A (Upstream Klipper Core)** aus dem Referenzbericht `FEHLERBERICHT_U1_KLIPPER.md`.

## Statusübersicht & Metriken

- **Gesamtanzahl Befunde:** 38
- **Kritisch (KRITISCH):** 10
- **Hoch (HOCH):** 23
- **Mittel (MITTEL):** 5
- **Bearbeitungsstatus:** Alle Befunde initial erfasst (Status: Offen)

---

## Tabellarische Übersicht

| ID | Modul / Datei | Zeilen | Schweregrad | Status | Titel / Kurzbeschreibung |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **[SEC-05](BUG-SEC-05.md)** | `__init__.py` | `252-264, 304-318` | **HOCH** | Offen | Shell Command Injection & Unsichere `sudo`-Kompilierung in `chelper/__init__.py` |
| **[SEC-06](BUG-SEC-06.md)** | `webhooks.py` | `124-129, 247-249` | **HOCH** | Offen | Unbegrenztes Pufferwachstum (`partial_data` OOM-DoS) & Offene Unix-Socket-Berechtigungen in `webhooks.py` |
| **[BUF-02](BUG-BUF-02.md)** | `buttons.c` | `17, 49-53, 160-161` | **KRITISCH** | Offen | Schwerer Buffer Overflow (192 Bytes Out-of-Bounds Write im Timer-ISR) in `src/buttons.c` |
| **[BUF-03](BUG-BUF-03.md)** | `tmcuart.c` | `21, 77, 134-169` | **HOCH** | Offen | Out-of-Bounds Read & Write auf `m->data[10]` in `src/tmcuart.c` (ISR & Task) |
| **[BUF-04](BUG-BUF-04.md)** | `command.c, msgblock.c` | `85-98, 123-163, 89-119` | **HOCH** | Offen | Out-of-Bounds Buffer Read in `parse_int` & `command_parsef` (`src/command.c` & `klippy/chelper/msgblock.c`) |
| **[BUF-05](BUG-BUF-05.md)** | `serialqueue.c` | `307-318` | **KRITISCH** | Offen | Stack Over-Read & `input_buf` Buffer Overflow beim Lesen von CAN-Frames in `serialqueue.c` |
| **[BUF-06](BUG-BUF-06.md)** | `serialqueue.c` | `412-421` | **HOCH** | Offen | Ungeprüfter Stack-Buffer-Copy in `retransmit_event` (`serialqueue.c`) |
| **[BUF-07](BUG-BUF-07.md)** | `msgblock.c` | `136-143` | **HOCH** | Offen | Heap Buffer Overflow in `message_fill` (`msgblock.c`) |
| **[BUF-08](BUG-BUF-08.md)** | `mcu.py, stepcompress.c` | `755-775, 811-818, 822-829` | **HOCH** | Offen | Heap Out-of-Bounds Read/Write bei `move_num == 0` in `stepcompress.c` & Off-by-One in `mcu.py` |
| **[BUF-09](BUG-BUF-09.md)** | `i2c.c, hard_pwm.c, analog.c, gpio.c` | `48-65, 69-77, 25-30, 40-50` | **HOCH** | Offen | Out-of-Bounds Array-Zugriffe in Linux-MCU (`src/linux/i2c.c`, `gpio.c`, `analog.c`, `hard_pwm.c`) |
| **[INT-02](BUG-INT-02.md)** | `hard_pwm.c` | `294-302` | **HOCH** | Offen | Unerreichbares `else if` führt zu 16-Bit Prescaler-Truncation in `src/stm32/hard_pwm.c` |
| **[INT-05](BUG-INT-05.md)** | `i2c_software.c` | `48-58` | **HOCH** | Offen | Timer-Wraparound-Hänger & 32-Bit-Multiplikations-Overflow in `src/i2c_software.c` |
| **[INT-06](BUG-INT-06.md)** | `i2ccmds.c` | `86-114` | **MITTEL** | Offen | 8-Bit Längen-Truncation (`reg_len + data_len`) in `src/i2ccmds.c` |
| **[INT-07](BUG-INT-07.md)** | `sched.c` | `23, 295-309, 321-335` | **MITTEL** | Offen | 8-Bit Truncation der 16-Bit `static_string_id` in `src/sched.c` |
| **[INT-08](BUG-INT-08.md)** | `stepcompress.c` | `132-146, 161-163, 183-188` | **HOCH** | Offen | Signed 32-Bit Integer-Overflow (Undefined Behavior) in `compress_bisect_add` (`stepcompress.c`) |
| **[INT-09](BUG-INT-09.md)** | `basecmd.c` | `30-39` | **MITTEL** | Offen | Nicht-ausgerichtete Größenprüfung in `alloc_chunk` (`src/basecmd.c`) |
| **[DIV-02](BUG-DIV-02.md)** | `serialqueue.c` | `903-913` | **HOCH** | Offen | Division by Zero in `chelper` (`serialqueue.c`, `msgblock.c`, `stepcompress.c`, `kin_shaper.c`) |
| **[DIV-03](BUG-DIV-03.md)** | `virtual_sdcard.py` | `1323, 2040, 2142, 2166-2169, 2275` | **HOCH** | Offen | Fünf ungeschützte Division-by-Zero-Pfade in `virtual_sdcard.py` |
| **[DIV-08](BUG-DIV-08.md)** | `toolhead.py` | `757-786` | **HOCH** | Offen | Division by Zero in `toolhead.py`, `mcu.py`, `clocksync.py` und `stepper.py` |
| **[NULL-03](BUG-NULL-03.md)** | `serialqueue.c` | `458-476` | **KRITISCH** | Offen | Null Pointer Dereference (`SIGSEGV`) in `chelper` (`serialqueue.c`, `kin_shaper.c`, `kin_idex.c`, `pollreactor.c`, `stepcompress.c`) |
| **[LEAK-01](BUG-LEAK-01.md)** | `stepper.c` | `342-363` | **KRITISCH** | Offen | Move-Queue Memory Leak & Fehlende IRQ-Sperre in `get_all_stepper_info` (`src/stepper.c`) |
| **[LEAK-03](BUG-LEAK-03.md)** | `i2ccmds.c, i2c_software.c` | `25-39, 35-50` | **MITTEL** | Offen | Permanentes `alloc_chunk`-Speicherleck bei wiederholtem `i2c_set_software_bus` (`src/i2c_software.c` & `src/i2ccmds.c`) |
| **[LEAK-04](BUG-LEAK-04.md)** | `serialqueue.c` | `647-752` | **KRITISCH** | Offen | Pipe-FD-Leak, Mutex/Condvar-Leak & Unjoined-Thread in `serialqueue.c` |
| **[LEAK-05](BUG-LEAK-05.md)** | `kin_extruder.c` | `150-157` | **HOCH** | Offen | C-Heap Memory Leak in `extruder_set_pressure_advance` (`kin_extruder.c`) |
| **[UAF-03](BUG-UAF-03.md)** | `serialqueue.c` | `635-643, 728-752` | **KRITISCH** | Offen | Use-After-Free in `serialqueue_free` bei gleichzeitigem Thread-Exit (`serialqueue.c`) |
| **[UAF-04](BUG-UAF-04.md)** | `trdispatch.c, mcu.py` | `132-210, 174-177` | **HOCH** | Offen | Dangling Pointers (`tdm->node` & `tdm->fr`) bei Freigabe via `ffi_lib.free` (`trdispatch.c` & `mcu.py`) |
| **[STACK-01](BUG-STACK-01.md)** | `i2ccmds.c` | `74, 99` | **HOCH** | Offen | Ungeprüfte Variable Length Arrays (VLA) auf dem MCU-Stack in `src/i2ccmds.c` |
| **[STACK-03](BUG-STACK-03.md)** | `heaters.py` | `733-739` | **HOCH** | Offen | Endlosschleife in `PrinterHeaters.set_temperature` bei Shutdown während Queue-Wait (`heaters.py`) |
| **[STACK-06](BUG-STACK-06.md)** | `asyncfilereader.py` | `368` | **MITTEL** | Offen | Endlosschleife bei zyklischen Symlinks in `AsyncFileReader._do_listdir` (`asyncfilereader.py`) |
| **[RACE-02](BUG-RACE-02.md)** | `gcode.py` | `10, 201-250` | **KRITISCH** | Offen | Fehlerhaftes `threading.local()` statt Greenlet-Local State in `GCodeDispatch._process_commands` (`gcode.py`) |
| **[RACE-03](BUG-RACE-03.md)** | `webhooks.py` | `504-583` | **KRITISCH** | Offen | Reentrancy-Crash (`KeyError` / `ValueError`) in `QueryStatusHelper._do_query` (`webhooks.py`) |
| **[RACE-05](BUG-RACE-05.md)** | `mqtt.py, jsonrpc.py` | `79-82, 110-118, 122-127` | **HOCH** | Offen | Thread-Safety-Verletzungen & `RuntimeError` im Paho-MQTT-Hintergrundthread (`mqtt.py` & `jsonrpc.py`) |
| **[RACE-06](BUG-RACE-06.md)** | `asyncfilereader.py` | `290-307, 330-345` | **HOCH** | Offen | Unsynchronisierter Zugriff auf `self._gcode` & Überschreiben aktiver Leser in `asyncfilereader.py` |
| **[EXC-01](BUG-EXC-01.md)** | `reactor.py` | `269, 344-357, 366-409` | **KRITISCH** | Offen | `KeyError`-Crash im Haupt-Reactor bei Client-Disconnect unter Schreibblockade + `SelectReactor` / `EPollReactor` Crashes (`reactor.py`) |
| **[EXC-02](BUG-EXC-02.md)** | `pollreactor.c` | `136-148` | **KRITISCH** | Offen | `EINTR` beendet permanent den C-Hintergrundthread in `pollreactor.c` |
| **[LOG-04](BUG-LOG-04.md)** | `jsonrpc.py` | `105-113` | **HOCH** | Offen | `self.pending_requests.pop(0)` wirft immer `KeyError: 0` und löscht alle 100 offenen RPC-Requests (`jsonrpc.py`) |
| **[LOG-10](BUG-LOG-10.md)** | `virtual_sdcard.py` | `1606-1616, 2246-2264` | **HOCH** | Offen | `EXCLUDE_OBJECT`-Crash & Toter Code sowie falsche Z-Stepper-Annahme in `virtual_sdcard.py` |
| **[LOG-13](BUG-LOG-13.md)** | `klippy.py` | `581` | **HOCH** | Offen | Korrupte Fehlercode-Formatierung in `klippy.py`, `serialhdl.py`, `homing.py` und `"serial: None"` in `printer_device_scan.py` |
