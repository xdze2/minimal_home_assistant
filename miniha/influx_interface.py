from typing import List, Dict, Any

import pandas as pd
from influxdb import DataFrameClient
from .utils import normalize_to_datetime


class InfluxInterface:
    def __init__(
        self, host: str, port: int, username: str, password: str, database: str
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.database = database
        self.df_client = DataFrameClient(
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            database=self.database,
        )

    def query_df(
        self,
        measurement: str,
        field_list,
        start: str,
        end: str,
        group_by: str = None,
    ) -> pd.DataFrame:
        """Query InfluxDB and return a DataFrame."""

        fields_str = ",".join((f'"{u}"' for u in field_list))
        start = normalize_to_datetime(start).isoformat() + "Z"
        end = normalize_to_datetime(end).isoformat() + "Z"
        query_parts = [
            f'Select {fields_str} FROM "{measurement}"',
            f"WHERE time >= '{start}' AND time < '{end}'",
        ]
        if group_by is not None:
            query_parts.append(f"GROUP BY {group_by}")
        query_parts.append("ORDER BY time ASC")

        query = "\n".join(query_parts)
        print(f"InfluxDB query: {query}")
        raw_result = self.df_client.query(query)
        if not raw_result:
            return
        return raw_result[measurement]
