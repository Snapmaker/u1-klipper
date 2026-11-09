# BUG-NULL-04: `NoneType` Crashes in `virtual_sdcard.py` (`restore_print`, `force_record_pl_print_file_env`, `GCodeStateTracker`)

## Summary
In `klippy/extras/virtual_sdcard.py`, several unguarded accesses to potentially `None` objects lead to unhandled runtime exceptions (`TypeError` and `AttributeError`):
1. In `restore_print()` (lines 1843–1845), `file_env['env_flag'] = self.get_pl_env_flag()[0]` was performed directly on the result of `self.get_pl_print_file_env()`. When the environment file was missing or unreadable, `get_pl_print_file_env()` returned `None`, crashing with `TypeError: 'NoneType' object is not subscriptable`.
2. In `force_record_pl_print_file_env()`, `record_power_loss_info()`, and `handle_shutdown()`, `self.current_file.name` was accessed directly without verifying whether `self.current_file` was `None`, leading to `AttributeError: 'NoneType' object has no attribute 'name'`.
3. In `GCodeStateTracker.update_position()`, `print_task_config_info["reprint_info"]["extruder_map_table"]` assumed non-`None` return values and valid dictionary structure.
4. In `parse_power_loss_move_env()`, file reading used `.decode('utf-8')` without `errors='replace'`, risking `UnicodeDecodeError`, and fell through returning `None` if EOF was reached prior to `target_line`.

## Component / Affected Files
- **File:** `klippy/extras/virtual_sdcard.py`
  - **Affected Methods:** `restore_print()`, `force_record_pl_print_file_env()`, `record_power_loss_info()`, `handle_shutdown()`, `parse_power_loss_move_env()`, `GCodeStateTracker.update_position()`
  - **Lines:** 168-174, 830-835, 1205-1235, 1555-1565, 1845-1855, 2185-2205

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Host Python
- **Severity:** Critical (Power-Loss Recovery Failure / Unhandled Exception)

## Root Cause Analysis
- `VirtualSD.get_pl_print_file_env()` returns `None` on file read error or when power-loss file does not exist. Directly subscripting or assigning to `file_env` without verifying `isinstance(file_env, dict)` results in an uncaught `TypeError`.
- During idle states, prior to file opening, or after print completion, `self.current_file` is `None`. Methods attempting to read `self.current_file.name` unconditionally trigger `AttributeError`.
- In `GCodeStateTracker`, if `print_task_config.get_print_task_config()` returns `None`, chain-subscripting `["reprint_info"]` raises `TypeError`.

## Steps to Reproduce
1. Trigger power-loss recovery when `pl_print_file_env_path` is missing or corrupted.
2. In `restore_print()`, observe `TypeError: 'NoneType' object is not subscriptable`.
3. Call `force_record_pl_print_file_env()` when no file is currently being printed (`self.current_file is None`).
4. Observe `AttributeError: 'NoneType' object has no attribute 'name'`.

## Remediation
- In `restore_print()`, ensure `file_env = file_env or {}` and verify `isinstance(file_env, dict)` before assignment.
- Across `force_record_pl_print_file_env()`, `record_power_loss_info()`, and `handle_shutdown()`, guard `self.current_file.name` access using `getattr(self.current_file, 'name', None)`.
- In `GCodeStateTracker.update_position()`, defensively access `reprint_info` and fallback cleanly to `self.extruder_gcode_id = cmd` on missing mapping data.
- In `parse_power_loss_move_env()`, decode with `errors='replace'` and raise `command_error` if `target_line` is not reached.

## Verification
- Unit test implemented in `test/test_bug_null04.py` covering all 5 edge-case scenarios.
- Executed in `u1sim` container: 5 tests passed in 0.014s.
- `scripts/check_whitespace.py` verified with 0 warnings.

