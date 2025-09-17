from flask import Flask, send_from_directory, jsonify, request
import os
import json

app = Flask(__name__, static_folder="../frontend", static_url_path="")


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/data")
def data():
    # Example: get day from query param, e.g. /data?day=2024-06-01
    day = request.args.get("day", "2024-06-01")
    # For demo, load from a static JSON file
    with open("../data/sample_temps.json") as f:
        all_data = json.load(f)
    temps = all_data.get(day, [])
    return jsonify(temps)


# Serve other static files (JS, CSS)
@app.route("/<path:path>")
def static_proxy(path):
    return send_from_directory(app.static_folder, path)


def main():
    app.run(debug=True)
