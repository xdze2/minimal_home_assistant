import paho.mqtt.client as mqtt
from influxdb import InfluxDBClient
from datetime import datetime
import json
import signal
import sys

# MQTT settings
BROKER = "localhost"
TOPIC = "zigbee2mqtt/#"

# InfluxDB settings (InfluxDB 1.x)
INFLUX_HOST = "localhost"
INFLUX_PORT = 8086
INFLUX_DB = "sensors2"

# Connect to InfluxDB
print(f"Connecting to InfluxDB {INFLUX_HOST}:{INFLUX_PORT} on db={INFLUX_DB}...")
influx = InfluxDBClient(host=INFLUX_HOST, port=INFLUX_PORT)
influx.create_database(INFLUX_DB)
influx.switch_database(INFLUX_DB)

# Casting data to Influx Measurement

class SensorMeasurement:
    __measurement_name__: str = None

    @classmethod
    def from_mqtt_dict(clc, sensor_name: str, raw_fields: dict):
        assert clc.__measurement_name__ is not None
        # print(f"get {sensor_name}")
        device_info = raw_fields.get("device", dict())
        measurement_data = [
            {
                "measurement": clc.__measurement_name__,
                "tags": {
                    "name": device_info.get("friendlyName"),
                    "ieee_addr": device_info.get("ieeeAddr")
                },
                "time": datetime.now().isoformat(),#raw_fields["last_seen"],
                "fields": normalized_values(raw_fields, clc.__field_types__)
            }
        ]
        return measurement_data


def normalized_values(raw_fields: dict, target_types: dict) -> dict:
    """Cast value to type."""
    fields = dict()
    for key, value in raw_fields.items():
        if key not in target_types:
            # print(f"field={key} is ignored...")
            continue
        else:
            try:
                casting_fct = target_types[key]
                fields[key] = casting_fct(value)
            except (ValueError, TypeError):
                print(f"Error when casting value ({key}:{value}). Ignored.")
                continue

    return fields

class SonoffThermometerMeasurement(SensorMeasurement):
    __measurement_name__= "sonoff_thermometer"
    __field_types__ = {
        "linkquality": float,
        "last_seen": str,
        "elapsed": int,
        # sensor
        "temperature": float,
        "humidity": float,
        "battery": float,
    }
    __tag_types__ = {
        "sensor_id": str,
    }


class LinkyMeasurement(SensorMeasurement):
    __measurement_name__= "linky"
    __field_types__ = {
        "linkquality": float,
        "last_seen": str,
        "elapsed": int,
        # sensor
        "apparent_power": float,
        "active_power": float,
        "rms_current": float,
        "rms_voltage": float,
        "current_summ_delivered": float,
        "current_tier1_summ_delivered": float,
        "current_tier2_summ_delivered": float,
    }
    __tag_types__ = {
        "sensor_id": str,
    }

TOPIC_MEASUREMENT = {
    "sensors": SonoffThermometerMeasurement,
    "linky": LinkyMeasurement,
}

def mqtt_payload_to_measurement(topic: str, raw_fields: dict) -> dict:

    for topic_pattern, Measurement in TOPIC_MEASUREMENT.items():
        if topic_pattern in topic:
            meas_dict = Measurement.from_mqtt_dict(topic, raw_fields)
            return meas_dict
    else:
        # print(f"no matching measurement (topic={topic}). Ignored")
        return None
    

def on_message(client, userdata, message):
    try:
        payload = message.payload.decode()
        raw_fields = json.loads(payload)

        json_body = mqtt_payload_to_measurement(message.topic, raw_fields)
        if json_body is not None:
            influx.write_points(json_body)
            #print(f"Saved to InfluxDB: {json_body}")
    except Exception as e:
        print("Error processing message:", e)


# MQTT client
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_message = on_message
client.connect(BROKER)
client.subscribe(TOPIC)


def signal_handler(sig, frame):
    print("\nStopping gracefully...")
    try:
        client.disconnect()
        client.loop_stop()
        influx.close()
    except Exception as e:
        print("Error during cleanup:", e)
    sys.exit(0)

# Attach signal handler for Ctrl+C
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


print(f"Listening for MQTT messages on topics {TOPIC}...")
client.loop_forever()
