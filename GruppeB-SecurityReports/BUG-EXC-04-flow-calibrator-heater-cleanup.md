# BUG-EXC-04: Missing `try...finally` State Restoration in Probing and Calibration

## Summary
Across four calibration and probing modules (`extruder_calibration.py`, `probe.py`, `probe_inductance_coil.py`, and `flow_calibrator.py`), critical hardware configurations and session states were modified without safe `finally:` restoration handlers:
1. In `extruder_calibration.py`, `cmd_CALIBRATE_EXTRUDER_PARK_POSITION` and `cmd_PROBE_SINGLE_POINT` substituted the optical/analog calibration endstop for the global printer probe via `probe_obj.set_mcu_probe(self.mcu_probe)`. If an exception or abort occurred, the original Z probe was never restored, causing all subsequent `G28 Z` and `BED_MESH_CALIBRATE` commands to crash the nozzle into the build plate.
2. In `probe.py`, `cmd_PROBE_ACCURACY`, `ProbePointsHelper.start_probe()`, and `run_single_probe()` called `start_probe_session()` without `finally: probe_session.end_probe_session()`. Any sensor failure or runtime exception left `multi_probe_pending` perpetually active.
3. In `probe_inductance_coil.py`, `cmd_PROBE_XYZ_OFFSET_CALIBRATE()` placed head moves before `toolhead.set_accel(cur_accel)` in its `finally:` block. A motion exception skipped acceleration restoration.
4. In `flow_calibrator.py`, `cmd_FLOW_MEASURE_K()` heated the nozzle to test temperatures and aborted on errors outside `finally:`, leaving nozzle heating permanently engaged at operating temperatures.

## Component / Affected Files
- **Files:**
  - `klippy/extras/extruder_calibration.py` (lines 124, 196, 303-306, 308, 390-394)
  - `klippy/extras/probe.py` (lines 130-141, 456-470, 492-497)
  - `klippy/extras/probe_inductance_coil.py` (lines 555-560)
  - `klippy/extras/flow_calibrator.py` (lines 1300-1460)

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Firmware
- **Severity:** Critical (Thermal safety hazard, hardware crash risk & probe session state corruption)

## Root Cause Analysis
1. **Unrestored Global Probe MCU:**
   In `extruder_calibration.py`, the optical park sensor replaced `probe_obj.mcu_probe`. The lack of a `finally: probe_obj.set_mcu_probe(orig_mcu_probe)` block left Klipper's global probe pointing to the dock switch rather than the induction bed probe.
2. **Dangling Probe Session:**
   In `probe.py`, probing loops lacked `try...finally: probe_session.end_probe_session()`. Hardware or communication errors left the probe session un-finalized.
3. **Fragile Acceleration Cleanup:**
   In `probe_inductance_coil.py`, placing `_move()` before `toolhead.set_accel()` meant any travel failure bypassed acceleration restoration.
4. **Unattended Heater State:**
   In `flow_calibrator.py`, `pheaters.set_temperature(extruder.get_heater(), 0)` only executed on graceful completion, leaving the nozzle powered on after aborts.

## Steps to Reproduce
1. In `extruder_calibration.py`, trigger an abort or error during park position calibration; execute `G28 Z` and observe that the optical park endstop is checked instead of the Z induction probe.
2. Inject a probe failure during `PROBE_ACCURACY`; observe that subsequent probe commands fail because the previous probe session was not ended.
3. Abort `FLOW_MEASURE_K` during test extrusion; observe nozzle temperature remains at 220°C+.

## Proposed Fix / Patch
1. In `extruder_calibration.py`: Cache `orig_mcu_probe = getattr(probe_obj, 'mcu_probe', None)` and unconditionally restore it via `finally: probe_obj.set_mcu_probe(orig_mcu_probe)`.
2. In `probe.py`: Enclose all probing loops in `try...finally: probe_session.end_probe_session()`.
3. In `probe_inductance_coil.py`: Move acceleration restoration to the beginning of the `finally:` block and guard moves with exception handlers.
4. In `flow_calibrator.py`: Move heater shutdown, event notification, and pressure advance reset into an unconditional `finally:` handler.

## Regression & Safety Verification
- **Automated Unit Tests:**
  - `test/test_bug_exc04.py`: Verified `orig_mcu_probe` restoration on `probe_obj` after simulated calibration errors, verified `probe_session.end_probe_session()` invocation on failure across `run_single_probe` and `ProbePointsHelper`, and verified robust acceleration restoration even when toolhead moves fail.
  - `test/klippy/bug_exc04_flow_calibrator.test`: Verified `FLOW_MEASURE_K` safe heater shutdown on abort.
- **Whitespace Compliance:** Verified with `scripts/check_whitespace.py` (0 errors).
- **Regression:** Confirmed normal probe calibration, homing, and flow calibration procedures execute with full state recovery.
