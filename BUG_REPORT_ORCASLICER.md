# Comprehensive Systematic Bug & Security Audit Report: OrcaSlicer & u1-klipper

**Project:** Snapmaker OrcaSlicer (v2.4.1) & Snapmaker U1 Klipper Firmware (u1-klipper)  
**Method:** `/systematic-debugging` (Exhaustive static and logical code analysis across all subsystems: C++ Slicing Engine `src/libslic3r/`, Network & IPC `src/slic3r/Utils/`, GUI `src/slic3r/GUI/`, Machine Profiles `submodules/Profiles/Snapmaker/`, as well as Klipper Firmware `u1-klipper/klippy/` and Hardware Configurations `u1-klipper/lava/`)  
**Audited Vulnerability & Bug Classes:**
1. Zero Day & Security Vulnerabilities (Remote Code Execution via WebView IPC, unvalidated protocol execution, TLS certificate verification bypass, plaintext credential logging, insecure temporary files)
2. Buffer Overflows & Out-of-Bounds Access (Stack buffer overflow via sprintf, vector OOB access, character buffer length under-read)
3. Integer Overflows, Underflows & Truncation (64-bit to 32-bit file size truncation, atomic counter underflow)
4. Division by Zero (WipeTower2 division by zero on thin grid spacing, floating point NaN propagation)
5. Null Pointer Dereference / Segfaults (Unchecked pointer accesses on get_curr_plate(), m_agent, incompatible wstring-to-char casts)
6. Memory Leaks, Socket & Handle Leaks (Expat XML parser leaks, Ams object leaks, unreleased sockets on connection failure)
7. Dangling Pointers & Use-After-Free (Thread detach in Http destructor, asynchronous MQTT lambdas capturing raw this)
8. Deadlocks & Thread Hangs (Unbounded blocking reads without timeout in WebSocketClient)
9. Race Conditions & Concurrency (Unsynchronized curl_global_init, non-atomic cancellation flags)
10. Logical & Parsing Bugs (Missing break statements, switch fallthrough bugs, incorrect host path trimming)
11. Cross-System Interface, Firmware, API, Variable & Data Type Conflicts (G-code syntax conflicts, unknown macro parameters, variable naming discrepancies, data type validation errors, extruder index mismatch, color code formatting, physical coordinate boundary violations)

---

## Table of Contents & Summary by Bug Class

| No. | Bug Class | Verified Findings | Maximum Severity | Key Affected Modules |
| :--- | :--- | :---: | :---: | :--- |
| **1** | **Zero Day & Security Vulnerabilities** | 5 | **CRITICAL** | `SSWCP.cpp`, `PrinterWebView.cpp`, `Http.cpp`, `MQTT.cpp` |
| **2** | **Buffer Overflows & Out-of-Bounds** | 4 | **CRITICAL** | `AMF.cpp`, `fdm_U1.json`, `DeviceManager.cpp`, `SSWCP.cpp` |
| **3** | **Integer Overflows / Underflows / Truncation** | 2 | **HIGH** | `Http.cpp`, `MQTT.cpp` |
| **4** | **Division by Zero** | 3 | **CRITICAL** | `WipeTower2.cpp` |
| **5** | **Null Pointer / Segfaults / Incompatible Casts** | 4 | **CRITICAL** | `Plater.cpp`, `Monitor.cpp`, `Http.cpp`, `AMF.cpp` |
| **6** | **Memory, Socket & Handle Leaks** | 4 | **HIGH** | `AMF.cpp`, `DeviceManager.cpp`, `SSWCP.cpp` |
| **7** | **Dangling Pointers & Use-After-Free** | 2 | **CRITICAL** | `Http.cpp`, `MQTT.cpp` |
| **8** | **Deadlocks & Thread Hangs** | 2 | **HIGH** | `WebSocketClient.hpp`, `MQTT.cpp` |
| **9** | **Race Conditions & Concurrency** | 1 | **HIGH** | `Http.cpp` |
| **10** | **Logical & Parsing Bugs** | 2 | **HIGH** | `AMF.cpp`, `WebSocketClient.hpp` |
| **11** | **Cross-System Interface & Firmware Conflicts (OrcaSlicer vs. u1-klipper)** | 10 | **CRITICAL** | `Snapmaker U1 (0.4 nozzle).json`, `fdm_U1.json`, `GatewayDevice.cpp`, `GatewayProtocol.cpp`, `print_task_config.py`, `bed_mesh.py` |

**Total Count of Documented and Verified Findings:** 39

---

## 1. Zero Day & Security Vulnerabilities

### [SEC-01] Arbitrary URI Scheme Execution & Remote Code Execution via WebView IPC (`SSWCP.cpp` & `PrinterWebView.cpp`)
- **File & Lines:** [SSWCP.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/SSWCP.cpp#L692-L715), [PrinterWebView.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/PrinterWebView.cpp#L244-L252)
- **Severity:** CRITICAL (CWE-20: Improper Input Validation, CWE-937, CWE-78: OS Command Injection)
- **Root Cause Analysis:**
  In `PrinterWebView::OnScriptMessage`, all script messages dispatched from any loaded web page (such as Fluidd, Mainsail, third-party printer interfaces, or external redirects) are directly passed without origin verification to `SSWCP::handle_web_message`. There, `SSWCP_Instance::sw_OpenBrowser` handles the `"sw_OpenBrowser"` command by extracting `m_param_data["url"]` with zero sanitization and passing it to `wxLaunchDefaultBrowser(wx_url)`. On Windows, this delegates to the Win32 API `ShellExecuteEx`. An attacker or compromised local web interface can trigger arbitrary protocol schemes (`file:///`, `smb://`, `ms-msdt:`, `calculator:`, `powershell:`) to execute local binaries or exfiltrate local files.
- **Affected Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/GUI/SSWCP.cpp:692
  void SSWCP_Instance::sw_OpenBrowser() {
      try {
          std::string url = m_param_data.count("url") ? m_param_data["url"].get<std::string>() : "";
          wxString wx_url  = wxString::FromUTF8(url);
          ...
          wxGetApp().CallAfter([wx_url, weak_self]() {
              ...
              bool res = wxLaunchDefaultBrowser(wx_url);
              ...
          });
      }
  }
  ```
- **Remediation Proposal (Defensive Patch):**
  Enforce strict URI scheme whitelisting for `http://` and `https://` only, and validate destination domains against an allowlist:
  ```cpp
  void SSWCP_Instance::sw_OpenBrowser() {
      try {
          std::string url = m_param_data.value("url", "");
          if (url.rfind("http://", 0) != 0 && url.rfind("https://", 0) != 0) {
              BOOST_LOG_TRIVIAL(error) << "Blocked unauthorized browser scheme: " << url;
              handle_general_fail(-1, "Unauthorized URL scheme");
              return;
          }
          wxString wx_url = wxString::FromUTF8(url);
          ...
      }
  }
  ```

---

### [SEC-02] Global TLS Certificate Verification Disabled by Default in HTTP Client (`Http.cpp`)
- **File & Lines:** [Http.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/Http.cpp#L205-L206)
- **Severity:** CRITICAL (CWE-295: Improper Certificate Validation)
- **Root Cause Analysis:**
  In `Http::priv::priv`, `CURLOPT_SSL_VERIFYPEER` and `CURLOPT_SSL_VERIFYHOST` are hardcoded to `0L` for every HTTP connection. This completely disables TLS certificate chain verification, expiration checking, and hostname matching. Any Man-in-the-Middle (MitM) attacker on the local network can intercept and tamper with 3D model downloads, firmware updates, crash reports, and authentication credentials.
- **Affected Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/Utils/Http.cpp:205
  ::curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L);
  ::curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 0L);
  ```
- **Remediation Proposal (Defensive Patch):**
  Enable strict TLS verification by default and leverage the OS native certificate store:
  ```cpp
  ::curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
  ::curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
  #ifdef _WIN32
  ::curl_easy_setopt(curl, CURLOPT_SSL_OPTIONS, CURLSSLOPT_NATIVE_CA);
  #endif
  ```

---

### [SEC-03] Insecure Temporary File Creation for Private Keys in MQTT Client (`MQTT.cpp`)
- **File & Lines:** [MQTT.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp#L84-L120)
- **Severity:** HIGH (CWE-377: Insecure Temporary File, CWE-59: Improper Link Resolution Before File Access)
- **Root Cause Analysis:**
  In `MqttClient::init_ssl`, received CA certificates, client certificates, and private keys are written to predictable files in the world-writable system temporary directory (`temp_dir / ("key_" + client_id + std::to_string(int64_t(this)) + ".key")`). Standard file creation flags are used without restrictive permissions (such as 0600). Local unprivileged processes can monitor the directory, read private keys in plaintext, or execute pre-created symlink attacks to overwrite arbitrary user files.
- **Affected Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp:110
  boost::filesystem::path key_path = temp_dir / ("key_" + client_id + std::to_string(int64_t(this)) + ".key");
  if (!key_content.empty()) {
      boost::filesystem::ofstream key_file(key_path);
      key_file << key_content;
      key_file.close();
  }
  ```
- **Remediation Proposal (Defensive Patch):**
  Generate temporary files with cryptographically secure unique identifiers and exclusive POSIX permissions (0600), or configure OpenSSL contexts directly in memory via `SSL_CTX_use_PrivateKey` without writing to disk.

---

### [SEC-04] Plaintext Logging of Sensitive TLS Certificates, CAs, and Credentials (`MQTT.cpp`)
- **File & Lines:** [MQTT.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp#L74-L75)
- **Severity:** HIGH (CWE-532: Insertion of Sensitive Information into Log File)
- **Root Cause Analysis:**
  During SSL connection initialization, `BOOST_LOG_TRIVIAL(info)` logs the complete string contents of `ca_content`, `cert_content`, and `username_` unmasked to persistent disk logs.
- **Affected Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp:74
  BOOST_LOG_TRIVIAL(info) << "[MQTT_INFO] initializing MQTT SSL connection, server_address: " << server_address_
      << ", ca_content: " << ca_content << ", cert_content: " << cert_content << ", username: " << username_;
  ```
- **Remediation Proposal (Defensive Patch):**
  Never log raw cryptographic material; report only boolean flags or character counts:
  ```cpp
  BOOST_LOG_TRIVIAL(info) << "[MQTT_INFO] initializing MQTT SSL connection, server_address: " << server_address_
      << ", ca_present: " << !ca_content.empty() << ", cert_present: " << !cert_content.empty();
  ```

---

### [SEC-05] Disabled TLS Server Certificate Verification in MQTT Options (`MQTT.cpp`)
- **File & Lines:** [MQTT.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp#L123)
- **Severity:** HIGH (CWE-295: Improper Certificate Validation)
- **Root Cause Analysis:**
  `ssl_opts.set_verify(false);` explicitly disables certificate validation in the Paho MQTT C++ client options.
- **Affected Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp:122
  mqtt::ssl_options ssl_opts;
  ssl_opts.set_verify(false);
  ssl_opts.set_enable_server_cert_auth(true);
  ```
- **Remediation Proposal (Defensive Patch):**
  Enable `ssl_opts.set_verify(true);` and enforce proper certificate authority verification.

---

## 2. Buffer Overflows & Out-of-Bounds Access

### [BOF-01] Classic Stack Buffer Overflow via `sprintf` in `AMF.cpp`
- **File & Lines:** [AMF.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/libslic3r/Format/AMF.cpp#L989-L992)
- **Severity:** CRITICAL (CWE-121: Stack-based Buffer Overflow)
- **Root Cause Analysis:**
  In `extract_model_from_archive`, a fixed-size stack buffer `char error_buf[1024];` is allocated. Subsequently, `::sprintf` is called with unbounded input from `data->stat.m_filename` (which can reach up to 65,535 bytes under the standard ZIP specification) concatenated with the parser error message. Loading a crafted AMF or 3MF archive file overflows the stack frame, allowing arbitrary code execution or causing a catastrophic crash.
- **Affected Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/libslic3r/Format/AMF.cpp:989
  char error_buf[1024];
  ::sprintf(error_buf, "Parsing file %s error at line %d: {%s}", data->stat.m_filename, (int) XML_GetCurrentLineNumber(data->parser), data->ctx.error_message());
  throw Slic3r::FileIOError(error_buf);
  ```
- **Remediation Proposal (Defensive Patch):**
  Replace with `snprintf` or modern C++ string formatting:
  ```cpp
  std::string err_msg = (boost::format("Parsing file %s error at line %d: {%s}") 
      % data->stat.m_filename % (int) XML_GetCurrentLineNumber(data->parser) % data->ctx.error_message()).str();
  throw Slic3r::FileIOError(err_msg);
  ```

---

### [BOF-02] Vector Out-of-Bounds Access on Non-Existent 6th Extruder in `fdm_U1.json`
- **File & Lines:** [fdm_U1.json](file:///E:/KI%20Projekte/OrcaSlicer/submodules/Profiles/Snapmaker/machine/fdm_U1.json#L183)
- **Severity:** HIGH (CWE-125: Out-of-bounds Read)
- **Root Cause Analysis:**
  In the machine start G-code of `fdm_U1.json`, the expression references `is_extruder_used[5]` and `first_layer_temperature[5]`. The machine profile defines arrays with at most 5 elements (indices 0 through 4). Evaluating index 5 causes an out-of-bounds array access in the Slic3r expression interpreter.
- **Affected Code:**
  ```json
  "machine_start_gcode": "PRINT_START ... {if is_extruder_used[4]}T4_TEMP={first_layer_temperature[4]}{endif} {if is_extruder_used[5]}T5_TEMP={first_layer_temperature[5]}{endif} ..."
  ```
- **Remediation Proposal (Defensive Patch):**
  Constrain the machine start G-code macro to the 4 physical extruders supported by the Snapmaker U1 hardware (indices 0 to 3).

---

### [BOF-03] Vector Out-of-Bounds Access in `m_extder_data.extders` (`DeviceManager.cpp`)
- **File & Lines:** [DeviceManager.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/DeviceManager.cpp#L736-L757), [DeviceManager.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/DeviceManager.cpp#L3412), [DeviceManager.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/DeviceManager.cpp#L3585)
- **Severity:** HIGH (CWE-125: Out-of-bounds Read/Write)
- **Root Cause Analysis:**
  Throughout `DeviceManager.cpp`, direct indexing `m_extder_data.extders[MAIN_NOZZLE_ID]` occurs without verifying whether `m_extder_data.extders` is non-empty. For devices where extruders have not yet been queried or populated, this results in an immediate crash.
- **Remediation Proposal (Defensive Patch):**
  Add explicit boundary checks prior to access:
  ```cpp
  if (MAIN_NOZZLE_ID < m_extder_data.extders.size()) {
      m_extder_data.extders[MAIN_NOZZLE_ID].ext_has_filament = hw_switch_state;
  }
  ```

---

### [BOF-04] Character Buffer Length Under-Read with Multi-Byte UTF-8 in `WCP_Logger::worker`
- **File & Lines:** [SSWCP.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/SSWCP.cpp#L195)
- **Severity:** MEDIUM (CWE-125 / CWE-135)
- **Root Cause Analysis:**
  `asio::write(*socket, asio::buffer(log.ToUTF8().data(), log.length() + 1), ec);` passes `log.length()` as the byte buffer length. In wxWidgets, `log.length()` returns the number of UTF-16 code units (characters). However, multi-byte UTF-8 sequences (German umlauts, accented characters, Chinese/Japanese glyphs) require 2 to 4 bytes per character. Consequently, multi-byte log messages are truncated or split mid-glyph.
- **Remediation Proposal (Defensive Patch):**
  Query the actual byte count from the UTF-8 buffer directly:
  ```cpp
  const wxScopedCharBuffer utf8 = log.ToUTF8();
  asio::write(*socket, asio::buffer(utf8.data(), utf8.length()), ec);
  ```

---

## 3. Integer Overflows, Underflows & Truncation

### [INT-01] 32-Bit File Size Truncation for Uploads Exceeding 2 GB in `Http.cpp`
- **File & Lines:** [Http.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/Http.cpp#L413)
- **Severity:** HIGH (CWE-197: Numeric Truncation Error)
- **Root Cause Analysis:**
  `::curl_easy_setopt(curl, CURLOPT_INFILESIZE, filesize);` uses `CURLOPT_INFILESIZE`, which takes a 32-bit signed `long` under 64-bit Windows (MSVC LLP64 data model). Files larger than 2,147,483,647 bytes experience integer overflow and truncation, resulting in corrupted uploads.
- **Remediation Proposal (Defensive Patch):**
  Use the 64-bit cURL option:
  ```cpp
  ::curl_easy_setopt(curl, CURLOPT_INFILESIZE_LARGE, static_cast<curl_off_t>(filesize));
  ```

---

### [INT-02] Negative Atomic Underflow in `MqttClient::pending_reconnect_checks`
- **File & Lines:** [MQTT.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp#L487)
- **Severity:** MEDIUM (CWE-191: Integer Underflow)
- **Root Cause Analysis:**
  In `MqttClient::connection_lost`, `pending_reconnect_checks.fetch_add(1)` is executed on line 515 without matching decrements in certain early exit branches. If counter updates desynchronize, negative underflows break the destructor loop `while (pending_reconnect_checks.load(...) > 0)`.
- **Remediation Proposal (Defensive Patch):**
  Ensure symmetric increment/decrement tracking and guard decrements with `val > 0`.

---

## 4. Division by Zero (Hardware Faults & Logic Errors)

### [DIV-01] Division by Zero in Empty WipeTower Grid Calculation (`WipeTower2.cpp`)
- **File & Lines:** [WipeTower2.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/libslic3r/GCode/WipeTower2.cpp#L2702-L2703)
- **Severity:** CRITICAL (CWE-369: Divide By Zero)
- **Root Cause Analysis:**
  In `generate_empty_grid`, the code computes:
  `int n = dy / (m_perimeter_width * sparse_factor); float spacing = (dy - m_perimeter_width) / (n - 1);`
  When `dy` is small and `n == 1`, `(n - 1) == 0`. Dividing by zero produces `+inf` or `NaN`. Subsequent integer casts in `int loops_num = (m_wipe_tower_brim_width + spacing / 2.f) / spacing;` trigger undefined behavior (evaluating to `0x80000000` on x86) and hardware floating-point exceptions.
- **Affected Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/libslic3r/GCode/WipeTower2.cpp:2702
  int   n       = dy / (m_perimeter_width * sparse_factor);
  float spacing = (dy - m_perimeter_width) / (n - 1);
  int   i       = 0;
  for (i = 0; i < n; ++i) {
      writer.extrude(writer.x(), y, feedrate).extrude(i % 2 ? left : right, y);
      y = y + spacing;
  }
  ```
- **Remediation Proposal (Defensive Patch):**
  Guard the divisor against zero:
  ```cpp
  int n = dy / (m_perimeter_width * sparse_factor);
  float spacing = (n > 1) ? ((dy - m_perimeter_width) / (n - 1)) : 0.f;
  ```

---

### [DIV-02] Identical Division by Zero in Sparse Infill (`WipeTower2.cpp`)
- **File & Lines:** [WipeTower2.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/libslic3r/GCode/WipeTower2.cpp#L2913-L2914), [WipeTower2.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/libslic3r/GCode/WipeTower2.cpp#L4510-L4511)
- **Severity:** CRITICAL (CWE-369)
- **Root Cause Analysis:**
  The identical calculation `float spacing = (dy - m_perimeter_width) / (n - 1);` appears in two additional locations without checking for `n > 1`.
- **Remediation Proposal (Defensive Patch):**
  Implement conditional check `(n > 1)` at both locations.

---

### [DIV-03] Division by Zero for Zero Extrusion Length in `WipeTower2::volume_to_length`
- **File & Lines:** [WipeTower2.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/libslic3r/GCode/WipeTower2.cpp#L489), [WipeTower2.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/libslic3r/GCode/WipeTower2.cpp#L655)
- **Severity:** HIGH (CWE-369)
- **Root Cause Analysis:**
  The calculation `volume / (layer_height * (line_width - layer_height * (1.f - float(M_PI) / 4.f)))` divides by zero whenever `layer_height == 0.f` or `line_width == layer_height * (1 - PI/4)`.
- **Remediation Proposal (Defensive Patch):**
  Validate the denominator against an epsilon threshold (`> 1e-5f`) prior to division.

---

## 5. Null Pointer Dereference, Segfaults & Type Casts

### [NPE-01] Unchecked Null Pointer Dereference on `get_curr_plate()` in `Plater.cpp`
- **File & Lines:** [Plater.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/Plater.cpp#L12792), [Plater.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/Plater.cpp#L13670), [Plater.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/Plater.cpp#L15147), [Plater.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/Plater.cpp#L15449), [Plater.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/Plater.cpp#L15513), [Plater.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/Plater.cpp#L21603)
- **Severity:** CRITICAL (CWE-476: NULL Pointer Dereference)
- **Root Cause Analysis:**
  `partplate_list.get_curr_plate()` returns `nullptr` when all plates are deleted or during plater re-initialization. Dozens of call sites directly dereference the returned pointer (`partplate_list.get_curr_plate()->empty()`, `->update_apply_result_invalid()`, `->can_slice()`), triggering immediate `EXCEPTION_ACCESS_VIOLATION` crashes.
- **Affected Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/GUI/Plater.cpp:12792
  bool plate_empty = partplate_list.get_curr_plate()->empty();
  ```
- **Remediation Proposal (Defensive Patch):**
  Check pointer validity prior to invocation:
  ```cpp
  PartPlate* curr_plate = partplate_list.get_curr_plate();
  bool plate_empty = curr_plate ? curr_plate->empty() : true;
  ```

---

### [NPE-02] Unchecked Method Invocation on `m_agent` in `Monitor.cpp`
- **File & Lines:** [Monitor.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/Monitor.cpp#L361)
- **Severity:** HIGH (CWE-476: NULL Pointer Dereference)
- **Root Cause Analysis:**
  Line 350 checks `if (m_agent)` before accessing the agent, but line 361 invokes `m_agent->refresh_connection();` unconditionally. The surrounding `catch (...)` block does not catch hardware access violations.
- **Affected Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/GUI/Monitor.cpp:360
  try {
      m_agent->refresh_connection();
  }
  catch (...) { ; }
  ```
- **Remediation Proposal (Defensive Patch):**
  ```cpp
  if (m_agent) {
      try {
          m_agent->refresh_connection();
      } catch (const std::exception& e) {
          BOOST_LOG_TRIVIAL(error) << e.what();
      }
  }
  ```

---

### [NPE-03] Incompatible Raw Pointer Cast from `std::wstring` to `char*` in `Http.cpp`
- **File & Lines:** [Http.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/Http.cpp#L676)
- **Severity:** CRITICAL (CWE-843: Access of Resource Using Incompatible Type)
- **Root Cause Analysis:**
  In `Http::form_add_file(const std::wstring& name, ...)`, the code executes `(char*)name.c_str()`. On Windows, `wchar_t` is 2 bytes wide (UTF-16 LE). Directly reinterpreting the buffer as a `char*` causes the second byte (0x00 for ASCII characters) to be parsed as a null terminator, corrupting the form parameter name and causing memory safety violations in cURL.
- **Affected Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/Utils/Http.cpp:674
  Http& Http::form_add_file(const std::wstring& name, const fs::path& path, boost::filesystem::ifstream::off_type offset, size_t length)
  {
      if (p) { p->form_add_file((char*)name.c_str(), path.c_str(), nullptr, offset, length); }
      return *this;
  }
  ```
- **Remediation Proposal (Defensive Patch):**
  Convert `std::wstring` cleanly to UTF-8 `std::string`:
  ```cpp
  Http& Http::form_add_file(const std::wstring& name, const fs::path& path, boost::filesystem::ifstream::off_type offset, size_t length)
  {
      if (p) { 
          std::string utf8_name = boost::nowide::narrow(name);
          p->form_add_file(utf8_name.c_str(), path.string().c_str(), nullptr, offset, length); 
      }
      return *this;
  }
  ```

---

### [NPE-04] Inconsistent Stack State & Null Pointer Access in AMF Parser (`AMF.cpp`)
- **File & Lines:** [AMF.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/libslic3r/Format/AMF.cpp#L250-L290)
- **Severity:** HIGH (CWE-476)
- **Root Cause Analysis:**
  When an `<object>` tag lacks an `id` attribute, `this->stop()` is called but leaves the stack `m_path` unpopped. Subsequent XML callback handlers attempt to access `m_object`, which remains `nullptr`.
- **Remediation Proposal (Defensive Patch):**
  Perform explicit null checks before accessing `m_object` or `m_volume`.

---

## 6. Memory, Socket & Handle Leaks

### [LEAK-01] Permanent Memory Leak of Expat XML Parser Instance in `AMF.cpp`
- **File & Lines:** [AMF.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/libslic3r/Format/AMF.cpp#L958-L1021)
- **Severity:** HIGH (CWE-401: Missing Release of Memory after Effective Lifetime)
- **Root Cause Analysis:**
  `XML_Parser parser = XML_ParserCreate(nullptr);` is allocated in `extract_model_from_archive`. Neither normal return paths nor exception handlers ever invoke `XML_ParserFree(parser);`. Every AMF archive extraction permanently leaks the Expat parser context and internal hash tables.
- **Remediation Proposal (Defensive Patch):**
  Manage parser lifetime using an RAII scope guard:
  ```cpp
  XML_Parser parser = XML_ParserCreate(nullptr);
  if (!parser) return false;
  auto parser_cleanup = boost::make_scope_exit([&parser]() { XML_ParserFree(parser); });
  ```

---

### [LEAK-02] Total Leakage of `Ams` Objects in `MachineObject` Destructor (`DeviceManager.cpp`)
- **File & Lines:** [DeviceManager.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/DeviceManager.cpp#L665-L674)
- **Severity:** HIGH (CWE-401)
- **Root Cause Analysis:**
  The destructor loops over `amsList`, deletes `trayList` entries via `delete tray_it->second;`, but fails to call `delete it->second;` prior to `amsList.clear()`. All `Ams` instances allocated via `new Ams(...)` are permanently leaked.
- **Affected Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/GUI/DeviceManager.cpp:665
  for (auto it = amsList.begin(); it != amsList.end(); it++) {
      for (auto tray_it = it->second->trayList.begin(); tray_it != it->second->trayList.end(); tray_it++) {
          if (tray_it->second) {
              delete tray_it->second;
              tray_it->second = nullptr;
          }
      }
      it->second->trayList.clear();
      // MISSING: delete it->second;
  }
  amsList.clear();
  ```
- **Remediation Proposal (Defensive Patch):**
  ```cpp
  for (auto it = amsList.begin(); it != amsList.end(); it++) {
      for (auto tray_it = it->second->trayList.begin(); tray_it != it->second->trayList.end(); tray_it++) {
          delete tray_it->second;
      }
      it->second->trayList.clear();
      delete it->second;
  }
  amsList.clear();
  ```

---

### [LEAK-03] Socket and Resolver Leak on Connection Failure in `WCP_Logger::run` (`SSWCP.cpp`)
- **File & Lines:** [SSWCP.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/SSWCP.cpp#L120-L130)
- **Severity:** HIGH (CWE-401 / CWE-775)
- **Root Cause Analysis:**
  `socket = new tcp::socket(io_ctx); resolver = new tcp::resolver(io_ctx);` are created via raw `new`. If `asio::connect(*socket, ...)` fails (e.g., port 50000 is closed), the method immediately returns `false` without freeing the allocated objects, leaking sockets and file descriptors on every reconnection attempt.
- **Remediation Proposal (Defensive Patch):**
  Wrap handles in `std::unique_ptr<tcp::socket>` and `std::unique_ptr<tcp::resolver>`.

---

### [LEAK-04] Modeless Dialog Window Leak in `SSWCP_Instance::sw_OpenOrcaWebview`
- **File & Lines:** [SSWCP.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/GUI/SSWCP.cpp#L728-L733)
- **Severity:** MEDIUM (CWE-401)
- **Root Cause Analysis:**
  `auto dialog = new WebUrlDialog(); dialog->Show();` creates a modeless dialog with no parent and no automatic destruction logic. Repeated invocations leak dialog handles and GDI resources.
- **Remediation Proposal (Defensive Patch):**
  Bind `wxEVT_CLOSE_WINDOW` to trigger `Destroy()`.

---

## 7. Dangling Pointers & Use-After-Free

### [UAF-01] Use-After-Free via `io_thread.detach()` in `Http` Destructor (`Http.cpp`)
- **File & Lines:** [Http.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/Http.cpp#L539-L545)
- **Severity:** CRITICAL (CWE-416: Use After Free)
- **Root Cause Analysis:**
  When an `Http` object is destroyed, `Http::~Http()` invokes `p->io_thread.detach();`. Immediately thereafter, the `std::unique_ptr<priv> p` is destructed and its memory deallocated. The detached background thread continues running in `priv::perform`, attempting to access deallocated members (`curl`, `buffer`, etc.), causing heap corruption and segmentation faults.
- **Affected Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/Utils/Http.cpp:539
  Http::~Http()
  {
      assert(! p || ! p->putFile);
      if (p && p->io_thread.joinable()) {
          p->io_thread.detach();
      }
  }
  ```
- **Remediation Proposal (Defensive Patch):**
  Signal cancellation and join the thread synchronously during destruction:
  ```cpp
  Http::~Http()
  {
      if (p) {
          p->cancel();
          if (p->io_thread.joinable()) {
              p->io_thread.join();
          }
      }
  }
  ```

---

### [UAF-02] Use-After-Free & Race Condition in `MqttClient::CheckConnected()` (`MQTT.cpp`)
- **File & Lines:** [MQTT.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp#L407-L425)
- **Severity:** HIGH (CWE-416 / CWE-362)
- **Root Cause Analysis:**
  `std::async(std::launch::async, [this]() { ... })` captures the raw `this` pointer. If `MqttClient` is destroyed before the asynchronous operation completes, the background thread executes on dangling memory.
- **Remediation Proposal (Defensive Patch):**
  Derive from `std::enable_shared_from_this` and capture a `std::weak_ptr`.

---

## 8. Deadlocks & Thread Hangs

### [DLK-01] Unbounded Synchronous Read without Timeout in `WebSocketClient::receive` (`WebSocketClient.hpp`)
- **File & Lines:** [WebSocketClient.hpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/WebSocketClient.hpp#L67-L76)
- **Severity:** HIGH (CWE-834: Excessive Iteration / Hang)
- **Root Cause Analysis:**
  In `WebSocketClient::receive(int timeout = 0)`, the `timeout` parameter is ignored. `ws_.read(buffer);` blocks synchronously and indefinitely. If the Moonraker or Klipper service drops the connection ungracefully, the calling thread hangs forever.
- **Affected Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/Utils/WebSocketClient.hpp:67
  std::string receive(int timeout = 0){
      beast::flat_buffer buffer;
      ws_.read(buffer);
      return beast::buffers_to_string(buffer.data());
  }
  ```
- **Remediation Proposal (Defensive Patch):**
  Configure a Beast stream timeout before read operations:
  ```cpp
  std::string receive(int timeout_seconds = 5) {
      beast::flat_buffer buffer;
      beast::get_lowest_layer(ws_).expires_after(std::chrono::seconds(timeout_seconds > 0 ? timeout_seconds : 5));
      ws_.read(buffer);
      return beast::buffers_to_string(buffer.data());
  }
  ```

---

### [DLK-02] Blocking `std::future` Destructor in `MqttClient::CheckConnected`
- **File & Lines:** [MQTT.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/MQTT.cpp#L407)
- **Severity:** MEDIUM (CWE-833: Deadlock / Thread Hang)
- **Root Cause Analysis:**
  The temporary `std::future` returned by `std::async(std::launch::async, ...)` blocks in its destructor until the task completes, defeating asynchronous execution and causing UI stutter during network delays.
- **Remediation Proposal (Defensive Patch):**
  Use non-blocking task queues or explicit worker thread management.

---

## 9. Race Conditions & Concurrency

### [RCE-01] Unsynchronized cURL Global Init and Data Race on `Http::cancel` (`Http.cpp`)
- **File & Lines:** [Http.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/Http.cpp#L189), [Http.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/Http.cpp#L839)
- **Severity:** HIGH (CWE-362: Race Condition)
- **Root Cause Analysis:**
  `Http::tls_global_init()` invokes `curl_global_init()` without thread synchronization. When multiple HTTP requests are dispatched across worker threads simultaneously, concurrent global initialization produces undefined behavior in libcurl. Furthermore, the cancellation flag is a non-atomic `bool` accessed across threads.
- **Remediation Proposal (Defensive Patch):**
  Protect global initialization with `std::call_once` and declare `std::atomic<bool> cancel;`.

---

## 10. Logical & Parsing Bugs

### [LOG-01] Missing `break` Statement (Fallthrough Bug) in `AMFParserContext::characters` (`AMF.cpp`)
- **File & Lines:** [AMF.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/libslic3r/Format/AMF.cpp#L489-L505)
- **Severity:** HIGH (CWE-484: Omitted Break Statement in Switch)
- **Root Cause Analysis:**
  In the switch statement of `AMFParserContext::characters`, `case 6:` (vertex tags) lacks a terminating `break;`. Execution falls through into `case 7:` (coordinate tags), causing character data corruption and incorrect vertex coordinates during AMF geometry parsing.
- **Affected Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/libslic3r/Format/AMF.cpp:489
          case 6:
              switch (m_path.back()) {
                  case NODE_TYPE_VERTEX1: m_value[0].append(s, len); break;
                  case NODE_TYPE_VERTEX2: m_value[1].append(s, len); break;
                  case NODE_TYPE_VERTEX3: m_value[2].append(s, len); break;
                  default: break;
              }
              // MISSING: break;
          case 7:
              switch (m_path.back()) {
                  case NODE_TYPE_COORDINATE_X: m_value[0].append(s, len); break;
                  case NODE_TYPE_COORDINATE_Y: m_value[1].append(s, len); break;
                  case NODE_TYPE_COORDINATE_Z: m_value[2].append(s, len); break;
                  default: break;
              }
  ```
- **Remediation Proposal (Defensive Patch):**
  Add explicit `break;` statements after line 495 and line 502.

---

### [LOG-02] Faulty Path Truncation and Embedded Null Byte in `WebSocketClient::connect`
- **File & Lines:** [WebSocketClient.hpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/WebSocketClient.hpp#L46-L47)
- **Severity:** MEDIUM (CWE-704: Incorrect Type Conversion or Cast)
- **Root Cause Analysis:**
  `_host[host.size()-1] = '\0';` overwrites the trailing slash with a null byte but leaves `_host.size()` unchanged. The resulting HTTP `Host:` header sent to the WebSocket server contains an embedded null byte, causing strict HTTP parsers to abort the handshake.
- **Remediation Proposal (Defensive Patch):**
  ```cpp
  if (!_host.empty() && _host.back() == '/') {
      _host.pop_back();
  }
  ```

---

## 11. Cross-System Interface, Firmware, API & Data Type Conflicts (OrcaSlicer vs. u1-klipper)

### [IF-01] Inconsistent G-Code Parameter Syntax in Start G-Code (`G28 Z Z_OFFSET -0.07` vs. `Z_OFFSET=-0.07`)
- **OrcaSlicer Profile:** [Snapmaker U1 (0.4 nozzle).json](file:///E:/KI%20Projekte/OrcaSlicer/submodules/Profiles/Snapmaker/machine/Snapmaker%20U1%20(0.4%20nozzle).json#L51) (also 0.2, 0.6, 0.8)
- **Klipper Firmware:** [homing_xyz_override.py](file:///E:/KI%20Projekte/u1-klipper/klippy/extras/homing_xyz_override.py#L269)
- **Severity:** HIGH (Syntax and Parsing Inconsistency)
- **Root Cause Analysis:**
  In the start G-code of all U1 machine profiles, the command `G28 Z Z_OFFSET -0.07` (without an equals sign) is generated for "High Temp Plate" and "Graphic Effect Plate". Three lines later, the same profile uses `BED_MESH_CALIBRATE PROBE_COUNT=11,11 Z_OFFSET=-0.07` (with an equals sign). In standard Klipper G-code parsing, extended parameters without an equals sign cause tokenizer parsing errors.
- **Affected Code:**
  ```json
  {if curr_bed_type=="High Temp Plate"}
  G28 Z Z_OFFSET -0.07
  {elsif curr_bed_type=="Graphic Effect Plate"}
  G28 Z Z_OFFSET -0.07
  {else}
  G28 Z
  {endif}
  ```
- **Remediation Proposal (Defensive Patch):**
  Standardize on explicit key=value syntax:
  ```gcode
  G28 Z Z_OFFSET=-0.07
  ```

---

### [IF-02] Non-Existent Parameter `Z_OFFSET` in `BED_MESH_CALIBRATE` Causes Silent Z-Offset Loss
- **OrcaSlicer Profile:** [Snapmaker U1 (0.4 nozzle).json](file:///E:/KI%20Projekte/OrcaSlicer/submodules/Profiles/Snapmaker/machine/Snapmaker%20U1%20(0.4%20nozzle).json#L51)
- **Klipper Firmware:** [bed_mesh.py](file:///E:/KI%20Projekte/u1-klipper/klippy/extras/bed_mesh.py#L634-L675)
- **Severity:** HIGH (Silent Loss of Functionality / Bed Leveling Calibration Error)
- **Root Cause Analysis:**
  OrcaSlicer outputs `BED_MESH_CALIBRATE PROBE_COUNT=11,11 Z_OFFSET=-0.07`. However, the Klipper module `bed_mesh.py` has no parameter named `Z_OFFSET` in `cmd_BED_MESH_CALIBRATE` or `update_config`. The parameter is silently discarded. Consequently, the intended nozzle distance compensation for Smooth PEI and Graphic Effect plates is never applied during mesh leveling, leading to first-layer adhesion failures or nozzle scratching.
- **Remediation Proposal (Defensive Patch):**
  Apply the plate-specific Z-offset using standard Klipper G-code commands after mesh calibration:
  ```gcode
  SET_GCODE_OFFSET Z_ADJUST=-0.07
  ```

---

### [IF-03] Variable Naming Conflict in Nozzle Queries (`nozzle_diameters` vs. `nozzle_diameter` & `nozzle_volume_types` vs. `filament_volume_type`)
- **OrcaSlicer Source:** [GatewayDevice.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/GatewayDevice.cpp#L195-L204)
- **Klipper Firmware:** [print_task_config.py](file:///E:/KI%20Projekte/u1-klipper/klippy/extras/print_task_config.py#L73-L80)
- **Severity:** HIGH (Data Exchange & Interface Failure)
- **Root Cause Analysis:**
  In `GatewayDevice.cpp`, OrcaSlicer queries JSON array keys `"nozzle_diameters"` and `"nozzle_volume_types"` (plural). In the U1 Klipper firmware (`print_task_config_2.json`), these keys are defined as `"nozzle_diameter"` (singular) and `"filament_volume_type"`. As a result, `find_array` returns `nullptr`, preventing OrcaSlicer from reading nozzle sizes and high-flow capabilities from the printer.
- **Affected Code:**
  ```cpp
  // E:/KI Projekte/OrcaSlicer/src/slic3r/Utils/GatewayDevice.cpp:195
  if (const nlohmann::json* values = find_array(config, "nozzle_diameters"); values != nullptr)
  ...
  if (const nlohmann::json* values = find_array(config, "nozzle_volume_types"); values != nullptr)
  ```
- **Remediation Proposal (Defensive Patch):**
  Support both naming schemes in `GatewayDevice.cpp`:
  ```cpp
  const nlohmann::json* values = find_array(config, "nozzle_diameters");
  if (!values) values = find_array(config, "nozzle_diameter");
  ...
  const nlohmann::json* flow_values = find_array(config, "nozzle_volume_types");
  if (!flow_values) flow_values = find_array(config, "filament_volume_type");
  ```

---

### [IF-04] List Syntax Conflict for `FLOW_CALIBRATE_EXTRUDERS` between `SET_PRINT_PREFERENCES` and `SET_PRINT_TASK_PARAMETERS`
- **Klipper Firmware:** [print_task_config.py](file:///E:/KI%20Projekte/u1-klipper/klippy/extras/print_task_config.py#L752) vs. [print_task_config.py](file:///E:/KI%20Projekte/u1-klipper/klippy/extras/print_task_config.py#L1188)
- **Severity:** HIGH (Firmware Exception / Print Abort)
- **Root Cause Analysis:**
  In `cmd_SET_PRINT_PREFERENCES`, `FLOW_CALIBRATE_EXTRUDERS` is parsed using `flow_calibrate_extruders.split(',')` expecting a raw comma-delimited string (e.g. `"0,1,2"`). In `cmd_SET_PRINT_TASK_PARAMETERS`, the same parameter is parsed using `self._parse_str_to_list(flow_calibrate_extruders)` via `ast.literal_eval`, requiring Python list brackets (e.g. `"[0, 1, 2]"`). If comma-delimited format is sent to `SET_PRINT_TASK_PARAMETERS`, it aborts with `ValueError: Not a list`. If bracketed format is sent to `SET_PRINT_PREFERENCES`, `int("[0")` crashes with `ValueError`.
- **Remediation Proposal (Defensive Patch):**
  Implement a unified list parser in Klipper accepting both formats:
  ```python
  def _parse_int_list(self, param_str):
      clean_str = param_str.strip("[]()")
      if not clean_str:
          return []
      return [int(x.strip()) for x in clean_str.split(',') if x.strip()]
  ```

---

### [IF-05] Data Type Validation Bug in `NOZZLE_DIAMETER_LIST` (`isinstance(..., float)` Rejects Integer Zero)
- **Klipper Firmware:** [print_task_config.py](file:///E:/KI%20Projekte/u1-klipper/klippy/extras/print_task_config.py#L1248-L1254)
- **Severity:** HIGH (Configuration Wipeout)
- **Root Cause Analysis:**
  Line 1249 checks `if not isinstance(nozzle_diameter_list[i], float): raise gcmd.error(...)`. In Python, `isinstance(0, float)` evaluates to **False**. If unused extruder slots are padded with integer `0` or if a 1.0mm nozzle is passed as integer `1`, the check fails, the exception handler catches the error, and all nozzle diameters are reset to zeroes. In contrast, `nozzle_temp` (line 1264) properly checks `(float, int)`.
- **Remediation Proposal (Defensive Patch):**
  ```python
  if not isinstance(nozzle_diameter_list[i], (float, int)):
      raise gcmd.error("[print_task_config] Invalid NOZZLE_DIAMETER")
  ```

---

### [IF-06] Incorrect Extruder Index Comparison in `print_task_config.py`
- **Klipper Firmware:** [print_task_config.py](file:///E:/KI%20Projekte/u1-klipper/klippy/extras/print_task_config.py#L1402)
- **Severity:** CRITICAL (Erroneous Print Abort)
- **Root Cause Analysis:**
  During nozzle diameter verification, the check executes:
  `if abs(tmp_print_task_config_2['nozzle_diameter'][0] - actual_nozzle_diameter[i]) > 0.001:`
  Every used physical extruder `i` (0, 1, 2, 3) is compared against extruder 0's diameter (`[0]` instead of `[i]`). If extruder 0 is not used in the slice (diameter 0) while extruder 1 (0.4mm) is used, Klipper aborts immediately with `nozzle diameter mismatch: f1_0 != e1_0.4`.
- **Affected Code:**
  ```python
  // E:/KI Projekte/u1-klipper/klippy/extras/print_task_config.py:1400
  for i in range(PHYSICAL_EXTRUDER_NUM):
      if tmp_print_task_config['extruders_used'][i]:
          if abs(tmp_print_task_config_2['nozzle_diameter'][0] - actual_nozzle_diameter[i]) > 0.001:
              exception_code = 14
              raise gcmd.error(f"[print_task_config] nozzle diameter mismatch:" +
                               f"f{i}_{tmp_print_task_config_2['nozzle_diameter'][0]} != e{i}_{actual_nozzle_diameter[i]}")
  ```
- **Remediation Proposal (Defensive Patch):**
  Compare against index `[i]`:
  ```python
  for i in range(PHYSICAL_EXTRUDER_NUM):
      if tmp_print_task_config['extruders_used'][i]:
          if abs(tmp_print_task_config_2['nozzle_diameter'][i] - actual_nozzle_diameter[i]) > 0.001:
              exception_code = 14
              raise gcmd.error(f"[print_task_config] nozzle diameter mismatch:" +
                               f"f{i}_{tmp_print_task_config_2['nozzle_diameter'][i]} != e{i}_{actual_nozzle_diameter[i]}")
  ```

---

### [IF-07] Hex Color Code Formatting Collision (6-Char RGB vs. 8-Char RGBA vs. `#` Prefix)
- **OrcaSlicer Profile:** [fdm_U1.json](file:///E:/KI%20Projekte/OrcaSlicer/submodules/Profiles/Snapmaker/machine/fdm_U1.json#L33-L37), [GatewayDevice.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/GatewayDevice.cpp#L141-L164)
- **Klipper Firmware:** [print_task_config.py](file:///E:/KI%20Projekte/u1-klipper/klippy/extras/print_task_config.py#L218-L224)
- **Severity:** HIGH (Printer Configuration Reset)
- **Root Cause Analysis:**
  OrcaSlicer stores colors with leading hash marks (e.g. `#FCE94F` or `#FFFFFFFF`). In `print_task_config.py`, `_early_check` validates exact character lengths: `len(...) != 8` and `len(...) != 6`. A 7- or 9-character string containing `#` causes `_early_check` to raise a `ValueError`, wiping out all user settings and resetting the printer to default configuration.
- **Remediation Proposal (Defensive Patch):**
  Strip leading hash characters before validation in both OrcaSlicer and Klipper:
  ```python
  clean_color = color.lstrip('#').upper()
  ```

---

### [IF-08] Non-Existent 5th/6th Extruders and X-Axis Limit Breach (`X290`/`X300`) in `fdm_U1.json`
- **OrcaSlicer Profile:** [fdm_U1.json](file:///E:/KI%20Projekte/OrcaSlicer/submodules/Profiles/Snapmaker/machine/fdm_U1.json#L11-L183)
- **Klipper Firmware:** [printer.cfg](file:///E:/KI%20Projekte/u1-klipper/lava/printer.cfg#L128) (`position_max: 271`), [print_task_config.py](file:///E:/KI%20Projekte/u1-klipper/klippy/extras/print_task_config.py#L9) (`PHYSICAL_EXTRUDER_NUM = 4`)
- **Severity:** CRITICAL (Physical Toolhead Collision / Axis Hard Limit Fault)
- **Root Cause Analysis:**
  The base profile `fdm_U1.json` defines 5 extruders and includes purge moves in the start G-code traveling to `X290` and `X300` (`G0 X... 300`). The physical Snapmaker U1 machine is equipped with exactly 4 extruders, and the stepper X travel is mechanically limited to `position_max: 271`. Moves beyond 271 mm crash the toolhead into the physical gantry or trigger Klipper emergency shutdowns (`Move out of range: 290`).
- **Remediation Proposal (Defensive Patch):**
  Truncate all extruder arrays in `fdm_U1.json` to 4 tools and restrict purge travel coordinates to `X <= 270 mm`.

---

### [IF-09] Incorrect Bed Texture File Reference in `fdm_U1.json` (`Snapmaker U1_bed.svg`)
- **OrcaSlicer Profile:** [fdm_U1.json](file:///E:/KI%20Projekte/OrcaSlicer/submodules/Profiles/Snapmaker/machine/fdm_U1.json#L10)
- **Asset Location:** `OrcaSlicer/resources/profiles/Snapmaker/Snapmaker U1_texture.svg`
- **Severity:** MEDIUM (UI Rendering Asset Missing)
- **Root Cause Analysis:**
  `fdm_U1.json` specifies `"bed_texture": "Snapmaker U1_bed.svg"`. However, the SVG asset distributed with the application is named `Snapmaker U1_texture.svg`. OrcaSlicer fails to find the texture file, leaving the plater bed graphic unrendered.
- **Remediation Proposal (Defensive Patch):**
  Update the property in `fdm_U1.json`:
  ```json
  "bed_texture": "Snapmaker U1_texture.svg"
  ```

---

### [IF-10] JSON-RPC ID Collision for String IDs in `GatewayProtocol.cpp`
- **OrcaSlicer Source:** [GatewayProtocol.cpp](file:///E:/KI%20Projekte/OrcaSlicer/src/slic3r/Utils/GatewayProtocol.cpp#L159-L174)
- **Moonraker/Klipper:** JSON-RPC 2.0 Specification
- **Severity:** MEDIUM (Protocol Desynchronization / Response Drop)
- **Root Cause Analysis:**
  `classify_jsonrpc_message` correctly recognizes string IDs (`id->is_number_integer() || id->is_string()`), but then assigns `frame.id = id->is_number_integer() ? id->get<std::int64_t>() : 0;`. When string IDs are used (fully valid under JSON-RPC 2.0), all requests and responses are mapped to `id = 0`, causing response collisions and lost asynchronous notifications.
- **Remediation Proposal (Defensive Patch):**
  Store `id` as `std::string` or `std::variant<std::int64_t, std::string>`.

---

## 12. Summary & Recommended Action Plan

1. **Security Hardening:** Immediately patch the WebView IPC handler in `SSWCP.cpp` with strict protocol allowlists, and enable standard TLS certificate verification in `Http.cpp` and `MQTT.cpp`.
2. **Memory Safety & Resource Management:** Eliminate `sprintf` in `AMF.cpp`, ensure `XML_ParserFree` is called via RAII, and add missing `delete` calls in the `MachineObject` destructor.
3. **Numerical Robustness:** Guard against division by zero in `WipeTower2.cpp` for `n <= 1` and enforce stream timeouts in `WebSocketClient.hpp`.
4. **Firmware & Profile Synchronization:**
   - Correct `fdm_U1.json` extruder array lengths from 5 to 4 physical extruders.
   - Fix the extruder index `[0]` bug in `print_task_config.py:1402`.
   - Harmonize parameter keys (`nozzle_diameter` / `nozzle_diameters` and `filament_volume_type` / `nozzle_volume_types`).
   - Strip leading `#` characters during color exchanges.
