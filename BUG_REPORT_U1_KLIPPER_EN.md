# Comprehensive Systematic Bug & Security Audit Report: `u1-klipper-main`

**Project:** Snapmaker U1 Klipper Firmware & Host Software (`u1-klipper-main`)  
**Methodology:** `/systematic-debugging` (Full static & logical code analysis across all subsystems: MCU C firmware `src/`, Host C extension `klippy/chelper/`, Klippy Core `klippy/`, Kinematics & Probing `klippy/kinematics/` & `klippy/extras/`, and utility scripts `scripts/`)  
**Audited Defect Categories:**
1. Zero-Day & Security Vulnerabilities (Path Traversal, Arbitrary File Write/Delete, Command Injection, Unauthenticated IPC)
2. Buffer Overflows & Out-of-Bounds Memory Access (Stack/Heap/BSS Buffer Overflows, Array/List OOB)
3. Integer Overflows, Underflows, Truncation & Signedness Bugs
4. Division by Zero (Hardware division faults in C & `ZeroDivisionError` in Python)
5. Null Pointer Dereference / Segfaults / Unaligned Memory Access / `NoneType` Exceptions
6. Memory & Resource Leaks (Heap Memory Leaks, `alloc_chunk` Leaks, Move Queue Leaks, File Descriptor Leaks, Flash Lock Leaks, Zombie Processes)
7. Dangling Pointers & Use-After-Free / Use-After-Close
8. Stack Overflows (Variable Length Arrays on MCU stack, Infinite Loops)
9. Deadlocks & Infinite Hardware Polling Loops Without Timeout
10. Race Conditions (ISR vs. Main Loop, Paho MQTT Thread vs. Reactor, RFID Thread vs. Reactor, Greenlet Re-entrancy, Async File TOCTOU)
11. Unhandled Exceptions, Swallowed Exceptions & Faulty Exception Handlers
12. Logical Bugs (Off-by-One, Copy-Paste Bugs, Late-Binding Closures, Flawed Calibration Math, Persistent Configuration Corruption)

---

## Table of Contents & Summary by Defect Category

| No. | Defect Category | Verified Findings | Highest Severity | Primary Affected Modules |
| :--- | :--- | :---: | :---: | :--- |
| **1** | **Zero-Day & Security Vulnerabilities** | 6 | **CRITICAL** | `bed_mesh.py`, `probe_inductance_coil.py`, `flow_calibrator.py`, `chelper/__init__.py`, `webhooks.py` |
| **2** | **Buffer Overflows & Out-of-Bounds** | 12 | **CRITICAL** | `sdiocmds.c`, `buttons.c`, `tmcuart.c`, `command.c`, `serialqueue.c`, `msgblock.c`, `stepcompress.c`, `linux/i2c.c`, `linux/gpio.c`, `extruder.py`, `print_task_config.py` |
| **3** | **Integer Overflows / Underflows / Truncation** | 9 | **HIGH** | `sdiocmds.c`, `sdio.c`, `inductance_coil.c`, `hard_pwm.c`, `power_loss_check.c`, `i2c_software.c`, `i2ccmds.c`, `sched.c`, `stepcompress.c` |
| **4** | **Division by Zero** | 16 | **CRITICAL** | `sdio.c`, `inductance_coil.c`, `serialqueue.c`, `msgblock.c`, `stepcompress.c`, `kin_shaper.c`, `virtual_sdcard.py`, `bed_mesh.py`, `inductance_coil.py`, `homing_precise_corexy.py`, `homing_xyz_override.py`, `auto_screws_tilt_adjust.py`, `flow_calibrator.py`, `purifier_factory.py`, `defect_detection.py`, `power_loss_check.py`, `toolhead.py`, `mcu.py`, `clocksync.py`, `stepper.py` |
| **5** | **Null Pointer / Segfault / Unaligned / `NoneType`** | 15 | **CRITICAL** | `sdiocmds.c`, `sdio.c`, `inductance_coil.c`, `fatfs_api.c`, `serialqueue.c`, `kin_shaper.c`, `kin_idex.c`, `pollreactor.c`, `virtual_sdcard.py`, `extruder.py`, `bed_mesh.py`, `probe_inductance_coil.py`, `filament_feed.py`, `defect_detection.py`, `klippy.py`, `error_mcu.py`, `park_detector.py`, `timelapse.py` |
| **6** | **Memory, FD, Lock & Process Leaks** | 10 | **HIGH** | `stepper.c`, `power_loss_check.c`, `i2c_software.c`, `fatfs_api.c`, `linux/console.c`, `serialqueue.c`, `kin_extruder.c`, `inductance_coil.py`, `flow_calibrator.py`, `fm175xx_reader.py`, `mqtt.py` |
| **7** | **Dangling Pointers & Use-After-Free** | 5 | **CRITICAL** | `power_loss_check.c`, `inductance_coil.c`, `serialqueue.c`, `trdispatch.c`, `fm175xx_reader.py` |
| **8** | **Stack Overflows & Infinite Loops** | 6 | **HIGH** | `i2ccmds.c`, `auto_screws_tilt_adjust.py`, `heaters.py`, `filament_detect.py`, `purifier.py`, `asyncfilereader.py` |
| **9** | **Deadlocks & Hardware Polling Loops** | 9 | **CRITICAL** | `sdio.c`, `at32f403a.c`, `at32f415rc.c`, `n32g45x_adc.c`, `spi.c`, `canserial.c`, `filament_feed.py`, `filament_feed_fac_test.py`, `machine_state_manager.py`, `bed_mesh.py`, `flow_calibrator.py` |
| **10** | **Race Conditions & Concurrency Defects** | 11 | **CRITICAL** | `inductance_coil.c`, `power_loss_check.c`, `stepper.c`, `asyncfilereader.py`, `exception_manager.py`, `webhooks.py`, `gcode.py`, `heaters.py`, `fm175xx_reader.py`, `jsonrpc.py`, `mqtt.py` |
| **11** | **Unhandled / Swallowed Exceptions** | 10 | **HIGH** | `reactor.py`, `extruder.py`, `probe_inductance_coil.py`, `probe.py`, `extruder_calibration.py`, `filament_parameters.py`, `filament_protocol.py`, `configfile.py`, `inductance_coil.py` |
| **12** | **Logical Bugs & State Corruption** | 14 | **CRITICAL** | `inductance_coil.c`, `queuefile.py`, `extruder.py`, `virtual_sdcard.py`, `bed_mesh.py`, `probe_inductance_coil.py`, `homing_precise_corexy.py`, `filament_feed.py`, `print_task_config.py`, `flow_calibrator.py`, `defect_detection.py`, `jsonrpc.py` |

---

## 1. Zero-Day & Security Vulnerabilities

### [SEC-01] Path Traversal & Arbitrary `.json` File Overwrite/Deletion in `ProfileManager` (`bed_mesh.py`)
- **File & Lines:** [bed_mesh.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/bed_mesh.py#L2110-L2194)
- **Severity:** CRITICAL (Zero-Day / Arbitrary File Overwrite & Delete)
- **Root Cause Analysis:**
  In `ProfileManager.save_profile(prof_name)`, `load_profile(prof_name)`, and `remove_profile(prof_name)`, the user-supplied G-code parameter `prof_name` (`BED_MESH_PROFILE SAVE=... LOAD=... REMOVE=...`) is passed directly into `os.path.join(self.profiles_dir, prof_name + ".json")` without sanitizing path separators (`/` or `..`). Because `os.path.join("/path/bed_mesh", "../../printer_data/config/print_task")` resolves outside `self.profiles_dir`, any `.json` file on the filesystem can be overwritten, read, or deleted via `REMOVE=../../...` from G-code or a macro.
- **Affected Code:**
  ```python
  # klippy/extras/bed_mesh.py:2131-2135 & 2178-2185
  profile_path = os.path.join(self.profiles_dir, prof_name + ".json")
  ...
  if os.path.exists(profile_path):
      os.remove(profile_path)
  ```
- **Remediation (Defensive Fix):**
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

### [SEC-02] Arbitrary System File Overwrite via `BED_MESH_OUTPUT_FILE` (`bed_mesh.py`)
- **File & Lines:** [bed_mesh.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/bed_mesh.py#L304-L313)
- **Severity:** HIGH (Arbitrary File Write)
- **Root Cause Analysis:**
  `cmd_BED_MESH_OUTPUT_FILE` reads `FILE_PATH` directly from the G-code command (`gcmd.get('FILE_PATH', ...)`), creates arbitrary parent directories (`os.makedirs(os.path.dirname(file_path), exist_ok=True)`), and overwrites the target file in `'w'` mode. Furthermore, `os.makedirs("")` raises `FileNotFoundError` if a bare filename without a directory component is passed.
- **Affected Code:**
  ```python
  file_path = gcmd.get('FILE_PATH', os.path.join(config_dir, 'bed_mesh.json'))
  os.makedirs(os.path.dirname(file_path), exist_ok=True)
  with open(file_path, 'w') as f:
      f.write(status_json)
  ```
- **Remediation (Defensive Fix):**
  Restrict the destination path strictly to the configuration or log directory using `os.path.realpath()` and `os.path.commonpath()`.

---

### [SEC-03] Path Traversal / Arbitrary File Append via `LOG_FILE` in `probe_inductance_coil.py`
- **File & Lines:** [probe_inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/probe_inductance_coil.py#L728), [probe_inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/probe_inductance_coil.py#L999-L1010)
- **Severity:** HIGH (Path Traversal / Arbitrary File Append)
- **Root Cause Analysis:**
  In `cmd_CARTOGRAPHER_CALIBRATE` and `cmd_INDUCTANCE_COIL_PROBE_ACCURACY`, the G-code parameter `LOG_FILE` is passed directly to `open(log_file, 'a', ...)` and `queuefile.async_append_file(log_file, ...)` without path validation.
- **Remediation (Defensive Fix):**
  Allow only `os.path.basename(log_file)` inside a dedicated log directory.

---

### [SEC-04] Path Traversal & Unvalidated File Path via `AXIS` in `flow_calibrator.py`
- **File & Lines:** [flow_calibrator.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/flow_calibrator.py#L231-L241), [flow_calibrator.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/flow_calibrator.py#L1194-L1215)
- **Severity:** HIGH (Path Traversal & File Descriptor Leak)
- **Root Cause Analysis:**
  In `cmd_ACCEL_TIME_MEASURE`, `axis = gcmd.get("AXIS", None)` is not validated against `('x', 'y')` and is interpolated directly into `filename = f"/tmp/accel_time_measure_{axis}.csv"`. If `AXIS` contains traversal sequences such as `../../root/...`, files outside `/tmp` are overwritten. Additionally, in `AccelTimeQueryHelper.write_to_file()`, the file handle `f = open(self.filename, "w")` is opened without a `with` statement and is never closed via `f.close()`.
- **Remediation (Defensive Fix):**
  Validate `if axis not in ('x', 'y'): raise gcmd.error("Invalid AXIS")` and use `with open(self.filename, "w") as f:`.

---

### [SEC-05] Shell Command Injection & Unsafe `sudo` Compilation in `chelper/__init__.py`
- **File & Lines:** [__init__.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/__init__.py#L252-L264), [__init__.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/__init__.py#L304-L318)
- **Severity:** HIGH (Command Injection / Privilege Escalation)
- **Root Cause Analysis:**
  `do_build_code()`, `check_gcc_option()`, and `run_hub_ctrl()` interpolate unquoted file paths (`destlib`, `srcfiles`, `hubdir`) into command strings passed to `os.system()`. If the path contains spaces (such as `e:\KI Projekte\u1-klipper-main`) or shell metacharacters, the command fails or executes injected shell commands. Furthermore, `run_hub_ctrl()` compiles a binary at runtime as an unprivileged user and immediately executes it via `sudo %s/hub-ctrl`.
- **Affected Code:**
  ```python
  def run_hub_ctrl(enable_power):
      ...
      if check_build_code(srcfiles, destlib):
          do_build_code(HC_COMPILE_CMD % (destlib, ' '.join(srcfiles)))
      os.system(HC_CMD % (hubdir, enable_power))
  ```
- **Remediation (Defensive Fix):**
  Replace all `os.system()` calls with `subprocess.run([GCC_CMD, ...], check=True, shell=False)` using argument lists.

---

### [SEC-06] Unbounded Receive Buffer Growth (`partial_data` OOM DoS) & Permissive Unix Socket Creation in `webhooks.py`
- **File & Lines:** [webhooks.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/webhooks.py#L124-L129), [webhooks.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/webhooks.py#L247-L249)
- **Severity:** MEDIUM to HIGH (Denial of Service / Unauthorized Local IPC Access)
- **Root Cause Analysis:**
  1. `ClientConnection.process_received()` appends incoming bytes indefinitely to `self.partial_data += data` as long as no `\x03` frame terminator byte is sent, leading to an Out-of-Memory crash.
  2. `ServerSocket` does not set restrictive file permissions (`0o660`) when binding the Unix domain socket, and `_remove_socket_file()` deletes the target path via `os.remove()` without first verifying that it is a socket (`stat.S_ISSOCK()`).
- **Remediation (Defensive Fix):**
  Enforce a maximum buffer size on `self.partial_data` (e.g., 10 MiB) and restrict Unix socket permissions after `bind()` via `os.chmod(server_address, 0o660)`.

---

## 2. Buffer Overflows & Out-of-Bounds Memory Access

### [BUF-01] 32-Bit Integer Overflow Bypasses Bounds Check -> Arbitrary Out-of-Bounds Write/Read in `src/sdiocmds.c`
- **File & Lines:** [sdiocmds.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/sdiocmds.c#L135-L164)
- **Severity:** CRITICAL (Arbitrary Memory Write / Buffer Overflow on MCU)
- **Root Cause Analysis:**
  In `command_sdio_read_data_buffer` and `command_sdio_write_data_buffer`, `offset` is a `uint32_t` (`args[1]`) and `len` / `write_data_len` is a `uint8_t` (`args[2]`).
  1. When `offset >= 0xFFFFFFFFU - write_data_len + 1` (e.g., `offset = 0xFFFFFFF0`, `write_data_len = 32`), the 32-bit unsigned addition `offset + write_data_len` wraps around to `16`. The bounds check `if (offset + write_data_len <= sizeof(sdio->data_buffer))` (`16 <= 4096`) is **bypassed**! Consequently, `memcpy(buf, write_data, write_data_len)` writes to `sdio->data_buffer - 16`, overwriting the struct fields preceding `data_buffer` (including the hardware peripheral pointer `sdio->sdio_config.sdio`!).
  2. In addition, the pointer `uint8_t *buf = &(sdio->data_buffer[offset]);` is constructed **before** the bounds check (Undefined Behavior in C).
- **Affected Code:**
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
- **Remediation (Defensive Fix):**
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

### [BUF-02] Severe Buffer Overflow (192-Byte Out-of-Bounds Write in Timer ISR) in `src/buttons.c`
- **File & Lines:** [buttons.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/buttons.c#L17), [buttons.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/buttons.c#L49-L53), [buttons.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/buttons.c#L160-L161)
- **Severity:** CRITICAL (ISR Buffer Overflow / Heap Pool Corruption)
- **Root Cause Analysis:**
  In this firmware fork, `reports[16]` in `struct buttons` was widened from `uint8_t` to `uint32_t reports[16]` (to support up to 32 buttons). However, line 49 (inside the timer ISR `buttons_event`) still checks `if (b->report_count < sizeof(b->reports))`!
  Because `sizeof(b->reports)` is now `64` bytes while the array only has `16` elements (`0..15`), `b->reports[b->report_count++] = b->pressed;` for `report_count = 16..63` writes up to **48 `uint32_t` values (192 bytes) past the end of `b->reports`**, overwriting `report_count`, `ack_count`, `button_count`, `pins[]`, and neighboring objects in `dynmem_pool`!
  Additionally, line 160 passes `report_count` instead of `report_count * sizeof(b->reports[0])` as the byte length to `%*s`.
- **Affected Code:**
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
- **Remediation (Defensive Fix):**
  ```c
      if (b->report_count < ARRAY_SIZE(b->reports)) {
          b->reports[b->report_count++] = b->pressed;
  ```
  And in `buttons_task()` (line 160):
  ```c
      sendf("buttons_state oid=%c ack_count=%c state=%*s"
            , oid, b->ack_count, report_count * sizeof(b->reports[0]), b->reports);
  ```

---

### [BUF-03] Out-of-Bounds Read & Write on `m->data[10]` in `src/tmcuart.c` (ISR & Task)
- **File & Lines:** [tmcuart.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/tmcuart.c#L21), [tmcuart.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/tmcuart.c#L77), [tmcuart.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/tmcuart.c#L134-L169)
- **Severity:** HIGH (ISR Buffer Overflow)
- **Root Cause Analysis:**
  Each UART byte is framed with start and stop bits as a **10-bit word** stored in `uint8_t data[10]` (80 bits = at most **8 bytes**). However, line 139 checks `if (write > ARRAY_SIZE(m->data) || read > ARRAY_SIZE(m->data))` (`> 10` instead of `> 8`). When `write = 9` or `10` or `read = 9` or `10`, `pos` reaches up to `99`, causing `m->data[(pos >> 3) + 1]` to read and write `m->data[10..12]` out-of-bounds.
- **Remediation (Defensive Fix):**
  ```c
  if (write > (ARRAY_SIZE(m->data) * 8) / 10
      || read > (ARRAY_SIZE(m->data) * 8) / 10)
      shutdown("tmcuart data too large");
  ```

---

### [BUF-04] Out-of-Bounds Buffer Read in `parse_int` & `command_parsef` (`src/command.c` & `klippy/chelper/msgblock.c`)
- **File & Lines:** [command.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/command.c#L85-L98), [command.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/command.c#L123-L163), [msgblock.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/msgblock.c#L89-L119)
- **Severity:** HIGH (Out-of-Bounds Read)
- **Root Cause Analysis:**
  1. In `command_parsef()` (`src/command.c:129`), the loop checks `if (p > maxend)` instead of `if (p >= maxend)`. When `p == maxend`, `parse_int(&p)` or `uint_fast8_t len = *p++;` reads past `maxend`.
  2. In `parse_int()` (both in `src/command.c` and `klippy/chelper/msgblock.c`), the loop `while (c & 0x80) { c = *p++; ... }` has no upper bound check against `maxend`/`end`, allowing a malformed VLQ field with the continuation bit (`0x80`) set to read past the end of the buffer.
- **Remediation (Defensive Fix):**
  Pass `maxend`/`end` to `parse_int(uint8_t **pp, uint8_t *end)`, and check `if (p >= maxend) goto error;` and `if (len > (size_t)(maxend - p)) goto error;` in `command_parsef`.

---

### [BUF-05] Stack Over-Read & `input_buf` Buffer Overflow on CAN Frame Read in `serialqueue.c`
- **File & Lines:** [serialqueue.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/serialqueue.c#L307-L318)
- **Severity:** CRITICAL (Stack Over-Read & Buffer Overflow in C)
- **Root Cause Analysis:**
  In `input_event()`, the `SQT_CAN` branch checks neither `ret == sizeof(cf)` (protecting against partial reads / uninitialized stack memory), nor `cf.can_dlc <= 8`, nor `sq->input_pos + cf.can_dlc <= sizeof(sq->input_buf)` (`4096`).
- **Affected Code:**
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
- **Remediation (Defensive Fix):**
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

### [BUF-06] Unchecked Stack Buffer Copy in `retransmit_event` (`serialqueue.c`)
- **File & Lines:** [serialqueue.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/serialqueue.c#L412-L421)
- **Severity:** HIGH (Stack Buffer Overflow)
- **Root Cause Analysis:**
  `retransmit_event()` copies all messages in `sq->sent_queue` into a fixed-size stack buffer `uint8_t buf[MESSAGE_MAX * MAX_PENDING_BLOCKS + 1]` without checking whether `buflen + qm->len <= sizeof(buf)`.
- **Remediation (Defensive Fix):**
  Check `if (qm->len < 0 || buflen + qm->len > (int)sizeof(buf)) break;` before `memcpy`.

---

### [BUF-07] Heap Buffer Overflow in `message_fill` (`msgblock.c`)
- **File & Lines:** [msgblock.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/msgblock.c#L136-L143)
- **Severity:** HIGH (Heap Buffer Overflow)
- **Root Cause Analysis:**
  `message_fill(uint8_t *data, int len)` copies `len` bytes via `memcpy(qm->msg, data, len)` into the 64-byte array `qm->msg[MESSAGE_MAX]` without validating `len >= 0 && len <= MESSAGE_MAX`.
- **Remediation (Defensive Fix):**
  Add `if (len < 0 || len > MESSAGE_MAX) { errorf("Invalid length"); len = 0; }` before `memcpy`.

---

### [BUF-08] Heap Out-of-Bounds Read/Write When `move_num == 0` in `stepcompress.c` & Off-by-One in `mcu.py`
- **File & Lines:** [stepcompress.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/stepcompress.c#L755-L775), [stepcompress.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/stepcompress.c#L811-L818), [mcu.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/mcu.py#L822-L829)
- **Severity:** HIGH (Heap Out-of-Bounds Read/Write)
- **Root Cause Analysis:**
  In `mcu.py:823`, only `if move_count < self._reserved_move_slots:` is checked. When `move_count == self._reserved_move_slots`, `steppersync_alloc` is called with `move_num = 0` (`ss->move_clocks = malloc(0)`). Subsequently, `steppersync_flush()` reads `ss->move_clocks[0]` at line 811 and `heap_replace()` writes `mc[0] = req_clock` at line 765 out-of-bounds on the 0-byte heap buffer.
- **Remediation (Defensive Fix):**
  Change `mcu.py:823` to `if move_count <= self._reserved_move_slots:` and check `if (ss->num_move_clocks <= 0) return ERROR_RET;` in `stepcompress.c:811`.

---

### [BUF-09] Out-of-Bounds Array Accesses in Linux MCU (`src/linux/i2c.c`, `gpio.c`, `analog.c`, `hard_pwm.c`)
- **File & Lines:** [i2c.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/linux/i2c.c#L48-L65), [gpio.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/linux/gpio.c#L69-L77), [analog.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/linux/analog.c#L25-L30), [hard_pwm.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/linux/hard_pwm.c#L40-L50)
- **Severity:** MEDIUM to HIGH (Out-of-Bounds Read/Write & Uninitialized Variable)
- **Root Cause Analysis:**
  1. `src/linux/i2c.c`: Does not check `if (devices_count >= ARRAY_SIZE(devices))` before writing to `devices[devices_count]`, and ignores the return value of `ioctl(fd, I2C_FUNCS, &i2c_funcs)` with an uninitialized `i2c_funcs` variable.
  2. `src/linux/gpio.c`: Does not check `if (pin >= ARRAY_SIZE(gpio_lines))` before indexing `&gpio_lines[pin]`.
- **Remediation (Defensive Fix):**
  Add bounds checks against `ARRAY_SIZE(devices)` and `ARRAY_SIZE(gpio_lines)` and initialize `unsigned long i2c_funcs = 0;`.

---

### [BUF-10] Out-of-Bounds `IndexError` on `unknown[0]` and `filament_vendor[extruder_index]` in `extruder.py`
- **File & Lines:** [extruder.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/kinematics/extruder.py#L1163-L1168), [extruder.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/kinematics/extruder.py#L1259-L1265), [extruder.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/kinematics/extruder.py#L1451-L1453), [extruder.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/kinematics/extruder.py#L1728-L1729)
- **Severity:** HIGH (Crash during toolchange / park check)
- **Root Cause Analysis:**
  1. In `_check_extruder_park_status()` (lines 1451 & 1728), the `else` branch indexes `unknown[0]` without checking whether `unknown` is non-empty (`len(picked) > 1` and `len(unknown) == 0` immediately raises `IndexError: list index out of range`).
  2. In `compression_fila()` and `flush_fila()` (lines 1165 & 1261), `print_task_config.get_status()['filament_vendor'][self.active_extruder_index]` is indexed without bounds checking.
- **Remediation (Defensive Fix):**
  Always check `if unknown:` and `0 <= idx < len(vendors)` before indexing lists.

---

### [BUF-11] Out-of-Bounds List Indexing in `print_task_config.py`
- **File & Lines:** [print_task_config.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/print_task_config.py#L826-L836), [print_task_config.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/print_task_config.py#L1175), [print_task_config.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/print_task_config.py#L1399-L1405)
- **Severity:** MEDIUM to HIGH (`IndexError`)
- **Root Cause Analysis:**
  1. `cmd_SET_PRINT_USED_EXTRUDERS` does not validate `0 <= e < self.extruder_nums` before setting `self.print_task_config['extruder_used'][e] = True`.
  2. `cmd_SET_PRINT_FILAMENT_CONFIG` and `cmd_SET_EXTRUDER_FILAMENT_CALI_PARAM` only check `extruder >= self.extruder_nums`, allowing negative indices (`extruder < 0`).
  3. Line 1405 hardcodes index `0` in `tmp_print_task_config_2['nozzle_diameter'][0]` instead of `[i]`.
- **Remediation (Defensive Fix):**
  Validate all extruder indices strictly with `0 <= idx < self.extruder_nums` and use `[i]` at line 1405.

---

### [BUF-12] Off-by-One Channel Check & Unchecked `recv_buff[0]` in `fm175xx_reader.py` & `sc7a20.py`
- **File & Lines:** [fm175xx_reader.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/fm175xx_reader.py#L808), [fm175xx_reader.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/fm175xx_reader.py#L1037), [sc7a20.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/sc7a20.py#L85-L88)
- **Severity:** MEDIUM (`IndexError` on SPI communication glitch)
- **Root Cause Analysis:**
  - `fm175xx_reader.py:1037` checks `if channel < 0 or channel > FM175XX_CHANNEL_NUMS:` (`> 4` instead of `>= 4`), so `channel == 4` raises `IndexError`.
  - `fm175xx_reader.py:808` (`recv_buff[0]`) and `sc7a20.py:86` (`response[1]`) index SPI response arrays without checking their length.
- **Remediation (Defensive Fix):**
  Check `channel >= FM175XX_CHANNEL_NUMS` and `if not recv_buff:` / `if len(response) < 2:`.

---

## 3. Integer Overflows, Underflows, Truncation & Signedness Bugs

### [INT-01] 32-Bit Integer Overflow in SDIO Timeout Calculation & `uint8_t` Underflow in `sdio.c` / `sdiocmds.c`
- **File & Lines:** [sdiocmds.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/sdiocmds.c#L82), [sdiocmds.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/sdiocmds.c#L112), [sdio.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/sdio.c#L408)
- **Severity:** HIGH (Failed SDIO transfers & wrong clock frequency)
- **Root Cause Analysis:**
  1. In `sdiocmds.c` (lines 82, 112), `uint32_t timeout = TIMEOUT_MSEC * sdio->speed / 1000;` (`TIMEOUT_MSEC = 500`) is computed using 32-bit arithmetic. Whenever `sdio->speed >= 8,589,935` Hz (~8.59 MHz; standard SD cards operate at 24–48 MHz!), `500 * sdio->speed` overflows `UINT32_MAX`, resulting in a severely truncated hardware `DTIMER` timeout.
  2. In `sdio.c:408` (`uint8_t clkdiv = (SDIO_CLK_FREQ / speed) - 2;`), any `speed > 24000000` (`SDIO_CLK_FREQ = 48000000`) **underflows** `uint8_t` to `254` or `255` (setting the slowest possible clock instead of maximum speed!), whereas `speed < 186771` is truncated when cast to `uint8_t`.
- **Remediation (Defensive Fix):**
  ```c
  // src/sdiocmds.c:
  uint32_t timeout = (uint32_t)((uint64_t)TIMEOUT_MSEC * sdio->speed / 1000);

  // src/stm32/sdio.c:
  if (speed == 0) shutdown("Invalid SDIO speed");
  uint32_t div = SDIO_CLK_FREQ / speed;
  uint8_t clkdiv = (div <= 2) ? 0 : ((div - 2 > 255) ? 255 : (uint8_t)(div - 2));
  ```

---

### [INT-02] Unreachable `else if` Causes 16-Bit Prescaler Truncation in `src/stm32/hard_pwm.c`
- **File & Lines:** [hard_pwm.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/hard_pwm.c#L294-L302)
- **Severity:** HIGH (Corrupted hardware PWM frequency)
- **Root Cause Analysis:**
  The 16-bit overflow guard `else if (prescaler > UINT16_MAX)` is placed in the `else` branch of `if (prescaler > 0)`. Because `prescaler > UINT16_MAX` necessarily implies `prescaler > 0`, the `else if` branch is **dead code** and is never reached! When `prescaler > 65536`, `(uint16_t)prescaler` silently truncates the upper 16 bits.
- **Affected Code:**
  ```c
  uint32_t prescaler = cycle_time / (pclock_div * (MAX_PWM - 1));
  if (prescaler > 0) {
      prescaler -= 1;
  } else if (prescaler > UINT16_MAX) {
      prescaler = UINT16_MAX;
  }
  p->timer->PSC = (uint16_t) prescaler;
  ```
- **Remediation (Defensive Fix):**
  ```c
  if (prescaler > 0) {
      prescaler -= 1;
  }
  if (prescaler > UINT16_MAX) {
      prescaler = UINT16_MAX;
  }
  ```

---

### [INT-03] Tautological Bounds Check, `MOVING_SUM` 32-Bit Overflow & Signed Overflow in `src/stm32/inductance_coil.c`
- **File & Lines:** [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L45), [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L104-L117), [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L328-L357), [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L471-L479)
- **Severity:** HIGH (False Z-Trigger / Undefined Behavior)
- **Root Cause Analysis:**
  1. `if (tmp_pr_value > INPUT_CAPTURE_CAL_CRM_TIM_MAX_PR_VALUE)` compares `uint32_t tmp_pr_value` against `0xFFFFFFFFU` — this condition is **tautologically false**. If the `double` macro `INPUT_CAPTURE_CAL_CRM_TIM_PR(...)` exceeds `4294967295.0` or is negative, casting to `uint32_t` invokes Undefined Behavior.
  2. `MOVING_SUM.sum` is `uint32_t` and accumulates up to `50` 32-bit timer values (`value`), which can overflow 32 bits for longer periods.
  3. In `update_trigger_frequencies()` (line 471), `freq_param.trg_freq_ht + (int)cur_freq` can trigger signed 32-bit integer overflow.
- **Remediation (Defensive Fix):**
  Validate the `double` value against `(double)0xFFFFFFFFU` before casting to `uint32_t`, widen `MOVING_SUM.sum` to `uint64_t`, and perform the frequency offset addition in `int64_t`.

---

### [INT-04] 16-Bit Timer Underflow & `uint32_t` Overflow of `power_loss_trigger_time` (`power_loss_check.c` & `power_loss_check.py`)
- **File & Lines:** [power_loss_check.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/power_loss_check.c#L492-L493), [power_loss_check.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/power_loss_check.py#L30-L32), [power_loss_check.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/power_loss_check.py#L89-L92)
- **Severity:** MEDIUM to HIGH (Faulty brown-out detection)
- **Root Cause Analysis:**
  In `power_loss_check.c:492`, `(uint16_t)(TRM_OVER_FREQ * plc->power_loss_trigger_time - 1)` underflows to `0xFFFF` when `power_loss_trigger_time == 0` and truncates values `> 6.5536 s` (`TRM_OVER_FREQ = 10000`) to 16 bits. In `power_loss_check.py:89`, `power_loss_trigger_time` is loaded from JSON without range validation.
- **Remediation (Defensive Fix):**
  Clamp the value in both Python and C to a valid range (`1..65535` ticks).

---

### [INT-05] Timer Wraparound Hang & 32-Bit Multiplication Overflow in `src/i2c_software.c`
- **File & Lines:** [i2c_software.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/i2c_software.c#L48-L58)
- **Severity:** HIGH (Watchdog reset caused by ~30s hang or 0-delay on timer wraparound)
- **Root Cause Analysis:**
  1. `i2c_delay` uses `while (t > timer_read_time());` instead of `timer_is_before(timer_read_time(), t)`. When the 32-bit hardware timer wraps around `0xFFFFFFFF`, `t > timer_read_time()` either becomes immediately `false` (0 ns delay -> corrupted I2C timing) or stays `true` for `~2^32` ticks (~25–50 seconds), freezing the MCU until a watchdog reset!
  2. `nsecs_to_ticks` computes `timer_from_us(ns * 1000) / 1000000`, where `(ns * 1000) * (CONFIG_CLOCK_FREQ / 1000000)` overflows 32 bits on a 168 MHz MCU whenever `ns > 25565`.
- **Remediation (Defensive Fix):**
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

### [INT-06] 8-Bit Length Truncation (`reg_len + data_len`) in `src/i2ccmds.c`
- **File & Lines:** [i2ccmds.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/i2ccmds.c#L86-L114)
- **Severity:** MEDIUM (Corrupted I2C writes)
- **Root Cause Analysis:**
  In `command_i2c_modify_bits`, `reg_len` (`uint8_t`, up to 255) and `data_len` (`uint8_t`, up to 127) can sum to 382, but `reg_len + data_len` is passed to `i2c_write(..., uint8_t write_len, ...)`, truncating lengths `> 255` modulo 256.
- **Remediation (Defensive Fix):**
  Check `if (reg_len > 64 || data_len > 64 || (uint16_t)reg_len + data_len > 64) shutdown("i2c transfer too large");`.

---

### [INT-07] 8-Bit Truncation of 16-Bit `static_string_id` in `src/sched.c`
- **File & Lines:** [sched.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/sched.c#L23), [sched.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/sched.c#L295-L309), [sched.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/sched.c#L321-L335)
- **Severity:** MEDIUM (Wrong shutdown error messages when static strings exceed 255)
- **Root Cause Analysis:**
  The protocol formats `static_string_id=%hu` (16-bit), but `SchedStatus.shutdown_reason` and `sched_shutdown(uint_fast8_t reason)` store only 8 bits (`uint8_t`). Because custom modules add many new static strings, string IDs `>= 256` wrap modulo 256.
- **Remediation (Defensive Fix):**
  Widen `shutdown_reason` and the parameters of `sched_shutdown` and `sched_try_shutdown` to `uint16_t` / `uint_fast16_t`.

---

### [INT-08] Signed 32-Bit Integer Overflow (Undefined Behavior) in `compress_bisect_add` (`stepcompress.c`)
- **File & Lines:** [stepcompress.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/stepcompress.c#L132-L146), [stepcompress.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/stepcompress.c#L161-L163), [stepcompress.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/stepcompress.c#L183-L188)
- **Severity:** HIGH (Step compression failure / Undefined Behavior)
- **Root Cause Analysis:**
  In `compress_bisect_add()`, `nextmininterval` and `nextmaxinterval` can be up to `CLOCK_DIFF_MAX` (`3 << 28` = `805,306,368`) and `nextcount` can reach `65535`. The products `nextmaxinterval * nextcount`, `nextmininterval * nextcount`, `minadd * nextaddfactor`, and `interval * count` are computed in signed 32-bit `int32_t` and overflow `INT32_MAX` starting at `nextcount >= 3`.
- **Remediation (Defensive Fix):**
  Compute intermediate products (`nextaddfactor`, `c`, `(int64_t)nextmininterval * nextcount`, `(int64_t)nextmaxinterval * nextcount`, `(int64_t)minadd * nextaddfactor`) in `int64_t`.

---

### [INT-09] Unaligned Size Check in `alloc_chunk` (`src/basecmd.c`)
- **File & Lines:** [basecmd.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/basecmd.c#L30-L39)
- **Severity:** MEDIUM (Overrun past `dynmem_end()`)
- **Root Cause Analysis:**
  `alloc_chunk` checks `if (alloc_end + size > dynmem_end())`, but then increments `alloc_end` by `ALIGN(size, __alignof__(void*))`. When `size` is not a multiple of 4, `alloc_end` can advance up to 3 bytes past `dynmem_end()` (the stack boundary!).
- **Remediation (Defensive Fix):**
  Compute `size_t aligned = ALIGN(size, __alignof__(void*));` before the bounds check and verify `if (aligned < size || aligned > (size_t)((char*)dynmem_end() - (char*)alloc_end))`.

---

## 4. Division by Zero (`ZeroDivisionError` & Hardware Faults)

### [DIV-01] Hardware Division by Zero in `sdio_set_speed` (`src/stm32/sdio.c`) and `inductance_coil.c`
- **File & Lines:** [sdio.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/sdio.c#L408), [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L335), [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L407), [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L417)
- **Severity:** CRITICAL (MCU HardFault / UsageFault)
- **Root Cause Analysis:**
  1. `sdio.c:408`: `SDIO_CLK_FREQ / speed` divides by `0` if `command_sdio_set_speed` is called with `speed = 0`.
  2. `inductance_coil.c:335`: `1 / (info->freq_cal_cycle * ...)` divides by `0` if `freq_cal_cycle == 0` or `cal_capture_pulse_window_size == 0`.
  3. `inductance_coil.c:407 & 417`: `frequency_conversion()` divides by `g_freq_cal_info.freq_cal_factor` (`0` when `need_capture_pulse_sum == 0`) or by `(double)freq` (`0` when `trg_freq_ht/lt == 0`).
- **Remediation (Defensive Fix):**
  Add explicit checks `if (speed == 0) shutdown(...);`, `if (info->freq_cal_cycle <= 0 || g_freq_cal_info.cal_capture_pulse_window_size == 0) shutdown(...);`, and `if (freq == 0) return 0xFFFFFFFF;` before each division.

---

### [DIV-02] Division by Zero in `chelper` (`serialqueue.c`, `msgblock.c`, `stepcompress.c`, `kin_shaper.c`)
- **File & Lines:**
  - [serialqueue.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/serialqueue.c#L903-L913)
  - [msgblock.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/msgblock.c#L199-L202)
  - [stepcompress.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/stepcompress.c#L331), [stepcompress.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/stepcompress.c#L605-L609)
  - [kin_shaper.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/kin_shaper.c#L48-L52)
- **Severity:** HIGH (`SIGFPE` / `NaN` propagation in C solver)
- **Root Cause Analysis:**
  1. `serialqueue_set_wire_frequency`: `1. / frequency` without checking `frequency > 0.`.
  2. `clock_to_time`: `(clock - ce->conv_clock) / ce->est_freq` without checking `ce->est_freq > 0.`.
  3. `stepcompress.c`: `(lsc - .5) / sc->mcu_freq` (line 331), integer division `ticks / interval` (line 605, `SIGFPE` when `interval == 0`), and `sqrt(b*b - 4*a*c)` without guarding against a negative discriminant (`NaN` cast to `int32_t` is UB).
  4. `kin_shaper.c:52`: `init_shaper()` computes `double inv_a = 1. / sum_a;` even when `n == 0` (shaper disabled) or `sum_a == 0.`.
- **Remediation (Defensive Fix):**
  Check denominators for `<= 0` or `== 0` prior to division and clamp the discriminant in `stepcompress_find_past_position` with `disc > 0. ? disc : 0.`.

---

### [DIV-03] Five Unprotected Division-by-Zero Paths in `virtual_sdcard.py`
- **File & Lines:** [virtual_sdcard.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/virtual_sdcard.py#L1323), [virtual_sdcard.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/virtual_sdcard.py#L2040), [virtual_sdcard.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/virtual_sdcard.py#L2142), [virtual_sdcard.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/virtual_sdcard.py#L2166-L2169), [virtual_sdcard.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/virtual_sdcard.py#L2275)
- **Severity:** HIGH (`ZeroDivisionError` during power-loss save/restore)
- **Root Cause Analysis:**
  - Lines 1323, 2142, 2275: `1. / self.gcode_move.get_status()['speed_factor']` and `1. / gcode_move_status['extrude_factor']` divide by `0` when `M221 S0` is active or corrupted factors exist.
  - Line 2040: `restore_print` divides by `float(file_env['speed_factor'])` without a `!= 0` check.
  - Lines 2166–2169: `self.printer.lookup_object('gcode_move').max_accel / toolhead_status['max_accel']` divides by `0` if `max_accel == 0` (and also references a non-existent attribute `gcode_move.max_accel`!).
- **Remediation (Defensive Fix):**
  Validate all factors for `> 0` before division.

---

### [DIV-04] Division by Zero When `z_adj == self.fade_dist` in `bed_mesh.py`
- **File & Lines:** [bed_mesh.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/bed_mesh.py#L219-L220)
- **Severity:** HIGH (`ZeroDivisionError` mid-`move()`)
- **Root Cause Analysis:**
  In `ZMesh.calc_z()`, `elif (z + z_adj) >= self.fade_end:` checks the end of the fade region, and the `else` branch computes `factor = (self.fade_end - (z + z_adj)) / (self.fade_dist - z_adj)`. When `z_adj == self.fade_dist` (and `z < fade_start`), the denominator is `0.0`!
- **Remediation (Defensive Fix):**
  Check `denom = self.fade_dist - z_adj; if abs(denom) < 1e-9: return 0.` before dividing.

---

### [DIV-05] Division by Zero & `date_rate` Typo in `inductance_coil.py`
- **File & Lines:** [inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/inductance_coil.py#L186), [inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/inductance_coil.py#L267)
- **Severity:** HIGH (`ZeroDivisionError` when starting frequency measurement)
- **Root Cause Analysis:**
  In `__init__`, `self._data_rate = config.getint('date_rate', 500)` is read (typo `'date_rate'` instead of `'data_rate'`, and missing `minval=1`). In `_start_measurements()`, line 267 computes `rest_ticks = self._mcu.seconds_to_clock(1 / self._data_rate)`, which immediately crashes with `ZeroDivisionError` if `_data_rate == 0`.
- **Remediation (Defensive Fix):**
  Use `config.getint('data_rate', config.getint('date_rate', 500), minval=1)`.

---

### [DIV-06] Division by Zero in `homing_precise_corexy.py`, `homing_xyz_override.py`, `auto_screws_tilt_adjust.py`, `homing.py`
- **File & Lines:**
  - [homing_precise_corexy.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/homing_precise_corexy.py#L107-L108)
  - [homing_xyz_override.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/homing_xyz_override.py#L206-L215)
  - [auto_screws_tilt_adjust.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/auto_screws_tilt_adjust.py#L207-L208)
  - [homing.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/homing.py#L239-L240)
- **Severity:** MEDIUM to HIGH (`ZeroDivisionError` during homing / bed leveling)
- **Root Cause Analysis:**
  1. `homing_precise_corexy.py:107`: `int(self.cor_x_stepper.get_rotation_distance()[0] // self.cor_x_stepper.get_step_dist())` — raises `ZeroDivisionError` or `AttributeError` if `step_dist == 0` or `cor_x_stepper is None`.
  2. `homing_xyz_override.py:206`: `(bed_mesh_max[0] - bed_mesh_min[0]) / (x_count - 1)` divides by `0` when `x_count == 1` or `y_count == 1`.
  3. `auto_screws_tilt_adjust.py:207`: `sum(...) / len(positions)` divides by `0` if `positions` is empty.
  4. `homing.py:239`: `abs(movepos[2] - pos[2]) / move_d` divides by `0` when `move_d == 0.0`.
- **Remediation (Defensive Fix):**
  Ensure denominators are `> 0` before each division.

---

### [DIV-07] Division by Zero in `flow_calibrator.py`, `purifier_factory.py`, `defect_detection.py`, `power_loss_check.py`
- **File & Lines:**
  - [flow_calibrator.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/flow_calibrator.py#L509-L512)
  - [purifier_factory.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/purifier_factory.py#L23), [purifier_factory.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/purifier_factory.py#L33)
  - [defect_detection.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/defect_detection.py#L78), [defect_detection.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/defect_detection.py#L808)
  - [power_loss_check.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/power_loss_check.py#L189-L191)
- **Severity:** HIGH (`ZeroDivisionError`)
- **Root Cause Analysis:**
  1. `flow_calibrator.py:511`: `_calculate_linear_fitting_zero_crossing` computes `zero_crossing = -intercept / slope`. If all measured points are identical (`slope == 0.0`), `ZeroDivisionError` is raised.
  2. `purifier_factory.py:33`: `60. * freq / self.ppr` divides by `0` because `tachometer_ppr` allows `minval=0` at line 23.
  3. `defect_detection.py:808`: `int((mesh_max - mesh_min) / self.bed_detect_probe_distance)` without `above=0.` at line 78.
  4. `power_loss_check.py:189`: `high_level_tick / (high_level_tick + low_level_tick)` divides by `0` when the MCU reports `0, 0`.
- **Remediation (Defensive Fix):**
  Check `if abs(slope) < 1e-12: return None` in `flow_calibrator.py`; use `minval=1` in `purifier_factory.py`, `above=0.` in `defect_detection.py`, and `total = high_level_tick + low_level_tick; if total <= 0: return 0.` in `power_loss_check.py`.

---

### [DIV-08] Division by Zero in `toolhead.py`, `mcu.py`, `clocksync.py`, and `stepper.py`
- **File & Lines:**
  - [toolhead.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/toolhead.py#L757-L786)
  - [mcu.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/mcu.py#L672-L676)
  - [clocksync.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/clocksync.py#L114)
  - [stepper.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/stepper.py#L274-L280)
- **Severity:** HIGH (`ZeroDivisionError`)
- **Root Cause Analysis:**
  1. `ToolHead.set_accel(accel)` only checks `if accel < 0: return` and permits `accel == 0`, which immediately crashes in `_calc_junction_deviation()` (`... / self.max_accel`) with `ZeroDivisionError`. Likewise, `above=0.` is missing in `cmd_SET_MAX_Z_ACCEL` and `cmd_SET_MAX_Z_VELOCITY`.
  2. `MCU._handle_mcu_stats`: `1.0 / (count * self._mcu_freq)` divides by `0` if `count == 0`.
  3. `ClockSync._handle_clock`: `self.clock_covariance / self.time_variance` divides by `0.0` if `diff_sent_time == 0.0` on the first clock sample.
  4. `stepper.parse_gear_ratio`: Permits `g1 <= 0` or `g2 == 0` in `result *= g1 / g2`.
- **Remediation (Defensive Fix):**
  Use `if accel <= 0: return` in `set_accel`, `above=0.` in `cmd_SET_MAX_Z_*`, and add non-zero guards in `_handle_mcu_stats`, `_handle_clock`, and `parse_gear_ratio`.

---

## 5. Null Pointer Dereference, Segfaults, Unaligned Access & `NoneType` Exceptions

### [NULL-01] Unaligned 32-Bit Pointer Dereference in `src/stm32/inductance_coil.c`
- **File & Lines:** [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L628-L630)
- **Severity:** HIGH (Undefined Behavior / UsageFault on ARM Cortex-M)
- **Root Cause Analysis:**
  In `struct sensor_bulk` (`src/sensor_bulk.h:9-15`), `uint8_t data[SENSOR_BULK_MAX_SIZE]` is placed immediately after `uint32_t possible_overflows` (4 bytes) and `uint8_t data_count` (1 byte), putting `sb.data[0]` at **odd byte offset 5**. The direct cast and store `*(uint32_t *)d = cal_freq;` performs a 32-bit memory access to an unaligned odd address (`5 + 4*k`).
- **Affected Code:**
  ```c
  uint8_t *d = &icd->sb.data[icd->sb.data_count];
  uint32_t cal_freq = frequency_conversion(INDUCTANCE_COIL_DEV_GET_TICK(), 0, NULL);
  *(uint32_t *)d = cal_freq;
  ```
- **Remediation (Defensive Fix):**
  ```c
  memcpy(d, &cal_freq, sizeof(cal_freq));
  ```

---

### [NULL-02] Null Pointer Dereference in `src/sdiocmds.c`, `src/stm32/sdio.c` & `scripts/spi_flash/fatfs_api.c`
- **File & Lines:** [sdiocmds.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/sdiocmds.c#L48-L132), [sdio.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/sdio.c#L205), [fatfs_api.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/scripts/spi_flash/fatfs_api.c#L142-L143)
- **Severity:** HIGH (Null Pointer Dereference)
- **Root Cause Analysis:**
  1. `sdiocmds.c`: If SDIO commands are invoked prior to `sdio_set_bus`, `sdio->sdio_config.sdio == NULL`.
  2. `sdio.c:205`: `if (response_data != NULL)` dereferences `*response_data_len = 4;` without checking `response_data_len != NULL`.
  3. `fatfs_api.c:142`: `struct fatfs_file *fhdl = malloc(sizeof(struct fatfs_file)); memset(fhdl, 0, ...);` checks `if (fhdl)` only **after** `memset` at line 156.
- **Remediation (Defensive Fix):**
  Add NULL checks before every pointer dereference.

---

### [NULL-03] Null Pointer Dereference (`SIGSEGV`) in `chelper` (`serialqueue.c`, `kin_shaper.c`, `kin_idex.c`, `pollreactor.c`, `stepcompress.c`)
- **File & Lines:**
  - [serialqueue.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/serialqueue.c#L458-L476)
  - [kin_shaper.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/kin_shaper.c#L208)
  - [kin_idex.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/kin_idex.c#L58)
  - [pollreactor.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/pollreactor.c#L53-L63)
  - [stepcompress.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/stepcompress.c#L472)
- **Severity:** CRITICAL (`SIGSEGV` in host process)
- **Root Cause Analysis:**
  1. `serialqueue.c:458-476`: In `build_and_send_command()`, `min_clock = MAX_CLOCK`. If all messages in `ready_queue` have `m->req_clock >= MAX_CLOCK`, `qm` remains `NULL` and line 475 dereferences `qm->len` (`SIGSEGV`).
  2. `kin_shaper.c:208` & `kin_idex.c:58, 67`: Dereference `is->orig_sk->active_flags` and `dc->orig_sk->active_flags` without `if (!orig_sk) return -1;`.
  3. `pollreactor.c:53`: `pollreactor_free(NULL)` dereferences `pr->fds` without `if (!pr) return;`.
  4. `stepcompress.c:472`: `sc->queue = realloc(sc->queue, ...)` does not check for `NULL`.
- **Remediation (Defensive Fix):**
  Add `if (!qm) { sq->ready_bytes = 0; break; }` in `build_and_send_command` and validate all C pointers before dereferencing.

---

### [NULL-04] `NoneType` Crashes in `virtual_sdcard.py` (`restore_print` & `get_print_task_config`)
- **File & Lines:** [virtual_sdcard.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/virtual_sdcard.py#L830-L831), [virtual_sdcard.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/virtual_sdcard.py#L1843-L1845)
- **Severity:** CRITICAL (Unhandled crash during power-loss recovery)
- **Root Cause Analysis:**
  1. In `restore_print()` (lines 1843–1845), `if not file_env['env_flag']:` is evaluated **before** checking whether `file_env is None` (which `load_pl_env()` returns when the file is missing or corrupted). This raises `TypeError: 'NoneType' object is not subscriptable`.
  2. In `get_print_task_config()` (lines 830–831), `self.current_file.name` is dereferenced inside the `except` block even though `self.current_file` can be `None`.
- **Remediation (Defensive Fix):**
  Use `if not file_env or not file_env.get('env_flag'):` and `getattr(self.current_file, 'name', '<none>')`.

---

### [NULL-05] Missing Initialization of `self.mqtt_jsonrpc` in `defect_detection.py` & `None` Dereference in `timelapse.py`
- **File & Lines:** [defect_detection.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/defect_detection.py#L406), [defect_detection.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/defect_detection.py#L428), [defect_detection.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/defect_detection.py#L509), [defect_detection.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/defect_detection.py#L552), [timelapse.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/timelapse.py#L117)
- **Severity:** HIGH (`AttributeError` at runtime)
- **Root Cause Analysis:**
  In `DefectDetection.__init__`, `self.mqtt_jsonrpc` is never initialized, yet lines 406, 428, 509, and 552 call `self.mqtt_jsonrpc.send_async_request(...)` -> guaranteed `AttributeError: 'DefectDetection' object has no attribute 'mqtt_jsonrpc'`. In `timelapse.py`, `self.mqtt_jsonrpc` remains `None` when `print_task_config` is absent, but is called without an `if self.mqtt_jsonrpc is not None:` check.
- **Remediation (Defensive Fix):**
  Initialize `self.mqtt_jsonrpc = None` in `DefectDetection.__init__`, resolve it in `_handle_ready` via `self.printer.lookup_object('mqtt_jsonrpc', None)`, and guard every call with `is not None`.

---

### [NULL-06] Additional `NoneType` Dereferences in `klippy.py`, `extruder.py`, `bed_mesh.py`, `probe_inductance_coil.py`, `extruder_calibration.py`, `filament_feed.py`, `error_mcu.py`, `park_detector.py`
- **File & Lines:**
  - [klippy.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/klippy.py#L277-L282): `parsed_structured_code.get("id", id)` raises `AttributeError` when `_parse_structured_code()` returns `None`.
  - [extruder.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/kinematics/extruder.py#L1833-L1838): `current_extruder.xy_park_position[0]` raises `TypeError` when `xy_park_position` is not configured (`None`) on `extruder0`.
  - [bed_mesh.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/bed_mesh.py#L1167-L1172): `machine_state_manager.get_status()` called without checking for `None`.
  - [probe_inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/probe_inductance_coil.py#L1397-L1408): `_get_filament_temp(self, extruder=None)` passes `None` to `get_extruder_filament_params(None)`, crashing on `extruder < 0` with `TypeError`.
  - [extruder_calibration.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/extruder_calibration.py#L234): `"%.3f" % (self.get_analog_output(),)` raises `TypeError` because `get_analog_output()` returns `None` when no sensor is configured.
  - [filament_feed.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_feed.py#L584): `self.filament_detect.register_cb_2_filament_key_detect(...)` and `self.runout_sensor[ch]` are called without `is not None` checks.
  - [error_mcu.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/error_mcu.py#L172): `if "Protocol error" in msg:` raises `TypeError` when `msg is None`.
  - [park_detector.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/park_detector.py#L90): `adc_status['last_adc_value'] * 3.3` raises `TypeError` before the first ADC sample is received (`None`).
- **Remediation (Defensive Fix):**
  Add explicit `is not None` guards at all listed locations.

---

## 6. Memory & Resource Leaks (Memory Leaks, FD Leaks, Lock Leaks & Zombie Processes)

### [LEAK-01] Move Queue Memory Leak & Missing IRQ Lock in `get_all_stepper_info` (`src/stepper.c`)
- **File & Lines:** [stepper.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stepper.c#L342-L363)
- **Severity:** CRITICAL (Permanently leaked `stepper_move` nodes & Race Condition with Stepper ISR)
- **Root Cause Analysis:**
  In `get_all_stepper_info()`, when `is_pl_save == 1`, `move_queue_clear(&s->mq)` (which merely sets `s->mq.first = NULL`) is called **before** `stepper_stop(&s->stop_signal, 0)`!
  Because `stepper_stop()` iterates over `while (!move_queue_empty(&s->mq))` to return all `stepper_move` nodes to the global `move_free_list` via `move_free(m)`, calling `move_queue_clear(&s->mq)` beforehand causes `stepper_stop()` to see an empty queue — **permanently leaking every queued `stepper_move` node**!
  Furthermore, `get_all_stepper_info` is called from `power_loss_check.c` with **interrupts enabled**, even though both `stepper_get_position()` and `stepper_stop()` require interrupts to be disabled.
- **Affected Code:**
  ```c
  if (is_pl_save) {
      move_queue_clear(&s->mq);
      stepper_stop(&s->stop_signal, 0);
  }
  ```
- **Remediation (Defensive Fix):**
  Remove `move_queue_clear(&s->mq)` before `stepper_stop` (since `stepper_stop` pops and frees the queue itself) and wrap the entire loop in `irqstatus_t flag = irq_save(); ... irq_restore(flag);`.

---

### [LEAK-02] MCU Flash Left Permanently Unlocked on Error Paths in `flash_write` (`src/stm32/power_loss_check.c`)
- **File & Lines:** [power_loss_check.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/power_loss_check.c#L146-L203)
- **Severity:** HIGH (Hardware Flash Lock Leak during voltage brown-out)
- **Root Cause Analysis:**
  `flash_write()` calls `flash_unlock()` at line 146, but returns `return ERROR;` directly on four error paths (lines 169, 172, 178, 183) **without calling `flash_lock()`**. During an unstable power-loss condition, leaving program flash unlocked exposes firmware flash to corruption.
- **Remediation (Defensive Fix):**
  Route all error exits through a `goto out;` cleanup label that guarantees `flash_lock();` before `return status;`.

---

### [LEAK-03] Permanent `alloc_chunk` Memory Leak on Repeated `i2c_set_software_bus` (`src/i2c_software.c` & `src/i2ccmds.c`)
- **File & Lines:** [i2c_software.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/i2c_software.c#L25-L39), [i2ccmds.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/i2ccmds.c#L35-L50)
- **Severity:** MEDIUM (`dynmem_pool` exhaustion)
- **Root Cause Analysis:**
  Neither `command_i2c_set_software_bus` nor `i2cdev_set_software_bus` checks whether `i2c->flags & (IF_SOFTWARE | IF_HARDWARE)` is already set. Every repeated call allocates a new `alloc_chunk(sizeof(*is))` from the static MCU memory pool.
- **Remediation (Defensive Fix):**
  Check `if (i2c->flags & (IF_SOFTWARE | IF_HARDWARE)) shutdown("Invalid i2c config");` prior to `alloc_chunk`.

---

### [LEAK-04] Pipe FD Leak, Mutex/Condvar Leak & Unjoined Thread in `serialqueue.c`
- **File & Lines:** [serialqueue.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/serialqueue.c#L647-L752)
- **Severity:** CRITICAL (File descriptor exhaustion `EMFILE` & Use-After-Free)
- **Root Cause Analysis:**
  `serialqueue_alloc()` opens a pipe `pipe(sq->pipe_fds)` (2 file descriptors) and initializes two `pthread_mutex_t` and one `pthread_cond_t`. `serialqueue_free()` **never** closes `sq->pipe_fds[0]` or `sq->pipe_fds[1]` and never destroys the mutexes or condition variable. Every MCU reconnect or CAN bus retry cycle leaks 2 file descriptors.
- **Remediation (Defensive Fix):**
  Call `close(sq->pipe_fds[0]); close(sq->pipe_fds[1]);`, `pthread_mutex_destroy()`, and `pthread_cond_destroy()` in `serialqueue_free()`.

---

### [LEAK-05] C Heap Memory Leak in `extruder_set_pressure_advance` (`kin_extruder.c`)
- **File & Lines:** [kin_extruder.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/kin_extruder.c#L150-L157)
- **Severity:** HIGH (Continuous C heap leak on pressure advance updates)
- **Root Cause Analysis:**
  When pruning expired `struct pa_params` nodes from `es->pa_list`, the loop unlinks the node via `list_del(&first_pa->node)`, **but forgets to call `free(first_pa)`**!
- **Affected Code:**
  ```c
  while (!list_is_last(&first_pa->node, &es->pa_list)) {
      struct pa_params *next_pa = list_next_entry(first_pa, node);
      if (next_pa->active_print_time >= cleanup_time) break;
      list_del(&first_pa->node);
      first_pa = next_pa;
  }
  ```
- **Remediation (Defensive Fix):**
  Add `free(first_pa);` immediately after `list_del(&first_pa->node);`.

---

### [LEAK-06] Severe Memory Leak & Zombie Process in `FrequencyQueryHelper.write_to_file` (`inductance_coil.py`)
- **File & Lines:** [inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/inductance_coil.py#L82-L98)
- **Severity:** HIGH (RAM leak in main process & zombie child process)
- **Root Cause Analysis:**
  `write_to_file()` spawns `write_proc = multiprocessing.Process(target=self._write_to_file)` **without** calling `self.get_samples()` beforehand and **without** `write_proc.join()` or `daemon=True`.
  Consequently, `self.get_samples()` runs only **inside the forked child process**! `self.raw_samples = []` (line 66) clears only the copy in the child process's address space, leaving `self.raw_samples` in the parent `klippy` process uncleared in RAM forever! Moreover, without `join()`, the child process remains as a zombie process.
- **Remediation (Defensive Fix):**
  Call `samples = self.get_samples()` in the parent process before starting the async write, or use `queuefile.async_write_file`.

---

### [LEAK-07] FIFO File Descriptor Leak & 30s Main Reactor Freeze in `FlowCalcClient.calc_flow_factor` (`flow_calibrator.py`)
- **File & Lines:** [flow_calibrator.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/flow_calibrator.py#L113-L149)
- **Severity:** HIGH (File Descriptor Leak & 30-second freeze of the entire printer)
- **Root Cause Analysis:**
  If `os.open(self.resp_fifo, ...)` fails, `req_fd` is not closed. If `select.select` times out (`not rlist`), the method returns `None` **without closing `req_fd` and `resp_fd`** (`os.close()` is not in a `finally` block!). Furthermore, `select.select([resp_fd], [], [], timeout)` with `timeout = 30.0` blocks Klippy's main reactor thread synchronously for up to 30 seconds.
- **Remediation (Defensive Fix):**
  Close `req_fd` and `resp_fd` inside a `try ... finally:` block and perform the wait via the Klippy reactor (`reactor.pause`) instead of a synchronous 30s `select.select`.

---

### [LEAK-08] GPIO FD Leak & Thread Leak in `fm175xx_reader.py` and Thread Leak in `mqtt.py`
- **File & Lines:** [fm175xx_reader.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/fm175xx_reader.py#L217-L237), [fm175xx_reader.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/fm175xx_reader.py#L859-L865), [mqtt.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/mqtt.py#L47-L49)
- **Severity:** MEDIUM to HIGH (FD & Thread Leaks)
- **Root Cause Analysis:**
  1. `fm175xx_reader.py:217-237`: `chip_fd = os.open(gpio_chip_dev, ...)` is neither stored nor closed after `ioctl(chip_fd, GPIO_GET_LINEHANDLE_IOCTL, ...)`! Only `self._fd = req.fd` is closed later; `chip_fd` leaks permanently.
  2. `mqtt.py:47-49`: `self.client.loop_start()` starts the Paho background thread **before** `self.client.connect()` is called. If `connect()` raises an exception (e.g., broker not yet reachable), the background thread runs forever.
- **Remediation (Defensive Fix):**
  Close `os.close(chip_fd)` immediately after the `ioctl` call inside a `try...finally` block; in `mqtt.py`, use `connect_async()` or call `loop_start()` only after `connect()` succeeds.

---

### [LEAK-09] Directory Handle Leak (Missing `f_closedir`) in `scripts/spi_flash/fatfs_api.c` & PTY FD Leak in `src/linux/console.c` / `klippy/util.py`
- **File & Lines:** [fatfs_api.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/scripts/spi_flash/fatfs_api.c#L217-L232), [console.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/linux/console.c#L72-L112), [util.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/util.py#L71-L97)
- **Severity:** MEDIUM (Resource Leak)
- **Root Cause Analysis:**
  - `fatfs_list_dir()` calls `f_opendir(&dir, path)`, but never closes `dir` with `f_closedir(&dir)` and unconditionally returns `FR_OK` even on error.
  - `src/linux/console.c` does not close `mfd` and `sfd` when a subsequent syscall fails.
- **Remediation (Defensive Fix):**
  Call `f_closedir(&dir)` before returning in `fatfs_list_dir()` and return `res` instead of `FR_OK`.

---

## 7. Dangling Pointers & Use-After-Free / Use-After-Close

### [UAF-01] Dangling Global Pointer `plc` After `config_reset` & Active `TIM4_IRQHandler` Memory Corruption (`src/stm32/power_loss_check.c`)
- **File & Lines:** [power_loss_check.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/power_loss_check.c#L517-L521), [power_loss_check.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/power_loss_check.c#L672-L684)
- **Severity:** CRITICAL (Dangling Pointer / Use-After-Free in interrupt context)
- **Root Cause Analysis:**
  `static struct power_loss_check_dev *plc;` is allocated from Klipper's `dynmem_pool` via `oid_alloc()`. When Klipper executes a `config_reset` (`FIRMWARE_RESTART`) (`src/basecmd.c`), `dynmem_pool` is completely reset (`alloc_init()`), but the global pointer `plc` remains non-`NULL` and `TIM4_IRQHandler` remains enabled!
  1. `TIM4_IRQHandler` continues writing to `plc->debounce_count`, `plc->voltage_type`, and `plc->need_save` inside memory reallocated to new OIDs (Use-After-Free / Memory Corruption).
  2. Every subsequent call to `command_config_power_loss_check_dev` after a soft restart is rejected by `if (plc) return;`!
- **Remediation (Defensive Fix):**
  Disable `TMR4` and its NVIC IRQ in `power_loss_check_shutdown()`, and check existing instances via `foreach_oid` in `command_config_power_loss_check_dev` rather than relying on an unreset global pointer `plc` across `config_reset`.

---

### [UAF-02] Dangling Timer `config_freq_timer` & Active Priority-0 IRQ on Shutdown in `src/stm32/inductance_coil.c`
- **File & Lines:** [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L72), [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L432-L437), [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L665-L673)
- **Severity:** HIGH (Dangling Timer & Reconfiguration Lockout)
- **Root Cause Analysis:**
  1. `inductance_coil_shutdown()` only deletes `sched_del_timer(&d->timer)`, forgetting `sched_del_timer(&d->config_freq_timer)` and leaving the priority-0 hardware interrupt `INPUT_CAPTURE_CAL_CRM_IRQn` enabled.
  2. `static uint8_t inductance_coil_oid_malloc` stores `args[0]` (`oid`). When `oid == 0`, the variable remains `0` (rendering the singleton guard ineffective); when `oid != 0`, it is never cleared on `config_reset` and blocks any `FIRMWARE_RESTART`.
- **Remediation (Defensive Fix):**
  Delete both software timers and disable the hardware timers and `INPUT_CAPTURE_CAL_CRM_IRQn` in `inductance_coil_shutdown`; implement the singleton check via `foreach_oid`.

---

### [UAF-03] Use-After-Free in `serialqueue_free` on Concurrent Thread Exit (`serialqueue.c`)
- **File & Lines:** [serialqueue.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/serialqueue.c#L635-L643), [serialqueue.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/serialqueue.c#L728-L752)
- **Severity:** CRITICAL (Use-After-Free / `SIGSEGV` when closing serial connection)
- **Root Cause Analysis:**
  When a read/CAN error occurs in `input_event()`, the background thread itself calls `pollreactor_do_exit(sq->pr)` (`must_exit = 1`) **before** `pollreactor_run()` returns and **before** `background_thread()` acquires `pthread_mutex_lock(&sq->lock)` at line 638.
  If the main thread now calls `serialqueue_free(sq)`, `pollreactor_is_exit(sq->pr)` is already `1`, so `if (!pollreactor_is_exit(sq->pr)) serialqueue_exit(sq);` is **skipped**! `serialqueue_free()` never calls `pthread_join(sq->tid, NULL)` and immediately executes `free(sq)` while `background_thread()` is still accessing `sq->lock`!
- **Remediation (Defensive Fix):**
  Maintain a dedicated `sq->thread_running` flag so that `serialqueue_exit()` (including `pthread_join`) is **always** executed in `serialqueue_free()` if the thread has not yet been joined.

---

### [UAF-04] Dangling Pointers (`tdm->node` & `tdm->fr`) When Freed via `ffi_lib.free` (`trdispatch.c` & `mcu.py`)
- **File & Lines:** [trdispatch.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/trdispatch.c#L132-L210), [mcu.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/mcu.py#L174-L177)
- **Severity:** HIGH (Use-After-Free in `td->tdm_list` and `sq->fast_readers`)
- **Root Cause Analysis:**
  `trdispatch_mcu_alloc` links `tdm->node` into `td->tdm_list`, and `trdispatch_start` links `tdm->fr` into `sq->fast_readers`. However, `mcu.py` binds both structs directly to the Python GC with `ffi_lib.free` without unlinking them from the C linked lists first.
- **Remediation (Defensive Fix):**
  Provide dedicated C functions `trdispatch_free()` and `trdispatch_mcu_free()` that call `trdispatch_stop()` and `list_del(&tdm->node)` before `free()`.

---

### [UAF-05] Use-After-Close Race Condition on RFID Reader Shutdown (`fm175xx_reader.py`)
- **File & Lines:** [fm175xx_reader.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/fm175xx_reader.py#L938-L961)
- **Severity:** MEDIUM (`OSError: Bad file descriptor` / Race during shutdown)
- **Root Cause Analysis:**
  In `__shutdown()`, immediately after setting `self._running = False`, the GPIO/SPI driver is closed (`self._fm175xx.deinit()`) **without** waiting for `_thread_Check_Card()` to finish via `self._thread.join(timeout=2.0)`. Because the background thread may be mid-cycle during `time.sleep(0.1)`, it accesses already closed file descriptors after `deinit()`.
- **Remediation (Defensive Fix):**
  In `__shutdown()`, set `self._running = False` first, wait for `self._thread.join(timeout=2.0)`, and only then call `self._fm175xx.deinit()`.

---

## 8. Stack Overflows, Infinite Loops & Infinite Recursion

### [STACK-01] Unchecked Variable Length Arrays (VLA) on the MCU Stack in `src/i2ccmds.c`
- **File & Lines:** [i2ccmds.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/i2ccmds.c#L74), [i2ccmds.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/i2ccmds.c#L99)
- **Severity:** HIGH (MCU Stack Overflow)
- **Root Cause Analysis:**
  In `command_i2c_read` (`uint8_t data[data_len];`, up to 255 bytes) and `command_i2c_modify_bits` (`uint8_t receive_data[reg_len + data_len];`, up to 382 bytes), dynamically sized arrays are allocated directly on the small MCU stack.
- **Remediation (Defensive Fix):**
  Limit the maximum I2C transfer size to e.g. 64 bytes and use fixed-size buffers.

---

### [STACK-02] Infinite Probing Loop in `cmd_AUTO_SCREWS_TILT_ADJUST_MANUAL_TUNING` (`auto_screws_tilt_adjust.py`)
- **File & Lines:** [auto_screws_tilt_adjust.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/auto_screws_tilt_adjust.py#L520-L580)
- **Severity:** HIGH (Uncancellable Infinite Loop)
- **Root Cause Analysis:**
  `while True:` repeatedly executes `probe.run_probe(gcmd)` and exits the loop only if all screws fall within `self.manual_thread_adjust_threshold`. There is neither a `max_iter` limit nor a timeout check.
- **Remediation (Defensive Fix):**
  Add a maximum iteration count (`max_attempts`) and an abort check.

---

### [STACK-03] Infinite Loop in `PrinterHeaters.set_temperature` on Shutdown During Queue Wait (`heaters.py`)
- **File & Lines:** [heaters.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/heaters.py#L733-L739)
- **Severity:** HIGH (Infinite loop on shutdown / M109)
- **Root Cause Analysis:**
  The outer wait loop for the heater queue slot (`while True: if heater.name in self.heater_queue[:self.max_concurrent_heaters]: break; self.reactor.pause(eventtime + 1.)`) does **not** check `self.printer.is_shutdown()` and never updates `eventtime` inside the loop (`eventtime = self.reactor.monotonic()`). After the first second, `eventtime + 1.` is in the past, turning the loop into a 100% CPU busy-loop that never terminates on shutdown!
- **Affected Code:**
  ```python
  while True:
      with self.queue_lock:
          if heater.name in self.heater_queue[:self.max_concurrent_heaters]:
              break
      self.reactor.pause(eventtime + 1.)
  ```
- **Remediation (Defensive Fix):**
  ```python
  while not self.printer.is_shutdown():
      with self.queue_lock:
          if heater.name in self.heater_queue[:self.max_concurrent_heaters]:
              break
      eventtime = self.reactor.pause(self.reactor.monotonic() + 1.)
  ```

---

### [STACK-04] Infinite Loop `while (1):` in `cmd_FILAMENT_DT_SELF_TEST` (`filament_detect.py`)
- **File & Lines:** [filament_detect.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_detect.py#L238-L244)
- **Severity:** HIGH (Permanent lockup of G-code processing)
- **Root Cause Analysis:**
  `cmd_FILAMENT_DT_SELF_TEST` enters an infinite `while (1):` loop without any exit condition until the process is killed.
- **Remediation (Defensive Fix):**
  Bound the loop to a configurable test duration (`DURATION`, default e.g. 10 seconds) and `not self.printer.is_shutdown()`.

---

### [STACK-05] Broken Timeout (`wait_timeout_time` Overwritten Every Second) -> Infinite Loop in `cmd_WAIT_CHAMBER_TEMP` (`purifier.py`)
- **File & Lines:** [purifier.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/purifier.py#L1158), [purifier.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/purifier.py#L1188-L1190)
- **Severity:** HIGH (Infinite loop when chamber temperature is not reached)
- **Root Cause Analysis:**
  In `cmd_WAIT_CHAMBER_TEMP`, `wait_timeout_time = eventtime + timeout` is calculated before the loop (line 1158), but **inside** the `while not self.printer.is_shutdown():` loop at line 1188 it is overwritten on every iteration with `wait_timeout_time = eventtime`! Consequently, `if eventtime > wait_timeout_time:` at line 1189 (`eventtime > eventtime`) is **never true** and the timeout never fires!
- **Affected Code:**
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
- **Remediation (Defensive Fix):**
  Remove the erroneous assignment `wait_timeout_time = eventtime` at line 1188.

---

### [STACK-06] Infinite Loop on Circular Symlinks in `AsyncFileReader._do_listdir` (`asyncfilereader.py`)
- **File & Lines:** [asyncfilereader.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/asyncfilereader.py#L368)
- **Severity:** MEDIUM (Background file reader thread hang)
- **Root Cause Analysis:**
  `os.walk(dirname, followlinks=True)` follows symbolic links without cycle detection. A single symlink pointing to a parent directory hangs the background thread forever.
- **Remediation (Defensive Fix):**
  Track visited `os.path.realpath(root)` paths in a `set` and skip already visited directories.

---

## 9. Deadlocks & Infinite Hardware Polling Loops (Without Timeout)

### [DEAD-01] Infinite Hardware Polling Loops Without Timeout in MCU Drivers (`sdio.c`, `at32f403a.c`, `at32f415rc.c`, `n32g45x_adc.c`, `spi.c`, `canserial.c`)
- **File & Lines:**
  - [sdio.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/sdio.c#L307-L318), [sdio.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/sdio.c#L361-L372)
  - [at32f403a.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/at32f403a.c#L37-L52), [at32f415rc.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/at32f415rc.c#L17-L24)
  - [n32g45x_adc.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/n32g45x_adc.c#L65-L75)
  - [spi.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/spi.c#L218-L235)
  - [canserial.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/generic/canserial.c#L156-L160)
- **Severity:** HIGH (MCU Freeze & Watchdog Reset)
- **Root Cause Analysis:**
  - `sdio_read_data` and `sdio_write_data` spin in `while ((sdio->STA & ...) == 0)` waiting for hardware flags without a software timeout.
  - `at32f403a_log`, `at32f415_log`, and `__io_putchar` spin forever waiting for `USART_TDBE_FLAG`, even though `uart_debug_print_init` is disabled/commented out by default.
  - `n32g45x_adc.c:adc_calibrate()` and `spi.c` (AT32F403A) poll hardware flags without a timeout.
  - `canserial.c:156` (`for (;;) { int ret = canbus_send(&send); if (ret >= 0) return; }`) blocks the entire MCU task loop when the CAN TX buffer is full.
- **Remediation (Defensive Fix):**
  Guard all hardware polling loops with a software timer deadline (`timer_is_before(timer_read_time(), end)`) or a bounded iteration counter.

---

### [DEAD-02] Permanent Mutex Deadlock on `self._mutex_lock` and `self.channel_active` in `filament_feed.py` & `filament_feed_fac_test.py`
- **File & Lines:** [filament_feed.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_feed.py#L315-L374), [filament_feed.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_feed.py#L776-L789), [filament_feed_fac_test.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_feed_fac_test.py#L82-L141)
- **Severity:** CRITICAL (Permanent deadlock of the filament feeder)
- **Root Cause Analysis:**
  1. In `FeedMotor.run()` and `FeedMotor.run_one_cycle()` (`filament_feed.py:315-374`), `self._mutex_lock = True` is set, but the subsequent actuator/reactor calls are **not** wrapped in a `try ... finally: self._mutex_lock = False` block. In `filament_feed_fac_test.py:139`, `except Exception:` even catches exceptions without resetting `self._mutex_lock = False`! If a single exception occurs, `_mutex_lock` stays `True` permanently and every subsequent motor move raises `"FeedMotor is already running"`.
  2. In `FilamentFeedModule._load_prepare()` (`filament_feed.py:776-789`), `self.channel_active[ch] = True` is set **before** the `try:` block. If `self._check_extruder_temp(ch)` fails at line 778, the `finally:` block is not reached and the channel remains locked with `"channel[%d] is busy"` until a reboot!
- **Remediation (Defensive Fix):**
  Set `self._mutex_lock = True` and `self.channel_active[ch] = True` immediately before `try:` and guarantee release (`False`) inside the corresponding `finally:` block.

---

### [DEAD-03] Self-Deadlock on Non-Reentrant `ReactorMutex` in `machine_state_manager.py`
- **File & Lines:** [machine_state_manager.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/machine_state_manager.py#L269-L299)
- **Severity:** CRITICAL (Permanent Reactor Greenlet Deadlock)
- **Root Cause Analysis:**
  Klippy's `ReactorMutex` (`self._lock`) is **non-reentrant** (it only checks `if self.is_locked:`). In `change_state()` and `set_action_code()`, all registered `self._pre_hooks` and `self._post_hooks` are executed **inside** `with self._lock:`! If any hook callback calls `set_action_code()` or `change_state()` on the same greenlet, the greenlet blocks forever waiting for itself in `ReactorMutex.__enter__`.
- **Remediation (Defensive Fix):**
  Use a reentrant mutex (tracking `greenlet.getcurrent()`) or invoke hooks outside the lock.

---

### [DEAD-04] Deadlock Risk Calling `gcode.run_script_from_command` Inside `with self.lock:` in `bed_mesh.py`
- **File & Lines:** [bed_mesh.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/bed_mesh.py#L1258-L1270)
- **Severity:** HIGH (Greenlet deadlock on concurrent G-code execution)
- **Root Cause Analysis:**
  In `BedMeshCalibrate`, `with self.lock:` is held while calling `self.gcode.run_script_from_command(...)` (which acquires `gcode_mutex`). If another greenlet already holds `gcode_mutex` and invokes a `bed_mesh` function, a classic lock-order inversion (AB-BA deadlock) occurs.
- **Remediation (Defensive Fix):**
  Execute `gcode.run_script_from_command` outside `with self.lock:`.

---

## 10. Race Conditions & Concurrency Defects

### [RACE-01] Race Conditions Between Priority-0 ISR (`InputCapture_IRQHandler`), Timer ISR, and Task in `src/stm32/inductance_coil.c`
- **File & Lines:** [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L168-L237), [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L279-L320), [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L458-L518)
- **Severity:** HIGH (Corrupted trigger thresholds during Z-probing)
- **Root Cause Analysis:**
  `update_trigger_frequencies()` is called both from the software timer ISR (`inductance_coil_config_freq_event`) and from task context (`command_virtual_gpio_trigger`), yet modifies `d->cal_info` outside `irq_save()`. Furthermore, `inductance_coil_crm_tmr_init()` resets `g_freq_cal_info` without disabling the priority-0 interrupt `INPUT_CAPTURE_CAL_CRM_IRQn` first.
- **Remediation (Defensive Fix):**
  Wrap all writes to `d->cal_info` and `g_freq_cal_info` completely inside `irq_save()` / `irq_restore()`.

---

### [RACE-02] Flawed `threading.local()` Instead of Greenlet-Local State in `GCodeDispatch._process_commands` (`gcode.py`)
- **File & Lines:** [gcode.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/gcode.py#L10), [gcode.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/gcode.py#L201-L250)
- **Severity:** CRITICAL (Complete swallowing of `CommandError` and coded exceptions across concurrent greenlets)
- **Root Cause Analysis:**
  `_process_commands` uses `_thread_local = threading.local()` (`_thread_local.in_process_commands`) to determine whether a call is the outermost invocation (`is_top_level`).
  However, Klippy executes **all** greenlets (G-code, timers, webhooks) on the **same OS thread**! Whenever Greenlet A pauses inside a G-code command (e.g., `G28`, `M109`, `M400`) via `reactor.pause()`, `_thread_local.in_process_commands = True` remains set on the OS thread.
  If Greenlet B (e.g., via `webhooks.py` `gcode/script` or a timer) executes a G-code command while Greenlet A is paused, Greenlet B sees `_thread_local.in_process_commands == True` and sets `is_top_level = False`! If an error occurs in Greenlet B, `_respond_error()` and `raise_coded_exception(e)` are completely skipped!
- **Affected Code:**
  ```python
  _thread_local = threading.local()
  ...
  def _process_commands(self, commands, need_ack=True):
      is_top_level = not getattr(_thread_local, 'in_process_commands', False)
      if is_top_level:
          _thread_local.in_process_commands = True
  ```
- **Remediation (Defensive Fix):**
  Bind the flag to the current **greenlet** (`greenlet.getcurrent()`) instead of `threading.local()`:
  ```python
  cur_greenlet = greenlet.getcurrent()
  is_top_level = not getattr(cur_greenlet, 'in_process_commands', False)
  if is_top_level:
      cur_greenlet.in_process_commands = True
  ```

---

### [RACE-03] Re-Entrancy Crash (`KeyError` / `ValueError`) in `QueryStatusHelper._do_query` (`webhooks.py`)
- **File & Lines:** [webhooks.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/webhooks.py#L504-L583)
- **Severity:** CRITICAL (Unhandled reactor crash mid-print)
- **Root Cause Analysis:**
  `_do_query()` yields during longer status queries via `reactor.pause(reactor.NOW)` (lines 535, 556). While `_do_query` is paused, `send_status()` can reschedule the timer to `reactor.NOW` or a client can disconnect. Consequently, `del self.clients[cconn]` (line 518) raises `KeyError`, and `reactor.unregister_timer(self.query_timer)` (line 560, when `self.query_timer` was already set to `None`) raises `ValueError`.
- **Remediation (Defensive Fix):**
  Use `self.clients.pop(cconn, None)` instead of `del self.clients[cconn]` and check `if self.query_timer is not None:` before `unregister_timer`.

---

### [RACE-04] TOCTOU Read-Modify-Write File Race & Thread Unsafety in `exception_manager.py`
- **File & Lines:** [exception_manager.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/exception_manager.py#L54), [exception_manager.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/exception_manager.py#L190-L258), [exception_manager.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/exception_manager.py#L300-L305)
- **Severity:** HIGH (Data loss in `exception_persistent.json` & cross-thread reactor access)
- **Root Cause Analysis:**
  1. `save_persistent_exception()` and `clear_persistent_exception()` read the file from disk and enqueue an asynchronous write via `queuefile.async_write_file()` without using `self.file_lock`. When called in rapid succession (e.g., in `clear_exception()`, lines 303 & 305), the second call reads stale disk data before `queuefile` has flushed the first write.
  2. `raise_exception_async()` is called from background threads (`serialhdl.py`), mutates `self.async_exceptions` without a lock, and calls `reactor.update_timer()` directly from a foreign thread; furthermore, `_handle_async_exception()` is missing an `if not self.async_exceptions:` check before `.pop(0)`.
- **Remediation (Defensive Fix):**
  Maintain a lock-protected in-memory cache for persistent exceptions and synchronize `raise_exception_async` via `threading.Lock()` + `reactor.register_async_callback()`.

---

### [RACE-05] Thread-Safety Violations & `RuntimeError` in Paho MQTT Background Thread (`mqtt.py` & `jsonrpc.py`)
- **File & Lines:** [mqtt.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/mqtt.py#L79-L82), [mqtt.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/mqtt.py#L110-L118), [jsonrpc.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/jsonrpc.py#L122-L127)
- **Severity:** HIGH (Crash of the MQTT network thread)
- **Root Cause Analysis:**
  1. In `mqtt.py`, `_on_connect` and `_on_message` run on the Paho network thread and iterate over `self.subscribed_topics` without a lock while the main thread adds/removes topics (`RuntimeError: dictionary changed size during iteration`). Additionally, `list.remove(h)` (line 201) and `message.payload.decode()` (line 112) are unprotected against `ValueError` and `UnicodeDecodeError`.
  2. In `jsonrpc.py:122-127`, the MQTT message is published **before** inserting `self.pending_requests[request_id]`. If the response arrives on the Paho thread before line 125, it is dropped.
- **Remediation (Defensive Fix):**
  Protect `self.subscribed_topics` with a `threading.Lock()` and register `self.pending_requests[request_id]` **before** calling `publish_topic()`.

---

### [RACE-06] Unsynchronized Access to `self._gcode` & Active Reader Clobbering in `asyncfilereader.py`
- **File & Lines:** [asyncfilereader.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/asyncfilereader.py#L290-L307), [asyncfilereader.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/asyncfilereader.py#L330-L345)
- **Severity:** HIGH (Abrupt truncation of an active print / `AttributeError` in reader thread)
- **Root Cause Analysis:**
  1. `_loop()` checks `if self._gcode is not None and not self._gcode._closed:` without `self._gcode_lock`, while `_handle_close()` sets `self._gcode = None`.
  2. `_AsyncFileReaderSingleton` only stores a single `self._gcode` instance; if a second `AsyncFileReader` is opened during an active print, `_register_gcode()` forcefully closes the first reader, causing the active print to silently terminate with EOF (`''`) on the next `read()`!
- **Remediation (Defensive Fix):**
  Read `self._gcode` into a local variable under `with self._gcode_lock:` and manage a `set` of active readers instead of a single slot.

---

### [RACE-07] Missing Synchronization in `cmd_SET_PID_PROFILE` (`heaters.py`) & RFID Thread (`fm175xx_reader.py`)
- **File & Lines:** [heaters.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/heaters.py#L201-L205), [heaters.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/heaters.py#L476-L499), [fm175xx_reader.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/fm175xx_reader.py#L964-L1025)
- **Severity:** MEDIUM to HIGH (Race condition on PID state & RFID callbacks)
- **Root Cause Analysis:**
  1. `Heater.set_pid_profile()` mutates `self.control.Kp/Ki/Kd` and `temp_integ_max` **without** acquiring `with self.lock:`, while `temperature_callback()` concurrently executes `self.control.temperature_update()`.
  2. `_thread_Check_Card()` in `fm175xx_reader.py` invokes `self._card_info_callback` directly from the background thread instead of via `reactor.register_async_callback()` and modifies `_channel_Trigger` without a lock (`|=`, `&=`).
- **Remediation (Defensive Fix):**
  Wrap `set_pid_profile` in `with self.lock:` and dispatch RFID callbacks onto the reactor thread via `self.reactor.register_async_callback`.

---

## 11. Unhandled Exceptions, Swallowed Exceptions & Faulty Exception Handlers

### [EXC-01] `KeyError` Crash in Main Reactor on Client Disconnect While Write-Blocked + `SelectReactor` / `EPollReactor` Crashes (`reactor.py`)
- **File & Lines:** [reactor.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/reactor.py#L269), [reactor.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/reactor.py#L344-L357), [reactor.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/reactor.py#L366-L409)
- **Severity:** CRITICAL (Full printer crash on webhook client disconnect)
- **Root Cause Analysis:**
  1. **`PollReactor._dispatch_loop` (lines 344–357):** When a webhook client disconnects while its send buffer is full (`POLLHUP | POLLOUT` registered), `poll()` returns an event with **both** bits (`POLLHUP` and `POLLOUT`). The first block `if event & (select.POLLIN | select.POLLHUP):` calls `read_callback`, which detects EOF and calls `unregister_fd()` (`del self._fds[fd]`). Immediately afterward, line 352 checks `if event & select.POLLOUT:` and accesses `self._fds[fd].write_callback` -> **unhandled `KeyError` in the main reactor loop**!
  2. **`SelectReactor._dispatch_loop` (line 269):** Passes `self.write_fds` instead of `self._write_fds` (`AttributeError`).
  3. **`EPollReactor.register_fd` (line 369):** Stores `fds[fd] = read_callback` (function) instead of `file_handler`, but calls `self._fds[fd].read_callback(eventtime)` at line 398 (`AttributeError`).
- **Affected Code:**
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
- **Remediation (Defensive Fix):**
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

### [EXC-02] `EINTR` Permanently Terminates the C Background Thread in `pollreactor.c`
- **File & Lines:** [pollreactor.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/chelper/pollreactor.c#L136-L148)
- **Severity:** CRITICAL (Termination of MCU communication on any POSIX signal)
- **Root Cause Analysis:**
  When `poll()` is interrupted by any POSIX signal (`ret < 0` with `errno == EINTR`), `pollreactor_run()` immediately sets `pr->must_exit = 1` and permanently terminates the MCU's `serialqueue` thread!
- **Remediation (Defensive Fix):**
  ```c
  } else if (ret < 0) {
      if (errno == EINTR)
          continue;
      report_errno("poll", ret);
      pr->must_exit = 1;
  }
  ```

---

### [EXC-03] `UnboundLocalError` (`message`, `probe_session`, `need_save`) & Bare `raise` Outside `except`
- **File & Lines:**
  - [extruder.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/kinematics/extruder.py#L1456-L1484), [extruder.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/kinematics/extruder.py#L1731-L1748)
  - [probe_inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/probe_inductance_coil.py#L1183-L1190)
  - [purifier.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/purifier.py#L877-L944)
  - [filament_feed.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_feed.py#L838), [filament_feed.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_feed.py#L943)
  - [filament_feed_fac_test.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_feed_fac_test.py#L256)
- **Severity:** HIGH (`UnboundLocalError` & `RuntimeError: No active exception to reraise`)
- **Root Cause Analysis:**
  1. `extruder.py`: If `self.Switching_Tool` is neither `'T0'..'T3'` nor `None` (e.g., `""`), `message` remains unbound and `raise self.printer.command_error(message)` raises `UnboundLocalError`.
  2. `probe_inductance_coil.py`: If `start_probe_session` fails in `run_single_probe`, `probe_session.end_probe_session()` in the `finally:` block raises `UnboundLocalError`.
  3. `purifier.py`: If an error occurs before line 914 in `_handle_control_purifier`, `if need_save:` in the `finally:` block raises `UnboundLocalError`.
  4. `filament_feed.py` & `filament_feed_fac_test.py`: Execute a bare `raise` statement outside an `except` block (`RuntimeError: No active exception to reraise`).
- **Remediation (Defensive Fix):**
  Initialize local variables (`message = "Park status error"`, `probe_session = None`, `need_save = False`) before the `try` block and use `raise Exception(...)` instead of a bare `raise` outside `except`.

---

### [EXC-04] Missing `try ... finally:` State Restoration After Probing / Calibration (`extruder_calibration.py`, `probe.py`, `probe_inductance_coil.py`, `flow_calibrator.py`)
- **File & Lines:**
  - [extruder_calibration.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/extruder_calibration.py#L196), [extruder_calibration.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/extruder_calibration.py#L301-L302)
  - [probe.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/probe.py#L130-L141), [probe.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/probe.py#L454-L468)
  - [probe_inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/probe_inductance_coil.py#L537-L541)
  - [flow_calibrator.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/flow_calibrator.py#L1323-L1361)
- **Severity:** CRITICAL (Corrupted Z-probing / Heater left active on error)
- **Root Cause Analysis:**
  1. **`extruder_calibration.py`:** Overwrites `probe_obj.set_mcu_probe(self.mcu_probe)` (setting the optical/analog calibration sensor as the global printer probe!), but never restores the original inductive Z-probe in a `finally:` block if an exception occurs! Every subsequent `G28 Z` or `BED_MESH_CALIBRATE` then uses the wrong sensor and drives the nozzle into the print bed!
  2. **`probe.py`:** `run_single_probe`, `cmd_PROBE_ACCURACY`, and `cmd_PROBE_CALIBRATE` do not call `probe_session.end_probe_session()` inside a `finally:` block (`multi_probe_pending` remains `True` permanently).
  3. **`probe_inductance_coil.py:537-541`:** In the `finally:` block, `self._move(...)` is placed **before** `toolhead.set_accel(cur_accel)`. If `_move` raises an error, the acceleration remains altered.
  4. **`flow_calibrator.py:1323-1361`:** `cmd_FLOW_MEASURE_K` does not turn off the extruder heater in a `finally:` block if an error occurs during measurement (and crashes with `ValueError` on `K_STEP=0` in `range(..., 0)`).
- **Remediation (Defensive Fix):**
  Always restore modified state (`orig_mcu_probe`, `probe_session`, `cur_accel`, heater target temperature) inside `finally:` blocks.

---

### [EXC-05] Unhandled `UnicodeDecodeError`, `ValueError`, `KeyError` & Swallowed `gcmd.error(e)`
- **File & Lines:**
  - [inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/inductance_coil.py#L146-L147): Calls `gcmd.error(e)` **without `raise`** (the exception object is instantiated and immediately discarded!).
  - [filament_protocol.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_protocol.py#L369-L375): Unhandled `UnicodeDecodeError` in `m1_proto_data_parse` on corrupted RFID tag data.
  - [virtual_sdcard.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/virtual_sdcard.py#L1156-L1230): Unhandled `UnicodeDecodeError` and implicit `return None` (causing `TypeError: cannot unpack non-iterable NoneType object`) in `parse_power_loss_move_env`.
  - [filament_parameters.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_parameters.py#L1580-L1607): Unhandled `ValueError`/`AttributeError` in `_version_to_tuple`.
  - [extruder_config_bak.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/extruder_config_bak.py#L78-L80): `TypeError` when the JSON root is `null` or a list.
  - [heaters.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/heaters.py#L327-L334): `KeyError: 'default'` in `ControlPID.__init__` when default PID parameters are absent.
  - [configfile.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/configfile.py#L408-L415): `cmd_SAVE_CONFIG` does not catch `configparser.Error`.
- **Remediation (Defensive Fix):**
  Use `raise gcmd.error(str(e))`, decode with `.decode('utf-8', errors='replace')`, and validate input formats defensively.

---

## 12. Severe Logical Bugs & State-Corruption Bugs

### [LOG-01] Off-by-One Bug in `get_sum()` Triggers Spurious Inductive Z-Sensor Endstop Events (`src/stm32/inductance_coil.c`)
- **File & Lines:** [inductance_coil.c](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/src/stm32/inductance_coil.c#L128-L132)
- **Severity:** CRITICAL (Corrupted frequency calculation & spurious Z-endstop trigger)
- **Root Cause Analysis:**
  `get_sum(MOVING_SUM *ms)` is intended to return `0` until the sliding window (`ms->bufferSize`, default `2`) is completely filled with samples. However, the condition is written as `if (ms->count + 1 < ms->bufferSize || ms->bufferSize == 0) return 0;`.
  When `bufferSize = 2`, after the **very first** sample `ms->count == 1`, so `1 + 1 < 2` (`2 < 2`) already evaluates to `false`! Thus `get_sum()` returns the partial sum on the `(bufferSize - 1)`-th sample, even though `freq_cal_factor` and the trigger thresholds `cmp_trg_cnt_ht/lt` are scaled for `bufferSize` samples! This halves/doubles the measured frequency on the `(bufferSize - 1)`-th sample after every reset.
- **Affected Code:**
  ```c
  uint32_t get_sum(MOVING_SUM *ms) {
    if (ms->count + 1 < ms->bufferSize || ms->bufferSize == 0)
      return 0;
    return ms->sum;
  }
  ```
- **Remediation (Defensive Fix):**
  ```c
  uint32_t get_sum(MOVING_SUM *ms) {
    if (ms->bufferSize == 0 || ms->count < ms->bufferSize)
      return 0;
    return ms->sum;
  }
  ```

---

### [LOG-02] Unreachable `elif os.path.isdir` Branch Breaks Directory Deletion in `queuefile.py`
- **File & Lines:** [queuefile.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/queuefile.py#L105-L109)
- **Severity:** HIGH (`IsADirectoryError` & Dead Code)
- **Root Cause Analysis:**
  For any existing directory, `os.path.exists(op.filename)` returns `True`! Consequently, `op.op_type == "delete"` always enters the first branch (`os.remove(op.filename)` -> raises `IsADirectoryError`), and the `elif os.path.isdir(op.filename): shutil.rmtree(op.filename)` branch is **never reached**. Furthermore, `f.flush()` and `os.fdatasync()` are commented out in `safe_write` (lines 87–88, 128–129).
- **Affected Code:**
  ```python
  elif op.op_type == "delete":
      if os.path.exists(op.filename):
          os.remove(op.filename)
      elif os.path.isdir(op.filename):
          shutil.rmtree(op.filename)
  ```
- **Remediation (Defensive Fix):**
  ```python
  elif op.op_type == "delete":
      if os.path.isdir(op.filename) and not os.path.islink(op.filename):
          shutil.rmtree(op.filename)
      elif os.path.lexists(op.filename):
          os.remove(op.filename)
  ```

---

### [LOG-03] 8-Character RGBA Color Codes Wipe `print_task.json` on Next Reboot (`print_task_config.py`)
- **File & Lines:** [print_task_config.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/print_task_config.py#L223), [print_task_config.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/print_task_config.py#L681-L692), [print_task_config.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/print_task_config.py#L750-L759)
- **Severity:** CRITICAL (Self-destruction of persistent configuration on reboot)
- **Root Cause Analysis:**
  1. In `set_filament_slot()` (lines 681–692), the **8-character RGBA string** (`f"#{color_rgba[:6]}FF"`, 9 chars including `#`) is stored into `self.filament_color_multi['colors'][channel]` and persisted to `print_task.json`. On the next boot, `_early_check()` at line 223 validates `self._is_valid_rgb_color(c)` (which only accepts **6-character RGB strings** `#RRGGBB`!), treats the file as corrupted, and **resets the entire `print_task.json` to factory defaults**!
  2. In `cmd_SET_PRINT_PREFERENCES` (lines 750–759), `'flow_calib_extruders'` is written instead of `'flow_calibrate_extruders'`, rendering the preference ineffective.
- **Remediation (Defensive Fix):**
  Store `f"#{color_rgba[:6]}"` (6-digit RGB) in `self.filament_color_multi['colors'][channel]` at line 685 and fix the key name to `'flow_calibrate_extruders'` at lines 752/756.

---

### [LOG-04] `self.pending_requests.pop(0)` Always Raises `KeyError: 0` and Wipes All 100 In-Flight RPC Requests (`jsonrpc.py`)
- **File & Lines:** [jsonrpc.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/jsonrpc.py#L105-L113)
- **Severity:** HIGH (Mass loss of all in-flight JSON-RPC requests)
- **Root Cause Analysis:**
  `self.pending_requests` is a `dict` whose keys `request_id` start at `1` (`1, 2, 3, ...`). When `len(self.pending_requests) >= 100` is reached, line 109 attempts to evict the oldest item via `self.pending_requests.pop(0)` (as if it were a `list`!). Because key `0` does not exist in the `dict`, `.pop(0)` **always raises `KeyError: 0`**, enters the `except Exception:` block, and executes `self.pending_requests.clear()` — **wiping all 100 active requests simultaneously**!
- **Affected Code:**
  ```python
  if len(self.pending_requests) >= self.max_pending_requests:
      try:
          self.pending_requests.pop(0)
      except Exception:
          self.pending_requests.clear()
  ```
- **Remediation (Defensive Fix):**
  ```python
  if len(self.pending_requests) >= self.max_pending_requests:
      oldest_key = next(iter(self.pending_requests), None)
      if oldest_key is not None:
          self.pending_requests.pop(oldest_key, None)
  ```

---

### [LOG-05] Late-Binding Closure Bug (`i` Is Always `3`) & Missing `y_diff` Check in Park Calibration (`extruder.py`)
- **File & Lines:** [extruder.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/kinematics/extruder.py#L1770-L1776), [extruder.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/kinematics/extruder.py#L2065-L2071), [extruder.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/kinematics/extruder.py#L2110-L2116)
- **Severity:** HIGH (Wrong extruder Vref switch toggled & unchecked Y deviation)
- **Root Cause Analysis:**
  1. At lines 1770–1776, a loop `for i in range(len(extruder_list)):` registers delayed callbacks `lambda e, s=state: extruder_list[i].vref_sw.set_sw(s)`. Because `i` is not bound as a default argument, all callbacks toggle only the **last extruder** (`extruder_list[3]`) after the loop finishes!
  2. In `cmd_MOVE_TO_PARK_CALIBRATION_POINT` (line 2069) and `cmd_VERIFY_PARK_POSITION` (line 2114), `y_diff = abs(cur_pos[1] - park_detector.calibration_point[1])` is computed, but completely omitted from `if x_diff > 0.1:`!
- **Remediation (Defensive Fix):**
  Use `lambda e, s=state, idx=i: extruder_list[idx].vref_sw.set_sw(s)` and `if x_diff > 0.1 or y_diff > 0.1:`.

---

### [LOG-06] Flawed Averaging Over Subset (`/ 9`) in `homing_precise_corexy.py`
- **File & Lines:** [homing_precise_corexy.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/homing_precise_corexy.py#L282-L303)
- **Severity:** CRITICAL (Severe position error during CoreXY precision homing)
- **Root Cause Analysis:**
  In `perform_multi_point_diagonal_probing()`, when outlier points are re-probed (`need_probe_point_index`, e.g., 1 or 2 out of 9 points), `avg = 0` is reset, the loop accumulates **only the re-probed points** (`avg += temp_position`), and line 303 divides by `9` (`avg = avg / 9`)! If only 1 point was re-probed, `avg` is **1/9th of the actual position**!
- **Affected Code:**
  ```python
  if len(need_probe_point_index):
      avg = 0
      for i in need_probe_point_index:
          ...
          avg += temp_position
  avg = avg / 9
  ```
- **Remediation (Defensive Fix):**
  Update `probe_Trigger_position[i] = temp_position` inside the re-probing loop and then average across **all 9 elements**: `avg = sum(probe_Trigger_position) / len(probe_Trigger_position)`.

---

### [LOG-07] Copy-Paste Bug `hole_z` With Fallback `hole_x`, Inverted Determinant Formula & Unchecked `lstsq` in `probe_inductance_coil.py`
- **File & Lines:** [probe_inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/probe_inductance_coil.py#L50-L86), [probe_inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/probe_inductance_coil.py#L316-L330), [probe_inductance_coil.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/probe_inductance_coil.py#L1520)
- **Severity:** CRITICAL (Nozzle/bed crash during nozzle calibration because X coordinate ~150 mm is used as Z height!)
- **Root Cause Analysis:**
  1. Line 1520 reads `hole_z = macro.variables.get('hole_z', hole_x)` instead of `macro.variables.get('hole_z', hole_z)`! If `'hole_z'` is not defined in the macro, the X coordinate (`hole_x`) is used as the Z coordinate!
  2. In `find_circle_center()` (lines 50–86), `center_x` and `center_y` have inverted numerator signs and an unprotected `Decimal` denominator (`DivisionByZero` on collinear points).
  3. In `_find_circle_center()` (lines 316–330 & 493–505), the result of `np.linalg.lstsq` on collinear points is not checked for plausibility before moving the toolhead to that coordinate.
- **Remediation (Defensive Fix):**
  Change line 1520 to `hole_z = macro.variables.get('hole_z', hole_z)` and validate the computed circle center against a maximum allowed offset from the starting position before moving.

---

### [LOG-08] Swapped LED Pins (`white_pin` / `red_pin`) and `max()` Instead of `min()` During Ramp-Up in `filament_feed.py`
- **File & Lines:** [filament_feed.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_feed.py#L137), [filament_feed.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_feed.py#L411-L418), [filament_feed.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_feed.py#L1219-L1222)
- **Severity:** MEDIUM (Swapped error/status LEDs & immediate jump to maximum PWM)
- **Root Cause Analysis:**
  1. `FeedLight.__init__` expects `(printer, white_pin, red_pin)`, but line 416 calls it with `(self.printer, self.light_red_pin[i], self.light_white_pin[i])` (white and red swapped).
  2. Lines 1219 & 1221 use `duty = max(duty + duty_step, max_duty)` instead of `min(...)` when ramping up, jumping immediately to `max_duty` on the very first step.
- **Remediation (Defensive Fix):**
  Fix the argument order in `FeedLight(...)` and use `min(duty + duty_step, max_duty)`.

---

### [LOG-09] Falsy `0.0` Bug Deletes `flow_calibrator.json`, Mutates `DEFAULT_K`, and Returns `None` in `flow_calibrator.py`
- **File & Lines:** [flow_calibrator.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/flow_calibrator.py#L260), [flow_calibrator.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/flow_calibrator.py#L305-L327), [flow_calibrator.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/flow_calibrator.py#L478-L491)
- **Severity:** HIGH (Deletion of valid calibration data & `TypeError` when `k = 0.0`)
- **Root Cause Analysis:**
  1. `_load_flow_calibrate_param()` checks `if not val or not isinstance(val, (int, float)) or val < 0:`. Because `not 0.0` evaluates to `True` in Python, a valid K-factor of `0.0` is treated as corrupted, triggers `raise "invalid flow_calibrator.json"` (raising a string literal!), and deletes the entire `flow_calibrator.json` file! Moreover, `self.flow_calibrate_param = DEFAULT_K` shares the same dictionary reference, mutating `DEFAULT_K` in-place.
  2. `_get_next_k()` implicitly returns `None` when both `area_left == 0` and `area_right == 0`.
- **Remediation (Defensive Fix):**
  Check `if val is None or isinstance(val, bool) or not isinstance(val, (int, float)) or val < 0:`, use `DEFAULT_K.copy()`, and use `elif area_right >= area_left:` in `_get_next_k`.

---

### [LOG-10] `EXCLUDE_OBJECT` Crash & Dead Code plus Hardcoded Z-Stepper Assumption in `virtual_sdcard.py`
- **File & Lines:** [virtual_sdcard.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/virtual_sdcard.py#L1606-L1616), [virtual_sdcard.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/virtual_sdcard.py#L2246-L2264)
- **Severity:** HIGH (`AttributeError` on `EXCLUDE_OBJECT` during power-loss parsing)
- **Root Cause Analysis:**
  1. Line 2248 in `_parse_line_env` calls `self.get(params, 'NAME').upper()`. Because `VirtualSD` has no `self.get()` method (and `NAME` may be absent), the method crashes with `AttributeError`. Additionally, `elif 'END' in params:` is chained under `if 'START' in params:`, so it only executes when `'START'` is **not** in `params`.
  2. Line 1609 in `get_pl_stepper_pos()` hardcodes the assumption that `stepper_mcu_pos[2]` is always the Z stepper instead of checking `stepper_name.startswith('stepper_z')`.
- **Remediation (Defensive Fix):**
  Use `params.get('NAME', '').upper()` and identify the Z stepper by name rather than hardcoded index `2`.

---

### [LOG-11] Flawed Index Check `sorted_sub_idx[idx] == idx` in `bed_mesh.py`
- **File & Lines:** [bed_mesh.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/bed_mesh.py#L1460-L1462)
- **Severity:** MEDIUM (Incorrect mapping of sub-mesh points)
- **Root Cause Analysis:**
  In `substitute_points()`, `if idx < len(sorted_sub_idx) and sorted_sub_idx[idx] == idx:` is checked instead of `if idx in sorted_sub_idx:`. Whenever `sorted_sub_idx` is not a contiguous `[0, 1, 2, ...]` starting at index 0, `sorted_sub_idx[idx] == idx` fails for all subsequent indices!
- **Remediation (Defensive Fix):**
  Precompute `sub_idx_set = set(sorted_sub_idx)` and check `if idx in sub_idx_set:`.

---

### [LOG-12] Unconditional Z-Move & Reset to `PRINTING` in `finally:` Block After Print Cancellation (`defect_detection.py`)
- **File & Lines:** [defect_detection.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/defect_detection.py#L942-L961)
- **Severity:** HIGH (Unexpected Z movement & wrong printer state after abort/shutdown)
- **Root Cause Analysis:**
  In the `finally:` block of `cmd_FOREIGN_OBJECT_DETECT`, the printer state is unconditionally set back to `PRINTING` and `toolhead.manual_move([None, None, z_pos], ...)` is executed — even when detection was aborted due to a shutdown, emergency stop, or user cancellation.
- **Remediation (Defensive Fix):**
  In the `finally:` block, verify `not self.printer.is_shutdown()` and check whether the previous state should actually be restored.

---

### [LOG-13] Corrupted Error Code Formatting in `klippy.py`, `serialhdl.py`, `homing.py` and `"serial: None"` in `printer_device_scan.py`
- **File & Lines:**
  - [klippy.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/klippy.py#L581): `coded = f"{level:04d}-{id:04d}-{code:04d}-{level:04d}"` places `code` in the `index` slot and `level` in the `code` slot.
  - [serialhdl.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/serialhdl.py#L323-L324) & [homing.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/homing.py#L96): Use `"%4d"` (space-padding `"   0"`) instead of `"%04d"` (zero-padding `"0000"`).
  - [printer_device_scan.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/printer_device_scan.py#L74-L88): Writes the literal string `"serial: None"` into `printer.cfg` when an MCU device is not found during scanning (`info_list[index] is None`).
- **Remediation (Defensive Fix):**
  Use `f"{level:04d}-{id:04d}-{index:04d}-{code:04d}"` in `klippy.py:581`, replace `"%4d"` with `"%04d"`, and skip entries where `info_list[index] is None` in `printer_device_scan.py`.

---

### [LOG-14] Configuration Typos & Missing Section Prefixes in `extruder_calibration.py`, `filament_entangle_detect.py`, `mqtt.py`
- **File & Lines:**
  - [extruder_calibration.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/extruder_calibration.py#L79-L85), [extruder_calibration.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/extruder_calibration.py#L223-L224): Line 79 reads `config.getint('_probe_mode', ...)` without the `section +` prefix; line 84 initializes `extruder_y_cal_second_positions` only when `section == 'x'`, while line 224 accesses the misspelled key `self.cal_params['extruder_y_cal_second_posiions']` (missing `'t'`) -> guaranteed `KeyError`.
  - [filament_entangle_detect.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/filament_entangle_detect.py#L148-L151): Checks `self.extruder_name + "0"`, which becomes `"extruder10"` for `extruder1`.
  - [mqtt.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/mqtt.py#L155), [mqtt.py](file:///e:/KI%20Projekte/u1-klipper-main/u1-klipper-main/klippy/extras/mqtt.py#L212): `qos = qos or self.qos` overwrites an explicitly passed `qos=0` with `self.qos`.
- **Remediation (Defensive Fix):**
  Fix the typos `'extruder_y_cal_second_positions'` and `section + '_probe_mode'`, check `"extruder0"` directly in `filament_entangle_detect.py`, and use `qos = self.qos if qos is None else qos` in `mqtt.py`.
