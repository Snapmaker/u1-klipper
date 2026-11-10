# Exclude moves toward and inside objects
#
# Copyright (C) 2019  Eric Callahan <arksine.code@gmail.com>
# Copyright (C) 2021  Troy Jacobson <troy.d.jacobson@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import logging
import json

class ExcludeObject:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')
        self.gcode_move = self.printer.load_object(config, 'gcode_move')
        self.printer.register_event_handler('klippy:connect',
                                        self._handle_connect)
        self.printer.register_event_handler("virtual_sdcard:reset_file",
                                            self._reset_file)
        self.print_stats = None
        self.next_transform = None
        self.last_position_extruded = [0., 0., 0., 0.]
        self.last_position_excluded = [0., 0., 0., 0.]

        self._reset_state()
        self.gcode.register_command(
            'EXCLUDE_OBJECT_START', self.cmd_EXCLUDE_OBJECT_START,
            desc=self.cmd_EXCLUDE_OBJECT_START_help)
        self.gcode.register_command(
            'EXCLUDE_OBJECT_END', self.cmd_EXCLUDE_OBJECT_END,
            desc=self.cmd_EXCLUDE_OBJECT_END_help)
        self.gcode.register_command(
            'EXCLUDE_OBJECT', self.cmd_EXCLUDE_OBJECT,
            desc=self.cmd_EXCLUDE_OBJECT_help)
        self.gcode.register_command(
            'EXCLUDE_OBJECT_DEFINE', self.cmd_EXCLUDE_OBJECT_DEFINE,
            desc=self.cmd_EXCLUDE_OBJECT_DEFINE_help)

    def _register_transform(self):
        if self.next_transform is None:
            tuning_tower = self.printer.lookup_object('tuning_tower')
            if tuning_tower.is_active():
                logging.info('The ExcludeObject move transform is not being '
                    'loaded due to Tuning tower being Active')
                return

            self.next_transform = self.gcode_move.set_move_transform(self,
                                                                     force=True)
            self.extrusion_offsets = {}
            self.max_position_extruded_by_extruder = {}
            self.max_position_excluded_by_extruder = {}
            self.extruder_adj = 0
            self.initial_extrusion_moves = 5
            self.last_position = [0., 0., 0., 0.]
            self.last_position_e = {}
            self.last_position_e_extruded = {}
            self.last_position_e_excluded = {}
            self.last_tx_position = None

            self.get_position()
            self.last_position_extruded[:] = self.last_position
            self.last_position_excluded[:] = self.last_position

            for i in range(self.toolhead.max_physical_extruder_num):
                extruder_obj = self.printer.lookup_object('extruder', None)
                if i != 0:
                    extruder_obj = self.printer.lookup_object(f"extruder{i}", None)
                if extruder_obj is not None:
                    extruder_name = extruder_obj.get_name()
                    self.last_position_e[extruder_name] = extruder_obj.last_position
                    self.last_position_e_extruded[extruder_name] = extruder_obj.last_position
                    self.last_position_e_excluded[extruder_name] = extruder_obj.last_position
                    self.max_position_extruded_by_extruder[extruder_name] = extruder_obj.last_position
                    self.max_position_excluded_by_extruder[extruder_name] = extruder_obj.last_position

    def _handle_connect(self):
        self.toolhead = self.printer.lookup_object('toolhead')
        self.print_stats = self.printer.lookup_object('print_stats', None)

    def _unregister_transform(self):
        if self.next_transform:
            tuning_tower = self.printer.lookup_object('tuning_tower')
            if tuning_tower.is_active():
                logging.error('The Exclude Object move transform was not '
                    'unregistered because it is not at the head of the '
                    'transform chain.')
                return

            self.gcode_move.set_move_transform(self.next_transform, force=True)
            self.next_transform = None
            self.gcode_move.reset_last_position()

    def _reset_state(self):
        self.objects = []
        self.excluded_objects = []
        self.current_object = None
        self.in_excluded_region = False

    def _reset_file(self):
        self._reset_state()
        self._unregister_transform()

    def _get_extrusion_offsets(self):
        extruder_name = self.toolhead.get_extruder().get_name()
        offset = self.extrusion_offsets.get(extruder_name)
        if offset is None:
            offset = [0., 0., 0., 0.]
            self.extrusion_offsets[extruder_name] = \
                offset
        return offset

    def _get_last_position_e(self):
        extruder_name = self.toolhead.get_extruder().get_name()
        pos = self.last_position_e.get(extruder_name, None)
        if pos is None:
            pos = 0
            self.last_position_e[extruder_name] = pos
        return pos

    def _get_max_position_extruded(self):
        extruder_name = self.toolhead.get_extruder().get_name()
        pos = self.max_position_extruded_by_extruder.get(extruder_name, None)
        if pos is None:
            pos = 0
            self.max_position_extruded_by_extruder[extruder_name] = pos
        return pos

    def _get_max_position_excluded(self):
        extruder_name = self.toolhead.get_extruder().get_name()
        pos = self.max_position_excluded_by_extruder.get(extruder_name, None)
        if pos is None:
            pos = 0
            self.max_position_excluded_by_extruder[extruder_name] = pos
        return pos

    def _get_last_position_e_extruded(self):
        extruder_name = self.toolhead.get_extruder().get_name()
        pos = self.last_position_e_extruded.get(extruder_name, None)
        if pos is None:
            pos = 0
            self.last_position_e_extruded[extruder_name] = pos
        return pos

    def _get_last_position_e_excluded(self):
        extruder_name = self.toolhead.get_extruder().get_name()
        pos = self.last_position_e_excluded.get(extruder_name, None)
        if pos is None:
            pos = 0
            self.last_position_e_excluded[extruder_name] = pos
        return pos

    def get_position(self):
        offset = self._get_extrusion_offsets()
        pos = self.next_transform.get_position()
        if self.last_tx_position is None or any(
                abs(pos[i] - self.last_tx_position[i]) > 1e-6 for i in range(3)):
            # The head is not where this transform last sent it (a manual_move
            # park, homing, a tool change): the skipped-object XYZ offset no
            # longer describes where it is, so restart from the real position.
            offset[0] = offset[1] = offset[2] = 0.
            self.last_position_extruded[:3] = pos[:3]
            self.last_tx_position = pos[:3]
        self._get_last_position_e()
        for i in range(4):
            self.last_position[i] = pos[i] + offset[i]
        extruder_name = self.toolhead.get_extruder().get_name()
        self.last_position_e[extruder_name] = self.last_position[3]
        return list(self.last_position)

    def _normal_move(self, newpos, speed):
        offset = self._get_extrusion_offsets()
        last_pos_e = self._get_last_position_e()
        extruder_name = self.toolhead.get_extruder().get_name()

        if self.initial_extrusion_moves > 0 and \
            last_pos_e != newpos[3]:
            # Since the transform is not loaded until there is a request to
            # exclude an object, the transform needs to track a few extrusions
            # to get the state of the extruder
            self.initial_extrusion_moves -= 1

        self.last_position[:] = newpos
        self.last_position_e[extruder_name] = newpos[3]
        self.last_position_extruded[:] = self.last_position
        self.last_position_e_extruded[extruder_name] =  newpos[3]
        self.max_position_extruded_by_extruder[extruder_name] = \
                    max(self._get_max_position_extruded(), newpos[3])

        # These next few conditionals handle the moves immediately after leaving
        # and excluded object.  The toolhead is at the end of the last printed
        # object and the gcode is at the end of the last excluded object.
        #
        # Ideally, there will be Z and E moves right away to adjust any offsets
        # before moving away from the last position.  Any remaining corrections
        # will be made on the firs XY move.
        left_skipped_xy = False
        if (offset[0] != 0 or offset[1] != 0) and \
            (newpos[0] != self.last_position_excluded[0] or \
            newpos[1] != self.last_position_excluded[1]):
            offset[0] = 0
            offset[1] = 0
            offset[2] = 0
            offset[3] += self.extruder_adj
            self.extruder_adj = 0
            left_skipped_xy = True

        if offset[2] != 0 and newpos[2] != self.last_position_excluded[2]:
            offset[2] = 0

        if self.extruder_adj != 0 and \
            newpos[3] != self.last_position_e_excluded[extruder_name]:
            offset[3] += self.extruder_adj
            self.extruder_adj = 0

        tx_pos = newpos[:]
        for i in range(4):
            tx_pos[i] = newpos[i] - offset[i]
        if left_skipped_xy and self.last_tx_position is not None \
                and tx_pos[2] > self.last_tx_position[2]:
            # The slicer planned this lift from the skipped object's last
            # point; the head is at the last printed one. Lift there first, so
            # the travel does not ramp up across finished parts.
            self.next_transform.move(
                self.last_tx_position[:2] + [tx_pos[2],
                self.next_transform.get_position()[3]], speed)
        self.next_transform.move(tx_pos, speed)
        self.last_tx_position = tx_pos[:3]

    def _ignore_move(self, newpos, speed):
        offset = self._get_extrusion_offsets()
        last_pos_e = self._get_last_position_e()
        extruder_name = self.toolhead.get_extruder().get_name()

        for i in range(3):
            offset[i] = newpos[i] - self.last_position_extruded[i]
        offset[3] = offset[3] + newpos[3] - last_pos_e
        self.last_position[:] = newpos
        self.last_position_e[extruder_name] = newpos[3]
        self.last_position_excluded[:] =self.last_position
        self.last_position_e_excluded[extruder_name] = newpos[3]
        self.max_position_excluded_by_extruder[extruder_name] = \
                            max(self._get_max_position_excluded(), newpos[3])

    def _move_into_excluded_region(self, newpos, speed):
        self.in_excluded_region = True
        self._ignore_move(newpos, speed)

    def _move_from_excluded_region(self, newpos, speed):
        extruder_name = self.toolhead.get_extruder().get_name()

        self.in_excluded_region = False

        # This adjustment value is used to compensate for any retraction
        # differences between the last object printed and excluded one.
        self.extruder_adj = self.max_position_excluded_by_extruder[extruder_name] \
            - self.last_position_e_excluded[extruder_name] \
            - (self.max_position_extruded_by_extruder[extruder_name] \
               - self.last_position_e_extruded[extruder_name])
        self._normal_move(newpos, speed)

    def _test_in_excluded_region(self):
        # Inside cancelled object
        return self.current_object in self.excluded_objects \
            and self.initial_extrusion_moves == 0

    def get_status(self, eventtime=None):
        status = {
            "objects": self.objects,
            "excluded_objects": self.excluded_objects,
            "current_object": self.current_object,
            "in_excluded_region": self.in_excluded_region
        }
        return status

    def move(self, newpos, speed):
        move_in_excluded_region = self._test_in_excluded_region()
        self.last_speed = speed
        apply_exclusion = True

        if self.print_stats is not None:
            apply_exclusion = (self.print_stats.state == 'printing')

        if apply_exclusion:
            if move_in_excluded_region:
                if self.in_excluded_region:
                    self._ignore_move(newpos, speed)
                else:
                    self._move_into_excluded_region(newpos, speed)
            else:
                if self.in_excluded_region:
                    self._move_from_excluded_region(newpos, speed)
                else:
                    self._normal_move(newpos, speed)
        else:
            self._normal_move(newpos, speed)

    cmd_EXCLUDE_OBJECT_START_help = "Marks the beginning the current object" \
                                    " as labeled"
    def cmd_EXCLUDE_OBJECT_START(self, gcmd):
        name = gcmd.get('NAME').upper()
        if not any(obj["name"] == name for obj in self.objects):
            self._add_object_definition({"name": name})
        self.current_object = name
        self.was_excluded_at_start = self._test_in_excluded_region()

    cmd_EXCLUDE_OBJECT_END_help = "Marks the end the current object"
    def cmd_EXCLUDE_OBJECT_END(self, gcmd):
        if self.current_object == None and self.next_transform:
            gcmd.respond_info("EXCLUDE_OBJECT_END called, but no object is"
                              " currently active")
            return
        name = gcmd.get('NAME', default=None)
        if name != None and name.upper() != self.current_object:
            gcmd.respond_info("EXCLUDE_OBJECT_END NAME=%s does not match the"
                              " current object NAME=%s" %
                              (name.upper(), self.current_object))

        self.current_object = None

    cmd_EXCLUDE_OBJECT_help = "Cancel moves inside a specified objects"
    def cmd_EXCLUDE_OBJECT(self, gcmd):
        reset = gcmd.get('RESET', None)
        current = gcmd.get('CURRENT', None)
        name = gcmd.get('NAME', '').upper()

        if self.toolhead is None:
            raise self.gcode.error("toolhead not found")

        rec_exclude_objects = True
        if reset:
            if name:
                self._unexclude_object(name)

            else:
                self.excluded_objects = []

        elif name:
            if name.upper() not in self.excluded_objects:
                self._exclude_object(name.upper())

        elif current:
            if not self.current_object:
                raise self.gcode.error('There is no current object to cancel')

            else:
                self._exclude_object(self.current_object)

        else:
            rec_exclude_objects = False
            self._list_excluded_objects(gcmd)

        virtual_sdcard = self.printer.lookup_object('virtual_sdcard', None)
        if virtual_sdcard is not None and rec_exclude_objects:
            virtual_sdcard.record_pl_print_exclude_objects_env()

    cmd_EXCLUDE_OBJECT_DEFINE_help = "Provides a summary of an object"
    def cmd_EXCLUDE_OBJECT_DEFINE(self, gcmd):
        reset = gcmd.get('RESET', None)
        name = gcmd.get('NAME', '').upper()

        if reset:
            self._reset_file()

        elif name:
            parameters = gcmd.get_command_parameters().copy()
            parameters.pop('NAME')
            center = parameters.pop('CENTER', None)
            polygon = parameters.pop('POLYGON', None)

            obj = {"name": name.upper()}
            obj.update(parameters)

            if center != None:
                obj['center'] = json.loads('[%s]' % center)

            if polygon != None:
                raw = json.loads(polygon)
                if len(raw) > 20:
                    rounded = [[int(round(x)), int(round(y))] for x, y in raw]
                    deduped = [p for i, p in enumerate(rounded)
                            if i == 0 or p != rounded[i-1]]
                    if len(deduped) >= 3:
                        obj['polygon'] = deduped
                    else:
                        obj['polygon'] = [[round(x, 1), round(y, 1)] for x, y in raw]
                else:
                    obj['polygon'] = raw

            self._add_object_definition(obj)

        else:
            self._list_objects(gcmd)

    def _add_object_definition(self, definition):
        self.objects = sorted(self.objects + [definition],
                              key=lambda o: o["name"])

    def _exclude_object(self, name):
        self._register_transform()
        self.gcode.respond_info('Excluding object {}'.format(name.upper()))
        if name not in self.excluded_objects:
            self.excluded_objects = sorted(self.excluded_objects + [name])

    def _unexclude_object(self, name):
        self.gcode.respond_info('Unexcluding object {}'.format(name.upper()))
        if name in self.excluded_objects:
            excluded_objects = list(self.excluded_objects)
            excluded_objects.remove(name)
            self.excluded_objects = sorted(excluded_objects)

    def _list_objects(self, gcmd):
        if gcmd.get('JSON', None) is not None:
            object_list = json.dumps(self.objects)
        else:
            object_list = " ".join(obj['name'] for obj in self.objects)
        gcmd.respond_info('Known objects: {}'.format(object_list))

    def _list_excluded_objects(self, gcmd):
        object_list = " ".join(self.excluded_objects)
        gcmd.respond_info('Excluded objects: {}'.format(object_list))

def load_config(config):
    return ExcludeObject(config)
