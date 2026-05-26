import os
from datetime import datetime, date, timedelta

import numpy as np
import click
import matplotlib.pyplot as plt
from influxdb import InfluxDBClient

from collections import defaultdict

# --- Config ---
INFLUX_HOST = "192.168.1.87"
INFLUX_PORT = 8086
INFLUX_DB = "sensors2"
OUTPUT_DIR = "output"

# --- Connect to InfluxDB ---
influx = InfluxDBClient(host=INFLUX_HOST, port=INFLUX_PORT, database=INFLUX_DB)


def get_data(day: date):
    """Query InfluxDB for temperature data of a given day"""
    start = (
        datetime.combine(day, datetime.min.time()) - timedelta(hours=6)
    ).isoformat() + "Z"
    end = (
        datetime.combine(day + timedelta(days=1), datetime.min.time())
        + timedelta(hours=6)
    ).isoformat() + "Z"

    query = f"""
    SELECT "name", "temperature" FROM "sonoff_thermometer"
    WHERE time >= '{start}' AND time < '{end}'
    ORDER BY time ASC
    """
    raw_result = influx.query(query)

    if not raw_result:
        return

    results = defaultdict(list)

    for point in raw_result.get_points():
        name = point["name"].split("/")[-1]
        row = [
            datetime.fromisoformat(point["time"].replace("Z", "+00:00")),
            point["temperature"],
        ]
        print(row)
        results[name].append(row)
    return results


def plot_temperature(values: dict, day: date):
    """Plot temperature and save to PNG"""
    if not values:
        print(f"No data for {day}")
        return None

    plt.figure(figsize=(10, 5))

    for name, rows in values.items():
        rows = np.array(rows)
        plt.plot(rows[:, 0], rows[:, 1], label=name, marker=None, linestyle="-")

    midnight_start = datetime.combine(day, datetime.min.time())
    midnight_end = datetime.combine(day + timedelta(days=1), datetime.min.time())
    plt.axvline(midnight_start, color="gray", linestyle="--", linewidth=1)
    plt.axvline(midnight_end, color="gray", linestyle="--", linewidth=1)

    plt.title(f"Temperature on {day.isoformat()}")
    plt.xlabel("Time")
    plt.ylabel("Temperature (°C)")
    plt.grid(False)
    plt.legend()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, f"temperature_{day.isoformat()}.png")
    plt.savefig(filepath)
    plt.close()

    print(f"Saved plot: {filepath}")
    return filepath


@click.command()
@click.option(
    "--day",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Day in YYYY-MM-DD format (default: today)",
)
def main(day):
    """Plot temperature data from InfluxDB for the given day (or today)."""
    if day is None:
        day = date.today()
    else:
        day = day.date()

    values = get_data(day)
    plot_temperature(values, day)


if __name__ == "__main__":
    main()
