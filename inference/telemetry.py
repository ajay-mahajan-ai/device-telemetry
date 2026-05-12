#!/usr/bin/env python3
"""
Device Telemetry Publisher
Reads WiFi radio stats from /tmp/device_telemetry.json (written by C collector
every 10s) and publishes per-radio metrics to an MQTT broker.

Topic: telemetry/<device_id>/radio/<radio_index>
"""

import json
import time
import os
import socket
import argparse
import paho.mqtt.client as mqtt

METRICS_FILE = "/tmp/device_telemetry.json"

# Stats keys to extract from Device.WiFi.Radio.{i}.Stats.
STATS_KEYS = [
    "X_COMCAST-COM_ChannelUtilization",
    "Noise",
    "X_COMCAST-COM_NoiseFloor",
    "BytesSent",
    "BytesReceived",
    "PacketsSent",
    "PacketsReceived",
    "ErrorsSent",
    "ErrorsReceived",
    "FCSErrorCount",
    "RetryCount",
    "MultipleRetryCount",
    "X_COMCAST-COM_ActivityFactor",
    "X_COMCAST-COM_RetransmissionMetric",
]

# Basic radio keys from Device.WiFi.Radio.{i}.
RADIO_KEYS = [
    "Channel",
    "OperatingFrequencyBand",
    "Enable",
    "Status",
    "TransmitPower",
    "AutoChannelEnable",
    "OperatingStandards",
    "CurrentOperatingChannelBandwidth",
    "ChannelLoad",
    "Interference",
    "ActiveAssociatedDevices",
]


def get_device_id():
    return socket.gethostname()


def extract_radios(raw_radios: dict) -> list:
    """
    Parse the amxb_get result for WiFi.Radio.** (prplOS) or Device.WiFi.Radio.** (RDK-B).
    The result is a flat dict keyed by TR-181 path, e.g.:
      "WiFi.Radio.1.":       { "Channel": "6", ... }          (prplOS)
      "WiFi.Radio.1.Stats.": { "Noise": "-99", ... }          (prplOS)
      "Device.WiFi.Radio.1.":       { "Channel": "6", ... }   (RDK-B)
      "Device.WiFi.Radio.1.Stats.": { "Noise": "-99", ... }   (RDK-B)
    We group by radio index and merge radio + stats fields.
    """
    if not isinstance(raw_radios, dict):
        return []

    radios = {}

    for path, values in raw_radios.items():
        if not isinstance(values, dict):
            continue

        # Normalize: strip optional "Device." prefix so both platforms parse identically.
        norm = path.lstrip(".")
        if norm.startswith("Device."):
            norm = norm[len("Device."):]

        # Match WiFi.Radio.{i}. and WiFi.Radio.{i}.Stats.
        parts = norm.rstrip(".").split(".")
        # parts: ['WiFi','Radio','1'] or ['WiFi','Radio','1','Stats']
        if len(parts) < 3:
            continue
        if parts[0] != "WiFi" or parts[1] != "Radio":
            continue

        try:
            idx = int(parts[2])
        except ValueError:
            continue

        if idx not in radios:
            radios[idx] = {"radio_index": idx}

        is_main  = len(parts) == 3
        is_stats = len(parts) == 4 and parts[3] == "Stats"

        if is_stats:
            for k in STATS_KEYS:
                if k in values:
                    radios[idx][k] = _coerce(values[k])
        elif is_main:
            for k in RADIO_KEYS:
                if k in values:
                    radios[idx][k] = _coerce(values[k])
        # all other sub-paths (RadCaps, ScanConfig, ChannelMgt, …) are ignored

    return list(radios.values())


def _coerce(v):
    """Try to parse string values to int/float/bool; return as-is otherwise."""
    if isinstance(v, (int, float, bool)):
        return v
    if isinstance(v, str):
        if v.lower() == "true":
            return True
        if v.lower() == "false":
            return False
        try:
            return int(v)
        except ValueError:
            pass
        try:
            return float(v)
        except ValueError:
            pass
    return v


def _make_client():
    _cbv = getattr(mqtt, "CallbackAPIVersion", None)
    return mqtt.Client(_cbv.VERSION2) if _cbv else mqtt.Client()


class TelemetryPublisher:
    def __init__(self, mqtt_broker: str, mqtt_port: int, poll_interval: int,
                 public_broker: str = None, public_port: int = 1883,
                 public_topic_prefix: str = None):
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.poll_interval = poll_interval
        self.device_id = get_device_id()
        self.mqtt_client = _make_client()

        # Optional second publish to a public broker (e.g. broker.hivemq.com)
        self.public_broker = public_broker
        self.public_port = public_port
        self.public_topic_prefix = public_topic_prefix or "telemetry"
        self.public_client = _make_client() if public_broker else None

    def _connect(self, client, broker, port, label):
        client.loop_start()
        try:
            client.connect(broker, port, keepalive=60)
            print(f"INFO: Connected to {label} {broker}:{port} (device_id={self.device_id})")
        except Exception as e:
            print(f"WARN: {label} connect failed: {e} — will retry on next publish")

    def connect_mqtt(self):
        self._connect(self.mqtt_client, self.mqtt_broker, self.mqtt_port, "MQTT")
        if self.public_client:
            self._connect(self.public_client, self.public_broker, self.public_port, "public MQTT")

    def _publish(self, client, topic, payload_str, label):
        try:
            client.publish(topic, payload_str, qos=1)
        except Exception as e:
            print(f"WARN: publish failed ({label}) {topic}: {e}")
            try:
                client.reconnect()
            except Exception:
                pass

    def publish_radio(self, radio: dict, ts: int):
        idx = radio.get("radio_index", 0)
        payload = {**radio, "device_id": self.device_id, "timestamp": ts}
        payload_str = json.dumps(payload)

        topic = f"telemetry/{self.device_id}/radio/{idx}"
        self._publish(self.mqtt_client, topic, payload_str, "local")
        print(f"INFO: Published {topic} ch={radio.get('Channel')} "
              f"util={radio.get('X_COMCAST-COM_ChannelUtilization')} "
              f"noise={radio.get('Noise')}")

        if self.public_client:
            pub_topic = f"{self.public_topic_prefix}/{self.device_id}/radio/{idx}"
            self._publish(self.public_client, pub_topic, payload_str, "public")

    def run(self):
        self.connect_mqtt()
        last_mtime = 0

        print(f"INFO: Watching {METRICS_FILE}")
        while True:
            try:
                mtime = os.path.getmtime(METRICS_FILE)
                if mtime > last_mtime:
                    last_mtime = mtime
                    with open(METRICS_FILE) as f:
                        data = json.load(f)

                    ts = int(data.get("timestamp", time.time()))
                    radios = extract_radios(data.get("radios") or {})

                    if not radios:
                        print("WARN: No radio data found in metrics JSON")
                    for radio in radios:
                        self.publish_radio(radio, ts)

            except FileNotFoundError:
                pass
            except json.JSONDecodeError as e:
                print(f"WARN: JSON parse error: {e}")
            except Exception as e:
                print(f"ERROR: {e}")

            time.sleep(self.poll_interval)


def main():
    parser = argparse.ArgumentParser(description="Device Telemetry Publisher")
    parser.add_argument("--broker",               default=os.environ.get("MQTT_BROKER", "localhost"))
    parser.add_argument("--port",                 default=int(os.environ.get("MQTT_PORT", 1883)), type=int)
    parser.add_argument("--interval",             default=11, type=int)
    parser.add_argument("--public-broker",        default=os.environ.get("MQTT_BROKER_PUBLIC", ""))
    parser.add_argument("--public-port",          default=int(os.environ.get("MQTT_PORT_PUBLIC", 1883)), type=int)
    parser.add_argument("--public-topic-prefix",  default=os.environ.get("MQTT_TOPIC_PREFIX", "telemetry"))
    args = parser.parse_args()

    publisher = TelemetryPublisher(
        mqtt_broker=args.broker,
        mqtt_port=args.port,
        poll_interval=args.interval,
        public_broker=args.public_broker or None,
        public_port=args.public_port,
        public_topic_prefix=args.public_topic_prefix,
    )
    publisher.run()


if __name__ == "__main__":
    main()
