# Run user defined actions in place of a normal G28 homing command
# This module forces an override of the XYZ homing
import math, logging, copy
import stepper
from . import homing

class HomingXYZOverride:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode_move = self.printer.load_object(config, 'gcode_move')
        x_pos, y_pos = config.getfloatlist("home_xy_position", count=2)
        self.home_x_pos, self.home_y_pos = x_pos, y_pos
        self.z_hop = config.getfloat("z_hop", default=0.0)
        self.z_hop_speed = config.getfloat('z_hop_speed', 10., above=0.)
        self.z_hop_homing_accel = config.getfloat('z_hop_homing_accel', None, above=0.)
        self.z_safe = config.getfloat("z_safe", default=self.z_hop)
        self.z_safe_speed = config.getfloat("z_safe_speed", default=self.z_hop_speed)
        self.speed = config.getfloat('speed', 50.0, above=0.)
        self.start_z_pos = config.getfloat('set_position_z', 0)
        self.safe_move_y_pos = config.getfloat("safe_move_y_pos", default=250)

        # Conveniently supports using different probing speeds during homing.
        self.z_first_probe_speed = config.getfloat('z_first_probe_speed', 5, above=0.)
        self.z_first_probe_tolerance = config.getfloat('z_first_probe_tolerance', 0.04, minval=0.)
        self.z_first_probe_sample_count = config.getint('z_first_probe_sample_count', 2, minval=0)
        self.z_first_probe_retract_dist = config.getfloat('z_first_probe_retract_dist', 1, above=0.)

        self.z_offset = config.getfloat('z_offset', None)
        self.z_probe_speed = config.getfloat('z_probe_speed', None, above=0.)
        self.z_probe_fast_speed = config.getfloat('z_probe_fast_speed', None, above=0.)
        self.z_probe_accel = config.getfloat('z_probe_accel', None, above=0.)
        self.z_probe_z_accel = config.getfloat('z_probe_z_accel', 100, above=0.)
        self.z_probe_tolerance = config.getfloat('z_probe_tolerance', None, minval=0.)
        self.probe_lift_speed = config.getfloat('z_probe_lift_speed', None, above=0.)
        self.sample_count = config.getint('z_probe_samples', None, minval=1)
        self.relative_trigger_freq = config.getint('z_probe_trigger_freq', None, minval=10)
        self.sample_retract_dist = config.getfloat('z_probe_retract_dist', None, above=0.)
        self.in_script = False
        self.z_need_home = False
        self.z_raised = False
        self.is_homing = False
        self.force_calibration = False
        self.homing_stepper_z_info = None

        # gcode override template
        gcode_macro = self.printer.load_object(config, 'gcode_macro')
        self.template = gcode_macro.load_template(config, 'gcode')
        self.z_hop_homing_begin_gcode = gcode_macro.load_template(config, 'z_hop_homing_begin_gcode', '')
        self.z_hop_homing_end_gcode = gcode_macro.load_template(config, 'z_hop_homing_end_gcode', '')
        self.printer.load_object(config, 'homing')
        self.gcode = self.printer.lookup_object('gcode')
        self.prev_G28 = self.gcode.register_command("G28", None)
        self.gcode.register_command("G28", self.cmd_G28)
        self.printer.register_event_handler("stepper_enable:motor_off", self._motor_off)

        if config.has_section("homing_override") or config.has_section("safe_z_home"):
            raise config.error("(homing_override or safe_z_home) and homing_xyz_override cannot"
                               +" be used simultaneously")

    def _motor_off(self, print_time):
        self.z_raised = False
        self.homing_stepper_z_info = None

    def _z_hop_move(self, z_hop, pl_save_z_hop=False):
        toolhead = self.printer.lookup_object('toolhead')
        curtime = self.printer.get_reactor().monotonic()
        kin_status = toolhead.get_kinematics().get_status(curtime)
        rail = toolhead.get_kinematics().rails[2]
        pos = toolhead.get_position()
        cur_max_accel = None
        cur_z_max_accel = None
        if 'z' not in kin_status['homed_axes'] and self.z_raised == False:
            try:
                # Determine movement
                hi = rail.get_homing_info()
                if hi.positive_dir:
                    homepos = list(toolhead.get_position())
                    homepos[2] = hi.position_endstop
                    startpos = list(homepos)
                    startpos[2] = (hi.position_endstop - z_hop)

                    # Stop waiting before homing
                    if hi.homing_before_delay:
                        self.toolhead.dwell(hi.homing_before_delay)
                        self.toolhead.wait_moves()

                    endstops = rail.get_endstops()
                    hmove = homing.HomingMove(self.printer, endstops)
                    toolhead.set_position(startpos, homing_axes=[2])

                    if self.z_hop_homing_accel is not None:
                        cur_max_accel = toolhead.max_accel
                        toolhead.set_accel(self.z_hop_homing_accel)

                    if toolhead.kin is not None and toolhead.kin.max_z_accel != self.z_probe_z_accel:
                        cur_z_max_accel = toolhead.kin.max_z_accel
                        toolhead.kin.max_z_accel = self.z_probe_z_accel

                    # start z hop move
                    self.z_hop_homing_begin_gcode.run_gcode_from_command()
                    hmove.homing_move(homepos, hi.speed, True, check_triggered=False)
                    self.z_hop_homing_end_gcode.run_gcode_from_command()
                    toolhead.flush_step_generation()
                else:
                    # Always perform the z_hop if the Z axis is not homed
                    pos[2] = 0
                    toolhead.set_position(pos, homing_axes=[2])
                    toolhead.manual_move([None, None, z_hop], self.z_hop_speed)
                self.z_raised = True
                if pl_save_z_hop:
                    virtual_sdcard = self.printer.lookup_object('virtual_sdcard', None)
                    if virtual_sdcard is not None:
                        virtual_sdcard.record_pl_print_z_adjust_position(z_hop)
            finally:
                if cur_max_accel is not None:
                    toolhead.set_accel(cur_max_accel)
                if cur_z_max_accel is not None:
                    toolhead.kin.max_z_accel = cur_z_max_accel
                if hasattr(toolhead.get_kinematics(), "note_z_not_homed"):
                    toolhead.get_kinematics().note_z_not_homed()
        elif 'z' in kin_status['homed_axes'] and pos[2] < self.z_safe:
            # If the Z axis is homed, and below z_safe, lift it to z_safe
            toolhead.manual_move([None, None, self.z_safe], self.z_safe_speed)

    def _z_probe_pre_process(self, gcmd):
        probe_x_pos = probe_y_pos = None
        toolhead = self.printer.lookup_object('toolhead')
        # Check if the current extruder has a probe sensor
        cur_extruder = toolhead.get_extruder()
        if (not hasattr(cur_extruder, 'binding_probe') or cur_extruder.binding_probe is None):
            raise gcmd.error("The current extruder does not have a bound probe")
        curtime = self.printer.get_reactor().monotonic()
        kin_status = toolhead.get_kinematics().get_status(curtime)
        # Do not allow Z-axis homing if X and Y axes have not been homed
        if ('x' not in kin_status['homed_axes'] or
            'y' not in kin_status['homed_axes']):
            message = '{"coded": "0002-0528-0000-0000", "msg":"%s", "action": "pause"}' % ("Z homing abort: Must home X and Y axes first")
            raise gcmd.error(message)
        # Get the current extruder status
        retry_extruder_id = None
        for i in range(10):
            activate_status = cur_extruder.get_extruder_activate_status()
            retry_extruder_id = cur_extruder.check_allow_retry_switch_extruder()
            if activate_status[0][1] != 2 or retry_extruder_id is not None:
                break
            else:
                if i >= 9:
                    break
                gcmd.respond_info("Retrying to get normal extruder activation status (attempt {})".format(i))
                toolhead.dwell(0.2)
                toolhead.wait_moves()

        if activate_status[0][1] == 0 and activate_status[0][0] == cur_extruder.name:
            pass
        elif activate_status[0][1] == 0 or activate_status[0][1] == 1 or retry_extruder_id is not None:
            # The extruder status does not match the actual state, need to retrieve the extruder status once
            gcmd = self.gcode.create_gcode_command("", "", {"A": 0})
            extruder = self.printer.lookup_object(activate_status[0][0], None)
            if extruder is not None:
                cur_extruder = extruder
            cur_extruder.cmd_SWITCH_EXTRUDER_ADVANCED(gcmd)
        else:
            cur_extruder = toolhead.get_extruder()
            result = cur_extruder.analyze_switch_extruder_error(activate_status)
            if result:
                error_msg, activated, unknown, grip_states, activated_code, unknown_code = result
                if hasattr(cur_extruder, 'grab_hall_sensor_type') and cur_extruder.grab_hall_sensor_type:
                    if "multi-act" not in error_msg:
                        first_unknown_index = None
                        for i, idx in enumerate(unknown):
                            if grip_states[idx] != 'FFT':
                                first_unknown_index = idx
                                break

                        if first_unknown_index is not None:
                            grip_state = grip_states[first_unknown_index]
                            message = None
                            if grip_state == 'FFF' or grip_state == 'FFT':
                                info = "Z homing abort: detected that extruder%d is detached. %s" % (first_unknown_index, error_msg)
                                message = '{"coded": "0002-0528-%4d-0013", "oneshot": %d, "msg":"%s", "action": "pause"}' % (first_unknown_index, 1, info)
                            elif (grip_state == 'TTF' or grip_state == 'TTT'):
                                info = "Z homing abort: detected conflicting status for extruder%d: both parked and picked states detected. %s" % (first_unknown_index, error_msg)
                                message = '{"coded": "0002-0528-%4d-0014", "oneshot": %d, "msg":"%s", "action": "pause"}' % (first_unknown_index, 1, info)
                            if message is not None:
                                raise gcmd.error(message)
            else:
                error_msg = activate_status
            error_msg = f"Z homing abort: Extruder parking status error, {error_msg}"
            message = '{"coded": "0002-0528-0000-0001", "msg":"%s", "action": "pause"}' % (error_msg)
            raise gcmd.error(message)
            # raise gcmd.error("z homing error: Unknown extruder park status\n {}".format(activate_status))

        # Extruder sensor detection
        probe = self.printer.lookup_object('probe', None)
        if probe is None:
            raise gcmd.error("Z homing abort: The probe module must be configured")

        # Move to XY homing position
        home_x_pos, home_y_pos = self.home_x_pos, self.home_y_pos
        speed = self.speed
        bed_mesh = self.printer.lookup_object('bed_mesh', None)
        if bed_mesh is not None and bed_mesh.get_mesh() is not None:
            # bed_mesh.bmc.probe_mgr.probe_helper._move_next(0)
            z_mesh = bed_mesh.get_mesh()
            params = z_mesh.get_mesh_params()
            x_count = params['x_count']
            y_count = params['y_count']
            min_x, max_x = params['min_x'], params['max_x']
            min_y, max_y = params['min_y'], params['max_y']
            x_step = (max_x - min_x) / (x_count - 1)
            y_step = (max_y - min_y) / (y_count - 1)
            x_mid_index = (x_count - 1) // 2
            y_mid_index = (y_count - 1) // 2
            home_x_pos = min_x + x_mid_index * x_step
            home_y_pos = min_y + y_mid_index * y_step
            # bed_mesh.bmc.probe_mgr.probe_helper._move_next(0)
        # else:
        #     toolhead.manual_move([home_x_pos, home_y_pos], speed)
        # gcmd.respond_info("home_x_pos: {}, home_y_pos: {}".format(home_x_pos, home_y_pos))
        probe_x_pos = gcmd.get_float("I", None)
        probe_y_pos = gcmd.get_float("J", None)
        # gcmd.respond_info("probe_x_pos: {}, probe_y_pos: {}".format(probe_x_pos, probe_y_pos))
        if probe_x_pos is not None and probe_y_pos is not None:
            home_x_pos = probe_x_pos
            home_y_pos = probe_y_pos
        toolhead.wait_moves()
        pos = toolhead.get_position()
        if pos[1] > self.safe_move_y_pos:
            toolhead.manual_move([None, self.safe_move_y_pos, None], speed)

        if home_y_pos > self.safe_move_y_pos:
            toolhead.manual_move([home_x_pos, None], speed)
        toolhead.manual_move([home_x_pos, home_y_pos], speed)

    def _z_probe_homing_move(self, gcmd):
        toolhead = self.printer.lookup_object('toolhead')
        curtime = self.printer.get_reactor().monotonic()
        kin_status = toolhead.get_kinematics().get_status(curtime)
        rail = toolhead.get_kinematics().rails[2]
        position_min, position_max = rail.get_range()
        probe_x_pos = gcmd.get_float("I", None)
        probe_y_pos = gcmd.get_float("J", None)
        try:
            # Set the starting coordinates
            thcoord = list(toolhead.get_position())
            thcoord[2] = 1.1 * (position_max - position_min)
            toolhead.set_position(thcoord, homing_axes=[2])
            toolhead.get_kinematics().set_ignore_check_move_limit(True)
            # Build probe command
            probe = self.printer.lookup_object('probe')
            params = gcmd.get_command_parameters()
            if 'SAMPLES_TOLERANCE' not in params and self.z_probe_tolerance is not None:
                params['SAMPLES_TOLERANCE'] = self.z_probe_tolerance
            if 'PROBE_SPEED' not in params and self.z_probe_speed is not None:
                params['PROBE_SPEED'] = self.z_probe_speed
            if 'PROBE_FAST_SPEED' not in params and self.z_probe_fast_speed is not None:
                params['PROBE_FAST_SPEED'] = self.z_probe_fast_speed
            if 'PROBE_ACCEL' not in params and self.z_probe_accel is not None:
                params['PROBE_ACCEL'] = self.z_probe_accel
            if 'LIFT_SPEED' not in params and self.probe_lift_speed is not None:
                params['LIFT_SPEED'] = self.probe_lift_speed
            if 'SAMPLES' not in params and self.sample_count is not None:
                params['SAMPLES'] = self.sample_count
            if 'SAMPLE_TRIG_FREQ' not in params and self.relative_trigger_freq is not None:
                params['SAMPLE_TRIG_FREQ'] = self.relative_trigger_freq
            if 'SAMPLE_RETRACT_DIST' not in params and self.sample_retract_dist is not None:
                params['SAMPLE_RETRACT_DIST'] = self.sample_retract_dist

            z_probe_offset = gcmd.get_float("Z_OFFSET", self.z_offset)
            if z_probe_offset is None:
                z_probe_offset = probe.get_offsets()[2]
            gcmd.respond_info("z offset: {}".format(z_probe_offset))
            self.printer.send_event("inductance_coil:probe_start")
            if self.z_first_probe_sample_count > 0:
                fast_probe_params = copy.deepcopy(gcmd.get_command_parameters())
                fast_probe_params['PROBE_FAST_SPEED'] = self.z_first_probe_speed
                fast_probe_params['PROBE_SPEED'] = self.z_first_probe_speed
                fast_probe_params['SAMPLES'] = self.z_first_probe_sample_count
                fast_probe_params['SAMPLES_TOLERANCE'] = self.z_first_probe_tolerance
                probe_gcmd = self.gcode.create_gcode_command("PROBE", "PROBE", fast_probe_params)
                probe.cmd_helper.cmd_PROBE(probe_gcmd)
                toolhead.wait_moves()
                thcoord = list(toolhead.get_position())
                toolhead.manual_move([None, None, thcoord[2]+self.z_first_probe_retract_dist], self.z_hop_speed)
            probe_gcmd = self.gcode.create_gcode_command("PROBE", "PROBE", params)
            probe.cmd_helper.cmd_PROBE(probe_gcmd)
            toolhead.wait_moves()
            thcoord = list(toolhead.get_position())
            z_overshoot_comp = thcoord[2] - probe.get_status(0)['last_z_result']
            gcmd.respond_info("z_overshoot_comp: {}".format(z_overshoot_comp))
            thcoord[2] = self.start_z_pos + z_probe_offset + z_overshoot_comp
            bed_mesh = self.printer.lookup_object('bed_mesh', None)
            if bed_mesh is not None and bed_mesh.get_mesh() is not None:
                toolhead.set_position(thcoord, homing_axes=[2])
                z_mesh = bed_mesh.get_mesh()
                if z_mesh is not None and z_mesh.probed_matrix is not None:
                    z_mesh_params = z_mesh.get_mesh_params()
                    x_count = z_mesh_params['x_count']
                    y_count = z_mesh_params['y_count']
                    x_mid_index = (x_count - 1) // 2
                    y_mid_index = (y_count - 1) // 2
                    if probe_x_pos is not None and probe_y_pos is not None:
                        z_mesh_complete = self.start_z_pos - z_mesh.calc_z(probe_x_pos, probe_y_pos)
                        # gcmd.respond_info("probe_z_pos: {}, z_mesh: {}".format(z_mesh.calc_z(y_mid_index, probe_y_pos), z_mesh.probed_matrix[y_mid_index][x_mid_index]))
                    else:
                        z_mesh_complete = self.start_z_pos - z_mesh.probed_matrix[y_mid_index][x_mid_index]
                    gcmd.respond_info("z_mesh_complete: {}".format(z_mesh_complete))
                    cur_extruder = toolhead.get_extruder()
                    if hasattr(cur_extruder, "gcode_offset") and cur_extruder.gcode_offset is not None:
                        z_mesh_complete -= cur_extruder.gcode_offset[2]
                    adjusted_matrix = [[value + z_mesh_complete for value in row] for row in z_mesh.probed_matrix]
                    try:
                        z_mesh.build_mesh(adjusted_matrix)
                        bed_mesh.set_mesh(z_mesh)
                        bed_mesh.save_profile('default')
                    except Exception as e:
                        raise
                    finally:
                        pass
            else:
                gcode_offset_complete = 0
                cur_extruder = toolhead.get_extruder()
                if hasattr(cur_extruder, "gcode_offset") and cur_extruder.gcode_offset is not None:
                    gcode_offset_complete += cur_extruder.gcode_offset[2]
                thcoord[2] += gcode_offset_complete
                toolhead.set_position(thcoord, homing_axes=[2])
            if self.z_hop:
                pos = toolhead.get_position()
                if pos[2] < self.z_safe:
                    toolhead.manual_move([None, None, self.z_safe], self.z_safe_speed)
            self.gcode_move.reset_last_position()
            self.gcode_move.base_position[2] = self.gcode_move.homing_position[2]
            self.update_homing_stepper_z()
        except Exception as e:
            self.printer.lookup_object('stepper_enable').motor_off()
            raise
        finally:
            self.printer.send_event("inductance_coil:probe_end")
            toolhead.get_kinematics().set_ignore_check_move_limit(False)

    def update_homing_stepper_z(self):
        toolhead = self.printer.lookup_object('toolhead')
        toolhead.wait_moves()
        # cur_extruder = toolhead.get_extruder()
        # if hasattr(cur_extruder, "gcode_offset") and cur_extruder.gcode_offset is not None:
        #     z_offset = cur_extruder.gcode_offset[2]
        # else:
        #     z_offset = 0
        curtime = self.printer.get_reactor().monotonic()
        homed_axes_list = str(toolhead.get_status(curtime)['homed_axes'])
        if 'z' in homed_axes_list:
            kin = toolhead.get_kinematics()
            steppers = kin.get_steppers()
            stepper_mcu_pos = [s.get_mcu_position() for s in steppers]
            z_pos = toolhead.get_position()[2]
            self.homing_stepper_z_info = {
                    'stepper_z_pos': stepper_mcu_pos[2],
                    'z_pos': z_pos,
                    'dir_inverted': kin.rails[2].get_steppers()[0].get_dir_inverted()[0],
                    'step_dist':  kin.rails[2].get_steppers()[0].get_step_dist(),
                }
        else:
            self.homing_stepper_z_info = None

    def _bed_mesh_clear(self):
        try:
            bed_mesh = self.printer.lookup_object('bed_mesh', None)
            if bed_mesh is not None and bed_mesh.get_mesh() is not None:
                self.gcode.run_script_from_command("BED_MESH_CLEAR")
        except Exception:
            pass

    def _load_bed_mesh_profile(self):
        try:
            bed_mesh = self.printer.lookup_object('bed_mesh', None)
            if bed_mesh is not None and bed_mesh.get_mesh() is None:
                self.gcode.run_script_from_command("BED_MESH_PROFILE LOAD=default")
        except Exception:
            pass

    def cmd_G28(self, gcmd):
        action = gcmd.get("ACTION", None)
        if action is not None:
            self.gcode.run_script_from_command("SET_ACTION_CODE ACTION={}".format(action))
        try:
            self.is_homing = True
            self.cmd_G28_BASE(gcmd)
        finally:
            self.is_homing = False
            if action is not None:
                self.gcode.run_script_from_command("SET_ACTION_CODE ACTION=IDLE")

    def cmd_G28_BASE(self, gcmd):
        if self.in_script:
            # Was called recursively - invoke the real G28 command
            self.prev_G28(gcmd)
            return

        # if no axis is given as parameter we assume the override
        no_axis = True
        for axis in 'XYZ':
            if gcmd.get(axis, None) is not None:
                no_axis = False
                break

        if no_axis:
            override = True
            self.z_need_home = True
        else:
            # check if we home an axis which needs the override
            override = False
            # This module forces an override of the X Y axis homing
            for axis in 'XY':
                if gcmd.get(axis, None) is not None:
                    override = True
            if gcmd.get('Z', None) is not None:
                self.z_need_home = True
            else:
                self.z_need_home = False

        toolhead = self.printer.lookup_object('toolhead')
        curtime = self.printer.get_reactor().monotonic()
        kin_status = toolhead.get_kinematics().get_status(curtime)

        # Check if XY axes have homed correctly before moving Z axis alone
        if not override:
            if ('x' not in kin_status['homed_axes'] or
                'y' not in kin_status['homed_axes']):
                message = '{"coded": "0002-0528-0000-0000", "msg":"%s", "action": "pause"}' % ("Z homing abort: Must home X and Y axes first")
                raise gcmd.error(message)

        # Perform Z Hop if necessary
        need_z_hop = gcmd.get_float('Z_HOP', None)
        if need_z_hop is None and self.z_hop != 0.0:
            need_z_hop = self.z_hop

        if need_z_hop is not None:
            pl_save_z_hop = gcmd.get_int('PL_SAVE_Z_HOP', 0)
            self._z_hop_move(need_z_hop, pl_save_z_hop)

        if not override:
            # z-axis homing
            if self.z_need_home == True:
                try:
                    self._load_bed_mesh_profile()
                    self._z_probe_pre_process(gcmd)
                    self._z_probe_homing_move(gcmd)
                except Exception:
                    self._bed_mesh_clear()
                    raise
            return

        # Perform homing
        context = self.template.create_template_context()
        context['params'] = gcmd.get_command_parameters()
        context['rawparams'] = gcmd.get_raw_command_parameters()
        max_accel_bak = toolhead.max_accel
        try:
            self.in_script = True
            self.template.run_gcode_from_command(context)
            if self.z_need_home:
                try:
                    self._load_bed_mesh_profile()
                    self._z_probe_pre_process(gcmd)
                    self._z_probe_homing_move(gcmd)
                except Exception:
                    self._bed_mesh_clear()
                    raise
            else:
                kin_status = toolhead.get_kinematics().get_status(curtime)
                if ('z' not in kin_status['homed_axes']):
                    self._bed_mesh_clear()
        finally:
            self.in_script = False
            extruder_offset_object = self.printer.lookup_object('extruder_offset_calibration', None)
            if extruder_offset_object is not None:
                extruder_offset_object.reset_xyz_probe_positions()
            toolhead.set_accel(max_accel_bak)

def load_config(config):
    return HomingXYZOverride(config)
