# Snapmaker U1 Specific Bugs (Group B)

Central overview of all findings for **Group B (Snapmaker U1 Proprietary)** from the reference report `BUG_REPORT_U1_KLIPPER_EN.md`.

## Status Overview & Metrics

- **Total Findings:** 53
- **Critical (CRITICAL):** 12
- **High (HIGH):** 36
- **Medium (MEDIUM):** 5
- **Resolution Status:** 53 Resolved (Verified), 0 Open

---

## Tabular Overview

| ID | Module / File | Lines | Severity | Status | Title / Summary |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **[SEC-01](BUG-SEC-01-bed-mesh-path-traversal.md)** | `bed_mesh.py` | `2110-2194` | **CRITICAL** | Resolved (Verified) | Path Traversal & Arbitrary `.json` File Overwrite/Deletion in `ProfileManager` (`bed_mesh.py`) |
| **[SEC-02](BUG-SEC-02-bed-mesh-output-file-path-traversal.md)** | `bed_mesh.py` | `304-313` | **HIGH** | Resolved (Verified) | Arbitrary System File Overwrite via `BED_MESH_OUTPUT_FILE` (`bed_mesh.py`) |
| **[SEC-03](BUG-SEC-03-probe-inductance-coil-path-traversal.md)** | `probe_inductance_coil.py` | `728, 999-1010` | **HIGH** | Resolved (Verified) | Path Traversal / Arbitrary File Append via `LOG_FILE` in `probe_inductance_coil.py` |
| **[SEC-04](BUG-SEC-04-flow-calibrator-path-traversal.md)** | `flow_calibrator.py` | `231-241, 1194-1215` | **HIGH** | Resolved (Verified) | Path Traversal & Unvalidated File Path via `AXIS` in `flow_calibrator.py` |
| **[BUF-01](BUG-BUF-01-sdio-integer-overflow.md)** | `sdiocmds.c` | `135-164` | **CRITICAL** | Resolved (Verified) | 32-Bit Integer Overflow Bypasses Bounds Check -> Arbitrary Out-of-Bounds Write/Read in `src/sdiocmds.c` |
| **[BUF-10](BUG-BUF-10-extruder-index-out-of-bounds.md)** | `extruder.py, probe_inductance_coil.py` | `1160-1175, 1255-1275, 1475-1488, 1740-1760, 869-873` | **HIGH** | Resolved (Verified) | Out-of-Bounds `IndexError` on `unknown[0]` and `filament_vendor[extruder_index]` in `extruder.py` & `probe_inductance_coil.py` |
| **[BUF-11](BUG-BUF-11-print-task-config-out-of-bounds.md)** | `print_task_config.py` | `826-836, 1175, 1399-1405` | **HIGH** | Resolved (Verified) | Out-of-Bounds List Indexing in `print_task_config.py` |
| **[BUF-12](BUG-BUF-12-channel-and-buffer-bounds.md)** | `fm175xx_reader.py, sc7a20.py` | `808, 1037, 85-88` | **MEDIUM** | Resolved (Verified) | Off-by-One Channel Check & Unchecked `recv_buff[0]` in `fm175xx_reader.py` & `sc7a20.py` |
| **[INT-01](BUG-INT-01-sdio-timeout-overflow.md)** | `sdiocmds.c, sdio.c` | `82, 112, 408` | **HIGH** | Resolved (Verified) | 32-Bit Integer Overflow in SDIO Timeout Calculation & `uint8_t` Underflow in `sdio.c` / `sdiocmds.c` |
| **[INT-03](BUG-INT-03-tautological-bounds-and-overflow.md)** | `inductance_coil.c` | `45, 104-117, 328-357, 471-479` | **HIGH** | Resolved (Verified) | Tautological Bounds Check, `MOVING_SUM` 32-Bit Overflow & Signed Overflow in `src/stm32/inductance_coil.c` |
| **[INT-04](BUG-INT-04-timer-underflow-overflow.md)** | `power_loss_check.py, power_loss_check.c` | `492-493, 30-32, 89-92` | **HIGH** | Resolved (Verified) | 16-Bit Timer Underflow & `uint32_t` Overflow of `power_loss_trigger_time` (`power_loss_check.c` & `power_loss_check.py`) |
| **[DIV-01](BUG-DIV-01-hardware-division-by-zero.md)** | `inductance_coil.c, sdio.c` | `408, 335, 407, 417` | **CRITICAL** | Resolved (Verified) | Hardware Division by Zero in `sdio_set_speed` (`src/stm32/sdio.c`) and `inductance_coil.c` |
| **[DIV-04](BUG-DIV-04-bed-mesh-zero-division.md)** | `bed_mesh.py` | `219-220` | **HIGH** | Resolved (Verified) | Division by Zero when `z_adj == self.fade_dist` in `bed_mesh.py` |
| **[DIV-05](BUG-DIV-05-inductance-coil-division-by-zero.md)** | `inductance_coil.py` | `186, 267` | **HIGH** | Resolved (Verified) | Division by Zero & `date_rate` Typo in `inductance_coil.py` |
| **[DIV-06](BUG-DIV-06-homing-modules-zero-division.md)** | `homing_precise_corexy.py, homing_xyz_override.py, auto_screws_tilt_adjust.py, homing.py` | `107-108, 210, 207, 239` | **HIGH** | Resolved (Verified) | Division by Zero in `homing_precise_corexy.py`, `homing_xyz_override.py`, `auto_screws_tilt_adjust.py`, `homing.py` |
| **[DIV-07](BUG-DIV-07-flow-calibrator-zero-division.md)** | `flow_calibrator.py, purifier_factory.py, defect_detection.py, power_loss_check.py` | `509-512, 23, 78, 189` | **HIGH** | Resolved (Verified) | Division by Zero in `flow_calibrator.py`, `purifier_factory.py`, `defect_detection.py`, `power_loss_check.py` |
| **[NULL-01](BUG-NULL-01-unaligned-pointer-dereference.md)** | `inductance_coil.c` | `628-630` | **HIGH** | Resolved (Verified) | Unaligned 32-Bit Pointer Dereference in `src/stm32/inductance_coil.c` |
| **[NULL-02](BUG-NULL-02-sdio-null-pointer-dereference.md)** | `fatfs_api.c, sdiocmds.c, sdio.c` | `48-132, 205, 142-143` | **HIGH** | Resolved (Verified) | Null Pointer Dereference in `src/sdiocmds.c`, `src/stm32/sdio.c` & `scripts/spi_flash/fatfs_api.c` |
| **[NULL-04](BUG-NULL-04-virtual-sdcard-nonetype-crashes.md)** | `virtual_sdcard.py` | `830-835, 1205-1235, 1555-1565, 1845-1855, 2185-2205` | **CRITICAL** | Resolved (Verified) | `NoneType` Crashes in `virtual_sdcard.py` (`restore_print` & `get_print_task_config`) |
| **[NULL-05](BUG-NULL-05-mqtt-jsonrpc-initialization.md)** | `timelapse.py, defect_detection.py` | `406, 428, 509, 552, 117` | **HIGH** | Resolved (Verified) | Missing Initialization of `self.mqtt_jsonrpc` in `defect_detection.py` & `None` Dereference in `timelapse.py` |
| **[NULL-06](BUG-NULL-06-nonetype-dereferences.md)** | `klippy.py` | `277-282` | **HIGH** | Resolved (Verified) | Further `NoneType` Dereferences in `klippy.py`, `extruder.py`, `bed_mesh.py`, `probe_inductance_coil.py`, `extruder_calibration.py`, `filament_feed.py`, `error_mcu.py`, `park_detector.py` |
| **[LEAK-02](BUG-LEAK-02-flash-lock-leak.md)** | `power_loss_check.c` | `146-203` | **HIGH** | Resolved (Verified) | MCU Flash Remains Permanently Unlocked on Errors in `flash_write` (`src/stm32/power_loss_check.c`) |
| **[LEAK-06](BUG-LEAK-06-frequency-query-helper-leak.md)** | `inductance_coil.py` | `82-98` | **HIGH** | Resolved (Verified) | Severe Memory Leak & Zombie Process in `FrequencyQueryHelper.write_to_file` (`inductance_coil.py`) |
| **[LEAK-07](BUG-LEAK-07-flow-calibrator-fifo-leak.md)** | `flow_calibrator.py` | `113-149` | **HIGH** | Resolved (Verified) | FIFO File Descriptor Leak & 30s Main Reactor Freeze in `FlowCalcClient.calc_flow_factor` (`flow_calibrator.py`) |
| **[LEAK-08](BUG-LEAK-08-gpio-and-thread-leak.md)** | `fm175xx_reader.py, mqtt.py` | `217-237, 859-865, 47-49` | **HIGH** | Resolved (Verified) | GPIO FD Leak & Thread Leak in `fm175xx_reader.py` as well as Thread Leak in `mqtt.py` |
| **[LEAK-09](BUG-LEAK-09-resource-leaks.md)** | `fatfs_api.c, console.c, util.py` | `216-235, 72-120, 65-90` | **MEDIUM** | Resolved (Verified) | Directory Handle Leak (Missing `f_closedir`) in `scripts/spi_flash/fatfs_api.c` & PTY FD Leak in `src/linux/console.c` / `klippy/util.py` |
| **[UAF-01](BUG-UAF-01-dangling-pointer-and-active-irq-shutdown.md)** | `power_loss_check.c` | `517-521, 672-684` | **CRITICAL** | Resolved (Verified) | Dangling Global Pointer `plc` After `config_reset` & Active `TIM4_IRQHandler` Memory Corruption (`src/stm32/power_loss_check.c`) |
| **[UAF-02](BUG-UAF-02-dangling-timer-and-irq-shutdown.md)** | `inductance_coil.c` | `72, 432-437, 665-673` | **HIGH** | Resolved (Verified) | Dangling Timer `config_freq_timer` & Active Priority 0 IRQ on Shutdown in `src/stm32/inductance_coil.c` |
| **[UAF-05](BUG-UAF-05-use-after-close-rfid-shutdown.md)** | `fm175xx_reader.py` | `938-961` | **MEDIUM** | Resolved (Verified) | Use-After-Close Race Condition During RFID Reader Shutdown (`fm175xx_reader.py`) |
| **[STACK-02](BUG-STACK-02-auto-screws-tilt-adjust-infinite-probing.md)** | `auto_screws_tilt_adjust.py` | `520-580` | **HIGH** | Resolved (Verified) | Infinite Probing Loop in `cmd_AUTO_SCREWS_TILT_ADJUST_MANUAL_TUNING` (`auto_screws_tilt_adjust.py`) |
| **[STACK-04](BUG-STACK-04-filament-detect-self-test-loop.md)** | `filament_detect.py` | `238-244` | **HIGH** | Resolved (Verified) | Infinite Loop `while (1):` in `cmd_FILAMENT_DT_SELF_TEST` (`filament_detect.py`) |
| **[STACK-05](BUG-STACK-05-purifier-wait-chamber-temp-timeout.md)** | `purifier.py` | `1158, 1188-1190` | **HIGH** | Resolved (Verified) | Broken Timeout (`wait_timeout_time` Overwritten Every Second) -> Infinite Loop in `cmd_WAIT_CHAMBER_TEMP` (`purifier.py`) |
| **[DEAD-01](BUG-DEAD-01-hardware-polling-loop-timeouts.md)** | `sdio.c` | `307-318, 361-372` | **HIGH** | Resolved (Verified) | Infinite Hardware Polling Loops Without Timeout in MCU Drivers (`sdio.c`, `at32f403a.c`, `at32f415rc.c`, `n32g45x_adc.c`, `spi.c`, `canserial.c`) |
| **[DEAD-02](BUG-DEAD-02-filament-feed-mutex-deadlock.md)** | `filament_feed_fac_test.py, filament_feed.py` | `315-374, 776-789, 82-141` | **CRITICAL** | Resolved (Verified) | Permanent Mutex Deadlock on `self._mutex_lock` and `self.channel_active` in `filament_feed.py` & `filament_feed_fac_test.py` |
| **[DEAD-03](BUG-DEAD-03-machine-state-manager-deadlock.md)** | `machine_state_manager.py` | `269-299` | **CRITICAL** | Resolved (Verified) | Self-Deadlock on Non-Reentrant `ReactorMutex` in `machine_state_manager.py` |
| **[DEAD-04](BUG-DEAD-04-bed-mesh-abort-probe-deadlock.md)** | `bed_mesh.py` | `1258-1270` | **HIGH** | Resolved (Verified) | Deadlock Risk via `gcode.run_script_from_command` Inside `with self.lock:` in `bed_mesh.py` |
| **[RACE-01](BUG-RACE-01-interrupt-and-task-concurrency.md)** | `inductance_coil.c` | `168-237, 279-320, 458-518` | **HIGH** | Resolved (Verified) | Race Conditions Between Priority 0 ISR (`InputCapture_IRQHandler`), Timer ISR, and Task in `src/stm32/inductance_coil.c` |
| **[RACE-04](BUG-RACE-04-exception-manager-toctou-race.md)** | `exception_manager.py` | `54, 190-258, 300-305` | **HIGH** | Resolved (Verified) | TOCTOU Read-Modify-Write File Race & Thread Safety Violations in `exception_manager.py` |
| **[RACE-07](BUG-RACE-07-heaters-and-rfid-concurrency.md)** | `fm175xx_reader.py, heaters.py` | `201-205, 476-499, 964-1025` | **HIGH** | Resolved (Verified) | Missing Synchronization in `cmd_SET_PID_PROFILE` (`heaters.py`) & RFID Thread (`fm175xx_reader.py`) |
| **[EXC-03](BUG-EXC-03-unbound-local-error-and-bare-raise.md)** | `extruder.py` | `1456-1484, 1731-1748` | **HIGH** | Resolved (Verified) | `UnboundLocalError` (`message`, `probe_session`, `need_save`) & Bare `raise` Outside `except` |
| **[EXC-04](BUG-EXC-04-flow-calibrator-heater-cleanup.md)** | `extruder_calibration.py` | `196, 301-302` | **CRITICAL** | Resolved (Verified) | Missing `try ... finally:` Restoration After Probing / Calibration (`extruder_calibration.py`, `probe.py`, `probe_inductance_coil.py`, `flow_calibrator.py`) |
| **[EXC-05](BUG-EXC-05-swallowed-gcmd-error.md)** | `inductance_coil.py` | `146-147` | **HIGH** | Resolved (Verified) | Swallowed `gcmd.error(e)` in `cmd_FREQUENCY_MEASURE` (`inductance_coil.py`) |
| **[LOG-01](BUG-LOG-01-moving-sum-off-by-one.md)** | `inductance_coil.c` | `128-132` | **CRITICAL** | Resolved (Verified) | Off-by-One Bug in `get_sum()` Triggers Spurious Z Induction Probe Tripping (`src/stm32/inductance_coil.c`) |
| **[LOG-02](BUG-LOG-02-queuefile-unreachable-isdir.md)** | `queuefile.py` | `105-109` | **HIGH** | Resolved (Verified) | Unreachable `elif os.path.isdir` Branch Prevents Directory Deletion in `queuefile.py` |
| **[LOG-03](BUG-LOG-03-print-task-config-color-corruption.md)** | `print_task_config.py` | `223, 681-692, 750-759` | **CRITICAL** | Resolved (Verified) | 8-Digit RGBA Color Codes Corrupt `print_task.json` on Subsequent Reboot (`print_task_config.py`) |
| **[LOG-05](BUG-LOG-05-extruder-late-binding-and-y-diff.md)** | `extruder.py` | `1770-1776, 2065-2071, 2110-2116` | **HIGH** | Resolved (Verified) | Late-Binding Closure Bug (`i` Is Always `3`), Missing `y_diff` Check in Dock Calibration (`extruder.py`) |
| **[LOG-06](BUG-LOG-06-homing-precise-corexy-mean-calculation.md)** | `homing_precise_corexy.py` | `282-303` | **CRITICAL** | Resolved (Verified) | Flawed Subset Mean Calculation (`/ 9`) in `homing_precise_corexy.py` |
| **[LOG-07](BUG-LOG-07-probe-inductance-coil-math-and-fallback.md)** | `probe_inductance_coil.py` | `50-86, 316-330, 1520` | **CRITICAL** | Resolved (Verified) | Copy-Paste Error `hole_z` Falling Back to `hole_x`, Inverted Determinant Formula & Unprotected `lstsq` in `probe_inductance_coil.py` |
| **[LOG-08](BUG-LOG-08-filament-feed-inverted-pins-and-rampup.md)** | `filament_feed.py` | `137, 411-418, 1219-1222` | **MEDIUM** | Resolved (Verified) | Inverted LED Pins (`white_pin` / `red_pin`) and `max()` Instead of `min()` During Ramp-Up in `filament_feed.py` |
| **[LOG-09](BUG-LOG-09-flow-calibrator-zero-k-and-logic.md)** | `flow_calibrator.py` | `260, 305-327, 478-491` | **HIGH** | Resolved (Verified) | Falsy `0.0` Bug Clears `flow_calibrator.json`, Mutates `DEFAULT_K`, and Returns `None` in `flow_calibrator.py` |
| **[LOG-11](BUG-LOG-11-bed-mesh-substitute-points-index.md)** | `bed_mesh.py` | `1460-1462` | **MEDIUM** | Resolved (Verified) | Flawed Index Validation `sorted_sub_idx[idx] == idx` in `bed_mesh.py` |
| **[LOG-12](BUG-LOG-12-defect-detection-cancel-state.md)** | `defect_detection.py` | `800-809, 828-854, 888-965` | **HIGH** | Resolved (Verified) | Unconditional Z Move & Resetting to `PRINTING` in `finally:` Block After Print Cancellation (`defect_detection.py`) |
| **[LOG-14](BUG-LOG-14-config-typos-and-prefixes.md)** | `extruder_calibration.py` | `79-85, 223-224` | **HIGH** | Resolved (Verified) | Configuration Typos & Missing Section Prefixes in `extruder_calibration.py`, `filament_entangle_detect.py`, `mqtt.py` |

