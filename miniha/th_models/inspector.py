"""Streamlit app: inspect series + fit 1R1C model.

Run:
    UV_PROJECT_ENVIRONMENT=venv uv run streamlit run miniha/th_models/inspector.py
"""

from __future__ import annotations

import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from miniha.th_models.config import discover_configs, load_room_config
from miniha.th_models.fit import fit_thermal, prepare, simulate
from miniha.th_models.flags import MAX_GAP, find_gaps
from miniha.th_models.load import load_room
from miniha.th_models.sliding_exp import (
    WindowFit,
    merge_grow,
    resample_series,
    scan,
    to_dataframe,
)

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
                               name="indoor (1R1C)", line=dict(color="black")))
    fig.update_layout(height=320, margin=dict(l=40, r=20, t=30, b=30),
                      title="Observed vs 1R1C", yaxis_title="°C")
    return fig


def _plot_solar(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scattergl(x=df.index, y=df["I_solar"], mode="lines",
                               name="shortwave", line=dict(color="goldenrod")))
    fig.update_layout(height=200, margin=dict(l=40, r=20, t=30, b=30),
                      title="Solar irradiance (horizontal)", yaxis_title="W/m²")
    return fig


def _plot_residual(df: pd.DataFrame, sim: pd.Series) -> go.Figure:
    resid = df["T_in"] - sim
    fig = go.Figure()
    fig.add_trace(go.Scattergl(x=resid.index, y=resid.values, mode="lines",
                               name="obs − model", line=dict(color="gray")))
    fig.add_hline(y=0, line=dict(color="black", width=1))
    fig.update_layout(height=260, margin=dict(l=40, r=20, t=30, b=30),
                      title="Residual (observed − model)", yaxis_title="°C")
    return fig


def _render_fit(cached: dict) -> None:
    needed = {"indoor_temp", "outdoor_temp", "shortwave_radiation"}
    series = {name: _to_series(cached.get(name, [])) for name in needed}
    missing = [name for name, s in series.items() if s.empty]
    if missing:
        st.warning(f"Missing or empty series: {', '.join(f'`{m}`' for m in missing)}.")
        return
    indoor, outdoor, solar = series["indoor_temp"], series["outdoor_temp"], series["shortwave_radiation"]

    df = prepare(indoor, outdoor, solar)
    if len(df) < 4:
        st.warning(f"Not enough aligned samples to fit ({len(df)}).")
        return

    try:
        res = fit_thermal(df)
    except ValueError as e:
        st.error(f"Fit failed: {e}")
        return

    sim = simulate(df, res.tau_hours, res.dT_eq, res.g_solar)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("τ = R·C", f"{res.tau_hours:.2f} ± {res.tau_stderr_hours:.2f} h")
    c2.metric("ΔT_eq (Q₀·R)", f"{res.dT_eq:+.2f} ± {res.dT_eq_stderr:.2f} °C")
    c3.metric("g_solar (a·R)",
              f"{res.g_solar*1000:.2f} ± {res.g_solar_stderr*1000:.2f} m°C·m²/W")
    c4.metric("samples (Δ-pairs)", f"{res.n_samples}")
    c5.metric("step RMSE", f"{res.rmse * 1000:.1f} m°C")

    st.plotly_chart(_plot_in_out(df), use_container_width=True)
    st.plotly_chart(_plot_solar(df), use_container_width=True)
    st.plotly_chart(_plot_obs_vs_model(df, sim), use_container_width=True)
    st.plotly_chart(_plot_residual(df, sim), use_container_width=True)

    _render_model_doc()


@st.cache_data(show_spinner=False)
def _scan_cached(
    config_path: str,
    window_h: float,
    step_min: float,
    resample: str,
) -> pd.DataFrame:
    cached = _load_room_cached(config_path)
    indoor = _to_series(cached.get("indoor_temp", []))
    if indoor.empty:
        return to_dataframe([])
    fits = scan(
        indoor, window_h=window_h, step_min=step_min, resample=resample,
    )
    return to_dataframe(fits)


def _render_decay_scan(config_path: str, cached: dict) -> None:
    indoor = _to_series(cached.get("indoor_temp", []))
    if indoor.empty:
        st.warning("Missing or empty `indoor_temp` series.")
        return

    c1, c2, c3 = st.columns(3)
    window_h = c1.slider("Window length (h)", 1.0, 12.0, 4.0, 0.5)
    step_min = c2.slider("Step (min)", 5, 120, 30, 5)
    resample = c3.selectbox("Resample", ["5min", "10min", "15min"], index=0)

    c4, c5, c6 = st.columns(3)
    r2_min = c4.slider("R² ≥", 0.80, 1.0, 0.98, 0.005)
    tau_lo = c5.number_input("τ min (h)", 0.5, 100.0, 2.0, 0.5)
    tau_hi = c6.number_input("τ max (h)", 0.5, 200.0, 50.0, 1.0)

    c7, c8, c9 = st.columns(3)
    do_merge = c7.checkbox("Greedy-grow merge", value=True)
    tau_log_tol = c8.slider("τ log-tolerance", 0.05, 1.0, 0.2, 0.05)
    Tinf_tol = c9.slider("T∞ tolerance (°C)", 0.1, 5.0, 0.5, 0.1)

    with st.spinner(f"scanning (window={window_h}h, step={step_min}min, resample={resample})…"):
        fits_df = _scan_cached(config_path, window_h, step_min, resample)

    if fits_df.empty:
        st.info("No fits produced. Try a longer window.")
        return

    accepted = fits_df[
        (fits_df["r2"] >= r2_min)
        & (fits_df["tau_h"] >= tau_lo)
        & (fits_df["tau_h"] <= tau_hi)
    ].reset_index(drop=True)

    if do_merge and len(accepted):
        with st.spinner(f"merging {len(accepted)} windows…"):
            fits_in = [
                WindowFit(
                    t_start=row["t_start"], t_end=row["t_end"],
                    tau_h=row["tau_h"], T_inf=row["T_inf"], T_0=row["T_0"],
                    r2=row["r2"], n=int(row["n"]),
                )
                for _, row in accepted.iterrows()
            ]
            resampled = resample_series(indoor, resample)
            merged = merge_grow(
                fits_in, resampled, resample,
                r2_min=r2_min, tau_log_tol=tau_log_tol, Tinf_tol_C=Tinf_tol,
            )
            accepted = to_dataframe(merged)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Windows scanned", f"{len(fits_df)}")
    m2.metric("Accepted", f"{len(accepted)}")
    m3.metric(
        "Median τ (h)",
        f"{accepted['tau_h'].median():.2f}" if len(accepted) else "—",
    )
    m4.metric(
        "Median span (h)",
        f"{((accepted['t_end'] - accepted['t_start']).dt.total_seconds() / 3600).median():.1f}"
        if len(accepted) else "—",
    )

    st.plotly_chart(_plot_decay_overlay(indoor, accepted), use_container_width=True)

    if len(accepted):
        c_l, c_r = st.columns(2)
        with c_l:
            st.plotly_chart(_plot_tau_vs_time(accepted), use_container_width=True)
        with c_r:
            st.plotly_chart(_plot_tau_hist(accepted), use_container_width=True)
        st.dataframe(accepted.head(1000), hide_index=True)
        if len(accepted) > 1000:
            st.caption(f"showing first 1000 of {len(accepted)} accepted windows")


MAX_VRECTS = 400


def _plot_decay_overlay(indoor: pd.Series, accepted: pd.DataFrame) -> go.Figure:
    if len(indoor) > 5000:
        indoor = indoor.iloc[:: len(indoor) // 5000 + 1]
    fig = go.Figure()
    fig.add_trace(
        go.Scattergl(x=indoor.index, y=indoor.values, mode="lines",
                     name="indoor", line=dict(color="royalblue"))
    )
    # Plot accepted windows as one line trace with None separators between
    # segments. Cheaper than N traces or N vrect shapes.
    if len(accepted):
        y_min = float(indoor.min())
        y_band = float(indoor.max() - y_min) * 0.05
        y_bar = y_min - y_band
        xs: list = []
        ys: list = []
        for _, row in accepted.iterrows():
            xs += [row["t_start"], row["t_end"], None]
            ys += [y_bar, y_bar, None]
        fig.add_trace(go.Scattergl(
            x=xs, y=ys, mode="lines",
            line=dict(color="seagreen", width=6),
            name=f"accepted ({len(accepted)})",
            hoverinfo="skip",
        ))
    fig.update_layout(
        height=360, margin=dict(l=40, r=20, t=30, b=30),
        title=f"Indoor temperature · {len(accepted)} accepted windows",
        yaxis_title="°C",
    )
    return fig


def _plot_tau_vs_time(accepted: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scattergl(
            x=accepted["t_start"], y=accepted["tau_h"], mode="markers",
            marker=dict(
                size=7, color=accepted["r2"], colorscale="Viridis",
                cmin=accepted["r2"].min(), cmax=1.0,
                colorbar=dict(title="R²"),
            ),
            name="τ",
        )
    )
    fig.update_layout(
        height=320, margin=dict(l=40, r=20, t=30, b=30),
        title="τ vs window start (color = R²)", yaxis_title="τ (h)",
    )
    return fig


def _plot_tau_hist(accepted: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=accepted["tau_h"], nbinsx=30,
                               marker=dict(color="seagreen")))
    fig.update_layout(
        height=320, margin=dict(l=40, r=20, t=30, b=30),
        title="τ distribution", xaxis_title="τ (h)", yaxis_title="count",
    )
    return fig


def _render_model_doc() -> None:
    with st.expander("Model & fit method"):
        st.markdown("**Continuous-time energy balance** (single zone, lumped capacitance):")
        st.latex(r"C \, \frac{dT_\text{in}}{dt} \;=\; \frac{T_\text{out} - T_\text{in}}{R} \;+\; Q_0 \;+\; a \, I_\text{solar}")
        st.markdown(
            "- $T_\\text{in}, T_\\text{out}$: indoor / outdoor air temperature [°C]\n"
            "- $I_\\text{solar}$: horizontal shortwave irradiance [W/m²]\n"
            "- $R$: thermal resistance envelope ↔ outside [°C / W]\n"
            "- $C$: lumped thermal capacitance of the zone [J / °C]\n"
            "- $Q_0$: constant heat input (internal gains, adjacent-room coupling) [W]\n"
            "- $a$: effective solar aperture (window area × shading × transmittance) [m²]"
        )

        st.markdown("**Discretisation** on a uniform grid of step $\\Delta t$:")
        st.latex(r"\Delta T_\text{in}[k] \;=\; \alpha \, (T_\text{out}[k] - T_\text{in}[k]) \;+\; \beta \;+\; \gamma \, I_\text{solar}[k]")
        st.latex(r"\alpha = \frac{\Delta t}{\tau},\quad \beta = \frac{\Delta t \, Q_0}{C},\quad \gamma = \frac{\Delta t \, a}{C}")
        st.markdown(
            "$R$, $C$, $Q_0$, $a$ are not individually identifiable from temperatures alone "
            "(a common scale is unobservable). The identifiable combinations are:"
        )
        st.latex(r"\tau = R\,C, \quad \Delta T_\text{eq} = Q_0 R = \beta/\alpha, \quad g_\text{solar} = a R = \gamma/\alpha")

        st.markdown(
            "**Fit (current): one-step OLS (equation error).** "
            "Stack the discretised equation over all consecutive sample pairs and solve a linear "
            "least-squares problem for $(\\alpha, \\beta, \\gamma)$:"
        )
        st.latex(r"\min_{\alpha,\beta,\gamma} \sum_k \bigl(\Delta T_\text{in}[k] - \alpha(T_\text{out}[k]-T_\text{in}[k]) - \beta - \gamma I_\text{solar}[k]\bigr)^2")
        st.markdown(
            "Closed-form via `np.linalg.lstsq`. Standard errors come from the residual covariance "
            "$\\sigma^2 (X^\\top X)^{-1}$; propagation to $\\tau, \\Delta T_\\text{eq}, g_\\text{solar}$ "
            "uses the first-order delta method.\n\n"
            "**Caveat.** One-step fits compare predictions one step ahead, anchored on the *observed* "
            "previous value — they do not penalise drift over long horizons. With correlated regressors "
            "(here, outdoor temperature and solar irradiance both peak in the afternoon), the OLS "
            "solution can split heat input between $\\beta$ and $\\gamma$ in physically wrong ways. "
            "Next step is a **simulation-based (output-error) fit**: integrate the discretised ODE forward "
            "and minimise $\\sum (T_\\text{in}^\\text{sim}[k] - T_\\text{in}^\\text{obs}[k])^2$."
        )


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
        cfg_path = st.selectbox(
            "Select a config",
            configs,
            format_func=lambda p: p.name,
        )
        if st.button("Reload data", use_container_width=True):
            _load_room_cached.clear()
            st.rerun()

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
            return

    tab_inspect, tab_fit, tab_decay = st.tabs(["Inspect", "1R1C model", "Decay scan"])
    with tab_inspect:
        _render_inspect(cfg, cached)
    with tab_fit:
        _render_fit(cached)
    with tab_decay:
        _render_decay_scan(str(cfg_path), cached)


if __name__ == "__main__":
    main()
else:
    main()
