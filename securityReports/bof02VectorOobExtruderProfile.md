# Vulnerability Advisory: BOF-02

## Metadata & Reporting Context
- **Report Date:** November 3, 2026
- **Target Software:** Snapmaker OrcaSlicer (v2.4.1)
- **Vulnerability Identifier:** BOF-02
- **Vulnerability Title:** Vector Out-of-Bounds Read in Machine Start G-Code Expression Evaluator
- **Affected Components:** `submodules/Profiles/Snapmaker/machine/fdm_U1.json`
- **Vulnerability Classification:** CWE-125 (Out-of-bounds Read)
- **CVSS v3.1 Score:** 7.1 (HIGH) - `CVSS:3.1/AV:L/AC:L/PR:N/UI:R/S:U/C:N/I:N/A:H`
- **Security Contact:** Snapmaker OrcaSlicer Security Team (`softfeverever@gmail.com`)

---

## Scope of Vulnerability
- **Affected Users & Systems:** All users selecting or slicing models with the Snapmaker U1 base machine profile (`fdm_U1`).
- **Threat Actor Profile:** User or attacker providing slicing profiles containing out-of-range array indices.

---

## Executive Summary
In `submodules/Profiles/Snapmaker/machine/fdm_U1.json`, the machine start G-code definition contains macro conditions that reference `is_extruder_used[5]` and `first_layer_temperature[5]`. In OrcaSlicer's configuration profile format, machine arrays for `fdm_U1` are defined with 5 elements (indices 0 to 4). When the Slic3r macro expression evaluator parses the G-code template during slice preparation, indexing at position 5 evaluates past the bounds of the vector, leading to out-of-bounds memory access and slicing pipeline crashes.

---

## Technical Root Cause Analysis
In `fdm_U1.json`, line 183:

```json
"machine_start_gcode": "PRINT_START ... {if is_extruder_used[4]}T4_TEMP={first_layer_temperature[4]}{endif} {if is_extruder_used[5]}T5_TEMP={first_layer_temperature[5]}{endif} ...\n{if (is_extruder_used[4]) and initial_tool != 4} ... G0 X290 ... {endif}"
```

1. **Physical Hardware Limitation:** The Snapmaker U1 has 4 physical toolheads (`PHYSICAL_EXTRUDER_NUM = 4`).
2. **Profile Array Definition:** Profile arrays (`nozzle_diameter`, `extruder_colour`, `deretraction_speed`, etc.) define 5 entries (indices 0, 1, 2, 3, 4).
3. **Out-of-Bounds Evaluation:** Referencing index `[5]` attempts to access the 6th element of a 5-element `std::vector`, violating boundary invariants in `PlaceholderParser.cpp`.

---

## Steps to Reproduce
1. In OrcaSlicer, select the "Snapmaker U1" printer profile based on `fdm_U1`.
2. Load a 3D model.
3. Click "Slice Plate".
4. When expression evaluation reaches `is_extruder_used[5]`, an out-of-bounds read occurs, failing the slicing job or causing abnormal termination.

---

## Defensive Remediation & Verification

### Profile Fix
Correct `fdm_U1.json` to reference only the actual 4 extruders of the U1 hardware (indices 0, 1, 2, 3):

```json
"machine_start_gcode": "PRINT_START TOOL_TEMP={first_layer_temperature[initial_tool]} {if is_extruder_used[0]}T0_TEMP={first_layer_temperature[0]}{endif} {if is_extruder_used[1]}T1_TEMP={first_layer_temperature[1]}{endif} {if is_extruder_used[2]}T2_TEMP={first_layer_temperature[2]}{endif} {if is_extruder_used[3]}T3_TEMP={first_layer_temperature[3]}{endif} BED_TEMP=[first_layer_bed_temperature] TOOL=[initial_tool]\n"
```

Also, update the parser in `PlaceholderParser.cpp` to validate array index boundaries with graceful fallback to false/empty rather than triggering out-of-bounds memory reads.
