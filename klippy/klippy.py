#!/usr/bin/env python2
# Main code for host side printer firmware
#
# Copyright (C) 2016-2024  Kevin O'Connor <kevin@koconnor.net>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import sys, os, gc, optparse, logging, time, collections, importlib, json, copy, re
import pwd, grp
import util, reactor, queuelogger, msgproto, queuefile
import asyncfilereader
import json_compat
import gcode, configfile, pins, mcu, toolhead, webhooks, exception_manager, coded_exception, printer_device_scan
# import traceback

message_ready = "Printer is ready"

message_startup = """
Printer is not ready
The klippy host software is attempting to connect.  Please
retry in a few moments.
"""

message_restart = """
Once the underlying issue is corrected, use the "RESTART"
command to reload the config and restart the host software.
Printer is halted
"""

SCHED_FIFO_PRIORITY = 10  # SCHED_FIFO priority for the main thread

class Printer:
    config_error = configfile.error
    command_error = gcode.CommandError
    def __init__(self, main_reactor, bglogger, start_args):
        self.bglogger = bglogger
        self.start_args = start_args
        self.reactor = main_reactor
        self.reactor.register_callback(self._connect)
        self.state_message = message_startup
        self.in_shutdown_state = False
        self.run_result = None
        self.event_handlers = {}
        self.objects = collections.OrderedDict()
        # Init printer components that must be setup prior to config
        for m in [gcode, webhooks, exception_manager]:
            m.add_early_printer_objects(self)
    def get_config_dir(self):
        try:
            return os.path.dirname(self.start_args['config_file'])
        except Exception:
            # return home directory if no config file is specified
            return os.path.expanduser("~")
    def set_extruder_power(self, state, extruder=['all']):
        """Set the extruder power state."""
        try:
            if state == 'on':
                logging.info("Setting extruder power ON")
                os.system("lava_io set HEAD_MCU_POWER=0 HEAD_MCU0_BOOT=1 HEAD_MCU1_BOOT=1 HEAD_MCU2_BOOT=1 HEAD_MCU3_BOOT=1")
                time.sleep(0.2)
                os.system("lava_io set HEAD_MCU_POWER=1")
            elif state == 'off':
                logging.info("Setting extruder power OFF")
                os.system("lava_io set HEAD_MCU_POWER=0")
            else:
                logging.error("Invalid state: %s" % (state,))
                return False
        except Exception as e:
            logging.error("Failed to set extruder power: %s" % (str(e),))
            return False
        return True
    def set_main_mcu_power(self, state):
        try:
            if state == 'on':
                logging.info("Setting main MCU power ON")
                os.system("lava_io set MAIN_MCU_POWER=0")
                time.sleep(0.2)
                os.system("lava_io set MAIN_MCU_POWER=1")
            else:
                logging.info("Setting main MCU power OFF")
                os.system("lava_io set MAIN_MCU_POWER=0")
            return True
        except Exception as e:
            logging.error(f"Failed to set main power: {e}")
            return False
    def get_snapmaker_config_dir(self, dir_name="snapmaker"):
        dir = os.path.join(self.get_config_dir(), dir_name)
        try:
            if not os.path.exists(dir):
                os.makedirs(dir)
        except Exception:
            logging.error("Failed to create Snapmaker config directory")
            return os.path.expanduser("~")
        return dir

    def check_extruder_config_permission(self):
        return True

    def is_valid_json_format(self, obj):
        if not isinstance(obj, dict):
            return False
        try:
            json.dumps(obj)
            return True
        except TypeError:
            return False
        except Exception as e:
            return False

    def load_snapmaker_config_file(self, path=None, default_config=None, format='json',
                                   create_if_not_exist=False):
        if path is None:
            raise ValueError("The path parameter must be specified!")
        if not format in ['json']:
            raise ValueError("The file format is not supported: %s" % (format))

        config_info = None
        if format == 'json':
            try:
                config_info = self._read_config_json(path)
            except FileNotFoundError:
                logging.error("config file not exits: %s" % (path))
                if default_config is not None:
                    config_info = copy.deepcopy(default_config)
                else:
                    config_info = {}
                try:
                    if create_if_not_exist:
                        json_content = json_compat.dumps(config_info, indent=4)
                        queuefile.async_write_file(path, json_content, safe_write=True)
                except:
                    logging.error("create config file err: %s" % (path))
            except Exception:
                if default_config is not None:
                    config_info = copy.deepcopy(default_config)
                else:
                    config_info = {}
            else:
                if default_config is not None:
                    config_info.update({key: config_info.get(key, default_value)
                                        for key, default_value in default_config.items()})

        return config_info

    def _read_config_json(self, path):
        """Read a JSON config file. Returns dict on success.
        Raises FileNotFoundError if file not found.
        Uses async read thread when reactor is running (non-blocking),
        else synchronous (startup)."""
        if getattr(self.reactor, '_g_dispatch', None) is not None:
            reader = asyncfilereader.get_async_file_io()
            req = reader.submit_read(path, parse_json=True)
            result = reader.wait(req, self.reactor)
            if not isinstance(result, dict):
                raise ValueError("config file content is not a dict: %s" % path)
            return result
        with open(path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        if not isinstance(data, dict):
            raise ValueError("config file content is not a dict: %s" % path)
        return data

    def update_snapmaker_config_file(self, path=None, config_info=None, default_config=None, format='json'):
        if path is None:
            raise ValueError("The path parameter must be specified!")
        if not format in ['json']:
            raise ValueError("The file format is not supported: %s" % (format))

        update_ok = False
        if format == 'json':
            if config_info == None:
                config_info = {}

            if not self.is_valid_json_format(config_info):
                raise ValueError("The config_info is not json format!")

            try:
                json_content = json.dumps(config_info, indent=4)
                queuefile.async_write_file(path, json_content, safe_write=True)
                update_ok = True
            except IOError as e:
                logging.error(f"Error writing to file: {e}")
            except Exception as e:
                logging.error(f"Unknown error: {e}")
            finally:
                return update_ok

    def extract_encoded_message(self, message):
        try:
            if isinstance(message, str):
                try:
                    json_match = re.search(r'\{[\s\S]*\}', message)
                    if not json_match:
                        # logging.warning("No JSON-like structure found in input text:\n{}".format(message))
                        return None
                    json_str = json_match.group(0)
                    # Try to parse JSON
                    try:
                        data = json.loads(json_str)
                        return data
                    except json.JSONDecodeError as e:
                        logging.error(f"JSON parsing failed: {e}")
                        logging.error(f"Problematic JSON: {json_str}")
                        return None

                except Exception as e:
                    logging.error(f"Unexpected error during JSON extraction: {e}")
                    return None
            elif isinstance(message, dict):
                return message
            else:
                logging.warning(f"Unsupported data type: {type(message)}")
                return None
        except Exception as e:
            logging.error(f"Unexpected error during processing: {e}")
            return None

    def extract_coded_message_field(self, input_data, field_name='msg'):
        try:
            extracted = self.extract_encoded_message(input_data)
            if isinstance(extracted, dict) and field_name in extracted:
                return extracted[field_name]
            return input_data

        except Exception as e:
            logging.error(f"Error in extract_field: {str(e)}")
            return input_data

    def raise_structured_code_exception(self, structured_code, message=None, oneshot=1, is_persistent=0, action=None):
        try:
            exception_manager = self.lookup_object('exception_manager', None)
            if exception_manager is not None:
                parsed_info = exception_manager._parse_structured_code(structured_code)
                if parsed_info is not None:
                    id = parsed_info['id']
                    index = parsed_info['index']
                    code = parsed_info['code']
                    level = parsed_info.get('level', None)
                    exception_manager.raise_exception_async(
                        id, index, code, message, oneshot, level, is_persistent, action)
                else:
                    logging.error("Invalid structured code format: {}".format(structured_code))
        except Exception as e:
            logging.error("Failed to raise structured code exception: {}".format(e))

    def clear_structured_code_exception(self, structured_code):
        try:
            exception_manager = self.lookup_object('exception_manager', None)
            if exception_manager is not None:
                parsed_info = exception_manager._parse_structured_code(structured_code)
                if parsed_info is not None:
                    id = parsed_info['id']
                    index = parsed_info['index']
                    code = parsed_info['code']
                    exception_manager.clear_exception(id, index, code)
        except Exception as e:
            logging.error("Failed to clear structured code exception: {}".format(structured_code))

    def clear_exception(self, id, index, code):
        exception_manager = self.lookup_object('exception_manager', None)
        if exception_manager is not None:
            exception_manager.clear_exception(id, index, code)

    def raise_coded_exception(self, exception, parse_coded_msg=True):
        try:
            # stack_str = "".join(traceback.format_stack())
            # logging.info("Call stack:\n%s", stack_str)
            exception_manager = self.lookup_object('exception_manager', None)
            if exception_manager is not None:
                exc_obj = coded_exception.CodedException.from_exception(exception)
                id, index, code, message, oneshot, level, is_persistent, action, proactive_report = \
                    exc_obj.id, exc_obj.index, exc_obj.code, exc_obj.message, exc_obj.oneshot, \
                    exc_obj.level, exc_obj.is_persistent, exc_obj.action, exc_obj.proactive_report
                if parse_coded_msg and message:
                    coded_message = self.extract_encoded_message(message)
                    if coded_message is not None:
                        structured_code = coded_message.get("coded", None)
                        if structured_code is not None:
                            parsed_structured_code = exception_manager._parse_structured_code(structured_code)
                            id = parsed_structured_code.get("id", id)
                            index = parsed_structured_code.get("index", index)
                            code = parsed_structured_code.get("code", code)
                            level = parsed_structured_code.get("level", level)
                        else:
                            id = coded_message.get("id", id)
                            index = coded_message.get("index", index)
                            code = coded_message.get("code", code)
                            level = coded_message.get("level", level)
                        message = coded_message.get("msg", message)
                        oneshot = coded_message.get("oneshot", oneshot)
                        is_persistent = coded_message.get("is_persistent", is_persistent)
                        action = coded_message.get("action", action)
                        proactive_report = coded_message.get("proactive_report", proactive_report)

                if not proactive_report:
                    logging.info(f"Exception not reported proactively: id:{id} index:{index} code:{code}")
                    return

                exception_manager.raise_exception_async(
                            id, index, code, message, oneshot, level, is_persistent, action)
        except Exception as e:
            logging.error("Failed to raise exception: {}".format(e))

    def get_start_args(self):
        return self.start_args
    def get_reactor(self):
        return self.reactor
    def get_state_message(self):
        if self.state_message == message_ready:
            category = "ready"
        elif self.state_message == message_startup:
            category = "startup"
        elif self.in_shutdown_state:
            category = "shutdown"
        else:
            category = "error"
        return self.state_message, category
    def is_shutdown(self):
        return self.in_shutdown_state
    def _set_state(self, msg):
        if self.state_message in (message_ready, message_startup):
            self.state_message = msg
        if (msg != message_ready
            and self.start_args.get('debuginput') is not None):
            self.request_exit('error_exit')
    def update_error_msg(self, oldmsg, newmsg):
        if (self.state_message != oldmsg
            or self.state_message in (message_ready, message_startup)
            or newmsg in (message_ready, message_startup)):
            return
        self.state_message = newmsg
        logging.error(newmsg)
    def add_object(self, name, obj):
        if name in self.objects:
            raise self.config_error(
                "Printer object '%s' already created" % (name,))
        self.objects[name] = obj
    def lookup_object(self, name, default=configfile.sentinel):
        if name in self.objects:
            return self.objects[name]
        if default is configfile.sentinel:
            raise self.config_error("Unknown config object '%s'" % (name,))
        return default
    def lookup_objects(self, module=None):
        if module is None:
            return list(self.objects.items())
        prefix = module + ' '
        objs = [(n, self.objects[n])
                for n in self.objects if n.startswith(prefix)]
        if module in self.objects:
            return [(module, self.objects[module])] + objs
        return objs
    def load_object(self, config, section, default=configfile.sentinel):
        if section in self.objects:
            return self.objects[section]
        module_parts = section.split()
        module_name = module_parts[0]
        py_name = os.path.join(os.path.dirname(__file__),
                               'extras', module_name + '.py')
        py_dirname = os.path.join(os.path.dirname(__file__),
                                  'extras', module_name, '__init__.py')
        if not os.path.exists(py_name) and not os.path.exists(py_dirname):
            if default is not configfile.sentinel:
                return default
            raise self.config_error("Unable to load module '%s'" % (section,))
        mod = importlib.import_module('extras.' + module_name)
        init_func = 'load_config'
        if len(module_parts) > 1:
            init_func = 'load_config_prefix'
        init_func = getattr(mod, init_func, None)
        if init_func is None:
            if default is not configfile.sentinel:
                return default
            raise self.config_error("Unable to load module '%s'" % (section,))
        self.objects[section] = init_func(config.getsection(section))
        return self.objects[section]
    def _read_config(self):
        self.objects['configfile'] = pconfig = configfile.PrinterConfig(self)
        config = pconfig.read_main_config()
        if self.bglogger is not None:
            pconfig.log_config(config)
        # Create printer components
        for m in [pins, mcu]:
            m.add_printer_objects(config)
        for section_config in config.get_prefix_sections(''):
            self.load_object(config, section_config.get_name(), None)
        for m in [toolhead]:
            m.add_printer_objects(config)
        # Validate that there are no undefined parameters in the config file
        pconfig.check_unused_options(config)
    def _connect(self, eventtime):
        try:
            self._read_config()
            self.send_event("klippy:mcu_identify")
            for cb in self.event_handlers.get("klippy:connect", []):
                if self.state_message is not message_startup:
                    return
                cb()
        except (self.config_error, pins.error) as e:
            logging.exception("Config error")
            # self._set_state("%s\n%s" % (str(e), message_restart))
            if isinstance(e, self.config_error):
                coded, oneshot, message, is_persistent = "0003-0522-0000-0003", 0, str(e), 0
            else:
                coded, oneshot, message, is_persistent = "0003-0522-0000-0004", 0, str(e), 0

            message = self.extract_coded_message_field(message)
            err_msg = json.dumps({
                "coded": coded,
                "oneshot": oneshot,
                "msg": message
            })
            self.raise_structured_code_exception(coded, message, oneshot, is_persistent)
            self._set_state("%s\n%s" % (err_msg, message_restart))
            self.send_event("klippy:connect_error")
            return
        except msgproto.error as e:
            msg = "Protocol error"
            logging.exception(msg)
            # self._set_state(msg)
            coded, oneshot, message, is_persistent = "0003-0522-0000-0005", 0, str(e), 0
            message = self.extract_coded_message_field(message)
            err_msg = json.dumps({
                "coded": coded,
                "oneshot": oneshot,
                "msg": message
            })
            self._set_state("%s\n%s" % (err_msg, msg))
            self.raise_structured_code_exception(coded, message, oneshot, is_persistent)
            self.send_event("klippy:notify_mcu_error", "%s\n%s" % (err_msg, msg), {"error": message})
            util.dump_mcu_build()
            self.send_event("klippy:connect_error")
            return
        except mcu.error as e:
            msg = "MCU error during connect"
            mcu_index_manager = ["'host'", "'mcu'", "'e0'", "'e1'", "'e2'", "'e3'"]
            logging.exception(msg)
            err_info = str(e)
            mcu_index = 255
            for index, mcu_str in enumerate(mcu_index_manager):
                if f"{mcu_str}" in f"{err_info}":
                    mcu_index = index
                    break
            if mcu_index == 2:
                usb_info = printer_device_scan.run_shell_command("lsusb")
                hub_count = 0
                if usb_info[0] == 0:
                    hub_count = usb_info[1].count("QinHeng Electronics USB HUB")
                if hub_count < 2:
                    mcu_index = 101
                    err_info += ", USB HUB not detected (%d/2)" % hub_count
                else:
                    serial_devices = printer_device_scan.run_shell_command(
                        "ls /dev/serial/by-path/")
                    if serial_devices[0] != 0:
                        mcu_index = 100
                        err_info += ", All extruders not detected (hub OK)"
            coded, oneshot, message, is_persistent = f"0003-0522-{mcu_index:04d}-0006", 0, err_info, 0
            message = self.extract_coded_message_field(message)
            err_msg = json.dumps({
                "coded": coded,
                "oneshot": oneshot,
                "msg": message
            })
            self._set_state("%s\n%s" % (err_msg, msg))
            self.raise_structured_code_exception(coded, message, oneshot, is_persistent)
            self.send_event("klippy:notify_mcu_error", "%s\n%s" % (err_msg, msg), {"error": message})
            util.dump_mcu_build()
            self.send_event("klippy:connect_error")
            return
        except Exception as e:
            logging.exception("Unhandled exception during connect")
            coded, oneshot, message, is_persistent = "0003-0522-0000-0007", 0, str(e), 0
            message = self.extract_coded_message_field(message)
            self.raise_structured_code_exception(coded, message, oneshot, is_persistent)
            err_msg = json.dumps({
                "coded": coded,
                "oneshot": oneshot,
                "msg": message
            })
            self._set_state("%s \nInternal error during connect: %s\n%s"
                            % (err_msg, str(e), message_restart,))
            self.send_event("klippy:connect_error")
            return
        try:
            self._set_state(message_ready)
            for cb in self.event_handlers.get("klippy:ready", []):
                if self.state_message is not message_ready:
                    return
                cb()
        except Exception as e:
            logging.exception("Unhandled exception during ready callback")
            structured_code = None
            coded_message = self.extract_encoded_message(str(e))
            if coded_message is not None:
                structured_code = coded_message.get("coded", None)
            if structured_code is not None:
                err_msg = json.dumps({
                    "coded": structured_code,
                    "oneshot": 0,
                    "msg": "Internal error during ready callback: %s"
                                    % (self.extract_coded_message_field(str(e)))
                })
                self.invoke_shutdown(err_msg)
            else:
                self.invoke_shutdown("Internal error during ready callback: %s"
                                    % (str(e),))
    def run(self):
        systime = time.time()
        monotime = self.reactor.monotonic()
        logging.info("Start printer at %s (%.1f %.1f)",
                     time.asctime(time.localtime(systime)), systime, monotime)
        self.set_main_mcu_power('on')
        self.set_extruder_power('on')
        # Enter main reactor loop
        try:
            self.reactor.run()
        except:
            msg = "Unhandled exception during run"
            logging.exception(msg)
            # Exception from a reactor callback - try to shutdown
            try:
                self.reactor.register_callback((lambda e:
                                                self.invoke_shutdown(msg)))
                self.reactor.run()
            except:
                logging.exception("Repeat unhandled exception during run")
                # Another exception - try to exit
                self.run_result = "error_exit"
        # Check restart flags
        run_result = self.run_result
        try:
            if run_result == 'firmware_restart':
                self.send_event("klippy:firmware_restart")
            self.send_event("klippy:disconnect")
        except:
            logging.exception("Unhandled exception during post run")
        return run_result
    def set_rollover_info(self, name, info, log=True):
        if log:
            logging.info(info)
        if self.bglogger is not None:
            self.bglogger.set_rollover_info(name, info)
    def invoke_shutdown(self, msg, details={}):
        if self.in_shutdown_state:
            return
        logging.error("Transition to shutdown state: %s", msg)
        self.in_shutdown_state = True
        # self._set_state(msg)

        if msg == "MCU shutdown" and details.get('reason') == 'Timer too close':
            index = {'host': 0, 'mcu': 1, 'e0': 2, 'e1': 3, 'e2': 4,'e3': 5}.get(details['mcu'], 255)
            err_msg = "MCU '%s' shutdown: %s" % (details['mcu'], details.get('reason'))
            msg = '{"coded": "%s", "oneshot": 0, "msg":"%s"}' % (f"0003-0522-{index:04d}-0016", err_msg)

        shutdown_codes = {
            "Shutdown due to webhooks request": "0018",
            "Shutdown due to M112 command": "0019"
        }
        if msg in shutdown_codes:
            msg = '{"coded": "0003-0522-0000-%s", "oneshot": 0, "msg":"%s"}' % (shutdown_codes[msg], msg)

        if not (msg == "MCU shutdown" and details.get('reason') == 'ADC out of range'):
            coded, oneshot, message, is_persistent = f"0003-0522-0000-0002", 0, msg, 0
            coded_message = self.extract_encoded_message(msg)
            if msg and msg.startswith('{"coded"'):
                if coded_message is not None:
                    coded = coded_message.get("coded", coded)
                    oneshot = coded_message.get("oneshot", oneshot)
                    message = coded_message.get("msg", message)
                    is_persistent = coded_message.get("is_persistent", is_persistent)
            else:
                if coded_message is not None:
                    id, index, code, level = 522, 0, 2, 3
                    id = coded_message.get("id", id)
                    index = coded_message.get("index", index)
                    code = coded_message.get("code", code)
                    message = coded_message.get("msg", message)
                    oneshot = coded_message.get("oneshot", oneshot)
                    level = coded_message.get("level", level)
                    is_persistent = coded_message.get("is_persistent", is_persistent)
                    coded = f"{level:04d}-{id:04d}-{code:04d}-{level:04d}"
                msg = json.dumps({
                    "coded": coded,
                    "oneshot": oneshot,
                    "msg": message
                })

            self.raise_structured_code_exception(coded, message, oneshot, is_persistent)

        self._set_state(msg)

        virtual_sdcard = self.lookup_object('virtual_sdcard', None)
        if virtual_sdcard is not None:
            virtual_sdcard.force_record_pl_print_file_env(transfer_p_t=True)

        for cb in self.event_handlers.get("klippy:shutdown", []):
            try:
                cb()
            except:
                logging.exception("Exception during shutdown handler")
        logging.info("Reactor garbage collection: %s",
                     self.reactor.get_gc_stats())
        self.send_event("klippy:notify_mcu_shutdown", msg, details)
    def invoke_async_shutdown(self, msg, details):
        self.reactor.register_async_callback(
            (lambda e: self.invoke_shutdown(msg, details)))
    def register_event_handler(self, event, callback):
        self.event_handlers.setdefault(event, []).append(callback)
    def send_event(self, event, *params):
        return [cb(*params) for cb in self.event_handlers.get(event, [])]
    def request_exit(self, result):
        if self.run_result is None:
            self.run_result = result
        self.reactor.end()


######################################################################
# Startup
######################################################################

def import_test():
    # Import all optional modules (used as a build test)
    dname = os.path.dirname(__file__)
    for mname in ['extras', 'kinematics']:
        for fname in os.listdir(os.path.join(dname, mname)):
            if fname.endswith('.py') and fname != '__init__.py':
                module_name = fname[:-3]
            else:
                iname = os.path.join(dname, mname, fname, '__init__.py')
                if not os.path.exists(iname):
                    continue
                module_name = fname
            importlib.import_module(mname + '.' + module_name)
    sys.exit(0)

def arg_dictionary(option, opt_str, value, parser):
    key, fname = "dictionary", value
    if '=' in value:
        mcu_name, fname = value.split('=', 1)
        key = "dictionary_" + mcu_name
    if parser.values.dictionary is None:
        parser.values.dictionary = {}
    parser.values.dictionary[key] = fname

def set_sched_fifo():
    try:
        import ctypes
        SCHED_FIFO = 1
        class sched_param(ctypes.Structure):
            _fields_ = [('sched_priority', ctypes.c_int)]
        param = sched_param(SCHED_FIFO_PRIORITY)
        libc = ctypes.CDLL('libc.so.6')
        res = libc.sched_setscheduler(0, SCHED_FIFO, ctypes.byref(param))
        if res != 0:
            logging.warning('Failed to set SCHED_FIFO, permission denied or not supported.')
        else:
            logging.info('SCHED_FIFO set successfully with priority %d', SCHED_FIFO_PRIORITY)
    except Exception as e:
        logging.warning('Exception setting SCHED_FIFO: %s', e)

def switch_user_group(user_name):
    """Switch the process to run as the specified user and group."""
    if user_name is None:
        return

    try:
        # Get current user info to check if we need to switch
        current_uid = os.getuid()
        current_user = pwd.getpwuid(current_uid).pw_name

        # If already running as the target user, no need to switch
        if current_user == user_name:
            logging.info("Already running as user '%s'", user_name)
            return

        # Only root can switch to another user
        if current_uid != 0:
            logging.warning("Cannot switch to user '%s': not running as root", user_name)
            return

        # Get user and group information
        try:
            user_info = pwd.getpwnam(user_name)
        except KeyError:
            logging.error("User '%s' not found", user_name)
            return

        user_uid = user_info.pw_uid
        user_gid = user_info.pw_gid
        user_home = user_info.pw_dir

        # Get supplementary groups for the user
        groups = [g.gr_gid for g in grp.getgrall() if user_name in g.gr_mem]
        groups.append(user_gid)  # Add primary group

        # Switch to the new user and group
        os.setgroups(groups)  # Set supplementary groups
        os.setregid(user_gid, user_gid)  # Set real and effective group ID
        os.setreuid(user_uid, user_uid)  # Set real and effective user ID

        # Set HOME environment variable
        os.environ['HOME'] = user_home
        os.environ['USER'] = user_name

        logging.info("Successfully switched to user '%s' (uid=%d, gid=%d)",
                    user_name, user_uid, user_gid)

    except OSError as e:
        logging.error("Failed to switch to user '%s': %s", user_name, str(e))
    except Exception as e:
        logging.error("Unexpected error switching to user '%s': %s", user_name, str(e))

def main():
    usage = "%prog [options] <config file>"
    opts = optparse.OptionParser(usage)
    opts.add_option("-i", "--debuginput", dest="debuginput",
                    help="read commands from file instead of from tty port")
    opts.add_option("-I", "--input-tty", dest="inputtty",
                    default='/tmp/printer',
                    help="input tty name (default is /tmp/printer)")
    opts.add_option("-a", "--api-server", dest="apiserver",
                    help="api server unix domain socket filename")
    opts.add_option("-l", "--logfile", dest="logfile",
                    help="write log to file instead of stderr")
    opts.add_option("-v", action="store_true", dest="verbose",
                    help="enable debug messages")
    opts.add_option("-o", "--debugoutput", dest="debugoutput",
                    help="write output to file instead of to serial port")
    opts.add_option("-d", "--dictionary", dest="dictionary", type="string",
                    action="callback", callback=arg_dictionary,
                    help="file to read for mcu protocol dictionary")
    opts.add_option("--import-test", action="store_true",
                    help="perform an import module test")
    opts.add_option("-u", "--user", dest="run_user", default="lava",
                    help="run as user (default: lava)")
    opts.add_option("-f", "--factory", dest="factory_mode", action="store_true",
                    help="enable factory mode")
    opts.add_option("--minor-core", dest="minor_core", type="string", default="2,3",
                    help="comma-separated CPU cores for background calculations (e.g. 2,3)")
    options, args = opts.parse_args()
    # switch_user_group(options.run_user)
    if options.import_test:
        import_test()
    if len(args) != 1:
        opts.error("Incorrect number of arguments")
    start_args = {'config_file': args[0], 'apiserver': options.apiserver,
                  'start_reason': 'startup'}
    start_args["factory_mode"] = True if options.factory_mode else False
    if options.minor_core:
        start_args["minor_core"] = set(
            int(c.strip()) for c in options.minor_core.split(','))
    debuglevel = logging.INFO
    if options.verbose:
        debuglevel = logging.DEBUG
    if options.debuginput:
        start_args['debuginput'] = options.debuginput
        debuginput = open(options.debuginput, 'rb')
        start_args['gcode_fd'] = debuginput.fileno()
    else:
        start_args['gcode_fd'] = util.create_pty(options.inputtty)
    if options.debugoutput:
        start_args['debugoutput'] = options.debugoutput
        start_args.update(options.dictionary)
    bglogger = None
    if options.logfile:
        start_args['log_file'] = options.logfile
        bglogger = queuelogger.setup_bg_logging(options.logfile, debuglevel)
    else:
        logging.getLogger().setLevel(debuglevel)
    queuefile.setup_bg_file_operations()
    try:
        asyncfilereader.setup_async_file_reader()
    except Exception:
        logging.exception("asyncfilereader setup failed")
    try:
        if not json_compat.HAS_ORJSON:
            logging.warning("orjson not available; large JSON will hold GIL longer")
    except Exception:
        pass
    logging.info("Starting Klippy...")
    git_info = util.get_git_version()
    git_vers = git_info["version"]
    extra_files = [fname for code, fname in git_info["file_status"]
                   if (code in ('??', '!!') and fname.endswith('.py')
                       and (fname.startswith('klippy/kinematics/')
                            or fname.startswith('klippy/extras/')))]
    modified_files = [fname for code, fname in git_info["file_status"]
                      if code == 'M']
    extra_git_desc = ""
    if extra_files:
        if not git_vers.endswith('-dirty'):
            git_vers = git_vers + '-dirty'
        if len(extra_files) > 10:
            extra_files[10:] = ["(+%d files)" % (len(extra_files) - 10,)]
        extra_git_desc += "\nUntracked files: %s" % (', '.join(extra_files),)
    if modified_files:
        if len(modified_files) > 10:
            modified_files[10:] = ["(+%d files)" % (len(modified_files) - 10,)]
        extra_git_desc += "\nModified files: %s" % (', '.join(modified_files),)
    extra_git_desc += "\nBranch: %s" % (git_info["branch"])
    extra_git_desc += "\nRemote: %s" % (git_info["remote"])
    extra_git_desc += "\nTracked URL: %s" % (git_info["url"])
    start_args['software_version'] = git_vers
    start_args['cpu_info'] = util.get_cpu_info()
    if bglogger is not None:
        versions = "\n".join([
            "Args: %s" % (sys.argv,),
            "Git version: %s%s" % (repr(start_args['software_version']),
                                   extra_git_desc),
            "CPU: %s" % (start_args['cpu_info'],),
            "Python: %s" % (repr(sys.version),)])
        logging.info(versions)
    elif not options.debugoutput:
        logging.warning("No log file specified!"
                        " Severe timing issues may result!")
    gc.disable()
    logging.info(f'start args: {start_args}')
    # Start Printer() class
    while 1:
        if bglogger is not None:
            bglogger.clear_rollover_info()
            bglogger.set_rollover_info('versions', versions)
        gc.collect()
        main_reactor = reactor.Reactor(gc_checking=True)
        printer = Printer(main_reactor, bglogger, start_args)
        res = printer.run()
        if res in ['exit', 'error_exit']:
            break
        time.sleep(1.)
        main_reactor.finalize()
        main_reactor = printer = None
        logging.info("Restarting printer")
        start_args['start_reason'] = res

    if bglogger is not None:
        bglogger.stop()

    try:
        asyncfilereader.clear_async_file_reader()
    except Exception:
        logging.exception("asyncfilereader clear failed")
    queuefile.clear_bg_file_operations()

    if res == 'error_exit':
        sys.exit(-1)

if __name__ == '__main__':
    main()
