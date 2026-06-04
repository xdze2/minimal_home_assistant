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

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from miniha.th_models.config import discover_configs, load_room_config
from miniha.th_models.fit import fit_thermal, prepare, simulate
from miniha.th_models.fit_2r2c import fit_2r2c, simulate_2r2c
from miniha.th_models.flags import MAX_GAP, find_gaps
from miniha.th_models.load import load_room
from miniha.th_models.sliding_exp import (
    WindowFit,
    merge_grow as _old_merge_grow,
    resample_series,
    scan as _old_scan,
    to_dataframe as _old_to_dataframe,
)
from miniha.th_models.sliding.exp_fitter import ExpFitter, ExpFitterConfig
from miniha.th_models.sliding.rc_fitter import RcFitter, RcFitterConfig
from miniha.th_models.sliding.scan import (
    merge_grow as sliding_merge_grow,
    resample_inputs,
    scan as sliding_scan,
    to_dataframe as sliding_to_dataframe,
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
    y_lo = float(min(df["T_in"].min(), df["T_out"].min()))
    y_hi = float(max(df["T_in"].max(), df["T_out"].max()))
    pad = (y_hi - y_lo) * 0.05 or 1.0
    y_lo -= pad
    y_hi += pad
    solar = df["I_solar"].clip(lower=0).to_numpy()
    fig.add_trace(go.Heatmap(
        x=df.index, y=[y_lo, y_hi], z=[solar, solar],
        colorscale=[(0.0, "white"), (1.0, "goldenrod")],
        zmin=0, zmax=max(float(solar.max()), 1.0),
        showscale=True, colorbar=dict(title="W/m²", thickness=10),
        hoverinfo="skip", name="solar",
    ))
    fig.add_trace(go.Scattergl(x=df.index, y=df["T_in"], mode="lines",
                               name="indoor", line=dict(color="royalblue")))
    fig.add_trace(go.Scattergl(x=df.index, y=df["T_out"], mode="lines",
                               name="outdoor", line=dict(color="crimson")))
    tz = "Europe/Paris"
    idx = df.index
    if idx.tz is None:
        local = idx.tz_localize("UTC").tz_convert(tz)
    else:
        local = idx.tz_convert(tz)
    start_day = local.min().normalize()
    end_day = local.max().normalize() + pd.Timedelta(days=1)
    midnights = pd.date_range(start_day, end_day, freq="D", tz=tz)
    for ts in midnights:
        fig.add_vline(x=ts, line=dict(color="black", width=1))
    fig.update_layout(height=320, margin=dict(l=40, r=20, t=30, b=30),
                      title="Indoor vs outdoor", yaxis_title="°C",
                      yaxis=dict(range=[y_lo, y_hi]))
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


def _render_fit(cfg, cached: dict) -> None:
    needed = {"indoor_temp", "outdoor_temp", "shortwave_radiation"}
    series = {name: _to_series(cached.get(name, [])) for name in needed}
    missing = [name for name, s in series.items() if s.empty]
    if missing:
        st.warning(f"Missing or empty series: {', '.join(f'`{m}`' for m in missing)}.")
        return
    indoor, outdoor, solar = series["indoor_temp"], series["outdoor_temp"], series["shortwave_radiation"]

    # Window selector — defaults to the full config window.
    full_start = cfg.window.start.date()
    full_end = cfg.window.end.date()
    total_days = max((full_end - full_start).days, 1)
    DURATION_OPTIONS = [1, 2, 3, 7, 14, 30, 60, 90, 180, 365]
    default_duration = next((d for d in DURATION_OPTIONS if d >= total_days), DURATION_OPTIONS[-1])

    c_start, c_dur = st.columns(2)
    win_start = c_start.date_input("Start date", value=full_start,
                                   min_value=full_start, max_value=full_end,
                                   key="fit1r1c_start")
    duration_days = c_dur.selectbox("Window size", DURATION_OPTIONS,
                                    index=DURATION_OPTIONS.index(default_duration),
                                    format_func=lambda d: f"{d} day" if d == 1 else f"{d} days",
                                    key="fit1r1c_dur")
    win_end = win_start + pd.Timedelta(days=duration_days)

    def _slice_series(s: pd.Series) -> pd.Series:
        if s.empty:
            return s
        t0 = pd.Timestamp(win_start)
        t1 = pd.Timestamp(win_end)
        if s.index.tz is not None:
            t0 = t0.tz_localize(s.index.tz)
            t1 = t1.tz_localize(s.index.tz)
        return s[(s.index >= t0) & (s.index < t1)]

    indoor = _slice_series(indoor)
    outdoor = _slice_series(outdoor)
    solar = _slice_series(solar)

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

    st.plotly_chart(_plot_in_out(df), use_container_width=True, key="1r1c_in_out")
    st.plotly_chart(_plot_solar(df), use_container_width=True, key="1r1c_solar")
    st.plotly_chart(_plot_obs_vs_model(df, sim), use_container_width=True, key="1r1c_obs_vs_model")
    st.plotly_chart(_plot_residual(df, sim), use_container_width=True, key="1r1c_residual")

    _render_model_doc()


@st.cache_data(show_spinner=False)
def _scan_cached(
    config_path: str,
    fitter_name: str,
    window_h: float,
    step_min: float,
    resample: str,
    tau_prior_val: float = 8.0,
    tau_prior_sigma: float = 4.0,
) -> pd.DataFrame:
    cached = _load_room_cached(config_path)
    indoor = _to_series(cached.get("indoor_temp", []))
    if indoor.empty:
        return sliding_to_dataframe([])

    if fitter_name == "1R1C (T_out + solar)":
        outdoor = _to_series(cached.get("outdoor_temp", []))
        solar = _to_series(cached.get("shortwave_radiation", []))
        inputs = {"T_in": indoor, "T_out": outdoor, "shortwave_radiation": solar}
        rc_cfg = RcFitterConfig()
        rc_cfg.tau_prior.value = tau_prior_val
        rc_cfg.tau_prior.sigma = tau_prior_sigma
        fitter = RcFitter(rc_cfg)
    else:
        inputs = {"T_in": indoor}
        fitter = ExpFitter()

    results = sliding_scan(inputs, fitter, window_h=window_h, step_min=step_min, resample=resample)
    return sliding_to_dataframe(results)


def _render_decay_scan(config_path: str, cached: dict) -> None:
    indoor = _to_series(cached.get("indoor_temp", []))
    if indoor.empty:
        st.warning("Missing or empty `indoor_temp` series.")
        return

    fitter_name = st.selectbox(
        "Fitter",
        ["Exponential (free decay)", "1R1C (T_out + solar)"],
        index=0,
    )
    is_rc = fitter_name == "1R1C (T_out + solar)"

    RESAMPLE = "15min"
    WINDOW_OPTIONS = [2, 3, 4, 6, 8, 12, 18, 24, 36, 48, 72, 120, 168]  # hours, log-ish spacing
    STEP_FRACS = [2, 4, 8, 16, 24]  # step = window / denom

    c1, c2 = st.columns(2)
    window_h = c1.selectbox(
        "Window length (h)",
        WINDOW_OPTIONS,
        index=WINDOW_OPTIONS.index(12),
        format_func=lambda h: f"{h}h" if h < 24 else f"{h//24}d{h%24:02d}h" if h % 24 else f"{h//24}d",
    )
    step_denom = c2.selectbox(
        "Step (fraction of window)",
        STEP_FRACS,
        index=STEP_FRACS.index(8),
        format_func=lambda d: f"1/{d}  ({window_h * 60 // d}min)",
    )
    step_min = max(15, window_h * 60 // step_denom)

    c4, c5, c6 = st.columns(3)
    # For RcFitter quality = -RMSE; use a large negative default to pass all windows.
    if is_rc:
        r2_min = c4.slider("Quality ≥ (−RMSE)", -2.0, 0.0, -0.5, 0.05)
    else:
        r2_min = c4.slider("R² ≥", 0.80, 1.0, 0.98, 0.005)
    tau_lo = c5.number_input("τ min (h)", 0.5, 100.0, 2.0, 0.5)
    tau_hi = c6.number_input("τ max (h)", 0.5, 200.0, 50.0, 1.0)

    c7, c8, c9 = st.columns(3)
    do_merge = c7.checkbox("Greedy-grow merge", value=True)
    show_rejected = c8.checkbox("Show rejected fits", value=False)
    tau_log_tol = c9.slider("τ log-tolerance", 0.05, 1.0, 0.2, 0.05)

    _default_rc = RcFitterConfig()
    if is_rc:
        c9, c10 = st.columns(2)
        tau_prior_val = c9.number_input("τ prior (h)", 1.0, 50.0, float(_default_rc.tau_prior.value), 0.5)
        tau_prior_sigma = c10.number_input("τ prior σ (h)", 0.5, 20.0, float(_default_rc.tau_prior.sigma), 0.5)
        rc_cfg = RcFitterConfig(tau_log_tol=tau_log_tol)
        rc_cfg.tau_prior.value = tau_prior_val
        rc_cfg.tau_prior.sigma = tau_prior_sigma
        fitter_for_merge = RcFitter(rc_cfg)
    else:
        tau_prior_val = _default_rc.tau_prior.value
        tau_prior_sigma = _default_rc.tau_prior.sigma
        exp_cfg = ExpFitterConfig(tau_log_tol=tau_log_tol)
        fitter_for_merge = ExpFitter(exp_cfg)

    resample = RESAMPLE
    with st.spinner(f"scanning (window={window_h}h, step={step_min}min, resample={resample})…"):
        fits_df = _scan_cached(
            config_path, fitter_name, window_h, step_min, resample,
            tau_prior_val=tau_prior_val, tau_prior_sigma=tau_prior_sigma,
        )

    if fits_df.empty:
        st.info("No fits produced. Try a longer window.")
        return

    accepted = fits_df[
        (fits_df["quality"] >= r2_min)
        & (fits_df["tau_h"] >= tau_lo)
        & (fits_df["tau_h"] <= tau_hi)
    ].reset_index(drop=True)

    if do_merge and len(accepted):
        outdoor = _to_series(cached.get("outdoor_temp", []))
        solar = _to_series(cached.get("shortwave_radiation", []))
        if is_rc:
            inputs = {"T_in": indoor, "T_out": outdoor, "shortwave_radiation": solar}
        else:
            inputs = {"T_in": indoor}
        with st.spinner(f"merging {len(accepted)} windows…"):
            from miniha.th_models.sliding.protocol import WindowResult as _WR
            seeds = []
            for _, row in accepted.iterrows():
                wr = _WR(
                    t_start=row["t_start"], t_end=row["t_end"],
                    params={k: row[k] for k in row.index if k not in ("t_start", "t_end", "quality", "n")},
                    quality=row["quality"], n=int(row["n"]),
                )
                seeds.append(wr)
            merged = sliding_merge_grow(
                seeds, inputs, fitter_for_merge, resample, quality_min=r2_min,
            )
            accepted = sliding_to_dataframe(merged)

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

    outdoor = _to_series(cached.get("outdoor_temp", []))
    solar = _to_series(cached.get("shortwave_radiation", []))
    rejected_mask = ~(
        (fits_df["quality"] >= r2_min)
        & (fits_df["tau_h"] >= tau_lo)
        & (fits_df["tau_h"] <= tau_hi)
    )
    rejected = fits_df[rejected_mask].reset_index(drop=True) if show_rejected else pd.DataFrame()
    st.plotly_chart(
        _plot_decay_overlay(
            indoor, accepted,
            outdoor=outdoor if is_rc else None,
            solar=solar if is_rc else None,
            rejected=rejected if show_rejected else None,
        ),
        use_container_width=True,
    )

    if len(accepted):
        c_l, c_r = st.columns(2)
        with c_l:
            st.plotly_chart(_plot_tau_vs_time(accepted), use_container_width=True)
        with c_r:
            st.plotly_chart(_plot_tau_hist(accepted), use_container_width=True)

        if not is_rc and "T_inf" in accepted.columns:
            c_l2, c_r2 = st.columns(2)
            with c_l2:
                st.plotly_chart(_plot_tau_tinf_scatter(accepted), use_container_width=True)
            with c_r2:
                st.plotly_chart(_plot_tinf_vs_solar(accepted, outdoor, solar), use_container_width=True)

        st.dataframe(accepted.head(1000), hide_index=True)
        if len(accepted) > 1000:
            st.caption(f"showing first 1000 of {len(accepted)} accepted windows")


MAX_VRECTS = 400


def _rc_sim_segment(
    row: pd.Series,
    indoor: pd.Series,
    outdoor: pd.Series,
    solar: pd.Series,
    resample: str = "5min",
) -> tuple[list, list]:
    """Forward-simulate 1R1C for one accepted segment; return (xs, ys) lists."""
    t_start, t_end = row["t_start"], row["t_end"]
    mask_in = (indoor.index >= t_start) & (indoor.index <= t_end)
    mask_out = (outdoor.index >= t_start) & (outdoor.index <= t_end)
    mask_sol = (solar.index >= t_start) & (solar.index <= t_end)
    t_in_seg = indoor[mask_in]
    t_out_seg = outdoor[mask_out]
    sol_seg = solar[mask_sol]

    grid_sec = pd.Timedelta(resample).total_seconds()
    alpha = grid_sec / (row["tau_h"] * 3600.0)
    dT_eq = row["dT_eq"]
    g_solar = row["g_solar"]

    # Resample all inputs to the uniform grid over this segment.
    inputs = resample_inputs(
        {"T_in": t_in_seg, "T_out": t_out_seg, "shortwave_radiation": sol_seg}, resample
    )
    if not inputs or "T_out" not in inputs or inputs["T_out"].empty:
        return [], []

    T_out_arr = inputs["T_out"].to_numpy()
    sol_arr = inputs.get("shortwave_radiation", pd.Series(dtype=float)).reindex(inputs["T_out"].index).fillna(0.0).to_numpy()
    idx = inputs["T_out"].index

    sim = np.empty(len(T_out_arr))
    # Use actual indoor temperature at t_start as initial condition.
    if "T_in" in inputs and not inputs["T_in"].empty:
        sim[0] = float(inputs["T_in"].iloc[0])
    else:
        sim[0] = float(T_out_arr[0]) + dT_eq
    for k in range(len(T_out_arr) - 1):
        sim[k + 1] = sim[k] + alpha * (T_out_arr[k] - sim[k] + dT_eq + g_solar * max(sol_arr[k], 0.0))

    xs = list(idx) + [None]
    ys = list(sim) + [None]
    return xs, ys


def _plot_decay_overlay(
    indoor: pd.Series,
    accepted: pd.DataFrame,
    outdoor: pd.Series | None = None,
    solar: pd.Series | None = None,
    resample: str = "5min",
    rejected: pd.DataFrame | None = None,
) -> go.Figure:
    if len(indoor) > 5000:
        indoor = indoor.iloc[:: len(indoor) // 5000 + 1]
    fig = go.Figure()
    fig.add_trace(
        go.Scattergl(x=indoor.index, y=indoor.values, mode="lines",
                     name="indoor", line=dict(color="royalblue"))
    )
    y_min = float(indoor.min())
    y_band = float(indoor.max() - y_min) * 0.05
    y_bar = y_min - y_band
    y_bar_rejected = y_bar - y_band

    if len(accepted):
        fit_xs: list = []
        fit_ys: list = []
        is_rc = "dT_eq" in accepted.columns and outdoor is not None

        for _, row in accepted.iterrows():
            if is_rc:
                xs, ys = _rc_sim_segment(row, indoor, outdoor, solar, resample)
                fit_xs += xs
                fit_ys += ys
            else:
                # Exponential curve from stored params.
                t_start = row["t_start"]
                t_end = row["t_end"]
                tau_s = row["tau_h"] * 3600.0
                T_inf = row["T_inf"]
                T_0 = row["T_0"]
                n_pts = max(int((t_end - t_start).total_seconds() / 60), 2)
                t_rel = np.linspace(0.0, (t_end - t_start).total_seconds(), n_pts)
                ts = [t_start + pd.Timedelta(seconds=s) for s in t_rel]
                ys = (T_0 - T_inf) * np.exp(-t_rel / tau_s) + T_inf
                fit_xs += ts + [None]
                fit_ys += list(ys) + [None]

        label = "1R1C sim" if is_rc else "exp fit"
        fig.add_trace(go.Scattergl(
            x=fit_xs, y=fit_ys, mode="lines",
            line=dict(color="tomato", width=4),
            opacity=0.55,
            name=label,
            hoverinfo="skip",
        ))

        xs_bar: list = []
        ys_bar: list = []
        for _, row in accepted.iterrows():
            xs_bar += [row["t_start"], row["t_end"], None]
            ys_bar += [y_bar, y_bar, None]
        fig.add_trace(go.Scattergl(
            x=xs_bar, y=ys_bar, mode="lines",
            line=dict(color="seagreen", width=6),
            name=f"accepted ({len(accepted)})",
            hoverinfo="skip",
        ))

    if rejected is not None and len(rejected):
        xs_rej: list = []
        ys_rej: list = []
        for _, row in rejected.iterrows():
            xs_rej += [row["t_start"], row["t_end"], None]
            ys_rej += [y_bar_rejected, y_bar_rejected, None]
        fig.add_trace(go.Scattergl(
            x=xs_rej, y=ys_rej, mode="lines",
            line=dict(color="lightcoral", width=3),
            opacity=0.5,
            name=f"rejected ({len(rejected)})",
            hoverinfo="skip",
        ))
    has_rejected = rejected is not None and len(rejected)
    y_axis_min = y_bar_rejected - y_band if has_rejected else y_bar - y_band
    fig.update_layout(
        height=360, margin=dict(l=40, r=20, t=30, b=30),
        title=f"Indoor temperature · {len(accepted)} accepted windows",
        yaxis_title="°C",
        yaxis=dict(range=[y_axis_min, float(indoor.max()) + y_band]),
    )
    return fig


def _plot_tau_vs_time(accepted: pd.DataFrame) -> go.Figure:
    color_col = "r2" if "r2" in accepted.columns else "quality"
    color_vals = accepted[color_col]
    fig = go.Figure()
    fig.add_trace(
        go.Scattergl(
            x=accepted["t_start"], y=accepted["tau_h"], mode="markers",
            marker=dict(
                size=7, color=color_vals, colorscale="Viridis",
                cmin=float(color_vals.min()), cmax=float(color_vals.max()),
                colorbar=dict(title=color_col),
            ),
            name="τ",
        )
    )
    fig.update_layout(
        height=320, margin=dict(l=40, r=20, t=30, b=30),
        title=f"τ vs window start (color = {color_col})", yaxis_title="τ (h)",
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


def _plot_tinf_vs_solar(accepted: pd.DataFrame, outdoor: pd.Series, solar: pd.Series) -> go.Figure:
    """T∞ − T_out vs mean solar irradiance per segment. Each dot = one decay event."""
    rows = []
    for _, seg in accepted.iterrows():
        mask_out = (outdoor.index >= seg["t_start"]) & (outdoor.index <= seg["t_end"])
        mask_sol = (solar.index >= seg["t_start"]) & (solar.index <= seg["t_end"])
        T_out_mean = float(outdoor[mask_out].mean()) if mask_out.any() else float("nan")
        I_mean = float(solar[mask_sol].mean()) if mask_sol.any() else float("nan")
        rows.append({"dT": seg["T_inf"] - T_out_mean, "I_solar": I_mean, "tau_h": seg["tau_h"]})
    df = pd.DataFrame(rows).dropna()
    if df.empty:
        fig = go.Figure()
        fig.update_layout(title="T∞ − T_out vs solar (no outdoor/solar data)", height=320)
        return fig

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["I_solar"], y=df["dT"], mode="markers",
        marker=dict(
            size=9, color=df["tau_h"], colorscale="Plasma",
            colorbar=dict(title="τ (h)"), opacity=0.8,
        ),
        text=[f"τ={r.tau_h:.1f}h" for r in df.itertuples()],
        hovertemplate="I=%{x:.0f} W/m²<br>ΔT=%{y:.2f}°C<br>%{text}<extra></extra>",
        name="segments",
    ))
    # Simple OLS trendline
    if len(df) >= 3:
        x = df["I_solar"].to_numpy()
        y = df["dT"].to_numpy()
        A = np.column_stack([np.ones_like(x), x])
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        x_line = np.array([x.min(), x.max()])
        fig.add_trace(go.Scatter(
            x=x_line, y=coef[0] + coef[1] * x_line, mode="lines",
            line=dict(color="tomato", dash="dash", width=2),
            name=f"OLS  slope={coef[1]*1000:.2f} °C/(W/m²)·10³",
        ))
    fig.update_layout(
        height=340, margin=dict(l=40, r=20, t=40, b=40),
        title="T∞ − T_out vs mean solar irradiance (color = τ)",
        xaxis_title="mean I_solar over segment (W/m²)",
        yaxis_title="T∞ − T_out (°C)",
    )
    return fig


def _plot_tau_tinf_scatter(accepted: pd.DataFrame) -> go.Figure:
    """(τ, T∞) scatter — tight cloud = single regime; bimodal = multiple states."""
    color_col = "r2" if "r2" in accepted.columns else "quality"
    color_vals = accepted[color_col]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=accepted["tau_h"], y=accepted["T_inf"], mode="markers",
        marker=dict(
            size=8, color=color_vals, colorscale="Viridis",
            cmin=float(color_vals.min()), cmax=float(color_vals.max()),
            colorbar=dict(title=color_col), opacity=0.8,
        ),
        text=[f"{color_col}={r:.3f}" for r in color_vals],
        hovertemplate="τ=%{x:.1f}h<br>T∞=%{y:.2f}°C<br>%{text}<extra></extra>",
        name="segments",
    ))
    fig.update_layout(
        height=340, margin=dict(l=40, r=20, t=40, b=40),
        title="(τ, T∞) scatter — cloud shape diagnoses regime stability",
        xaxis_title="τ (h)", yaxis_title="T∞ (°C)",
    )
    return fig


def _plot_obs_vs_model_2r2c(df: pd.DataFrame, sim: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scattergl(x=df.index, y=df["T_in"], mode="lines",
                               name="indoor (obs)", line=dict(color="royalblue")))
    fig.add_trace(go.Scattergl(x=sim.index, y=sim["T_in_model"], mode="lines",
                               name="indoor (2R2C)", line=dict(color="black")))
    fig.add_trace(go.Scattergl(x=sim.index, y=sim["T_wall_model"], mode="lines",
                               name="wall (latent)", line=dict(color="darkorange", dash="dot")))
    fig.update_layout(height=320, margin=dict(l=40, r=20, t=30, b=30),
                      title="Observed vs 2R2C", yaxis_title="°C")
    return fig


def _render_fit_2r2c(cached: dict) -> None:
    needed = {"indoor_temp", "outdoor_temp", "shortwave_radiation"}
    series = {name: _to_series(cached.get(name, [])) for name in needed}
    missing = [name for name, s in series.items() if s.empty]
    if missing:
        st.warning(f"Missing or empty series: {', '.join(f'`{m}`' for m in missing)}.")
        return
    indoor, outdoor, solar = series["indoor_temp"], series["outdoor_temp"], series["shortwave_radiation"]

    df = prepare(indoor, outdoor, solar)
    if len(df) < 8:
        st.warning(f"Not enough aligned samples to fit ({len(df)}).")
        return

    try:
        warm_res = fit_thermal(df)
        warm = (warm_res.tau_hours, warm_res.dT_eq, warm_res.g_solar)
    except ValueError:
        warm = None

    with st.spinner("Fitting 2R2C (output-error NLS)…"):
        try:
            res = fit_2r2c(df, warm=warm)
        except ValueError as e:
            st.error(f"Fit failed: {e}")
            return

    if not res.success:
        st.warning(f"Optimiser did not fully converge: {res.message}")

    sim = simulate_2r2c(df, res)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("τ_fast", f"{res.tau_fast_h:.2f} h")
    c2.metric("τ_slow", f"{res.tau_slow_h:.2f} h")
    c3.metric("ΔT_eq (Q₀)", f"{res.dT_eq:+.2f} °C")
    c4.metric("g_solar", f"{res.g_solar * 1000:.2f} m°C·m²/W")
    c5.metric("trajectory RMSE", f"{res.rmse:.3f} °C")

    st.plotly_chart(_plot_in_out(df), use_container_width=True, key="2r2c_in_out")
    st.plotly_chart(_plot_solar(df), use_container_width=True, key="2r2c_solar")
    st.plotly_chart(_plot_obs_vs_model_2r2c(df, sim), use_container_width=True, key="2r2c_obs_vs_model")
    st.plotly_chart(_plot_residual(df, sim["T_in_model"]), use_container_width=True, key="2r2c_residual")

    with st.expander("Raw fitted parameters (R, C in arbitrary gauge — see model doc)"):
        st.write({
            "R_int (K/W)":  res.R_int,
            "R_ext (K/W)":  res.R_ext,
            "C_in (J/K)":   res.C_in,
            "C_wall (J/K)": res.C_wall,
            "Q0 (W)":       res.Q0,
            "a_in (m²)":    res.a_in,
            "a_wall (m²)":  res.a_wall,
            "T_wall(0) (°C)": res.T_wall0,
            "n_samples":    res.n_samples,
            "optimiser_success": res.success,
            "optimiser_message": res.message,
        })

    _render_model_doc_2r2c()


def _render_model_doc_2r2c() -> None:
    with st.expander("2R2C model & fit method"):
        st.markdown(
            "**Two-node lumped model.** Air node `T_in` (observed) coupled to "
            "a wall/mass node `T_wall` (latent). Solar gain splits between the "
            "two nodes (instant on air, lagged via the mass)."
        )
        st.latex(
            r"C_\text{in} \, \dot{T}_\text{in} \;=\; "
            r"\frac{T_\text{wall} - T_\text{in}}{R_\text{int}} \;+\; Q_0 \;+\; a_\text{in} I_\text{solar}"
        )
        st.latex(
            r"C_\text{wall} \, \dot{T}_\text{wall} \;=\; "
            r"\frac{T_\text{in} - T_\text{wall}}{R_\text{int}} \;+\; "
            r"\frac{T_\text{out} - T_\text{wall}}{R_\text{ext}} \;+\; a_\text{wall} I_\text{solar}"
        )
        st.markdown(
            "Two real eigenvalues of $A$ → two time constants: $\\tau_\\text{fast}$ "
            "(air mode) and $\\tau_\\text{slow}$ (mass mode). The 1R1C $\\tau$ is "
            "a weighted average; here they're separated.\n\n"
            "**Fit: output-error NLS.** Integrate the linear system forward with "
            "ZOH (matrix exponential), minimise $\\sum_k (T_\\text{in}^\\text{sim}[k] - T_\\text{in}^\\text{obs}[k])^2$ "
            "with `scipy.optimize.least_squares` (TRF). Log-parameterisation on "
            "$R_\\text{int}, R_\\text{ext}, C_\\text{in}, C_\\text{wall}$ for positivity. "
            "Warm-started from the 1R1C OLS fit on the same data; $T_\\text{wall}(0)$ "
            "is co-fit, $T_\\text{in}(0)$ pinned to the observation.\n\n"
            "**Gauge note.** Individual $R$, $C$, $Q_0$, $a$ values share an "
            "unobservable scale (same identifiability issue as 1R1C, doubled). "
            "Reported $\\tau_\\text{fast}, \\tau_\\text{slow}, \\Delta T_\\text{eq}, g_\\text{solar}$ "
            "are the scale-free quantities."
        )


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

    tab_inspect, tab_fit, tab_fit_2r2c, tab_decay = st.tabs(
        ["Inspect", "1R1C model", "2R2C model", "Decay scan"]
    )
    with tab_inspect:
        _render_inspect(cfg, cached)
    with tab_fit:
        _render_fit(cfg, cached)
    with tab_fit_2r2c:
        _render_fit_2r2c(cached)
    with tab_decay:
        _render_decay_scan(str(cfg_path), cached)


if __name__ == "__main__":
    main()
else:
    main()
