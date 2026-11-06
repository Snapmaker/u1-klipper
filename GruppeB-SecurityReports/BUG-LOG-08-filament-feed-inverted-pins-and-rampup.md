# BUG-LOG-08: Inverted LED Pin Mapping and Premature Maximum Motor PWM in `filament_feed.py`

## Summary
In `klippy/extras/filament_feed.py`, two distinct issues impacted hardware actuation:
1. `FeedLight.__init__` was invoked with inverted positional arguments `(printer, reactor, white_pin, red_pin)` instead of `(printer, reactor, red_pin, white_pin)`. Consequently, the firmware asserted white LED output when signaling error states and red LED output during regular operations.
2. During extrusion retry phases in `FilamentFeed._load_extruding()`, PWM duty cycle and period adjustments erroneously used `max()` instead of `min()`: `duty = max(1.0, duty + 0.05)` and `period = max(0.12, period + 0.01)`. This immediately forced 100% duty cycle on the very first retry step, completely skipping the intended gradual ramp-up.

## Component / Affected Files
- **File:** `klippy/extras/filament_feed.py`
  - **Affected Classes & Functions:** `FilamentFeed.__init__()`, `FilamentFeed._load_extruding()`
  - **Lines:** 422-430, 1225-1228

## Classification
- **Category:** Group B: Snapmaker U1 Specific Proprietary Modules / Firmware
- **Severity:** Medium (Inverted Hardware Status/Error Indication & Sudden Full-Power Actuation Spike)

## Root Cause Analysis
1. **Inverted Light Pin Arguments:**
   `FeedLight.__init__` is defined as `def __init__(self, printer, reactor, red_pin, white_pin)`.
   In `FilamentFeed.__init__`:
   ```python
   white_pin = config.get('light_ch_1_white')
   red_pin = config.get('light_ch_1_red')
   tmp_obj = FeedLight(self.printer, self.reactor, white_pin, red_pin)
   ```
   Positional parameter assignment bound `white_pin` to `self.red_light` and `red_pin` to `self.white_light`.
2. **Inverted Math Function on Ramp-Up Capping:**
   `duty` starts at `0.8`. The design intended to incrementally increase the duty cycle by `0.05` up to a maximum ceiling of `1.0`. Calling `max(1.0, duty + 0.05)` evaluated to `max(1.0, 0.85) = 1.0`, immediately saturating the motor driver to maximum power on retry index 0.

## Steps to Reproduce
1. In Python, instantiate `FeedLight` passing `white_pin` then `red_pin`.
2. Inspect `self.red_light.pin_name` and `self.white_light.pin_name`; observe they are swapped.
3. Simulate `duty = 0.8; duty = max(1.0, duty + 0.05)`.
4. Observe `duty` evaluates to `1.0` immediately instead of `0.85`.

## Proposed Fix / Patch
1. Pass pins using explicit keyword arguments `red_pin=red_pin, white_pin=white_pin` in `FilamentFeed.__init__()`.
2. Replace `max(1.0, ...)` with `min(1.0, duty + 0.05)` and `max(0.12, ...)` with `min(0.12, period + 0.01)`.

```diff
--- a/klippy/extras/filament_feed.py
+++ b/klippy/extras/filament_feed.py
@@ -424,7 +424,7 @@
         white_pin = config.get('light_ch_1_white')
         red_pin = config.get('light_ch_1_red')
-        tmp_obj = FeedLight(self.printer, self.reactor, white_pin, red_pin)
+        tmp_obj = FeedLight(self.printer, self.reactor, red_pin=red_pin, white_pin=white_pin)
@@ -1225,4 +1225,4 @@
                             if retry < 5:
-                                duty = max(1.0, duty + 0.05)
+                                duty = min(1.0, duty + 0.05)
                             else:
-                                period = max(0.12, period + 0.01)
+                                period = min(0.12, period + 0.01)
```

## Regression & Safety Verification
- **Automated Unit Tests:**
  - `test/test_bug_log08.py`: Verified `FeedLight` pin routing and verified monotonic, bounded 5-step gradual ramp-up progression.
- **Whitespace Compliance:** Verified with `scripts/check_whitespace.py` (0 errors).
- **Regression:** Verified normal filament feeding operations and motor cycle executions remain fully functional.

