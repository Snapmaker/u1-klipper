import logging
from json_compat import dumps
import paho.mqtt.client as paho_mqtt
import threading
import random

from typing import (
    List,
    Optional,
    Any,
    Callable,
    Dict,
    Union,
    Tuple,
)


class SubscriptionHandle:
    def __init__(self, topic: str, callback: Callable[[bytes], None]):
        self.callback = callback
        self.topic = topic

SubscribedDict = Dict[str, Tuple[int, List[SubscriptionHandle]]]

class MQTTClient:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()

        random_num_str = str(random.randint(10000, 9999999))
        self.client_id = config.get("client_id", f"klipper_{random_num_str}")
        self.address = config.get("address", "localhost")
        self.port = config.getint("port", 1883)
        self.qos = config.getint("default_qos", 0, minval=0, maxval=2)

        self._lock = threading.Lock()
        self.subscribed_topics: SubscribedDict = {}

        self.protocol = paho_mqtt.MQTTv5
        self.client = paho_mqtt.Client(client_id=self.client_id, protocol=self.protocol)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish = self._on_publish
        self.client.on_subscribe = self._on_subscribe
        self.client.on_unsubscribe = self._on_unsubscribe
        self.client.reconnect_delay_set(min_delay=1, max_delay=120)
        try:
            self.client.connect_async(self.address, self.port)
            self.client.loop_start()
        except Exception:
            try:
                self.client.loop_stop()
            except Exception:
                pass
            raise

        self.printer.register_event_handler('klippy:shutdown', self._handle_shutdown)
        self.printer.register_event_handler("gcode:request_restart",
                                            self._handle_request_restart)

    def _handle_shutdown(self):
        try:
            self.client.reconnect_delay_set(min_delay=0, max_delay=0)
            self.client.disconnect()
            self.client.loop_stop()
        except Exception:
            pass

    def _handle_request_restart(self, print_time):
        try:
            self.client.reconnect_delay_set(min_delay=0, max_delay=0)
            self.client.disconnect()
            self.client.loop_stop()
        except Exception:
            pass

    def get_status(self, eventtime=None):
        return {
            "connected": self.is_connected()
        }

    def _on_connect(self,
                    client: paho_mqtt.Client,
                    user_data: Any,
                    flags: Dict[str, Any],
                    reason_code: Union[int, paho_mqtt.ReasonCodes],
                    properties: Optional[paho_mqtt.Properties] = None
                    ) -> None:
        if reason_code == 0:
            logging.info("[mqtt] client connected")
            subs = [(k, v[0]) for k, v in self.subscribed_topics.items()]
            if subs:
                res, msgid = self.client.subscribe(subs)
                logging.info(f"[mqtt] subscribe, msgid: {msgid}, res: {res}")
        else:
            if isinstance(reason_code, int):
                err_str = paho_mqtt.connack_string(reason_code)
            else:
                err_str = reason_code.getName()
            logging.info(f"[mqtt] connection failed: {err_str}")

    def _on_disconnect(self,
                       client: paho_mqtt.Client,
                       user_data: Any,
                       reason_code: int,
                       properties: Optional[paho_mqtt.Properties] = None
                       ) -> None:
        logging.info(f"[mqtt] client disconnected, rc: {reason_code}")

    def _on_publish(self,
                    client: paho_mqtt.Client,
                    user_data: Any,
                    msg_id: int
                    ) -> None:
        pass

    def _on_message(self,
                    client: str,
                    user_data: Any,
                    message: paho_mqtt.MQTTMessage
                    ) -> None:
        topic = message.topic
        if topic in self.subscribed_topics:
            cb_hdls = self.subscribed_topics[topic][1]
            for hdl in cb_hdls:
                self.reactor.register_async_callback(
                    (lambda et, c=hdl.callback: c(message.payload)))
        else:
            logging.debug(f"[mqtt] unsub msg, topic: {topic}, "
                         f" payload: {message.payload.decode()}")

    def _on_subscribe(self,
                      client: paho_mqtt.Client,
                      user_data: Any,
                      msg_id: int,
                      flex: Union[List[int], List[paho_mqtt.ReasonCodes]],
                      properties: Optional[paho_mqtt.Properties] = None
                      ) -> None:
        logging.info(f"[mqtt] on_subscribe, msg_id: {msg_id} qos: {flex}")

    def _on_unsubscribe(self,
                        client: paho_mqtt.Client,
                        user_data: Any,
                        msg_id: int,
                        properties: Optional[paho_mqtt.Properties] = None,
                        reasoncodes: Optional[paho_mqtt.ReasonCodes] = None
                        ) -> None:
        logging.info(f"[mqtt] on_unsubscribe, msg_id: {msg_id}, reasoncodes: {reasoncodes}")

    def is_connected(self) -> bool:
        return self.client.is_connected()

    def subscribe_topic(self,
                        topic: str,
                        callback: Callable[[bytes], None],
                        qos: Optional[int] = None
                        ) -> SubscriptionHandle:
        if topic == "" or isinstance(topic, str) == False:
            raise Exception("[mqtt] topic must be a non-empty string")

        if '#' in topic or '+' in topic:
            raise Exception("[mqtt] wildcards may not be used")

        if callable(callback) is False:
            raise Exception("[mqtt] callback must be callable")

        qos = self.qos if qos is None else qos
        if qos < 0 or qos > 2:
            raise Exception("[mqtt] qos must in range [0, 2]")

        sub_handle = SubscriptionHandle(topic, callback)
        sub_handles = [sub_handle]
        need_sub = True

        with self._lock:
            if topic in self.subscribed_topics:
                prev_qos, sub_handles = self.subscribed_topics[topic]
                qos = max(qos, prev_qos)
                sub_handles.append(sub_handle)
                need_sub = qos != prev_qos
            self.subscribed_topics[topic] = (qos, sub_handles)

        if self.is_connected() and need_sub:
            res, msgid = self.client.subscribe(topic, qos)
            logging.info(f"[mqtt] subscribe {topic} qos: {qos}, msgid: {msgid}, res: {res}")

        return sub_handle

    def unsubscribe(self,
                    hdl: SubscriptionHandle
                    ) -> None:
        topic = hdl.topic
        need_unsub = False

        with self._lock:
            if topic in self.subscribed_topics:
                _, sub_handles = self.subscribed_topics[topic]
                try:
                    sub_handles.remove(hdl)
                except:
                    pass
                if len(sub_handles) == 0:
                    need_unsub = True
                    del self.subscribed_topics[topic]
        if self.is_connected() and need_unsub:
            res, msg_id = self.client.unsubscribe(topic)
            logging.info(f"[mqtt] unsubscribe {topic}, msgid: {msg_id}, res: {res}")

    def publish_topic(self,
                      topic: str,
                      payload: Any = None,
                      qos: Optional[int] = None,
                      retain: bool = False
                      ) -> None:
        if topic == "" or isinstance(topic, str) == False:
            raise Exception("[mqtt] topic must be a non-empty string")

        if '#' in topic or '+' in topic:
            raise Exception("[mqtt] wildcards may not be used")

        if self.client is None or self.is_connected() is False:
            raise Exception("[mqtt] mqtt is not connected")

        qos = self.qos if qos is None else qos
        if qos < 0 or qos > 2:
            raise Exception("[mqtt] qos must in range [0, 2]")

        if isinstance(payload, (dict, list)):
            try:
                payload = dumps(payload)
            except TypeError:
                raise Exception("[mqtt] dict or List is not json encodable")
        elif isinstance(payload, bool):
            payload = str(payload).lower()

        self.client.publish(topic, payload, qos, retain)

def load_config(config):
    return MQTTClient(config)
