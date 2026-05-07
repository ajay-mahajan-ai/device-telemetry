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


class TelemetryPublisher:
    def __init__(self, mqtt_broker: str, mqtt_port: int, poll_interval: int):
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.poll_interval = poll_interval
        self.device_id = get_device_id()
        _cbv = getattr(mqtt, "CallbackAPIVersion", None)
        self.mqtt_client = mqtt.Client(_cbv.VERSION2) if _cbv else mqtt.Client()

    def connect_mqtt(self):
        self.mqtt_client.loop_start()
        try:
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port, keepalive=60)
            print(f"INFO: Connected to MQTT {self.mqtt_broker}:{self.mqtt_port} "
                  f"(device_id={self.device_id})")
        except Exception as e:
            print(f"WARN: MQTT connect failed: {e} — will retry on next publish")

    def publish_radio(self, radio: dict, ts: int):
        idx = radio.get("radio_index", 0)
        topic = f"telemetry/{self.device_id}/radio/{idx}"
        payload = {**radio, "device_id": self.device_id, "timestamp": ts}
        try:
            self.mqtt_client.publish(topic, json.dumps(payload), qos=1)
            print(f"INFO: Published {topic} ch={radio.get('Channel')} "
                  f"util={radio.get('X_COMCAST-COM_ChannelUtilization')} "
                  f"noise={radio.get('Noise')}")
        except Exception as e:
            print(f"WARN: publish failed for {topic}: {e}")
            try:
                self.mqtt_client.reconnect()
            except Exception:
                pass

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
    parser.add_argument("--broker",   default=os.environ.get("MQTT_BROKER", "localhost"))
    parser.add_argument("--port",     default=int(os.environ.get("MQTT_PORT", 1883)), type=int)
    parser.add_argument("--interval", default=11, type=int)
    args = parser.parse_args()

    publisher = TelemetryPublisher(args.broker, args.port, args.interval)
    publisher.run()


if __name__ == "__main__":
    main()
