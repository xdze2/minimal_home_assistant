"""Per-room temperature plot, using the miniha webapp HTTP API.

Unlike plot_temp.py (which queries InfluxDB directly), this script reads
/config to discover rooms and sensor placement, then /temperatures and
/daikin to get the day's data. One subplot per room with at least one
mapped sensor; outdoor temperature is overlaid on each subplot for context.

Usage:
    python plot_temp2.py                 # today
    python plot_temp2.py --day 2026-05-26
    MINIHA_URL=http://host:5001 python plot_temp2.py --day 2026-05-26
"""

import os
from collections import defaultdict
from datetime import date, datetime
from typing import Iterable

import click
import matplotlib.pyplot as plt
import requests


DEFAULT_URL = os.environ.get("MINIHA_URL", "http://localhost:5001")
OUTPUT_DIR = "output"


def fetch_json(base_url: str, path: str, **params) -> dict:
    r = requests.get(f"{base_url}{path}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def series_to_xy(series: dict) -> tuple[list[datetime], list[float]]:
    """Convert /temperatures or /daikin series ({data: [{time, temperature}, ...]})
    to parallel x/y lists."""
    rows = (series or {}).get("data") or []
    xs, ys = [], []
    for row in rows:
        t = row.get("time")
        v = row.get("temperature")
        if t is None or v is None:
            continue
        xs.append(datetime.fromisoformat(t.replace("Z", "+00:00")))
        ys.append(float(v))
    return xs, ys


def group_series_by_room(
    config: dict, sonoff: dict, daikin: dict
) -> tuple[dict[str, list[tuple[str, dict]]], dict]:
    """Bucket all series by their room id.

    Returns (rooms_to_series, outdoor_series).
      rooms_to_series[room_id] = [(legend_label, series_dict), ...]
      outdoor_series is one merged "Outdoor" entry (mean across units would need
      resampling; here we just plot each outdoor line — they should overlap).
    """
    # Build a "label -> room_id" index from /config.
    label_to_room: dict[str, str] = {}
    for s in config.get("sensors", []):
        if s.get("room"):
            label_to_room[s["label"]] = s["room"]

    by_room: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    outdoor: list[tuple[str, dict]] = []

    for label, series in (sonoff or {}).items():
        room = label_to_room.get(label)
        if room:
            by_room[room].append((label, series))

    # Daikin keys are "<label> inside" / "<label> outside".
    for key, series in (daikin or {}).items():
        if key.endswith(" outside"):
            outdoor.append((key, series))
            continue
        base = key[: -len(" inside")] if key.endswith(" inside") else key
        room = label_to_room.get(base)
        if room:
            by_room[room].append((key, series))

    return by_room, outdoor


def plot_per_room(
    config: dict,
    by_room: dict[str, list[tuple[str, dict]]],
    outdoor: list[tuple[str, dict]],
    day: date,
) -> str | None:
    rooms = [r for r in config.get("rooms", []) if r["id"] in by_room]
    if not rooms:
        print(f"No room has any sensor data for {day}")
        return None

    fig, axes = plt.subplots(
        len(rooms), 1, figsize=(11, 2.6 * len(rooms)), sharex=True, squeeze=False
    )
    axes = axes[:, 0]

    for ax, room in zip(axes, rooms):
        # Indoor lines.
        for label, series in by_room[room["id"]]:
            xs, ys = series_to_xy(series)
            if xs:
                ax.plot(xs, ys, label=label, linewidth=1.2)

        # Outdoor reference on every subplot (thin grey).
        for label, series in outdoor:
            xs, ys = series_to_xy(series)
            if xs:
                ax.plot(xs, ys, label=label, color="#888", linewidth=0.9, alpha=0.7)

        ax.set_title(room["label"], loc="left", fontsize=10)
        ax.set_ylabel("°C")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8, loc="upper right", ncol=2)

    axes[-1].set_xlabel("Time")
    fig.suptitle(f"Temperatures — {day.isoformat()}", y=1.0)
    fig.tight_layout()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out = os.path.join(OUTPUT_DIR, f"temperature_by_room_{day.isoformat()}.png")
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"Saved plot: {out}")
    return out


@click.command()
@click.option(
    "--day",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Day in YYYY-MM-DD format (default: today)",
)
@click.option(
    "--url",
    default=DEFAULT_URL,
    show_default=True,
    help="Base URL of the miniha webapp (overrides MINIHA_URL).",
)
def main(day, url):
    day = day.date() if day else date.today()
    day_str = day.isoformat()

    config = fetch_json(url, "/config")
    sonoff = fetch_json(url, "/temperatures", day=day_str)
    daikin = fetch_json(url, "/daikin", day=day_str)

    # /temperatures returns {"data": []} when empty (legacy shape); normalize.
    if isinstance(sonoff, dict) and "data" in sonoff and len(sonoff) == 1:
        sonoff = {}

    by_room, outdoor = group_series_by_room(config, sonoff, daikin)
    plot_per_room(config, by_room, outdoor, day)


if __name__ == "__main__":
    main()
