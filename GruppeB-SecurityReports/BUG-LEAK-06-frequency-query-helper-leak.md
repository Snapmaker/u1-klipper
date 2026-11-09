# BUG-LEAK-06: Severe Memory Leak & Zombie Processes in `FrequencyQueryHelper.write_to_file` (`inductance_coil.py`)

## Summary
In `klippy/extras/inductance_coil.py`, `FrequencyQueryHelper.write_to_file()` started a background worker via `multiprocessing.Process(target=write_impl)` and called `self.get_samples()` inside the target function `write_impl()`. Because the process was spawned/forked into an isolated memory address space, clearing `self.msgs` inside `write_impl()` only released the buffer within the child process. In the parent Klippy process, `self.msgs` remained unmodified, accumulating frequency sample messages indefinitely and leaking system RAM. Furthermore, the worker processes were never joined or reaped, resulting in zombie processes (`<defunct>`) remaining in the system process table.

## Component / Affected Files
- **File:** `klippy/extras/inductance_coil.py`
  - **Affected Methods:** `FrequencyQueryHelper.__init__()`, `FrequencyQueryHelper.write_to_file()`
  - **Lines:** 28, 82-98

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Host Python
- **Severity:** High (RAM Memory Leak in Main Process / Zombie Process Leak)

## Root Cause Analysis
1. Forked copy-on-write memory: Calling `print_time, frequency = self.get_samples()` inside the child process execution (`write_impl`) operates on a separate address space copy. The mutation `del self.msgs[:]` was invisible to the parent Klippy daemon.
2. Unreaped worker processes: Spawning `multiprocessing.Process` with `daemon=True` without managing child PID state or invoking `.is_alive()` / `waitpid()` leaves terminated child processes in the zombie state until Klippy shuts down.
3. Raw file descriptor management: The unpatched code used `f = open(...)` and `f.close()` without a `try ... finally` or context manager, risking leaked file descriptors if writing raised an exception.

## Steps to Reproduce
1. Execute multiple `FREQUENCY_MEASURE` cycles with continuous sensor logging.
2. Observe `len(bg_client.msgs)` continuing to grow in the main Klippy process memory.
3. Check `ps aux | grep defunct` on Linux to observe accumulated child zombie processes.

## Proposed Fix / Patch
```diff
diff --git a/klippy/extras/inductance_coil.py b/klippy/extras/inductance_coil.py
--- a/klippy/extras/inductance_coil.py
+++ b/klippy/extras/inductance_coil.py
@@ -28,4 +28,5 @@ class FrequencyQueryHelper:
         self.frequency = []
         self.print_time = []
         self.msgs = []
+        self.active_procs = []

@@ -82,17 +83,23 @@ class FrequencyQueryHelper:
     def write_to_file(self, filename):
-        def write_impl():
+        self.active_procs = [p for p in self.active_procs if p.is_alive()]
+        print_time, frequency = self.get_samples()
+        def write_impl(target_filename, ptime, freq_data):
             try:
                 # Try to re-nice writing process
                 os.nice(20)
             except:
                 pass
-            f = open(filename, 'w+')
-            f.write("time,frequency\n")
-            print_time, frequency = self.get_samples()
-            for t, freq in zip(print_time, frequency):
-                f.write("%.4f,%d\n" % (
-                    t, freq))
-            f.close()
-        write_proc = multiprocessing.Process(target=write_impl)
+            try:
+                with open(target_filename, 'w+') as f:
+                    f.write("time,frequency\n")
+                    for t, freq in zip(ptime, freq_data):
+                        f.write("%.4f,%d\n" % (t, freq))
+            except Exception as err:
+                logging.exception("Failed to write frequency data to %s: %s",
+                                  target_filename, err)
+        write_proc = multiprocessing.Process(
+            target=write_impl, args=(str(filename), print_time, frequency))
         write_proc.daemon = True
         write_proc.start()
+        self.active_procs.append(write_proc)
```

## Verification
- Unit test `test/test_bug_leak06.py` verified:
  - Confirms `self.msgs` is cleared immediately in the parent process.
  - Confirms CSV file is written accurately with sample timestamps and frequencies.
  - Confirms finished worker processes are reaped via `active_procs`.

