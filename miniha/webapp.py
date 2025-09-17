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
    df = influx_client.query_df(
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

    if df is None or df.empty:
        print(f"no linky records for day {day}")
        return jsonify({"data": []})

    print(f"get {len(df)} linky records for day {day}")
    df = df.rename_axis("time").reset_index()
    json_obj = json.loads(df.to_json(orient="table", index=False))
    return jsonify(json_obj)


# # Serve other static files (JS, CSS)
# @app.route("/<path:path>")
# def static_proxy(path):
#     return send_from_directory(app.static_folder, path)


def main() -> None:
    app.run(debug=True)
