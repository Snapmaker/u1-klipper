# BUG-RACE-04: TOCTOU Race Condition and Thread Safety Violations in `ExceptionManager`

## Summary
In `klippy/exception_manager.py`, persistent exceptions written via `save_persistent_exception()` and cleared via `clear_persistent_exception()` suffered from a Time-of-Check to Time-of-Use (TOCTOU) race condition. The manager relied on reading `/tmp/persistent_exceptions.json` synchronously while writing back using asynchronous background file writers (`queuefile.async_write_file`). Rapid calls to save or clear exceptions read stale data from disk, overwriting or reverting concurrent changes. Additionally, `raise_exception_async()` called from background threads appended to `self.async_exceptions` without lock synchronization and called `self.reactor.update_timer()` directly from outside the reactor thread, leading to list corruption and timer race conditions.

## Component / Affected Files
- **File:** `klippy/exception_manager.py`
  - **Affected Classes & Functions:** `ExceptionManager.__init__()`, `ExceptionManager.save_persistent_exception()`, `ExceptionManager.clear_persistent_exception()`, `ExceptionManager.raise_exception_async()`, `ExceptionManager._handle_async_exception()`
  - **Lines:** 38-75, 115-180

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Firmware
- **Severity:** High (TOCTOU Data Inconsistency, State Loss & Unsynchronized Reactor Timer Updates)

## Root Cause Analysis
1. **Asynchronous File Write vs. Synchronous File Read (TOCTOU):**
   `queuefile.async_write_file()` queues disk writes in a background worker thread. When `save_persistent_exception()` or `clear_persistent_exception()` was called repeatedly in short succession, each call re-read the file from disk using `json.load()` before the prior queued background write had completed. As a result, newly added or deleted exception entries were overwritten with stale state.
2. **Missing Thread Synchronization on `async_exceptions`:**
   `self.async_exceptions` is a standard Python list. When multiple background threads or callbacks invoked `raise_exception_async()` concurrently, concurrent append operations could corrupt internal list state.
3. **Reactor Timer Called From Non-Reactor Thread:**
   `raise_exception_async()` directly invoked `self.reactor.update_timer(self.async_exception_handler, self.reactor.NOW)` from arbitrary caller threads. Reactor timers are not thread-safe and must be scheduled via `reactor.register_async_callback()`.
4. **Unprotected `pop(0)` in `_handle_async_exception`:**
   If `_handle_async_exception()` was triggered when `self.async_exceptions` was empty or drained concurrently, calling `self.async_exceptions.pop(0)` raised an unhandled `IndexError`.

## Steps to Reproduce
1. In Python, instantiate `ExceptionManager`.
2. Rapidly call `save_persistent_exception('0522-0000-0001', 3, 'err1')` followed immediately by `save_persistent_exception('0522-0000-0002', 3, 'err2')`.
3. Because `async_write_file` defers writing, the second call reads the unwritten disk file and omits `'0522-0000-0001'`.
4. Call `raise_exception_async` from 4 concurrent threads; observe race conditions on `async_exceptions` and cross-thread reactor timer updates.

## Proposed Fix / Patch
1. Maintain an authoritative in-memory cache `self._persistent_cache` in `ExceptionManager` initialized on startup.
2. Update the in-memory cache synchronously in both `save_persistent_exception()` and `clear_persistent_exception()` before dispatching background writes, and query the cache for existence checks.
3. Add `self._async_lock = threading.Lock()` protecting all mutations to `self.async_exceptions`.
4. Replace direct non-thread-safe `reactor.update_timer()` calls from foreign threads with `self.reactor.register_async_callback()`.
5. Guard `_handle_async_exception()` with `with self._async_lock:` and return `self.reactor.NEVER` safely if the queue is empty.

## Regression & Safety Verification
- **Automated Unit Tests:**
  - `test/test_bug_race04.py`: Verified in-memory cache consistency across rapid saves and clears, verified safe handling of empty exception queue, and verified concurrent access across 4 threads running 100 total async exceptions.
- **Whitespace Compliance:** Verified with `scripts/check_whitespace.py` (0 errors).
- **Regression:** Verified normal persistent exception storage and asynchronous alert propagation remain fully operational.

