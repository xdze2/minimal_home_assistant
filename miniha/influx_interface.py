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
    ) -> pd.DataFrame:
        """Query InfluxDB and return a DataFrame."""

        fields_str = ",".join(field_list)
        start = normalize_to_datetime(start).isoformat() + "Z"
        end = normalize_to_datetime(end).isoformat() + "Z"
        query = f"""
        SELECT {fields_str} FROM "{measurement}"
        WHERE time >= '{start}' AND time < '{end}'
        ORDER BY time ASC
        """
        raw_result = self.df_client.query(query)
        if not raw_result:
            return
        return raw_result[measurement]
