"""Fetch yesterday's hourly weather from Open-Meteo and write it to InfluxDB.

Run as a one-shot daily job (via systemd timer or cron). Locations are read
from `config/open_meteo.yaml` under the `locations:` key; each entry is
written with a `location` tag.
"""

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import click
import pandas as pd
import requests
import yaml
from influxdb import InfluxDBClient

MEASUREMENT_NAME = "open_meteo_historic"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HOURLY_VARIABLES = [
    "temperature_2m",
    "rain",
    "relative_humidity_2m",
    "cloud_cover",
    "wind_speed_10m",
    "shortwave_radiation",
    "direct_radiation",
    "diffuse_radiation",
]
DEFAULT_CONFIG_PATH = "config/open_meteo.yaml"


def load_locations(path: str | None = None) -> List[Dict[str, Any]]:
    p = Path(path or os.environ.get("MINIHA_OPEN_METEO") or DEFAULT_CONFIG_PATH)
    with p.open("r") as f:
        raw = yaml.safe_load(f) or {}
    locations = raw.get("locations") or []
    if not locations:
        raise ValueError(f"No `locations` entries found in {p}")
    return locations


def fetch_hourly(latitude: float, longitude: float, start: date, end: date) -> pd.DataFrame:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": ",".join(HOURLY_VARIABLES),
    }
    response = requests.get(ARCHIVE_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    hourly = data["hourly"]
    df = pd.DataFrame({
        "time": pd.to_datetime(hourly["time"], utc=True),
        **{v: hourly[v] for v in HOURLY_VARIABLES},
    })
    return df


def build_points(df: pd.DataFrame, location: str) -> List[Dict[str, Any]]:
    points: List[Dict[str, Any]] = []
    for row in df.itertuples(index=False):
        fields = {v: float(getattr(row, v)) for v in HOURLY_VARIABLES if getattr(row, v) is not None and not pd.isna(getattr(row, v))}
        if not fields:
            continue
        points.append({
            "measurement": MEASUREMENT_NAME,
            "tags": {"location": location},
            "time": row.time.isoformat(),
            "fields": fields,
        })
    return points


@click.command()
@click.option(
    "--day",
    "day_str",
    default=None,
    help="Single target day (YYYY-MM-DD). Shortcut for --start=DAY --end=DAY.",
)
@click.option(
    "--start",
    "start_str",
    default=None,
    help="Range start date (YYYY-MM-DD, inclusive).",
)
@click.option(
    "--end",
    "end_str",
    default=None,
    help="Range end date (YYYY-MM-DD, inclusive). Defaults to yesterday.",
)
def main(day_str: str | None, start_str: str | None, end_str: str | None) -> None:
    from .config import config

    if day_str and (start_str or end_str):
        raise click.UsageError("--day cannot be combined with --start/--end")

    if day_str:
        start_day = end_day = datetime.strptime(day_str, "%Y-%m-%d").date()
    else:
        end_day = (
            datetime.strptime(end_str, "%Y-%m-%d").date()
            if end_str
            else date.today() - timedelta(days=1)
        )
        start_day = (
            datetime.strptime(start_str, "%Y-%m-%d").date() if start_str else end_day
        )

    if start_day > end_day:
        raise click.UsageError("--start must be on or before --end")

    print(f"Fetching Open-Meteo archive from {start_day.isoformat()} to {end_day.isoformat()}...")

    locations = load_locations()
    print(f"Connecting to InfluxDB {config.INFLUX_HOST}:{config.INFLUX_PORT} on db={config.INFLUX_DB}...")
    influx = InfluxDBClient(host=config.INFLUX_HOST, port=config.INFLUX_PORT)
    influx.create_database(config.INFLUX_DB)
    influx.switch_database(config.INFLUX_DB)

    for loc in locations:
        name = loc["location"]
        lat = float(loc["latitude"])
        lon = float(loc["longitude"])
        print(f"[{name}] fetching ({lat}, {lon})...")
        df = fetch_hourly(lat, lon, start_day, end_day)
        points = build_points(df, name)
        if not points:
            print(f"[{name}] no points to write")
            continue
        print(f"[{name}] writing {len(points)} points")
        influx.write_points(points, batch_size=5000)

    influx.close()


if __name__ == "__main__":
    main()
