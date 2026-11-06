# BUG-DEAD-03: Self-Deadlock on Non-Reentrant Mutex in `MachineStateManager`

## Summary
In `klippy/extras/machine_state_manager.py`, `MachineStateManager.change_state()` and `set_action_code()` synchronised access using `self.printer.get_reactor().mutex()`. Klipper's `ReactorMutex` is strictly non-reentrant. Because `change_state()` held `self.lock` across the execution of all registered `pre_hooks` and `post_hooks`, any hook callback that called `set_action_code()`, `change_state()`, `register_hook()`, or `unregister_hook()` in the same greenlet caused a permanent self-deadlock, freezing reactor execution indefinitely.

## Component / Affected Files
- **File:** `klippy/extras/machine_state_manager.py`
  - **Affected Classes & Functions:** `MachineStateManager.change_state()`, `MachineStateManager.set_action_code()`, `MachineStateManager.register_hook()`, `MachineStateManager.unregister_hook()`
  - **Lines:** 120-135, 195-225, 260-325

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Firmware
- **Severity:** Critical (Reactor Greenlet Deadlock / Complete System Freeze)

## Root Cause Analysis
1. **Non-Reentrant Reactor Mutex:**
   In `klippy/reactor.py`, `ReactorMutex.__enter__()` checks `if not self.is_locked: self.is_locked = True; return;`. If the holding greenlet attempts to enter the mutex again, it appends itself to `self.queue` and sleeps via `self.reactor.pause(self.reactor.NEVER)`. Because the greenlet is paused, it can never exit the outer critical section to unlock the mutex, resulting in an unrecoverable deadlock.
2. **Hook Execution Inside Lock:**
   In `change_state()`:
   ```python
   with self.lock:
       ...
       for hook in self.pre_hooks:
           hook(...)
       ...
       for hook in self.post_hooks:
           hook(...)
   ```
   External modules listening to printer state changes frequently need to update their own action code or query status, which triggered re-acquisition of `self.lock`.
3. **List Mutation During Hook Dispatch:**
   Iterating directly over `self.pre_hooks` and `self.post_hooks` while holding a non-reentrant lock led to either deadlocks or runtime errors if a hook dynamically registered or unregistered listeners.

## Steps to Reproduce
1. In Python, instantiate `MachineStateManager(config)`.
2. Register a `post_hook` callback that invokes `set_action_code("PRINTING")`.
3. Call `change_state(MachineMainState.PRINTING)`.
4. Observe that the execution pauses forever at `ReactorMutex.__enter__` on the second call.

## Proposed Fix / Patch
1. Introduce a thread-aware `ReentrantReactorMutex` wrapper around `ReactorMutex` that tracks the owning greenlet via `greenlet.getcurrent()` and increments/decrements a recursion depth counter.
2. Replace `self.lock` with `ReentrantReactorMutex(self.printer.get_reactor().mutex())`.
3. Dispatch hooks across snapshot copies `list(self.pre_hooks)` and `list(self.post_hooks)` to allow safe mutation during callback execution.

```diff
--- a/klippy/extras/machine_state_manager.py
+++ b/klippy/extras/machine_state_manager.py
@@ -1,4 +1,29 @@
 import logging, time
+import greenlet
 from enum import Enum, IntEnum, unique
+
+class ReentrantReactorMutex:
+    def __init__(self, mutex):
+        self._mutex = mutex
+        self._owner = None
+        self._count = 0
+
+    def __enter__(self):
+        current = greenlet.getcurrent()
+        if self._owner is current:
+            self._count += 1
+            return self
+        self._mutex.__enter__()
+        self._owner = current
+        self._count = 1
+        return self
+
+    def __exit__(self, exc_type, exc_val, exc_tb):
+        if self._owner is not greenlet.getcurrent():
+            return
+        self._count -= 1
+        if self._count == 0:
+            self._owner = None
+            self._mutex.__exit__(exc_type, exc_val, exc_tb)
...
-        self.lock = self.printer.get_reactor().mutex()
+        self.lock = ReentrantReactorMutex(self.printer.get_reactor().mutex())
```

## Regression & Safety Verification
- **Automated Unit Tests:**
  - `test/test_bug_dead03.py`: Verified recursive lock acquisition inside pre-hooks and post-hooks executes without deadlock, and verified dynamic hook registration during iteration.
- **Whitespace Compliance:** Verified with `scripts/check_whitespace.py` (0 errors).
- **Regression:** Verified normal state transitions across all `MachineMainState` values operate reliably.

