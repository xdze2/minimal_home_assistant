import json
import time
from typing import Any, Dict, List, Tuple

import paho.mqtt.client as mqtt
import pandas as pd
import requests
from daikinapi import Daikin
from datetime import datetime
from .influx_interface import SensorMeasurement
from influxdb import InfluxDBClient


class DaikinAirconMeasurement(SensorMeasurement):
    __measurement_name__ = "daikin_aircon"
    __field_types__ = {
        "power": float,
        "target_temperature": float,
        "target_humidity": float,
        "inside_temperature": float,
        "outside_temperature": float,
        "compressor_frequency": float,
        "fan_rate": int,
        "fan_direction": int,
        "mode": int,
        "today_runtime": int,
        "today_power_consumption": float,
        "current_month_power_consumption": float,
        "price_int": float,
        "rev": str,
        "ver": str,
    }
    __tag_types__ = {
        "name": str,
        "mac": str,
        "type": str,
    }

    @classmethod
    def from_API(clc, API: Daikin) -> List[Dict[str, Any]]:
        assert clc.__measurement_name__ is not None
        # device_info = raw_fields.get("device", dict())

        fields = dict()
        for field_name, field_type in clc.__field_types__.items():
            try:
                value = getattr(API, field_name)
                fields[field_name] = field_type(value)
            except (ValueError, TypeError):
                print(f"Error when getting value ({field_name}:{value}). Ignored.")
                continue

        measurement_data = [
            {
                "measurement": clc.__measurement_name__,
                "tags": {"name": API.name, "mac": API.mac, "type": API.type},
                "time": datetime.now().isoformat(),  # API.datetime ?
                "fields": fields,
            }
        ]
        return measurement_data


# def on_message(client, userdata, message):
#     try:
#         payload = message.payload.decode()
#         raw_fields = json.loads(payload)

#         json_body = mqtt_payload_to_measurement(message.topic, raw_fields)
#         if json_body is not None:
#             influx.write_points(json_body)
#             # print(f"Saved to InfluxDB: {json_body}")
#     except Exception as e:
#         print("Error processing message:", e)


def main() -> None:
    from .config import config
    from .devices import load_devices

    print(f"Connecting to InfluxDB {config.INFLUX_HOST}:{config.INFLUX_PORT} on db={config.INFLUX_DB}...")
    influx = InfluxDBClient(host=config.INFLUX_HOST, port=config.INFLUX_PORT)
    influx.create_database(config.INFLUX_DB)
    influx.switch_database(config.INFLUX_DB)

    IP_ADDRESSES = [d.ip for d in load_devices().daikin]
    PERIOD_SECONDS = 120

    devices = list()

    for IP_ADDRESS in IP_ADDRESSES:
        try:
            print(f"Connecting to Daikin AC at {IP_ADDRESS}...")
            API = Daikin(IP_ADDRESS)
            devices.append(API)
        except requests.exceptions.ConnectionError as e:
            print(f"Failed to connect to Daikin AC at {IP_ADDRESS}: {e}. Ignored.")
            continue

    if len(devices) == 0:
        print("No Daikin AC connected. Exit.")
        return

    while True:

        for API in devices:
            measurement_data = DaikinAirconMeasurement.from_API(API)
            print(f"Measurement data: {measurement_data}")
            influx.write_points(measurement_data)

        try:
            time.sleep(PERIOD_SECONDS)
        except KeyboardInterrupt:
            print("Interrupted by user. Exit.")
            break

    influx.close()
