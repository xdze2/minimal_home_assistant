"""Streamlit app: inspect series + fit 1R1C model.

Run:
    UV_PROJECT_ENVIRONMENT=venv uv run streamlit run miniha/th_models/inspector.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from miniha.th_models.config import discover_configs, load_room_config
from miniha.th_models.fit import fit_1r1c, prepare, simulate
from miniha.th_models.flags import MAX_GAP, find_gaps
from miniha.th_models.load import load_room

USER_MODELS_DIR = Path(__file__).resolve().parents[2] / "user_models"


@st.cache_data(show_spinner=False)
def _load_room_cached(config_path: str) -> dict[str, list[tuple[pd.Timestamp, float]]]:
    cfg = load_room_config(config_path)
    series_map = load_room(cfg)
    return {role: list(zip(s.index, s.values)) for role, s in series_map.items()}


def _to_series(items) -> pd.Series:
    if not items:
        return pd.Series(dtype="float64")
    idx, vals = zip(*items)
    return pd.Series(vals, index=pd.DatetimeIndex(idx))


def _plot_one_series(role: str, series: pd.Series, gaps) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scattergl(x=series.index, y=series.values, mode="lines", name=role))
    for g in gaps:
        fig.add_vrect(x0=g.start, x1=g.end, fillcolor="red", opacity=0.15, line_width=0)
    fig.update_layout(
        height=300,
        margin=dict(l=40, r=20, t=30, b=30),
        title=role,
    )
    return fig


def _render_inspect(cfg, cached: dict) -> None:
    rows = []
    for role, items in cached.items():
        s = _to_series(items)
        gaps = find_gaps(s, MAX_GAP, window_start=cfg.window.start, window_end=cfg.window.end)
        rows.append(
            {
                "role": role,
                "n": int(len(s)),
                "nan": int(s.isna().sum()) if len(s) else 0,
                "min": float(s.min()) if len(s) else None,
                "max": float(s.max()) if len(s) else None,
                "gaps>1h": len(gaps),
            }
        )
        st.plotly_chart(_plot_one_series(role, s, gaps), use_container_width=True)
    st.dataframe(pd.DataFrame(rows), hide_index=True)


def _plot_in_out(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scattergl(x=df.index, y=df["T_in"], mode="lines",
                               name="indoor", line=dict(color="royalblue")))
    fig.add_trace(go.Scattergl(x=df.index, y=df["T_out"], mode="lines",
                               name="outdoor", line=dict(color="crimson")))
    fig.update_layout(height=320, margin=dict(l=40, r=20, t=30, b=30),
                      title="Indoor vs outdoor", yaxis_title="°C")
    return fig


def _plot_obs_vs_model(df: pd.DataFrame, sim: pd.Series) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scattergl(x=df.index, y=df["T_in"], mode="lines",
                               name="indoor (obs)", line=dict(color="royalblue")))
    fig.add_trace(go.Scattergl(x=sim.index, y=sim.values, mode="lines",
                               name="indoor (1R1C)", line=dict(color="orange", dash="dot")))
    fig.update_layout(height=320, margin=dict(l=40, r=20, t=30, b=30),
                      title="Observed vs 1R1C", yaxis_title="°C")
    return fig


def _plot_residual(df: pd.DataFrame, sim: pd.Series) -> go.Figure:
    resid = sim - df["T_in"]
    fig = go.Figure()
    fig.add_trace(go.Scattergl(x=resid.index, y=resid.values, mode="lines",
                               name="model − obs", line=dict(color="gray")))
    fig.add_hline(y=0, line=dict(color="black", width=1))
    fig.update_layout(height=260, margin=dict(l=40, r=20, t=30, b=30),
                      title="Residual (model − observed)", yaxis_title="°C")
    return fig


def _render_fit(cached: dict) -> None:
    indoor = _to_series(cached.get("indoor_temp", []))
    outdoor = _to_series(cached.get("outdoor_temp", []))
    if indoor.empty or outdoor.empty:
        st.warning("Need both `indoor_temp` and `outdoor_temp` series.")
        return

    df = prepare(indoor, outdoor)
    if len(df) < 3:
        st.warning(f"Not enough aligned samples to fit ({len(df)}).")
        return

    try:
        res = fit_1r1c(df)
    except ValueError as e:
        st.error(f"Fit failed: {e}")
        return

    sim = simulate(df, res.tau_hours)

    c1, c2, c3 = st.columns(3)
    c1.metric("τ = R·C", f"{res.tau_hours:.2f} h", f"± {res.tau_stderr_hours:.2f} h")
    c2.metric("samples (Δ-pairs)", f"{res.n_samples}")
    c3.metric("step RMSE", f"{res.rmse * 1000:.1f} m°C")

    st.plotly_chart(_plot_in_out(df), use_container_width=True)
    st.plotly_chart(_plot_obs_vs_model(df, sim), use_container_width=True)
    st.plotly_chart(_plot_residual(df, sim), use_container_width=True)


def main() -> None:
    st.set_page_config(page_title="th_models", layout="wide")
    st.title("th_models")

    configs = discover_configs(USER_MODELS_DIR)

    with st.sidebar:
        st.header("Configs")
        st.caption(f"Directory: `{USER_MODELS_DIR}`")
        if not configs:
            st.warning("No YAML files in user_models/")
            return
        for p in configs:
            st.write(f"- `{p.name}`")

    for cfg_path in configs:
        cfg = load_room_config(cfg_path)
        st.header(f"Room: {cfg.room}")
        st.caption(
            f"`{cfg_path.name}` · window "
            f"{cfg.window.start.isoformat()} → {cfg.window.end.isoformat()}"
        )

        with st.spinner(f"Loading {cfg.room}…"):
            try:
                cached = _load_room_cached(str(cfg_path))
            except Exception as e:
                st.error(f"Load failed: {e}")
                continue

        tab_inspect, tab_fit = st.tabs(["Inspect", "1R1C fit"])
        with tab_inspect:
            _render_inspect(cfg, cached)
        with tab_fit:
            _render_fit(cached)

        st.divider()


if __name__ == "__main__":
    main()
else:
    main()
