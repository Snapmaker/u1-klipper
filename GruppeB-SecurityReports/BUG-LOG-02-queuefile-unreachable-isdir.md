# BUG-LOG-02: Unreachable Directory Deletion and Suppressed Flush in `queuefile.py`

## Summary
In `klippy/queuefile.py`, `QueueListener._process_operation()` failed to delete directories due to inverted condition ordering: `if os.path.exists(op.filename): os.remove(op.filename)` preceded `elif os.path.isdir(op.filename): shutil.rmtree(op.filename)`. In Python, `os.path.exists()` returns `True` for directories as well as files. Calling `os.remove()` on a directory raised an unhandled `IsADirectoryError` (on POSIX) or `PermissionError` (on Windows), leaving the directory intact and dead-code rendering `shutil.rmtree()`. Additionally, disk synchronization calls (`f.flush()` and `os.fdatasync()`) were commented out across `safe_write` and `append` branches, preventing explicit cache flushes even when callers requested `flush=True`.

## Component / Affected Files
- **File:** `klippy/queuefile.py`
  - **Affected Classes & Functions:** `QueueListener._process_operation()`
  - **Lines:** 81-145

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Firmware
- **Severity:** High (`IsADirectoryError` on directory deletion, dead code & omitted disk synchronization)

## Root Cause Analysis
1. **Inverted Existence Check vs. Directory Check:**
   `os.path.exists(path)` evaluates to `True` for directories. When `op.op_type == "delete"` ran:
   ```python
   if os.path.exists(op.filename):
       os.remove(op.filename)
   elif os.path.isdir(op.filename):
       shutil.rmtree(op.filename)
   ```
   The `elif os.path.isdir` branch could never be reached because any valid directory satisfied the first condition. `os.remove()` fails when passed a directory path.
2. **Suppressed Disk Synchronization:**
   `FileOperation` supports `flush=True`. However, in `write`, `safe_write`, and `append`, the calls to `f.flush()` and `os.fdatasync()` were commented out with `#`, causing files written with `flush=True` to remain uncommitted in OS buffer caches.

## Steps to Reproduce
1. In Python, instantiate `QueueListener`.
2. Create a temporary folder containing files: `os.makedirs('/tmp/test_dir')`.
3. Submit a delete operation: `QueueListener._process_operation(FileOperation("delete", '/tmp/test_dir'))`.
4. Observe that `os.remove()` is called, raising `IsADirectoryError` and failing the operation.

## Proposed Fix / Patch
1. In `_process_operation()`, check `if os.path.isdir(op.filename) and not os.path.islink(op.filename): shutil.rmtree(op.filename)` first, followed by `elif os.path.lexists(op.filename): os.remove(op.filename)`.
2. When `op.flush` is set, execute `f.flush()` and invoke `os.fdatasync()` (or `os.fsync()`) across both `write` and `append` operations.

```diff
--- a/klippy/queuefile.py
+++ b/klippy/queuefile.py
@@ -105,4 +105,4 @@
             elif op.op_type == "delete":
-                if os.path.exists(op.filename):
-                    os.remove(op.filename)
-                elif os.path.isdir(op.filename):
+                if os.path.isdir(op.filename) and not os.path.islink(op.filename):
                     shutil.rmtree(op.filename)
+                elif os.path.lexists(op.filename):
+                    os.remove(op.filename)
                 result = True
```

## Regression & Safety Verification
- **Automated Unit Tests:**
  - `test/test_bug_log02.py`: Verified recursive directory deletion with nested files, regular file deletion, nonexistent file handling, and synchronous write/append operations with `flush=True`.
- **Whitespace Compliance:** Verified with `scripts/check_whitespace.py` (0 errors).
- **Regression:** Verified normal asynchronous and synchronous file operations in Klipper remain completely functional.

