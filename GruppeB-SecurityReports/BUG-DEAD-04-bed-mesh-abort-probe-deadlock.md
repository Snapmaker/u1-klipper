# Security & Bug Report: BUG-DEAD-04 - Deadlock Risk in `abort_probe()` via G-Code Execution Inside Mutex

## 1. Summary / Description
A concurrency defect exists in `klippy/extras/bed_mesh.py` within the `abort_probe()` method of `ProbeManager`. When `abort_probe()` is invoked while holding `self.lock`, it called `self.gcode.run_script_from_command("EXIT_TO_IDLE REQ_FROM_STATE=BED_LEVELING")` directly inside the critical section protected by `with self.lock:`.

Executing arbitrary or state transition G-Code scripts while holding a component-level mutex creates an inversion of lock order and deadlock risk when the executed G-Code script interacts with the `bed_mesh` module or other subsystems waiting on `self.lock`.

## 2. Component / Affected Files
- **Affected File:** `klippy/extras/bed_mesh.py`
- **Affected Method:** `ProbeManager.abort_probe()`
- **Lines Affected:** Lines ~1258-1270

## 3. Classification
- **Category:** Concurrency / Deadlock
- **Group:** Group B (Snapmaker U1 Specific Extension)
- **Severity:** High

## 4. Root Cause Analysis
In `ProbeManager.abort_probe()`:
```python
with self.lock:
    if (self.state == BedMeshProbeState.PROBING or
        self.state == BedMeshProbeState.PREHEART or self.state == BedMeshProbeState.PRESACN):
        self.gcode.run_script_from_command("EXIT_TO_IDLE REQ_FROM_STATE=BED_LEVELING")
```
`gcode.run_script_from_command()` triggers Klippy's command dispatcher and printer event dispatch loops synchronously or re-entrantly. If the command handler for `EXIT_TO_IDLE` or any registered callback tries to query `bed_mesh` status or manipulate probe state, it attempts to acquire `self.lock`. Because Python's `threading.Lock` is non-reentrant, this leads to an immediate self-deadlock or an AB-BA deadlock between the G-code execution thread and the probe management thread.

## 5. Steps to Reproduce
1. Configure `bed_mesh` with `is_inductance_coil_probe`.
2. Initiate probe sequence and trigger `abort_probe()`.
3. Observed result prior to fix: Lock held across synchronous script dispatch blocking concurrent command handling.
4. Deterministic batch test: `test/klippy/bug_dead04_bed_mesh.test`.

## 6. Proposed Fix / Patch
The fix releases the mutex prior to executing the external script dispatch:

```diff
--- a/klippy/extras/bed_mesh.py
+++ b/klippy/extras/bed_mesh.py
@@ -1254,16 +1254,23 @@ class ProbeManager:
     def abort_probe(self):
         if self.is_inductance_coil_probe:
             machine_state_manager = self.printer.lookup_object(
                 'machine_state_manager', None)
+            run_exit_script = False
             with self.lock:
                 if (self.state == BedMeshProbeState.PROBING or
-                    self.state == BedMeshProbeState.PREHEART or self.state == BedMeshProbeState.PRESACN):
-                    self.gcode.run_script_from_command("EXIT_TO_IDLE REQ_FROM_STATE=BED_LEVELING")
-                    # self.gcode.run_script_from_command("SET_MAIN_STATE MAIN_STATE=IDLE")
+                    self.state == BedMeshProbeState.PREHEART or
+                    self.state == BedMeshProbeState.PRESACN):
                     self.state = BedMeshProbeState.IDLE
+                    run_exit_script = True
                 elif machine_state_manager is not None:
                     status = machine_state_manager.get_status()
                     if str(status.get("main_state", "")) == "BED_LEVELING":
-                        self.gcode.run_script_from_command("EXIT_TO_IDLE REQ_FROM_STATE=BED_LEVELING")
+                        run_exit_script = True
+            if run_exit_script:
+                self.gcode.run_script_from_command(
+                    "EXIT_TO_IDLE REQ_FROM_STATE=BED_LEVELING")
```

## 7. Regression & Safety Verification
- **Deterministic Test:** Executed `test/klippy/bug_dead04_bed_mesh.test` with `scripts/test_klippy.py`.
- **Formatting & CI Check:** Verified via `scripts/check_whitespace.py` (0 errors, max line length <= 80 characters, LF line endings).
- **Result:** Test completed with exit code 0 (`All test cases passed`).

