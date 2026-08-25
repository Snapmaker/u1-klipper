import logging, time
from enum import Enum, IntEnum, unique

class MachineStateManagerErr(Exception):
    """Machine state manager error base class"""
    pass

@unique
class MachineMainState(IntEnum):
    """Printer main state enumeration (starting from 0)"""
    IDLE = 0            # Idle state
    PRINTING = 1        # Printing
    XYZ_OFFSET_CALIBRATE = 2  # XYZ offset calibration
    BED_LEVELING = 3    # Bed leveling
    FLOW_CALIBRATION = 4  # Flow calibration
    SHAPER_CALIBRATE = 5  # Shaper calibration
    UPGRADING = 6       # Firmware upgrading
    ABNORMAL = 7
    SCREWS_TILT_ADJUST = 8 # Screws tilt adjust
    AUTO_LOAD = 9               # auto load filament
    AUTO_UNLOAD = 10            # auto unload filament
    MANUAL_LOAD = 11            # manual load filament
    PARK_POINT_MANUAL_CALIBRATION = 12  # park point manual calibration
    HOMING_ORIGIN_CALIBRATION = 13

    def __str__(self):
        return self.name

@unique
class ActionCode(IntEnum):
    """Action code enumeration (starting from 0)"""
    IDLE = 0
    HOMING = 1
    DETECT_PLATE = 2
    PREHEAT_CHAMBER = 3
    # Printing
    PRINT_PL_RESTORE = 128
    PRINT_PAUSED = 129 # not used
    PRINT_RESUMING = 130
    PRINT_REPLENISHING = 131
    PRINT_SWITCH_CHECKING = 132
    PRINT_AUTO_FEEDING  = 133
    PRINT_PREEXTRUDING  = 134
    PRINT_AUTO_UNLOADING = 135
    PRINT_BED_DETECTING = 136
    # XYZ offset calibration
    MANUAL_CLEAN_EXTRUDER  = 192
    MANUAL_CLEAN_EXTRUDER1 = 193
    MANUAL_CLEAN_EXTRUDER2 = 194
    MANUAL_CLEAN_EXTRUDER3 = 195
    EXTRUDER_XYZ_OFFSET_PROBE = 196
    EXTRUDER1_XYZ_OFFSET_PROBE = 197
    EXTRUDER2_XYZ_OFFSET_PROBE = 198
    EXTRUDER3_XYZ_OFFSET_PROBE = 199
    AUTO_CLEAN_NOZZLE = 200
    WAIT_NOZZLE_COOLING = 201
    # Bed leveling
    BED_LEVELING = 256
    BED_PREHEATING = 257
    BED_PRESCANNING = 258
    # Flow calibration
    EXTRUDER_FLOW_CALIBRATING = 320
    EXTRUDER1_FLOW_CALIBRATING = 321
    EXTRUDER2_FLOW_CALIBRATING = 322
    EXTRUDER3_FLOW_CALIBRATING = 323
    # Shaper calibration
    SHAPER_CALIBRATING = 384
    # Firmware upgrading
    # 448
    # Screws tilt adjust
    RESET_TO_INITIAL = 512
    PROBE_REFERENCE_POINTS = 513
    MANUAL_TUNING = 514
    PROBING_ADJUST_VERIFY = 515
    # auto load
    AUTO_LOADING = 576
    # auto unload
    AUTO_UNLOADING = 640
    # manual load
    MANUAL_LOADING = 704
    # extruder_park_calibration
    PARK_POINT_MANUAL_CALIBRATING = 768
    EXTRUDER_PICK_VERIFY = 769
    EXTRUDER_PARK_VERIFY = 770
    # homing origin calibration
    HOMING_ORIGIN_CALIBRATING = 832

    def __str__(self):
        return self.name

# Default transition rules
# Format: {target_state: [allowed_current_states]}
DEFAULT_TRANSITION_RULES = {
    # MachineMainState.IDLE: [
    #     MachineMainState.IDLE,
    #     MachineMainState.PRINTING,
    #     MachineMainState.XYZ_OFFSET_CALIBRATE,
    #     MachineMainState.BED_LEVELING,
    #     MachineMainState.FLOW_CALIBRATION,
    #     MachineMainState.SHAPER_CALIBRATE,
    #     MachineMainState.UPGRADING
    # ],
    MachineMainState.PRINTING: [MachineMainState.IDLE],
    MachineMainState.BED_LEVELING: [MachineMainState.IDLE],
    MachineMainState.XYZ_OFFSET_CALIBRATE: [MachineMainState.IDLE],
    MachineMainState.FLOW_CALIBRATION: [MachineMainState.IDLE],
    MachineMainState.SHAPER_CALIBRATE: [MachineMainState.IDLE],
    MachineMainState.UPGRADING: [MachineMainState.IDLE]
}

# Default exit rules for EXIT_TO_IDLE command
# Format: {current_state: {allowed_current_states}}
DEFAULT_EXIT_RULES = {
    MachineMainState.IDLE: {MachineMainState.IDLE},
    MachineMainState.PRINTING: {MachineMainState.PRINTING},
    MachineMainState.BED_LEVELING: {MachineMainState.BED_LEVELING},
    MachineMainState.XYZ_OFFSET_CALIBRATE: {MachineMainState.XYZ_OFFSET_CALIBRATE},
    MachineMainState.FLOW_CALIBRATION: {MachineMainState.FLOW_CALIBRATION},
    MachineMainState.SHAPER_CALIBRATE: {MachineMainState.SHAPER_CALIBRATE},
    MachineMainState.UPGRADING: {MachineMainState.UPGRADING}
}

class MachineStateManager:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.pre_hooks = []
        self.post_hooks = []
        self.lock = self.printer.get_reactor().mutex()
        self.state_history = []
        self.max_history = 10
        all_states = list(MachineMainState)
        # Initialize default exit rules (each state can only exit to idle from itself)
        default_exit_rules = {
            **{state: {state} for state in all_states}
        }

        # Initialize exit rules with defaults
        self.exit_rules = default_exit_rules.copy()

        # Override with DEFAULT_EXIT_RULES
        for state, allowed_states in DEFAULT_EXIT_RULES.items():
            self.exit_rules[state] = set(allowed_states)

        # Initialize default transition rules
        default_rules = {
            MachineMainState.IDLE: all_states,  # IDLE can transition from any state
            MachineMainState.ABNORMAL: all_states,  # ABNORMAL can also transition from any state
            **{state: [MachineMainState.IDLE] for state in all_states
               if state not in (MachineMainState.IDLE, MachineMainState.ABNORMAL)}  # Others can only transition from IDLE
        }

        # Initialize transition rules
        self.transition_rules = default_rules.copy()

        # Override default rules if custom rules provided
        for target_state, allowed_states in DEFAULT_TRANSITION_RULES.items():
            self.transition_rules[target_state] = set(allowed_states)

        # self.register_pre_hook(self.default_pre_hook)
        # self.register_post_hook(self.default_post_hook)

        self.main_state = MachineMainState.IDLE
        self.action_code = ActionCode.IDLE
        gcode = self.printer.lookup_object('gcode')
        gcode.register_command('SET_ACTION_CODE', self.cmd_SET_ACTION_CODE)
        gcode.register_command('SET_MAIN_STATE', self.cmd_SET_MAIN_STATE)
        gcode.register_command('GET_MACHINE_STATE', self.cmd_GET_MACHINE_STATE)
        gcode.register_command('GET_STATE_HISTORY', self.cmd_GET_STATE_HISTORY)
        gcode.register_command('EXIT_TO_IDLE', self.cmd_EXIT_TO_IDLE)
        gcode.register_command('SHOW_STATE_RULES', self.cmd_SHOW_STATE_RULES)
        self.printer.register_event_handler("klippy:shutdown", self._handle_shutdown)

    def _handle_shutdown(self):
        try:
            self.change_state(MachineMainState.ABNORMAL)
        except Exception as e:
            logging.exception("{}".format(str(e)))

    def can_transition(self, target_state, current_state=None):
        if current_state is None:
            current_state = self.main_state
        rules = self.transition_rules.get(target_state, set())
        if isinstance(rules, list):
            rules = set(rules)
        return current_state in rules

    def set_action_code(self, action_code, main_state=None):
        """Set action code for current state
        Args:
            action_code: The action code to set
            main_state: Optional state to verify against current state
                       If None, skips state verification
        Raises:
            self.printer.command_error: If state verification fails
        """
        with self.lock:
            if main_state is not None and self.main_state != main_state:
                raise MachineStateManagerErr(
                    f"Cannot set action code {action_code} "
                    f"(current state: {self.main_state}, "
                    f"requested state: {main_state})")
            self.action_code = action_code

    def register_hook(self, hook, hook_type='pre'):
        """Register hook method
        Args:
            hook: callback function to register
            hook_type: 'pre' or 'post', specifies hook type
        """
        with self.lock:
            hook_list = self.pre_hooks if hook_type == 'pre' else self.post_hooks
            if hook not in hook_list:
                hook_list.append(hook)

    def unregister_hook(self, hook, hook_type='pre'):
        """Unregister hook method
        Args:
            hook: callback function to unregister
            hook_type: 'pre' or 'post', specifies hook type
        """
        with self.lock:
            hook_list = self.pre_hooks if hook_type == 'pre' else self.post_hooks
            if hook in hook_list:
                hook_list.remove(hook)

    def register_pre_hook(self, hook):
        self.register_hook(hook, 'pre')

    def unregister_pre_hook(self, hook):
        self.unregister_hook(hook, 'pre')

    def register_post_hook(self, hook):
        self.register_hook(hook, 'post')

    def unregister_post_hook(self, hook):
        self.unregister_hook(hook, 'post')

    def _safe_update_state(self, old_state, new_state, action=None):
        self.main_state = new_state
        if action is None:
            self.action_code = ActionCode.IDLE  # Reset action code
        else:
            self.action_code = action  # Keep specified action

    def _add_state_history(self, from_state, to_state, success, error=None):
        """Add state transition record to history"""
        if len(self.state_history) >= self.max_history:
            self.state_history.pop(0)
        record = {
            'timestamp': self.printer.get_reactor().monotonic(),
            'from_state': from_state,
            'to_state': to_state,
            'success': success
        }
        if not success:
            record['error'] = error
        self.state_history.append(record)

    def change_state(self, new_state, action=None):
        with self.lock:
            old_state = self.main_state
            # Skip if both state and action are unchanged
            if old_state == new_state and (action is None or action == self.action_code):
                return

            # Only validate state transition if state is actually changing
            if old_state != new_state:
                allowed_states = self.transition_rules.get(new_state, [])
                try:
                    if old_state not in allowed_states:
                        raise MachineStateManagerErr(
                            f"Invalid state transition from {old_state} to {new_state}")

                    for hook in self.pre_hooks:
                        if not hook(old_state, new_state):
                            raise MachineStateManagerErr(f"Pre-hook {hook.__name__} returned False")
                except Exception as e:
                    error_msg = (
                        f"State transition failed: from {old_state} to {new_state}\n"
                        f"Current state: {self.main_state}\n"
                        f"Action code: {self.action_code}"
                    )
                    self._add_state_history(old_state, new_state, False, error_msg)
                    raise

            self._safe_update_state(old_state, new_state, action)
            self._add_state_history(old_state, new_state, True)

            # Only run post hooks if state actually changed
            if old_state != new_state:
                try:
                    for hook in self.post_hooks:
                        hook(old_state, new_state)
                except Exception as e:
                    logging.exception("Post-hook execution failed")

    def exit_to_idle(self, requested_from_state=None):
        """Exit current state to IDLE if allowed by exit rules
        Args:
            requested_from_state: The state that is requesting the exit.
                                 If None, uses current state.
        """
        current_state = self.main_state
        allowed_states = self.exit_rules.get(current_state, set())
        if requested_from_state is not None and requested_from_state not in allowed_states:
            raise MachineStateManagerErr(
                f"Cannot exit to idle from {current_state} "
                f"(requested from state: {requested_from_state})")
        self.change_state(MachineMainState.IDLE)

    # Register default hooks
    def default_pre_hook(self, old_state, new_state):
        gcode = self.printer.lookup_object('gcode')
        gcode.respond_info(f"pre_hook: {old_state} -> {new_state}")
        return True

    def default_post_hook(self, old_state, new_state):
        gcode = self.printer.lookup_object('gcode')
        gcode.respond_info(f"post_hook: {old_state} -> {new_state}")
        return True

    def get_status(self, eventtime=None):
        return {
            'main_state':  self.main_state,
            'action_code': self.action_code
        }

    def cmd_SET_ACTION_CODE(self, gcmd):
        action = gcmd.get('ACTION')
        main_state = gcmd.get('MAIN_STATE', None)
        try:
            if action.isdigit():
                action_code = ActionCode(int(action))
            else:
                action_code = ActionCode[action]
        except (ValueError, KeyError):
            raise gcmd.error("Invalid action code: %s" % (action,))

        main_state_val = None
        if main_state is not None:
            try:
                if main_state.isdigit():
                    main_state_val = MachineMainState(int(main_state))
                else:
                    main_state_val = MachineMainState[main_state]
            except (ValueError, KeyError):
                raise gcmd.error("Invalid main state: %s" % (main_state,))

        try:
            self.set_action_code(action_code, main_state_val)
            if main_state_val is not None:
                gcmd.respond_info("Success: Set action code {} for state {}".format(action_code, main_state_val))
            else:
                gcmd.respond_info("Success: Set action code {}".format(action_code))
        except Exception as e:
            raise gcmd.error(str(e))

    def cmd_SET_MAIN_STATE(self, gcmd):
        state = gcmd.get('MAIN_STATE')
        action = gcmd.get('ACTION', None)
        try:
            if state.isdigit():
                new_state = MachineMainState(int(state))
            else:
                new_state = MachineMainState[state]

            if action is not None:
                if action.isdigit():
                    action_code = ActionCode(int(action))
                else:
                    action_code = ActionCode[action]
            else:
                action_code = None
        except (ValueError, KeyError) as e:
            raise gcmd.error("Invalid parameter: %s" % (str(e),))

        try:
            self.change_state(new_state, action_code)
            gcmd.respond_info("Success: Changed main state to {}{}".format(
                new_state, "" if action_code is None else " with action {}".format(action_code)))
        except Exception as e:
            raise gcmd.error("Failed to change state: {}".format(str(e)))

    def cmd_GET_MACHINE_STATE(self, gcmd):
        """Handle GET_MACHINE_STATE gcode command"""
        gcmd.respond_info("Machine State: %s, Action: %s" % (
            self.main_state, self.action_code))

    def cmd_GET_STATE_HISTORY(self, gcmd):
        """Handle GET_STATE_HISTORY gcode command
        Args:
            SHOW_ERROR: Optional parameter (0/1) to control error display
        """
        if not self.state_history:
            gcmd.respond_info("State history is empty")
            return

        show_error = gcmd.get_int('SHOW_ERROR', 0)
        gcmd.respond_info("=== State History (latest %d entries) ===" % len(self.state_history))
        for entry in reversed(self.state_history):
            timestamp = str(entry['timestamp'])
            if entry['success']:
                msg = "%s: %s -> %s SUCCESS" % (
                    timestamp, entry['from_state'], entry['to_state'])
            else:
                msg = "%s: %s -> %s FAILED" % (
                    timestamp, entry['from_state'], entry['to_state'])
                if show_error:
                    msg += " (Error: %s)" % entry['error']
            gcmd.respond_info(msg)

    def cmd_SHOW_STATE_RULES(self, gcmd):
        """Display current state transition and exit rules"""
        gcmd.respond_info("=== Current State: %s ===" % self.main_state)

        gcmd.respond_info("\n=== Transition Rules ===")
        for target_state, from_states in sorted(self.transition_rules.items()):
            gcmd.respond_info("%-15s <- %s" % (
                target_state, ", ".join(str(s) for s in sorted(from_states))))

        gcmd.respond_info("\n=== Exit Rules ===")
        for state, exit_states in sorted(self.exit_rules.items()):
            gcmd.respond_info("%-15s can exit to: %s" % (
                state, ", ".join(str(s) for s in sorted(exit_states))))

    def cmd_EXIT_TO_IDLE(self, gcmd):
        """Handle EXIT_TO_IDLE gcode command
        Args:
            REQ_FROM_STATE: Optional parameter to specify the requesting state
        """
        requested_from_state = gcmd.get('REQ_FROM_STATE', None)
        try:
            if requested_from_state is not None:
                if requested_from_state.isdigit():
                    requested_from_state = MachineMainState(int(requested_from_state))
                else:
                    requested_from_state = MachineMainState[requested_from_state]
            self.exit_to_idle(requested_from_state)
            gcmd.respond_info("Success: Exited to idle state")
        except Exception as e:
            raise gcmd.error(f"Failed to exit to idle: {str(e)}")

def load_config(config):
    return MachineStateManager(config)
