import os
from datetime import datetime, date, timedelta

import pandas as pd
import numpy as np
import click
import matplotlib.pyplot as plt
from influxdb import DataFrameClient

from collections import defaultdict

from miniha.config import config

INFLUX_HOST = config.INFLUX_HOST
INFLUX_PORT = config.INFLUX_PORT
INFLUX_DB = config.INFLUX_DB
OUTPUT_DIR = config.OUTPUT_DIR


def get_data(day: date) -> pd.DataFrame:
    """Query InfluxDB for temperature data of a given day"""
    start = datetime.combine(day, datetime.min.time()).isoformat() + "Z"
    end = datetime.combine(day + timedelta(days=1), datetime.min.time()).isoformat() + "Z"

    query = f"""
    SELECT "apparent_power", "active_power", "current_summ_delivered", "rms_current", "rms_voltage" FROM "linky"
    WHERE time >= '{start}' AND time < '{end}'
    ORDER BY time ASC
    """
    influx_client = DataFrameClient(host=INFLUX_HOST, port=INFLUX_PORT, database=INFLUX_DB)
    raw_result = influx_client.query(query)
    if not raw_result :
        return

    return raw_result["linky"]


def plot_temperature(df: pd.DataFrame, day: date):
    """Plot temperature and save to PNG"""
    if df is None or len(df) == 0:
        print(f"No data for {day}")
        return None

    plt.figure(figsize=(14, 5))

    time = df.index
    plt.plot(time, df["apparent_power"], label="apparent_power", marker=None, linestyle="-", color="red", linewidth=1)
    plt.plot(time, df["active_power"], label="active_power", marker=None, linestyle="-", color="blue", linewidth=1)
    #plt.plot(time, , label="current_summ_delivered", marker=None, linestyle="-", color="blue", linewidth=1)

    delta_kWh = df["current_summ_delivered"][-1] - df["current_summ_delivered"][0]
    delta_time = time[-1] - time[0]
    print(f"{delta_kWh} kWh in {delta_time} s")


    df2 = df.dropna(subset=['active_power'])
    time_hours = (df2.index - df2.index[0]).total_seconds() / 3600
    power = df2['active_power'].values
    energy_Wh = np.trapz(power, time_hours)
    print(f"Energy: {energy_Wh:.2f} Wh")


    plt.axhline(y=0, color='k', linewidth=1)
    plt.title(f"Power on {day.isoformat()}")
    plt.xlabel("Time")
    plt.ylabel("Puissance")
    plt.grid(False)
    plt.legend()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, f"power_{day.isoformat()}.png")
    plt.savefig(filepath)
    plt.close()

    print(f"Saved plot: {filepath}")
    return filepath


@click.command()
@click.option("--day", type=click.DateTime(formats=["%Y-%m-%d"]),
              default=None,
              help="Day in YYYY-MM-DD format (default: today)")
def main(day):
    """Plot temperature data from InfluxDB for the given day (or today)."""
    if day is None:
        day = date.today()
    else:
        day = day.date()

    values = get_data(day)
    plot_temperature(values, day)

    # # print(values)
    # df = pd.DataFrame.from_records(values['linky'], columns=["date", "power"])
    # os.makedirs(OUTPUT_DIR, exist_ok=True)
    # filepath = os.path.join(OUTPUT_DIR, f"power_{day.isoformat()}.csv")
    # df.to_csv(filepath, index=False)
    # print(f"csv file saved to {filepath}...")

if __name__ == "__main__":
    main()
