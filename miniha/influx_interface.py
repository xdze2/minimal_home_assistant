from typing import List, Dict, Any, Tuple

import pandas as pd
from influxdb import DataFrameClient
from .utils import normalize_to_datetime
from datetime import datetime


class InfluxInterface:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 8086,
        username: str = "",
        password: str = "",
        database: str = "db",
    ) -> None:
        self.df_client = DataFrameClient(
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
        )

    def query_df(
        self,
        measurement: str,
        field_list: List[str],
        start: str,
        end: str,
        group_by: str = None,
    ) -> Dict[Tuple, pd.DataFrame]:
        """Query InfluxDB and return a Dict of DataFrame."""

        fields_str = ",".join((f'"{u}"' for u in field_list))
        start = normalize_to_datetime(start).isoformat() + "Z"
        end = normalize_to_datetime(end).isoformat() + "Z"
        query_parts = [
            f'SELECT {fields_str} FROM "{measurement}"',
            f"WHERE time >= '{start}' AND time < '{end}'",
        ]
        if group_by is not None:
            query_parts.append(f'GROUP BY "{group_by}"')
        query_parts.append('ORDER BY "time" ASC')

        query = "\n".join(query_parts)
        # print(f"InfluxDB query: {query}")
        raw_result = self.df_client.query(query)
        if not raw_result:
            return
        return raw_result

    def list_measurements(self) -> List[str]:
        """List all measurements in the database."""
        result = self.df_client.query("SHOW MEASUREMENTS")
        if result is None:
            return []
        else:
            return [pts["name"] for pts in result.get_points()]

    def get_last_record_for_measurement(self, measurement: str) -> pd.DataFrame:
        """Get the last record for a given measurement."""
        query = f'SELECT * FROM "{measurement}" ORDER BY time DESC LIMIT 1'
        result = self.df_client.query(query)
        if not result:
            return pd.DataFrame()
        # Return the first DataFrame in the result dict
        for df in result.values():
            return df
        return pd.DataFrame()


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
                    "ieee_addr": device_info.get("ieeeAddr"),
                },
                "time": datetime.now().isoformat(),  # raw_fields["last_seen"],
                "fields": normalized_values(raw_fields, clc.__field_types__),
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
