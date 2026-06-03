"""Tests for generic scan() and merge_grow().

Uses synthetic pd.Series built from known models so results are predictable.
Tests are fitter-agnostic where possible; they verify the scan/merge
machinery, not the physics.
"""

import numpy as np
import pandas as pd
import pytest

from miniha.th_models.sliding.exp_fitter import ExpFitter, ExpFitterConfig
from miniha.th_models.sliding.rc_fitter import RcFitter
from miniha.th_models.sliding.scan import merge_grow, resample_inputs, scan, to_dataframe


# --- Helpers ------------------------------------------------------------------

def make_exp_series(
    tau_h: float = 6.0,
    T_inf: float = 14.0,
    T_0: float = 20.0,
    n: int = 200,
    dt_min: float = 5.0,
    t0: pd.Timestamp | None = None,
) -> pd.Series:
    if t0 is None:
        t0 = pd.Timestamp("2026-01-01")
    idx = pd.date_range(t0, periods=n, freq=f"{int(dt_min)}min")
    t_sec = np.arange(n) * dt_min * 60.0
    y = (T_0 - T_inf) * np.exp(-t_sec / (tau_h * 3600.0)) + T_inf
    return pd.Series(y, index=idx)


def make_1r1c_series(
    tau_h: float = 8.0,
    dT_eq: float = 2.0,
    g_solar: float = 0.005,
    n: int = 200,
    dt_min: float = 15.0,
    t0: pd.Timestamp | None = None,
    seed: int = 0,
) -> dict[str, pd.Series]:
    if t0 is None:
        t0 = pd.Timestamp("2026-01-01")
    rng = np.random.default_rng(seed)
    idx = pd.date_range(t0, periods=n, freq=f"{int(dt_min)}min")
    dt_s = dt_min * 60.0
    T_out = 5.0 + rng.normal(0, 0.3, n)
    I_solar = np.clip(100.0 + rng.normal(0, 10, n), 0, None)
    alpha = dt_s / (tau_h * 3600.0)
    T_in = np.empty(n)
    T_in[0] = 15.0
    for k in range(n - 1):
        T_in[k + 1] = T_in[k] + alpha * (T_out[k] - T_in[k] + dT_eq + g_solar * I_solar[k])
    return {
        "T_in": pd.Series(T_in, index=idx),
        "T_out": pd.Series(T_out, index=idx),
        "shortwave_radiation": pd.Series(I_solar, index=idx),
    }


# --- resample_inputs ----------------------------------------------------------

class TestResampleInputs:
    def test_returns_aligned_series(self):
        s = make_exp_series()
        result = resample_inputs({"T_in": s}, "5min")
        assert "T_in" in result
        assert not result["T_in"].empty

    def test_multiple_series_same_index(self):
        s1 = make_exp_series()
        s2 = make_exp_series(T_0=10.0)
        result = resample_inputs({"T_in": s1, "T_out": s2}, "5min")
        assert result["T_in"].index.equals(result["T_out"].index)

    def test_empty_series_returns_empty(self):
        result = resample_inputs({"T_in": pd.Series(dtype=float)}, "5min")
        assert result["T_in"].empty


# --- scan ---------------------------------------------------------------------

class TestScanExpFitter:
    def test_finds_results_on_clean_decay(self):
        s = make_exp_series(tau_h=6.0, n=200)
        fitter = ExpFitter()
        results = scan({"T_in": s}, fitter, window_h=4.0, step_min=30.0)
        assert len(results) > 0

    def test_results_have_valid_timestamps(self):
        s = make_exp_series(tau_h=6.0, n=200)
        fitter = ExpFitter()
        results = scan({"T_in": s}, fitter, window_h=4.0, step_min=30.0)
        for r in results:
            assert r.t_start is not pd.NaT
            assert r.t_end is not pd.NaT
            assert r.t_start < r.t_end

    def test_results_within_input_range(self):
        s = make_exp_series(tau_h=6.0, n=200)
        fitter = ExpFitter()
        results = scan({"T_in": s}, fitter, window_h=4.0, step_min=30.0)
        for r in results:
            assert r.t_start >= s.index[0]
            assert r.t_end <= s.index[-1]

    def test_empty_series_returns_empty(self):
        fitter = ExpFitter()
        results = scan({"T_in": pd.Series(dtype=float)}, fitter, window_h=4.0, step_min=30.0)
        assert results == []

    def test_no_decay_returns_few_results(self):
        # A rising signal should produce very few (ideally zero) accepted windows.
        idx = pd.date_range("2026-01-01", periods=200, freq="5min")
        y = np.linspace(14.0, 20.0, 200)
        s = pd.Series(y, index=idx)
        fitter = ExpFitter()
        results = scan({"T_in": s}, fitter, window_h=4.0, step_min=30.0)
        assert len(results) == 0


class TestScanRcFitter:
    def test_finds_results_on_1r1c_data(self):
        series = make_1r1c_series(n=200)
        fitter = RcFitter()
        results = scan(series, fitter, window_h=8.0, step_min=60.0, resample="15min")
        assert len(results) > 0

    def test_passes_all_inputs_to_fitter(self):
        """RcFitter needs T_out; scan should pass it through."""
        series = make_1r1c_series(n=200)
        fitter = RcFitter()
        results = scan(series, fitter, window_h=8.0, step_min=60.0, resample="15min")
        # If T_out wasn't passed, all fits would be None → empty
        assert len(results) > 0


# --- merge_grow ---------------------------------------------------------------

class TestMergeGrow:
    def test_reduces_result_count(self):
        s = make_exp_series(tau_h=6.0, n=400)
        fitter = ExpFitter()
        results = scan({"T_in": s}, fitter, window_h=4.0, step_min=15.0)
        assert len(results) > 1
        merged = merge_grow(results, {"T_in": s}, fitter, resample="5min", r2_min=0.98)
        assert len(merged) <= len(results)

    def test_merged_spans_are_longer(self):
        s = make_exp_series(tau_h=6.0, n=400)
        fitter = ExpFitter()
        results = scan({"T_in": s}, fitter, window_h=4.0, step_min=15.0)
        merged = merge_grow(results, {"T_in": s}, fitter, resample="5min", r2_min=0.98)
        if merged:
            scan_median_span = np.median(
                [(r.t_end - r.t_start).total_seconds() for r in results]
            )
            merge_median_span = np.median(
                [(r.t_end - r.t_start).total_seconds() for r in merged]
            )
            assert merge_median_span >= scan_median_span

    def test_merged_results_sorted_by_time(self):
        s = make_exp_series(tau_h=6.0, n=400)
        fitter = ExpFitter()
        results = scan({"T_in": s}, fitter, window_h=4.0, step_min=15.0)
        merged = merge_grow(results, {"T_in": s}, fitter, resample="5min", r2_min=0.98)
        starts = [r.t_start for r in merged]
        assert starts == sorted(starts)

    def test_empty_input_returns_empty(self):
        s = make_exp_series()
        fitter = ExpFitter()
        result = merge_grow([], {"T_in": s}, fitter, resample="5min")
        assert result == []


# --- to_dataframe -------------------------------------------------------------

class TestToDataframe:
    def test_returns_dataframe(self):
        s = make_exp_series(tau_h=6.0, n=200)
        fitter = ExpFitter()
        results = scan({"T_in": s}, fitter, window_h=4.0, step_min=30.0)
        df = to_dataframe(results)
        assert not df.empty
        assert "t_start" in df.columns
        assert "t_end" in df.columns
        assert "tau_h" in df.columns

    def test_empty_results_returns_empty_df(self):
        df = to_dataframe([])
        assert df.empty
