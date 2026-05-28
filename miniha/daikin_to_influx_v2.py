import time
from datetime import datetime
from typing import Any, Dict, List, Set

import requests
from daikinapi import Daikin
from influxdb import InfluxDBClient

MEASUREMENT_NAME = "daikin_aircon_v2"

FIELD_TYPES: Dict[str, type] = {
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

# Fields safe to force-write on heartbeat because the value at heartbeat
# time is genuinely current (setpoints, config, and live sensor readings).
HEARTBEAT_FIELDS: Set[str] = {
    "mode",
    "fan_rate",
    "fan_direction",
    "target_temperature",
    "target_humidity",
    "price_int",
    "rev",
    "ver",
    "inside_temperature",
    "outside_temperature",
    "compressor_frequency",
    "power",
}


UNAVAILABLE_SENTINELS = {"--", "-", ""}


def read_device_fields(API: Daikin) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    for field_name, field_type in FIELD_TYPES.items():
        try:
            value = getattr(API, field_name)
        except (AttributeError, ValueError, TypeError) as e:
            print(f"Error when getting value ({field_name}): {e}. Ignored.")
            continue
        if isinstance(value, str) and value.strip() in UNAVAILABLE_SENTINELS:
            continue
        try:
            fields[field_name] = field_type(value)
        except (ValueError, TypeError) as e:
            print(f"Error when casting value ({field_name}={value!r}): {e}. Ignored.")
            continue
    return fields


def seed_cache_from_db(influx: InfluxDBClient, mac: str) -> Dict[str, Any]:
    """Query last value per field from InfluxDB to seed the in-memory cache."""
    cache: Dict[str, Any] = {}
    query = f'SELECT last(*) FROM "{MEASUREMENT_NAME}" ' f"WHERE \"mac\" = '{mac}'"
    try:
        result = influx.query(query)
    except Exception as e:
        print(f"Failed to seed cache for {mac}: {e}")
        return cache

    for point in result.get_points():
        for key, value in point.items():
            if key == "time" or value is None:
                continue
            if key.startswith("last_"):
                field_name = key[len("last_") :]
                if field_name in FIELD_TYPES:
                    try:
                        cache[field_name] = FIELD_TYPES[field_name](value)
                    except (ValueError, TypeError):
                        cache[field_name] = value
    return cache


def build_point(
    API: Daikin,
    current: Dict[str, Any],
    cache: Dict[str, Any],
    heartbeat_due: bool,
) -> Dict[str, Any]:
    """Return only fields to write: changed values + heartbeat fields if due."""
    fields_to_write: Dict[str, Any] = {}
    for key, value in current.items():
        if cache.get(key) != value:
            fields_to_write[key] = value
        elif heartbeat_due and key in HEARTBEAT_FIELDS:
            fields_to_write[key] = value

    if not fields_to_write:
        return None

    return {
        "measurement": MEASUREMENT_NAME,
        "tags": {"name": API.name, "mac": API.mac, "type": API.type},
        "time": datetime.now().isoformat(),
        "fields": fields_to_write,
    }


def main() -> None:

    INFLUX_HOST = "192.168.1.87"
    INFLUX_PORT = 8086
    INFLUX_DB = "sensors2"

    IP_ADDRESSES = ["192.168.1.73", "192.168.1.84"]
    PULL_PERIOD = 120  # seconds between device polls
    HEARTBEAT_PERIOD = 60 * 60  # seconds between forced setpoint writes

    print(f"Connecting to InfluxDB {INFLUX_HOST}:{INFLUX_PORT} on db={INFLUX_DB}...")
    influx = InfluxDBClient(host=INFLUX_HOST, port=INFLUX_PORT)
    influx.create_database(INFLUX_DB)
    influx.switch_database(INFLUX_DB)

    devices: List[Daikin] = []
    for ip in IP_ADDRESSES:
        try:
            print(f"Connecting to Daikin AC at {ip}...")
            devices.append(Daikin(ip))
        except requests.exceptions.ConnectionError as e:
            print(f"Failed to connect to Daikin AC at {ip}: {e}. Ignored.")
            continue

    if not devices:
        print("No Daikin AC connected. Exit.")
        return

    caches: Dict[str, Dict[str, Any]] = {}
    last_heartbeat: Dict[str, float] = {}
    for API in devices:
        caches[API.mac] = seed_cache_from_db(influx, API.mac)
        last_heartbeat[API.mac] = 0.0
        print(f"Seeded cache for {API.mac}: {len(caches[API.mac])} fields")

    while True:
        now = time.time()

        for API in devices:
            try:
                current = read_device_fields(API)
            except Exception as e:
                print(f"Failed to read {API.mac}: {e}")
                continue

            print("current", current)
            heartbeat_due = (now - last_heartbeat[API.mac]) >= HEARTBEAT_PERIOD
            point = build_point(API, current, caches[API.mac], heartbeat_due)

            if point is None:
                print(f"{API.mac}: no changes, skipping write")
            else:
                print(f"{API.mac}: writing {list(point['fields'].keys())}")
                influx.write_points([point])
                caches[API.mac].update(point["fields"])
                if heartbeat_due:
                    last_heartbeat[API.mac] = now

        try:
            time.sleep(PULL_PERIOD)
        except KeyboardInterrupt:
            print("Interrupted by user. Exit.")
            break

    influx.close()


if __name__ == "__main__":
    main()
