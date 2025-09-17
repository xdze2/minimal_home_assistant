from flask import Flask, send_from_directory, jsonify, request
import os
import json
from .influx_interface import InfluxInterface

import pandas as pd
from .config import config


influx_client = InfluxInterface(
    host=config.INFLUX_HOST,
    port=config.INFLUX_PORT,
    username="",
    password="",
    database=config.INFLUX_DB,
)

app = Flask(__name__, static_folder="../frontend", static_url_path="")


@app.route("/")
def index() -> object:
    return send_from_directory(app.static_folder, "index.html")


# @app.route("/data")
# def data() -> object:
#     day = request.args.get("day", "2024-06-01")
#     temps = influx_client.get_temps_for_day(day)
#     print(temps)
#     return jsonify(temps)


@app.route("/linky")
def get_linky_data() -> object:
    day = request.args.get("day", "2024-06-01")
    query_res = influx_client.query_df(
        measurement="linky",
        field_list=[
            "apparent_power",
            "active_power",
            "current_summ_delivered",
            "rms_current",
            "rms_voltage",
        ],
        start=day,
        end=pd.to_datetime(day) + pd.Timedelta(days=1),
    )
    df = query_res.get("linky")
    if df is None or df.empty:
        print(f"no linky records for day {day}")
        return jsonify({"data": []})

    print(f"get {len(df)} linky records for day {day}")
    df = df.rename_axis("time").reset_index()
    json_obj = json.loads(df.to_json(orient="table", index=False))
    return jsonify(json_obj)


@app.route("/temperatures")
def get_temperatures_data() -> object:
    day = request.args.get("day", "2024-06-01")
    df_dicts = influx_client.query_df(
        measurement="sonoff_thermometer",
        field_list=[
            "name",
            "temperature",
        ],
        start=day,
        end=pd.to_datetime(day) + pd.Timedelta(days=1),
        group_by="name",
    )
    if df_dicts is None or len(df_dicts) == 0:
        print(f"no records for day {day}")
        return jsonify({"data": []})

    results = dict()
    for meas_name, df in df_dicts.items():
        if df is None or df.empty:
            continue
        print(f"get {len(df)} records for day {day} and sensor {meas_name}")
        try:
            sensor_name = meas_name[1][0][1]
            sensor_name = sensor_name.split("/")[-1]
        except IndexError as err:
            print(f"[ERROR] cannot extract sensor name from {meas_name}: {err}")
            continue
        df = df.rename_axis("time").reset_index()
        results[sensor_name] = json.loads(df.to_json(orient="table", index=False))

    return jsonify(results)


@app.route("/events")
def get_events() -> object:
    day = request.args.get("day", "2024-06-01")
    # Mock data: events for the given day
    # Times are in ISO format, UTC
    events = [
        {
            "start": f"{day}T07:30:00Z",
            "end": f"{day}T08:00:00Z",
            "title": "Breakfast",
            "message": "Family breakfast time.",
        },
        {
            "start": f"{day}T12:00:00Z",
            "end": f"{day}T12:30:00Z",
            "title": "Lunch",
            "message": "Lunch break.",
        },
        {
            "start": f"{day}T18:30:00Z",
            "end": f"{day}T19:00:00Z",
            "title": "Dinner",
            "message": "Dinner with friends.",
        },
    ]
    return jsonify(events)


# # Serve other static files (JS, CSS)
# @app.route("/<path:path>")
# def static_proxy(path):
#     return send_from_directory(app.static_folder, path)


def main() -> None:
    app.run(debug=True, host="0.0.0.0", port=5000)
