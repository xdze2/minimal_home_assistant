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
import plotly.subplots as sp
import streamlit as st

from dataclasses import replace

from miniha.th_models.config import Window, discover_configs, load_room_config
from miniha.th_models.load import load_room
from miniha.th_models.fit import FitResult, fit_thermal, prepare

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


_FILL_COLORS = {
    "royalblue": "rgba(65,105,225,0.25)",
    "tomato":    "rgba(255,99,71,0.25)",
    "goldenrod": "rgba(218,165,32,0.25)",
}


def _area(x, y, color: str, name: str) -> go.Scatter:
    return go.Scatter(
        x=x, y=y, mode="lines", name=name,
        line=dict(color=color, width=1),
        fill="tozeroy",
        fillcolor=_FILL_COLORS.get(color, color),
    )


def _plot_room(
    indoor: pd.Series,
    outdoor: pd.Series,
    solar: pd.Series,
    fit: FitResult | None,
) -> go.Figure:
    fig = sp.make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        row_heights=[0.4, 0.2, 0.2, 0.2],
        vertical_spacing=0.03,
    )

    # ── row 1: temperatures + solar heatmap ──────────────────────────────────
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
            showscale=False, hoverinfo="skip", name="solar",
        ), row=1, col=1)

    if not indoor.empty:
        fig.add_trace(go.Scattergl(x=indoor.index, y=indoor.values, mode="lines",
                                   name="indoor", line=dict(color="royalblue")),
                      row=1, col=1)
    if not outdoor.empty:
        fig.add_trace(go.Scattergl(x=outdoor.index, y=outdoor.values, mode="lines",
                                   name="outdoor",
                                   line=dict(color="rgba(220,20,60,0.55)", width=3)),
                      row=1, col=1)

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

    fig.update_yaxes(title_text="°C", range=[y_lo, y_hi], row=1, col=1)

    # ── compute 30-min grid series ────────────────────────────────────────────
    T30_in = indoor.resample("30min").mean() if not indoor.empty else pd.Series(dtype=float)

    def _interp_to(s: pd.Series, grid: pd.Series) -> pd.Series:
        return (s.reindex(s.index.union(grid.index))
                 .interpolate(method="time")
                 .reindex(grid.index))

    # ── row 2: dT/dt ──────────────────────────────────────────────────────────
    if not T30_in.empty:
        dT_dt = T30_in.diff() / 0.5  # °C/h
        fig.add_trace(_area(dT_dt.index, dT_dt.values, "royalblue", "dT/dt (°C/h)"),
                      row=2, col=1)
    fig.update_yaxes(title_text="°C/h", row=2, col=1)

    # ── row 3: conduction (T_ext − T_int) / τ ────────────────────────────────
    if fit is not None and not outdoor.empty and not T30_in.empty:
        T30_out = _interp_to(outdoor, T30_in)
        cond = (T30_out - T30_in) / fit.tau_hours
        fig.add_trace(_area(cond.index, cond.values, "tomato", "(T_ext−T_int)/τ (°C/h)"),
                      row=3, col=1)
    elif not outdoor.empty and not indoor.empty:
        delta = _interp_to(outdoor, T30_in) - T30_in
        fig.add_trace(_area(delta.index, delta.values, "tomato", "T_ext−T_int (°C)"),
                      row=3, col=1)
    fig.update_yaxes(title_text="°C/h", row=3, col=1)

    # ── row 4: solar gain α·I / τ ─────────────────────────────────────────────
    if fit is not None and not solar.empty and not T30_in.empty:
        T30_sol = _interp_to(solar, T30_in).clip(lower=0)
        solar_gain = fit.g_solar * T30_sol / fit.tau_hours
        fig.add_trace(_area(solar_gain.index, solar_gain.values, "goldenrod", "α·I_rad/τ (°C/h)"),
                      row=4, col=1)
    elif not solar.empty:
        fig.add_trace(_area(solar.index, solar.values, "goldenrod", "I_rad (W/m²)"),
                      row=4, col=1)
    fig.update_yaxes(title_text="°C/h", row=4, col=1)

    tau_label = f"τ={fit.tau_hours:.1f}h  g={fit.g_solar:.4f}°C/(W/m²)" if fit else "no fit"
    fig.update_layout(
        height=560,
        margin=dict(l=50, r=20, t=30, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0),
        annotations=[dict(
            text=tau_label, xref="paper", yref="paper",
            x=0.0, y=-0.02, showarrow=False,
            font=dict(size=11), xanchor="left", yanchor="top",
        )],
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

    fit: FitResult | None = None
    try:
        df_fit = prepare(indoor, outdoor, solar)
        if len(df_fit) >= 4:
            fit = fit_thermal(df_fit)
    except Exception:
        pass

    st.plotly_chart(_plot_room(indoor, outdoor, solar, fit),
                    use_container_width=True, key=f"{cfg_path.name}_room")


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
