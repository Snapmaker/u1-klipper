# timelapse manager for klippy
#
# Copyright (C) 2025-2030  Scott Huang <shili.huang@snapmaker.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import logging
import time, os
from .jsonrpc import *

REQUEST_TOPIC           = "camera/request"
RESPONSE_TOPIC          = "camera/response"

REQUEST_INTERVAL_MIN    = 1
REQUEST_TIMEOUT         = 5

DEBUG_PICTURE_DIR       = "/userdata/gcodes/pictures"

class TimeLapse:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.webhooks = self.printer.lookup_object('webhooks')

        self.frame_rate = config.getint('frame_rate', 24)

        self.is_active = False
        self.mqtt_client = None
        self.mqtt_subscrip_handle = None
        self.print_task_config = None
        self.last_request_time = 0
        self.timeslapse_ignore = False

        self.mqtt_transport = None
        self.mqtt_jsonrpc = None

        # Register GCode commands
        self.gcode.register_command('TIMELAPSE_START', self.cmd_TIMELAPSE_START,
                                   desc=self.cmd_TIMELAPSE_START_help)
        self.gcode.register_command('TIMELAPSE_STOP', self.cmd_TIMELAPSE_STOP,
                                   desc=self.cmd_TIMELAPSE_STOP_help)
        self.gcode.register_command('TIMELAPSE_TAKE_FRAME', self.cmd_TIMELAPSE_TAKE_FRAME,
                                   desc=self.cmd_TIMELAPSE_TAKE_FRAME_help)
        self.gcode.register_command('TIMELAPSE_IGNORE', self.cmd_TIMELAPSE_IGNORE)

        self.printer.register_event_handler('klippy:ready', self._handle_ready)
        self.printer.register_event_handler('print_stats:start', self._handle_start_print_job)
        self.printer.register_event_handler('print_stats:stop', self._handle_stop_print_job)

    def _handle_ready(self):
        self.mqtt_client = self.printer.lookup_object("mqtt", None)
        self.print_task_config = self.printer.lookup_object('print_task_config', None)
        if self.mqtt_client is None or self.print_task_config is None:
            logging.error("[timelapse] cannot load necessary objects")
            return

        try:
            self.mqtt_jsonrpc = JSONRPCClient(
                                reactor=self.reactor,
                                transport_type=JSONRPC_TRANSPORT_MQTT,
                                mqtt_client=self.mqtt_client,
                                request_topic=REQUEST_TOPIC,
                                response_topic=RESPONSE_TOPIC,
                                qos=0)
            self.mqtt_jsonrpc.connect()
        except Exception as e:
            logging.error(f"[timelapse] failed to initialize jsonrpc: {e}")
            self.mqtt_jsonrpc = None

    def _handle_start_print_job(self):
        self.timeslapse_ignore = False

    def _handle_stop_print_job(self):
        self.timeslapse_ignore = False

    def get_status(self, eventtime=None):
        return {
            'is_active': self.is_active
        }

    cmd_TIMELAPSE_START_help = "Start timelapse recording"
    def cmd_TIMELAPSE_START(self, gcmd):
        if (self.mqtt_client is None or self.print_task_config is None
                or self.mqtt_jsonrpc is None):
            raise gcmd.error("[timelapse] cannot start, klippy not ready!")

        if not self.print_task_config.print_task_config['time_lapse_camera']:
            gcmd.respond_info("[timelapse] cannot start, not enabled!")
            return

        if self.timeslapse_ignore == True:
            gcmd.respond_info("[timelapse] cannot start, timelapse is ignored!")
            return

        if self.is_active:
            gcmd.respond_info("[timelapse] already started!")
            return

        start_type = gcmd.get('TYPE', 'new')
        frame_rate = gcmd.get_int('FRAME_RATE', self.frame_rate)

        gcode_name = None
        gcode_path = None
        virtual_sdcard = self.printer.lookup_object('virtual_sdcard', None)
        if virtual_sdcard is not None:
            gcode_path = virtual_sdcard.get_status(self.reactor.monotonic())['file_path']
            if gcode_path is not None:
                gcode_name = os.path.basename(gcode_path).split('.', 1)[0]

        if start_type == 'continue':
            gcmd.respond_info("[timelapse] continuing existing timelapse")
        else:
            gcmd.respond_info("[timelapse] starting new timelapse")

        params = {
            "mode": "classic",
            "frame_rate": frame_rate,
            "type": start_type,
            "gcode_name": gcode_name,
            "gcode_path": gcode_path,
        }

        try:
            self.gcode.run_script_from_command("SET_LED LED=cavity_led WHITE=1\r\n")
            if self.mqtt_jsonrpc is None:
                raise ValueError("mqtt_jsonrpc not initialized")
            response_info = self.mqtt_jsonrpc.send_request_with_response(
                                        "camera.start_timelapse",
                                        params,
                                        timeout=REQUEST_TIMEOUT)

            logging.info(f"[timelapse] start timelapse, response: {response_info}")
            result = response_info.get("result", None)
            if result == None:
                raise ValueError("request failed")
            state = result.get("state", None)
            if state == None or state != "success":
                raise ValueError("request failed")

            self.is_active = True

        except Exception as e:
            logging.error(f"[timelapse] start failed : {str(e)}")
            raise gcmd.error(
                message = "fail to start timelapse",
                action = 'pause',
                id = 524,
                index = 0,
                code = 0,
                oneshot = 1,
                level = 2)

    cmd_TIMELAPSE_STOP_help = "Stop timelapse recording"
    def cmd_TIMELAPSE_STOP(self, gcmd):
        force = gcmd.get_int('FORCE', 0)

        if self.mqtt_client is None or self.mqtt_jsonrpc is None:
            self.is_active = False
            gcmd.respond_info("!![timelapse] stop error, mqtt not ready!")
            return

        if self.is_active == False and force == 0:
            gcmd.respond_info("[timelapse] not started!")
            return

        try:
            if self.mqtt_jsonrpc is None:
                raise ValueError("mqtt_jsonrpc not initialized")
            response_info = self.mqtt_jsonrpc.send_request_with_response(
                                        "camera.stop_timelapse",
                                        {},
                                        timeout=REQUEST_TIMEOUT)
            logging.info(f"[timelapse] stop timelapse, response: {response_info}")
            result = response_info.get("result", None)
            if result == None:
                raise ValueError("request failed")
            state = result.get("state", None)
            if state == None or state != "success":
                raise ValueError("request failed")

        except Exception as e:
            gcmd.respond_info(f"!![timelapse] stop failed : {str(e)}")

        else:
            gcmd.respond_info("[timelapse] stopped")

        finally:
            self.is_active = False

    cmd_TIMELAPSE_TAKE_FRAME_help = "Trigger timelapse photo capture"
    def cmd_TIMELAPSE_TAKE_FRAME(self, gcmd):
        debug = gcmd.get_int('DEBUG', 0)
        reason = "printing"
        filepath = "/tmp/tmp.jpg"
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        if (self.mqtt_client is None or self.print_task_config is None
                or self.mqtt_jsonrpc is None):
            logging.error("[timelapse] take error, klippy not ready!")
            return

        if self.timeslapse_ignore == True:
            return

        if debug == 0:
            if not self.is_active or not self.print_task_config.print_task_config['time_lapse_camera']:
                return

        if self.reactor.monotonic() < self.last_request_time + REQUEST_INTERVAL_MIN:
            logging.info(f"[timelapse] request too frequent, ignored")
            return

        self.last_request_time = self.reactor.monotonic()

        try:
            if debug != 0:
                if not os.path.exists(DEBUG_PICTURE_DIR):
                    os.makedirs(DEBUG_PICTURE_DIR)
                reason = 'debug'
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filepath = f"{DEBUG_PICTURE_DIR}/pic_{timestamp}.jpg"
                gcmd.respond_info(f"[timelapse] take a picture for debug, save to {filepath}")

            params = {
                "reason": reason,
                "timestamp": False,
                "filepath": filepath
            }

            if self.mqtt_jsonrpc is not None:
                self.mqtt_jsonrpc.send_request("camera.take_a_photo", params)

        except Exception as e:
            logging.error(f"[timelapse] failed to take a picture: {str(e)}")

    def cmd_TIMELAPSE_IGNORE(self, gcmd):
        ignore = gcmd.get_int('IGNORE', 1)
        self.timeslapse_ignore = bool(ignore)

def load_config(config):
    return TimeLapse(config)

