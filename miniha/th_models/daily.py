"""Streamlit app: daily view — one card per room, 2 columns.

Run:
    UV_PROJECT_ENVIRONMENT=venv uv run streamlit run miniha/th_models/daily.py
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

_FR_DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_FR_MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin",
              "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def _fmt_day_fr(d: date) -> str:
    return f"{_FR_DAYS[d.weekday()]} {d.day} {_FR_MONTHS[d.month - 1]}"

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dataclasses import replace

from miniha.th_models.config import Window, discover_configs, load_room_config
from miniha.th_models.load import load_room

USER_MODELS_DIR = Path(__file__).resolve().parents[2] / "user_models"


@st.cache_data(show_spinner=False)
def _load_room_cached(
    config_path: str, day_iso: str, n_days: int
) -> dict[str, list[tuple[pd.Timestamp, float]]]:
    cfg = load_room_config(config_path)
    day = date.fromisoformat(day_iso)
    day_start = datetime.combine(day, datetime.min.time())
    w_start = day_start - timedelta(hours=6)
    w_end = day_start + timedelta(days=n_days, hours=6)
    cfg = replace(cfg, window=Window(start=w_start, end=w_end))
    series_map = load_room(cfg)
    return {role: list(zip(s.index, s.values)) for role, s in series_map.items()}


def _to_series(items) -> pd.Series:
    if not items:
        return pd.Series(dtype="float64")
    idx, vals = zip(*items)
    return pd.Series(vals, index=pd.DatetimeIndex(idx))


def _slice(s: pd.Series, t0: pd.Timestamp, t1: pd.Timestamp) -> pd.Series:
    if s.empty:
        return s
    idx = s.index
    if idx.tz is not None and t0.tz is None:
        t0 = t0.tz_localize(idx.tz)
        t1 = t1.tz_localize(idx.tz)
    elif idx.tz is None and t0.tz is not None:
        t0 = t0.tz_localize(None)
        t1 = t1.tz_localize(None)
    return s.loc[(s.index >= t0) & (s.index <= t1)]


def _plot_card(indoor: pd.Series, outdoor: pd.Series, solar: pd.Series,
               day_start, day_end) -> go.Figure:
    fig = go.Figure()

    candidates = [s for s in (indoor, outdoor) if not s.empty]
    if candidates:
        y_lo = float(min(s.min() for s in candidates))
        y_hi = float(max(s.max() for s in candidates))
    else:
        y_lo, y_hi = 0.0, 1.0
    pad = (y_hi - y_lo) * 0.05 or 1.0
    y_lo -= pad
    y_hi += pad

    if not solar.empty:
        solar_z = solar.clip(lower=0).to_numpy()
        fig.add_trace(go.Heatmap(
            x=solar.index, y=[y_lo, y_hi], z=[solar_z, solar_z],
            colorscale=[(0.0, "white"), (1.0, "goldenrod")],
            zmin=0, zmax=max(float(solar_z.max()), 1.0),
            showscale=True, colorbar=dict(title="W/m²", thickness=10),
            hoverinfo="skip", name="solar",
        ))

    if not indoor.empty:
        fig.add_trace(go.Scattergl(x=indoor.index, y=indoor.values, mode="lines",
                                   name="indoor", line=dict(color="royalblue")))
    if not outdoor.empty:
        fig.add_trace(go.Scattergl(x=outdoor.index, y=outdoor.values, mode="lines",
                                   name="outdoor",
                                   line=dict(color="rgba(220,20,60,0.45)", width=4)))

    tz = "Europe/Paris"
    midnight_index = None
    for s in (indoor, outdoor, solar):
        if not s.empty:
            midnight_index = s.index
            break
    if midnight_index is not None:
        local = (midnight_index.tz_localize("UTC").tz_convert(tz)
                 if midnight_index.tz is None else midnight_index.tz_convert(tz))
        start_day = local.min().normalize()
        end_day = local.max().normalize() + pd.Timedelta(days=1)
        for ts in pd.date_range(start_day, end_day, freq="D", tz=tz):
            fig.add_vline(x=ts, line=dict(color="black", width=1))

    fig.update_yaxes(title_text="°C", range=[y_lo, y_hi])
    fig.update_layout(
        height=340, margin=dict(l=40, r=20, t=24, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1.0),
    )
    return fig


def _render_card(cfg_path: Path, day: date, n_days: int) -> None:
    cfg = load_room_config(cfg_path)
    st.markdown(f"**{cfg.room}**")

    try:
        cached = _load_room_cached(str(cfg_path), day.isoformat(), n_days)
    except Exception as e:
        st.error(f"Load failed: {e}")
        return

    day_start = pd.Timestamp(datetime.combine(day, datetime.min.time()))
    day_end = day_start + timedelta(days=n_days)

    indoor = _slice(_to_series(cached.get("indoor_temp", [])), day_start, day_end)
    outdoor = _slice(_to_series(cached.get("outdoor_temp", [])), day_start, day_end)
    solar = _slice(_to_series(cached.get("shortwave_radiation", [])), day_start, day_end)

    st.plotly_chart(_plot_card(indoor, outdoor, solar, day_start, day_end),
                    use_container_width=True, key=f"{cfg_path.name}_card")


def _default_day(configs: list[Path]) -> date:
    for p in configs:
        try:
            cfg = load_room_config(p)
            return cfg.window.end.date()
        except Exception:
            continue
    return date.today()


def main() -> None:
    st.set_page_config(page_title="th_models — daily", layout="wide")

    configs = discover_configs(USER_MODELS_DIR)
    if not configs:
        st.warning(f"No YAML files in {USER_MODELS_DIR}")
        return

    DURATION_OPTIONS = [1, 2, 3, 5, 10, 30]
    with st.sidebar:
        st.header("Day")
        day = st.date_input("Select day", value=_default_day(configs))
        n_days = st.selectbox(
            "Duration",
            DURATION_OPTIONS, index=0,
            format_func=lambda d: f"{d} day" if d == 1 else f"{d} days",
        )
        if st.button("Reload data", use_container_width=True):
            _load_room_cached.clear()
            st.rerun()
        st.caption(f"{len(configs)} room(s) in `user_models/`")

    if n_days == 1:
        st.title(_fmt_day_fr(day))
    else:
        end = day + timedelta(days=n_days - 1)
        st.title(f"{_fmt_day_fr(day)} → {_fmt_day_fr(end)}")

    for cfg_path in configs:
        with st.container(border=True):
            _render_card(cfg_path, day, n_days)


if __name__ == "__main__":
    main()
else:
    main()
