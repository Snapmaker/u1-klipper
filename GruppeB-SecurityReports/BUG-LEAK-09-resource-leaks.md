# BUG-LEAK-09: Directory Handle Leak in `fatfs_api.c` & PTY FD Leak in `console.c` / `util.py`

## Summary
In `scripts/spi_flash/fatfs_api.c`, `fatfs_list_dir()` opened a directory using FatFs `f_opendir(&dir, path)` but never called `f_closedir(&dir)`, permanently leaking FatFs directory handles and internal resources. It also unconditionally returned `FR_OK` even when `f_opendir` failed.
In `src/linux/console.c`, `console_setup()` acquired pseudo-terminal master and slave file descriptors via `openpty(&mfd, &sfd, ...)`. If any subsequent system call failed (`set_non_blocking`, `set_close_on_exec`, `symlink`, `chmod`), the function returned `-1` without closing `mfd` and `sfd`, permanently leaking file descriptors.
In `klippy/util.py`, `dump_mcu_build()` opened `.config` and `out/klipper.dict` using bare `f = open(...)` without ensuring closure via context managers on read or JSON decode exceptions.

## Component / Affected Files
- **Files:**
  - `scripts/spi_flash/fatfs_api.c`
    - Method: `fatfs_list_dir()` (lines 216–235)
  - `src/linux/console.c`
    - Method: `console_setup()` (lines 72–120)
  - `klippy/util.py`
    - Method: `dump_mcu_build()` (lines 65–90)

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Host & Firmware
- **Severity:** Medium (Resource Leak / File Descriptor Exhaustion)

## Root Cause Analysis
1. In `fatfs_list_dir()`, `f_opendir()` allocates internal directory tracking state in FatFs. Leaving the directory unclosed with `f_closedir()` prevents clean state cleanup and leads to exhaustion of directory tracking slots in embedded FatFs configurations.
2. In `console_setup()`, seven distinct system calls follow `openpty()`. Each error exit returned `-1` immediately, abandoning open file descriptors for both master and slave endpoints of the allocated PTY.
3. In `util.py`, `f.close()` was bypassed if `f.read()` or `json.loads()` threw an exception inside the `try` block.

## Steps to Reproduce
1. In Python CFFI spi_flash scripts, call `fatfs_list_dir()` repeatedly across multiple directories. Observe leaked FatFs DIR structures.
2. Trigger `console_setup()` with a read-only symlink target or simulate failure in `chmod()`. Observe open `/dev/ptmx` and slave PTY file descriptors remaining open in the process.

## Remediation
- In `fatfs_list_dir()`, validate pointers `if (!flist || !path) return FR_INVALID_PARAMETER;`, call `f_closedir(&dir)` before returning, and return the actual FatFs result code `res`.
- In `console_setup()`, direct all post-`openpty` failure paths to a `fail:` label that invokes `close(mfd)` and `close(sfd)`.
- In `klippy/util.py`, wrap file operations in standard `with open(...) as f:` context managers.

## Verification
- Python unit test implemented in `test/test_bug_leak09.py` (3 tests passed in 0.011s).
- C unit test implemented in `test/test_bug_leak09_console.c` verifying fail-path cleanup logic.
- Code validated with `scripts/check_whitespace.py` (0 warnings).

