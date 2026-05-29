"""Streamlit inspector: display configured series, flag >1h gaps.

Run:
    UV_PROJECT_ENVIRONMENT=venv uv run streamlit run miniha/th_models/inspector.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from miniha.th_models.config import discover_configs, load_room_config
from miniha.th_models.flags import MAX_GAP, find_gaps
from miniha.th_models.load import load_room

USER_MODELS_DIR = Path(__file__).resolve().parents[2] / "user_models"


@st.cache_data(show_spinner=False)
def _load_room_cached(config_path: str) -> dict[str, list[tuple[pd.Timestamp, float]]]:
    cfg = load_room_config(config_path)
    series_map = load_room(cfg)
    # Cache-friendly: list of tuples instead of Series.
    return {role: list(zip(s.index, s.values)) for role, s in series_map.items()}


def _to_series(items) -> pd.Series:
    if not items:
        return pd.Series(dtype="float64")
    idx, vals = zip(*items)
    return pd.Series(vals, index=pd.DatetimeIndex(idx))


def _plot_series(role: str, series: pd.Series, gaps) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scattergl(x=series.index, y=series.values, mode="lines", name=role))
    for g in gaps:
        fig.add_vrect(x0=g.start, x1=g.end, fillcolor="red", opacity=0.15, line_width=0)
    fig.update_layout(
        height=300,
        margin=dict(l=40, r=20, t=30, b=30),
        title=role,
        xaxis_title=None,
        yaxis_title=None,
    )
    return fig


def main() -> None:
    st.set_page_config(page_title="th_models inspector", layout="wide")
    st.title("th_models — inspector")

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

        rows = []
        for role, items in cached.items():
            s = _to_series(items)
            gaps = find_gaps(s, MAX_GAP)
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
            st.plotly_chart(_plot_series(role, s, gaps), use_container_width=True)

        st.dataframe(pd.DataFrame(rows), hide_index=True)
        st.divider()


if __name__ == "__main__":
    main()
else:
    main()
