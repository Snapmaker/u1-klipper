# exception manager for klippy
#
# Copyright (C) 2025-2030  Scott Huang <shili.huang@snapmaker.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import logging, os, json, copy, queuefile

EXCEPTION_PERSISTENT_FILE = 'exception_persistent.json'

class ExceptionList:
    MODULE_ID_MOTION                     = 522
    MODULE_ID_TOOLHEAD                   = 523
    MODULE_ID_CAMERA                     = 524
    MODULE_ID_FEEDING                    = 525
    MODULE_ID_HEATER_BED                 = 526
    MODULE_ID_CAVITY                     = 527
    MODULE_ID_HOMING                     = 528
    MODULE_ID_GCODE                      = 529
    MODULE_ID_PROBE_OR_CALIBRATION       = 530
    MODULE_ID_PRINT_FILE                 = 531
    MODULE_ID_DEFECT_DETECTION           = 532
    MODULE_ID_PURIFIER                   = 533
    MODULE_ID_SYSTEM                     = 2052

    # TOOLHEAD
    CODE_TOOLHEAD_FILAMENT_RUNOUT = 0

    # FEEDING
    CODE_FEEDING_GENERIC                    = 0
    CODE_FEEDING_MOTOR_SPEED                = 1
    CODE_FEEDING_WHEEL_SPEED                = 2
    CODE_FEEDING_NO_FILAMENT                = 3

    def __init__(self):
        pass

class ExceptionManager:
    def __init__(self, printer):
        self.printer = printer
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.webhooks = self.printer.lookup_object('webhooks')

        config_dir = self.printer.get_snapmaker_config_dir()
        self.exception_file_path = os.path.join(config_dir, EXCEPTION_PERSISTENT_FILE)
        self.allow_moonraker_throw = False

        self.exceptions = []
        self.reported_exceptions = []
        self.async_exceptions = []
        self.list = ExceptionList()

        self.file_lock = self.reactor.mutex()

        persistent_exceptions = self._load_persistent_exceptions()
        for key, exception_data in persistent_exceptions.items():
            parsed = self._parse_basic_code(key)
            if parsed:
                self.exceptions.append({
                    'id': parsed['id'],
                    'index': parsed['index'],
                    'code': parsed['code'],
                    'level': exception_data['level'],
                    'message': exception_data['message']
                })

        self.gcode.register_command('RAISE_EXCEPTION', self.cmd_RAISE_EXCEPTION)
        self.gcode.register_command('CLEAR_EXCEPTION', self.cmd_CLEAR_EXCEPTION)
        self.gcode.register_command('QUERY_EXCEPTION', self.cmd_QUERY_EXCEPTION)
        self.gcode.register_command('RM_EXCEPTION_PERSISTENT_FILE', self.cmd_RM_EXCEPTION_PERSISTENT_FILE)

        self.async_handle_timer = self.reactor.register_timer(self._handle_async_exception)
        self.allow_throw_check_timer = self.reactor.register_timer(self._allow_moonraker_throw_check, self.reactor.NOW)

    def _allow_moonraker_throw_check(self, eventtime):
        if not self.allow_moonraker_throw:
            self.allow_moonraker_throw = self.webhooks.has_remote_method('raise_exception')
            return eventtime + 1
        logging.info("Moonraker throw is already allowed.")
        return self.reactor.NEVER

    @staticmethod
    def _parse_basic_code(coded_string):
        try:
            parts = coded_string.split('-')
            if len(parts) != 3:
                logging.warning(f"Expected 3-part format without level, got: {coded_string}")
                return None
            return {
                "id": int(parts[0]),
                "index": int(parts[1]),
                "code": int(parts[2])
            }
        except ValueError as e:
            logging.exception(f"Failed to parse basic_code string: {coded_string}")
            return None

    @staticmethod
    def _parse_structured_code(coded_string):
        try:
            parts = coded_string.split('-')
            if len(parts) != 4:
                logging.warning(f"Expected 4-part format, got: {coded_string}")
                return None
            return {
                "level": int(parts[0]),
                "id": int(parts[1]),
                "index": int(parts[2]),
                "code": int(parts[3])
            }
        except ValueError as e:
            logging.exception(f"Failed to parse structured_coded string: {coded_string}")
            return None

    def _validate_coded_key(self, key):
        if not key.replace('-', '').isdigit():
            logging.warning(f"Invalid key contains non-digit characters: {key}")
            return False

        parsed = self._parse_basic_code(key)
        if parsed is None:
            return False

        return True

    def _load_persistent_exceptions(self):
        raw_data = self._read_exception_file()
        if not raw_data:
            return {}

        try:
            valid_data = {}
            invalid_entries = []

            for key, value in raw_data.items():
                if not self._validate_coded_key(key):
                    invalid_entries.append(f"Invalid coded key: {key}")
                    continue

                if not isinstance(value, dict):
                    invalid_entries.append(f"Value must be dict for key: {key}")
                    continue

                if 'level' not in value:
                    invalid_entries.append(f"Missing/invalid level for key: {key}")
                    continue

                if 'message' not in value:
                    invalid_entries.append(f"Missing/invalid message for key: {key}")
                    continue

                valid_data[key] = value

            if invalid_entries:
                logging.warning(f"Found {len(invalid_entries)} invalid entries:\n" +
                            "\n".join(invalid_entries))

            return valid_data

        except Exception as e:
            logging.error(f"Error loading persistent exceptions: {str(e)}")
            return {}

    def _read_exception_file(self):
        """Read the persistent exception file. Uses the async read thread when
        the reactor is running (non-blocking), else synchronous (startup)."""
        if getattr(self.reactor, '_g_dispatch', None) is not None:
            try:
                from asyncfilereader import get_async_file_io
                reader = get_async_file_io()
                req = reader.submit_read(self.exception_file_path, parse_json=True)
                result = reader.wait(req, self.reactor)
                return result if isinstance(result, dict) else {}
            except FileNotFoundError:
                return {}
            except Exception:
                logging.exception("Error loading persistent exceptions")
                return {}
        if not os.path.exists(self.exception_file_path):
            return {}
        try:
            with open(self.exception_file_path, 'r') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logging.error(f"Error loading persistent exceptions: {str(e)}")
            return {}

    def save_persistent_exception(self, coded_code, level, message):
        if not self._validate_coded_key(coded_code):
            logging.error(f"Invalid coded_code format: {coded_code}")
            return False

        data = self._load_persistent_exceptions()
        if coded_code in data and data[coded_code]['message'] == message and data[coded_code]['level'] == level:
            logging.warning(f"Exception with coded_code {coded_code} already exists in persistent storage.")
            return True  # Already exists
        data[coded_code] = {'level': level, 'message': message}
        try:
            json_content = json.dumps(data, indent=4)
            queuefile.async_write_file(self.exception_file_path, json_content, safe_write=True)
            return True
        except Exception as e:
            logging.error(f"Error saving persistent exception: {str(e)}")
            return False

    def clear_persistent_exception(self, coded_code):
        if not self._validate_coded_key(coded_code):
            logging.error(f"Invalid coded_code format: {coded_code}")
            return False

        data = self._load_persistent_exceptions()
        if coded_code not in data:
            # logging.warning(f"Exception with coded_code {coded_code} does not exist in persistent storage.")
            return False

        del data[coded_code]
        logging.info(f"Clearing persistent exception: {coded_code}")
        try:
            json_content = json.dumps(data, indent=4)
            queuefile.async_write_file(self.exception_file_path, json_content, safe_write=True)
            return True
        except Exception as e:
            logging.error(f"Error clearing persistent exception: {str(e)}")
            return False

    def remove_persistent_exceptions(self):
        try:
            queuefile.async_delete_file(self.exception_file_path)
            return True
        except Exception as e:
            logging.error(f"Error removing persistent exceptions: {str(e)}")
            return False

    def _handle_async_exception(self, eventtime):
        # got one exception from queue to raise it to moonraker
        # must be attention to the order of exceptions
        id, index, code, message, oneshot, level, is_persistent = self.async_exceptions.pop(0)
        self.raise_exception(id, index, code, message, oneshot, level, is_persistent)
        if len(self.async_exceptions) > 0:
            return eventtime + 0.001
        return self.reactor.NEVER

    def is_allowed_to_throw_to_moonraker(self):
        return self.allow_moonraker_throw

    def raise_exception_async(self, id, index, code, message, oneshot=1, level=None, is_persistent=0, action=None):
        action_levels = {
            'none': 1,
            'pause': 2,
            'pause_runout': 2,
            'cancel': 3
        }
        level = level if level is not None else action_levels.get(action, 3)
        self.async_exceptions.append((id, index, code, message, oneshot, level, is_persistent))
        self.reactor.update_timer(self.async_handle_timer, self.reactor.NOW)

    def raise_exception(self, id, index, code, message, oneshot=1, level=3, is_persistent=0):
        if not oneshot:
            duplicate, updated = False, False
            # cache = {'id': id, 'index': index, 'code': code, 'level': level, 'message': message}
            for e in self.exceptions:
                try:
                    if (e['id'] == id and e['index'] == index and e['code'] == code):
                        if e['level'] == level and e['message'] == message:
                            duplicate = True
                        else:
                            e.update({'level': level, 'message': message})
                            updated = True
                        break
                except KeyError:
                    continue

            if not duplicate and not updated:
                self.exceptions.append({
                    'id': id, 'index': index, 'code': code,
                    'level': level, 'message': message
                })

            if is_persistent:
                if not self.save_persistent_exception(f"{id:04d}-{index:04d}-{code:04d}", level, message):
                    logging.error(f"Failed to save persistent exception: {message}")

        logging.info(f"Raising exception: id:{id} index:{index} code:{code} oneshot:{oneshot} level:{level} is_persistent:{is_persistent}, message: {message}")

        if self.is_allowed_to_throw_to_moonraker():
            try:
                self.webhooks.call_remote_method('raise_exception', id=id, index=index,
                                                code=code, message=message, oneshot=oneshot, level=level)
            except self.printer.command_error:
                logging.exception("moonraker didn't response remote method: raise_exception")
    # TODO: Integrate this logic into the _handle_async_exception function for centralized exception handling
    def clear_exception(self, id, index, code, gcmd=None):
        excep = {'id': id, 'index': index, 'code': code}

        to_remove = [ex for ex in self.exceptions
                    if all(ex.get(k) == v for k, v in excep.items())]

        if to_remove:
            for ex in to_remove:
                self.exceptions.remove(ex)
                self.clear_persistent_exception(f"{id:04d}-{index:04d}-{code:04d}")

        self.clear_persistent_exception(f"{id:04d}-{index:04d}-{code:04d}")

        if self.is_allowed_to_throw_to_moonraker():
            try:
                self.webhooks.call_remote_method('clear_exception', id=id, index=index, code=code)
            except self.printer.command_error:
                logging.exception("moonraker didn't response remote method: clear_exception")
        # else:
        #     logging.error("can only clear motion and toolhead exception on moonraker")
        if to_remove:
            logging.info(f'exception cleared: id:{id} index:{index} code:{code}')

        if gcmd and to_remove:
            gcmd.respond_raw(f'exception cleared: id:{id} index:{index} code:{code}')

    def has_exception(self, id, index, code):
        for ex in self.exceptions:
            if ex.get('id') == id and ex.get('index') == index and ex.get('code') == code:
                return True
        return False

    def get_status(self, eventtime):
        if self.reported_exceptions != self.exceptions:
            self.reported_exceptions = copy.deepcopy(self.exceptions)
        return {'exceptions': self.reported_exceptions}

    def cmd_RAISE_EXCEPTION(self, gcmd):
        id = gcmd.get_int('ID', self.list.MODULE_ID_MOTION)
        index = gcmd.get_int('INDEX')
        code = gcmd.get_int('CODE')
        oneshot = gcmd.get_int('ONESHOT', 1)
        level = gcmd.get_int('LEVEL', 3)
        is_persistent = gcmd.get_int('IS_PERSISTENT', 0)
        message = gcmd.get('MSG', None)
        if message is None:
            message = f'exception id:{id} index:{index} code:{code} oneshot:{oneshot} level:{level} is_persistent:{is_persistent}'
        self.raise_exception(id, index, code, message, oneshot, level, is_persistent)
        gcmd.respond_raw(message)

    def cmd_CLEAR_EXCEPTION(self, gcmd):
        id = gcmd.get_int('ID')
        index = gcmd.get_int('INDEX')
        code = gcmd.get_int('CODE')
        self.clear_exception(id, index, code, gcmd)
        # gcmd.respond_info(f'clear exception id:{id} index:{index} code:{code}')

    def cmd_QUERY_EXCEPTION(self, gcmd):
        for e in self.exceptions:
            gcmd.respond_info(f"{e['level']:04d}-{e['id']:04d}-{e['index']:04d}-{e['code']:04d}, message: {e['message']}")

    def cmd_RM_EXCEPTION_PERSISTENT_FILE(self, gcmd):
        persistent_exceptions = self._load_persistent_exceptions()
        exceptions = []
        for key, exception_data in persistent_exceptions.items():
            parsed = self._parse_basic_code(key)
            if parsed:
                exceptions.append({
                    'id': parsed['id'],
                    'index': parsed['index'],
                    'code': parsed['code'],
                    'level': exception_data['level'],
                    'message': exception_data['message']
                })
        logging.info(f"Removing persistent exceptions: {len(exceptions)} found")
        for e in exceptions:
            self.clear_exception(e['id'], e['index'], e['code'])
        self.remove_persistent_exceptions()

def add_early_printer_objects(printer):
    printer.add_object('exception_manager', ExceptionManager(printer))
