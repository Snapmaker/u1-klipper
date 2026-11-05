# Vulnerability Advisory: BOF-03

## Metadata & Reporting Context
- **Report Date:** November 3, 2026
- **Target Software:** Snapmaker OrcaSlicer (v2.4.1)
- **Vulnerability Identifier:** BOF-03
- **Vulnerability Title:** Unchecked Vector Out-of-Bounds Access in DeviceManager Extruder Array
- **Affected Components:** `src/slic3r/GUI/DeviceManager.cpp`
- **Vulnerability Classification:** CWE-125 (Out-of-bounds Read), CWE-787 (Out-of-bounds Write)
- **CVSS v3.1 Score:** 7.5 (HIGH) - `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H`
- **Security Contact:** Snapmaker OrcaSlicer Security Team (`softfeverever@gmail.com`)

---

## Scope of Vulnerability
- **Affected Users & Systems:** All users connected to third-party or newly configured 3D printers through the Device Manager interface.
- **Threat Actor Profile:** Malformed printer state telemetry broadcast over the local network or uninitialized machine configuration.

---

## Executive Summary
Multiple functions in `DeviceManager.cpp` perform direct subscript indexing on `m_extder_data.extders[MAIN_NOZZLE_ID]` without ensuring that `m_extder_data.extders` has been allocated or contains sufficient elements. When telemetry packets or status queries arrive for a printer whose extruder configuration is uninitialized or empty, accessing `extders[MAIN_NOZZLE_ID]` reads or writes beyond the memory bounds of the `std::vector`, leading to application crashes (`SIGSEGV`).

---

## Technical Root Cause Analysis
In `DeviceManager.cpp`, multiple methods access `extders` using raw indexing:

```cpp
// E:/KI Projekte/OrcaSlicer/src/slic3r/GUI/DeviceManager.cpp:736
m_extder_data.extders[MAIN_NOZZLE_ID].snow.ams_id  = "";
m_extder_data.extders[MAIN_NOZZLE_ID].snow.slot_id = "";

// E:/KI Projekte/OrcaSlicer/src/slic3r/GUI/DeviceManager.cpp:3412
m_extder_data.extders[MAIN_NOZZLE_ID].ext_has_filament = hw_switch_state;

// E:/KI Projekte/OrcaSlicer/src/slic3r/GUI/DeviceManager.cpp:3585
m_extder_data.extders[MAIN_NOZZLE_ID].temp = jj["nozzle_temper"].get<float>();
```

1. **Unchecked Vector Access:** `std::vector::operator[]` does not perform bounds checking in release builds.
2. **Missing Invariant Verification:** If `m_extder_data.extders` is empty (`size() == 0`), indexing `[MAIN_NOZZLE_ID]` (where `MAIN_NOZZLE_ID == 0`) accesses unallocated memory outside the vector's buffer.
3. **Telemetry Race Condition:** Network status packets received over MQTT or HTTP arriving prior to complete machine slot handshake trigger these calls on empty data structures.

---

## Steps to Reproduce
1. Establish a network connection to a printer that reports temperature telemetry before reporting toolhead counts.
2. Or trigger device status parsing when `m_extder_data.extders` has been cleared during disconnection.
3. Observe an immediate access violation crash in `DeviceManager.cpp` at line 3412 or 3585.

---

## Defensive Remediation & Verification

### Code Fix
Add explicit bounds verification or safe vector resizing before accessing nozzle state:

```cpp
// E:/KI Projekte/OrcaSlicer/src/slic3r/GUI/DeviceManager.cpp:3412
if (MAIN_NOZZLE_ID < m_extder_data.extders.size()) {
    m_extder_data.extders[MAIN_NOZZLE_ID].ext_has_filament = hw_switch_state;
} else {
    BOOST_LOG_TRIVIAL(warning) << "[DeviceManager] Extruder array out of bounds for nozzle ID " << MAIN_NOZZLE_ID;
}
```

Or utilize `std::vector::at()` or ensure `m_extder_data.extders` is pre-sized to `std::max(1, count)` during constructor initialization.
