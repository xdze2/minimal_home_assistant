import yaml
from .influx_interface import InfluxInterface
import json
from flask import Flask, send_from_directory, jsonify, request

import pandas as pd
from .config import config


influx_client = InfluxInterface(
    host=config.INFLUX_HOST,
    port=config.INFLUX_PORT,
    username="",
    password="",
    database=config.INFLUX_DB,
)

# app = Flask(__name__, static_folder="../frontend", static_url_path="")

dashboard_filepath = "config/dashboard.yaml"
with open(dashboard_filepath) as stream:
    try:
        dashboard_specs = yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        print(exc)


def main():
    for graph in dashboard_specs.get("graphs", []):
        print(f"Graph: {graph['title']} {graph["measurement"]} {graph['fields']}")

        day = "2026-01-28"
        nbr_days = 5
        query_res = influx_client.query_df(
            measurement=graph["measurement"],
            field_list=graph["fields"],
            start=day,
            end=pd.to_datetime(day) + pd.Timedelta(days=nbr_days),
            group_by=graph.get("group_by", None),
        )
        if query_res is None:
            print(f"no {graph["measurement"]} records...")
            return jsonify({"data": []})

        df = query_res.get(graph["measurement"])
        if df is None or df.empty:
            print(f"no {graph["measurement"]} records for day {day}")
            return jsonify({"data": []})

        print(f"get {len(df)} {graph["measurement"]} records for day {day}")
        df = df.rename_axis("time").reset_index()
        json_obj = json.loads(df.to_json(orient="table", index=False))
        print(json_obj)
        # return jsonify(json_obj)


# def generate_influx_queries(yaml_input):
#     data = yaml.safe_load(yaml_input)
#     queries = []

#     for graph in data.get("graphs", []):
#         # 1. Format the Fields
#         fields_str = ", ".join([f'"{f}"' for f in graph["fields"]])

#         # 2. Format the Filters (Tags)
#         filter_parts = [f"\"{k}\" = '{v}'" for k, v in graph["filters"].items()]
#         # Add a placeholder for the time range (standard for dashboards)
#         filter_parts.append("$timeFilter")
#         where_clause = " AND ".join(filter_parts)

#         # 3. Construct the final InfluxQL string
#         query = (
#             f"SELECT {fields_str} FROM \"{graph['measurement']}\" WHERE {where_clause}"
#         )

#         queries.append({"title": graph["title"], "query": query})

#     return queries


# # Execution
# results = generate_influx_queries(yaml_data)

# for res in results:
#     print(f"Graph: {res['title']}")
#     print(f"Query: {res['query']}\n")
