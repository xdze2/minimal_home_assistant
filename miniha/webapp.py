from flask import Flask, send_from_directory, jsonify, request
import json
from .influx_interface import InfluxInterface
from .sensors import load_sensors, Sensor

import pandas as pd
from .config import config


DAIKIN_MEASUREMENT = "daikin_aircon_v2"
SONOFF_MEASUREMENT = "sonoff_thermometer"
LINKY_MEASUREMENT = "linky"


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


@app.route("/config")
def get_config() -> object:
    """Expose the sensor registry to the frontend."""
    registry = load_sensors()
    return jsonify({
        "rooms": [{"id": r.id, "label": r.label} for r in registry.rooms],
        "sensors": [
            {
                "id": s.id,
                "source": s.source,
                "room": s.room,
                "kind": s.kind,
                "label": registry.label_for(s),
                "provides_outdoor": s.provides_outdoor,
            }
            for s in registry.sensors
        ],
    })


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
    if query_res is None:
        print(f"no linky records///")
        return jsonify({"data": []})

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

    registry = load_sensors()
    results = dict()
    for meas_name, df in df_dicts.items():
        if df is None or df.empty:
            continue
        tags = dict(meas_name[1]) if len(meas_name) > 1 else {}
        sensor = registry.find_sensor(SONOFF_MEASUREMENT, tags)
        if sensor is None or sensor.room is None:
            continue
        label = registry.label_for(sensor)
        df = df.rename_axis("time").reset_index()
        results[label] = json.loads(df.to_json(orient="table", index=False))

    return jsonify(results)


@app.route("/daikin")
def get_daikin_data() -> object:
    """Per-day Daikin readings (inside + outside) keyed by 'Room label – sensor id'.

    Returns one entry per series. Each entry has the same shape as /temperatures:
      { "<label> inside":  {data: [{time, temperature}, ...]},
        "<label> outside": {data: [{time, temperature}, ...]} }
    """
    day = request.args.get("day", "2024-06-01")
    df_dicts = influx_client.query_df(
        measurement=DAIKIN_MEASUREMENT,
        field_list=["name", "inside_temperature", "outside_temperature"],
        start=day,
        end=pd.to_datetime(day) + pd.Timedelta(days=1),
        group_by="name",
    )
    if df_dicts is None or len(df_dicts) == 0:
        return jsonify({})

    registry = load_sensors()
    results: dict = {}
    for meas_name, df in df_dicts.items():
        if df is None or df.empty:
            continue
        tags = dict(meas_name[1]) if len(meas_name) > 1 else {}
        sensor = registry.find_sensor(DAIKIN_MEASUREMENT, tags)
        if sensor is None or sensor.room is None:
            continue
        label = registry.label_for(sensor)
        df = df.rename_axis("time").reset_index()

        inside = df[["time", "inside_temperature"]].dropna(subset=["inside_temperature"])
        if not inside.empty:
            inside = inside.rename(columns={"inside_temperature": "temperature"})
            results[f"{label} inside"] = json.loads(inside.to_json(orient="table", index=False))

        outside = df[["time", "outside_temperature"]].dropna(subset=["outside_temperature"])
        if not outside.empty:
            outside = outside.rename(columns={"outside_temperature": "temperature"})
            results[f"{label} outside"] = json.loads(outside.to_json(orient="table", index=False))

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


@app.route("/linky_daily")
def linky_daily() -> object:
    day = request.args.get("day", "2024-06-01")
    # Query linky data for the day
    query_res = influx_client.query_df(
        measurement="linky",
        field_list=[
            "active_power",
            "current_summ_delivered",
        ],
        start=day,
        end=pd.to_datetime(day) + pd.Timedelta(days=1),
    )
    if query_res is None:
        return jsonify({"data": []})
    df = query_res.get("linky")
    result = {
        "total_kwh": None,
        "status": "missing",
        "cost_eur": None,
        "top_events": [],
    }

    if df is None or df.empty:
        return jsonify(result)

    # Compute total kWh consumed (from current_summ_delivered, in kWh)
    df = df.rename_axis("time").reset_index()
    df = df.sort_values("time")
    if "current_summ_delivered" in df.columns:
        delivered = df["current_summ_delivered"].dropna()
        if not delivered.empty:
            total_kwh = delivered.iloc[-1] - delivered.iloc[0]
            result["total_kwh"] = round(float(total_kwh), 3)
        else:
            result["total_kwh"] = None
    else:
        result["total_kwh"] = None

    # Data status
    expected_points = 24 * 60 * 4  # assuming 15s interval
    actual_points = len(df)
    if actual_points == 0:
        result["status"] = "missing"
    elif actual_points > 0.95 * expected_points:
        result["status"] = "ok"
    elif actual_points > 0.5 * expected_points:
        result["status"] = "ongoing"
    else:
        result["status"] = "nok"

    # Cost estimation (simple: 0.22 €/kWh)
    if result["total_kwh"] is not None:
        result["cost_eur"] = round(result["total_kwh"] * 0.22, 2)
    else:
        result["cost_eur"] = None

    # Top 5 main consumption events (longest periods of high active_power)
    top_events = []
    if "active_power" in df.columns:
        threshold = df["active_power"].quantile(0.90)  # top 10% as "high"
        df["high"] = df["active_power"] > threshold
        df["grp"] = (df["high"] != df["high"].shift()).cumsum()
        high_groups = df[df["high"]].groupby("grp")
        events = []
        for _, group in high_groups:
            start = group["time"].iloc[0]
            end = group["time"].iloc[-1]
            duration = (end - start).total_seconds() / 60  # minutes
            max_power = group["active_power"].max()
            events.append({
                "start": start.isoformat(),
                "end": end.isoformat(),
                "duration_min": round(duration, 1),
                "max_power": round(float(max_power), 1),
            })
        # Sort by duration, take top 5
        top_events = sorted(events, key=lambda e: e["duration_min"], reverse=True)[:5]
    result["top_events"] = top_events

    return jsonify(result)


@app.route("/monthly_summary")
def monthly_summary() -> object:
    """Return per-day aggregates for the last N days (default 60).

    Response shape:
      {
        "start": "YYYY-MM-DD",
        "end":   "YYYY-MM-DD",
        "rooms": ["kitchen", "bedroom", ...],
        "days":  [
          {
            "date":    "YYYY-MM-DD",
            "ext_min": float|None, "ext_max": float|None,
            "kwh":     float|None,
            "rooms":   {"kitchen": {"min": .., "max": ..}, ...},
          }, ...
        ]
      }
    """
    days = int(request.args.get("days", 60))
    end_arg = request.args.get("end")
    # Keep all keys tz-naive so dict lookups match the parsed Influx timestamps
    # (which we tz_convert(None) below).
    if end_arg:
        end_date = pd.to_datetime(end_arg).normalize()
    else:
        end_date = pd.Timestamp.utcnow().tz_localize(None).normalize()
    end_excl = end_date + pd.Timedelta(days=1)  # include end_date fully
    start_date = end_excl - pd.Timedelta(days=days)

    start_iso = start_date.isoformat() + "Z"
    end_iso = end_excl.isoformat() + "Z"

    client = influx_client.df_client
    registry = load_sensors()

    # 1) Outdoor temperature: from sensors flagged `provides_outdoor` in sensors.yaml.
    #    Build a WHERE clause that selects only those units, group by their match tag,
    #    then average per-unit daily min/max in pandas.
    ext_per_day: dict[pd.Timestamp, dict[str, float]] = {}
    outdoor = registry.outdoor_sensors()
    if outdoor:
        # All outdoor sensors share a single source today; if that changes, split per source.
        by_source: dict[str, list[Sensor]] = {}
        for s in outdoor:
            by_source.setdefault(s.source, []).append(s)

        ext_frames = []
        for source, sensors_in_src in by_source.items():
            # OR together the per-sensor match clauses.
            clauses = []
            for s in sensors_in_src:
                inner = " AND ".join(f"\"{k}\" = '{v}'" for k, v in s.match.items())
                clauses.append(f"({inner})")
            where = " OR ".join(clauses)
            # Group by the union of match keys so each unit is its own series.
            group_keys = sorted({k for s in sensors_in_src for k in s.match.keys()})
            group_by = ", ".join(f'"{k}"' for k in group_keys)
            ext_query = (
                f'SELECT min("outside_temperature") AS ext_min, '
                f'max("outside_temperature") AS ext_max '
                f'FROM "{source}" '
                f"WHERE time >= '{start_iso}' AND time < '{end_iso}' "
                f"AND ({where}) "
                f"GROUP BY time(1d), {group_by} fill(none)"
            )
            try:
                ext_raw = client.query(ext_query)
                for _key, df in ext_raw.items():
                    if df is None or df.empty:
                        continue
                    ext_frames.append(df[["ext_min", "ext_max"]])
            except Exception as err:
                print(f"[ext] query failed for {source}: {err}")

        if ext_frames:
            ext_all = pd.concat(ext_frames)
            # Average each unit's daily min and daily max across units → robust envelope.
            ext_daily = ext_all.groupby(ext_all.index).mean()
            for ts, row in ext_daily.iterrows():
                day = (ts.tz_convert(None) if ts.tzinfo else ts).normalize()
                ext_per_day[day] = {
                    "min": None if pd.isna(row["ext_min"]) else round(float(row["ext_min"]), 2),
                    "max": None if pd.isna(row["ext_max"]) else round(float(row["ext_max"]), 2),
                }

    # 2) Linky daily kWh: counter delta per day.
    linky_query = (
        f'SELECT max("current_summ_delivered") - min("current_summ_delivered") AS kwh, '
        f'count("active_power") AS n_points '
        f'FROM "{LINKY_MEASUREMENT}" '
        f"WHERE time >= '{start_iso}' AND time < '{end_iso}' "
        f"GROUP BY time(1d) fill(none)"
    )
    kwh_per_day: dict[pd.Timestamp, dict[str, object]] = {}
    try:
        linky_raw = client.query(linky_query)
        # Single-series result keyed by measurement name.
        for _key, df in linky_raw.items():
            if df is None or df.empty:
                continue
            today = pd.Timestamp.utcnow().tz_localize(None).normalize()
            for ts, row in df.iterrows():
                day = (ts.tz_convert(None) if ts.tzinfo else ts).normalize()
                kwh_val = None if pd.isna(row.get("kwh")) else round(float(row["kwh"]), 3)
                n_pts = int(row.get("n_points") or 0)
                if kwh_val is None and n_pts == 0:
                    status = "missing"
                elif day == today:
                    status = "ongoing"
                elif kwh_val is not None and kwh_val > 0:
                    status = "ok"
                else:
                    status = "nok"
                kwh_per_day[day] = {"kwh": kwh_val, "status": status}
    except Exception as err:
        print(f"[linky] query failed: {err}")

    # 3) Indoor temperature per registered sensor: daily min/max grouped by sensor.
    #    Key in the response is "Room label – sensor id" so the frontend displays
    #    user-friendly names without doing its own lookup.
    inside_query = (
        f'SELECT min("temperature") AS t_min, max("temperature") AS t_max '
        f'FROM "{SONOFF_MEASUREMENT}" '
        f"WHERE time >= '{start_iso}' AND time < '{end_iso}' "
        f"GROUP BY time(1d), \"name\" fill(none)"
    )
    rooms_per_day: dict[pd.Timestamp, dict[str, dict[str, float]]] = {}
    rooms_seen: set[str] = set()
    try:
        inside_raw = client.query(inside_query)
        for key, df in inside_raw.items():
            if df is None or df.empty:
                continue
            tags = dict(key[1]) if len(key) > 1 else {}
            sensor = registry.find_sensor(SONOFF_MEASUREMENT, tags)
            if sensor is None or sensor.room is None:
                continue  # unmapped sensor → skip (already warned at load time)
            label = registry.label_for(sensor)
            rooms_seen.add(label)
            for ts, row in df.iterrows():
                day = (ts.tz_convert(None) if ts.tzinfo else ts).normalize()
                bucket = rooms_per_day.setdefault(day, {})
                bucket[label] = {
                    "min": None if pd.isna(row["t_min"]) else round(float(row["t_min"]), 2),
                    "max": None if pd.isna(row["t_max"]) else round(float(row["t_max"]), 2),
                }
    except Exception as err:
        print(f"[inside] query failed: {err}")

    # Assemble: one entry per day in range, newest first.
    out_days = []
    cursor = end_date
    while cursor >= start_date:
        ext = ext_per_day.get(cursor, {"min": None, "max": None})
        linky_info = kwh_per_day.get(cursor, {"kwh": None, "status": "missing"})
        out_days.append({
            "date": cursor.strftime("%Y-%m-%d"),
            "ext_min": ext["min"],
            "ext_max": ext["max"],
            "kwh": linky_info["kwh"],
            "status": linky_info["status"],
            "rooms": rooms_per_day.get(cursor, {}),
        })
        cursor -= pd.Timedelta(days=1)

    return jsonify({
        "start": start_date.strftime("%Y-%m-%d"),
        "end": end_date.strftime("%Y-%m-%d"),
        "rooms": sorted(rooms_seen),
        "days": out_days,
    })


# # Serve other static files (JS, CSS)
# @app.route("/<path:path>")
# def static_proxy(path):
#     return send_from_directory(app.static_folder, path)


def main() -> None:
    app.run(debug=True, host="0.0.0.0", port=config.WEBAPP_PORT)


if __name__ == "__main__":
    main()
