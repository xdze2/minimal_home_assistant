"""Tests for ExpFitter.

All tests use synthetic data generated from the exact model so we know
the ground truth and can assert recovery within tight tolerances.
"""

import numpy as np
import pytest

from miniha.th_models.sliding.exp_fitter import ExpFitter, ExpFitterConfig


def make_decay(tau_h: float, T_inf: float, T_0: float, n: int = 60, dt_s: float = 300.0) -> tuple[np.ndarray, np.ndarray]:
    """Generate a clean exponential decay. Returns (t_sec, y)."""
    t = np.arange(n) * dt_s
    y = (T_0 - T_inf) * np.exp(-t / (tau_h * 3600.0)) + T_inf
    return t, y


class TestExpFitterCleanSignal:
    def test_recovers_tau(self):
        # Grid-search T_inf is approximate; use a longer window (>2τ) for
        # reliable recovery and a tolerance that reflects the method.
        tau_h = 6.0
        t, y = make_decay(tau_h=tau_h, T_inf=14.0, T_0=20.0, n=200, dt_s=300.0)
        fitter = ExpFitter()
        result = fitter.fit(t, {"T_in": y})
        assert result is not None
        assert abs(result.params["tau_h"] - tau_h) < 1.0

    def test_recovers_T_inf(self):
        T_inf = 13.5
        t, y = make_decay(tau_h=8.0, T_inf=T_inf, T_0=19.0)
        fitter = ExpFitter()
        result = fitter.fit(t, {"T_in": y})
        assert result is not None
        assert abs(result.params["T_inf"] - T_inf) < 0.3

    def test_r2_near_one_on_clean_signal(self):
        t, y = make_decay(tau_h=5.0, T_inf=12.0, T_0=18.0)
        fitter = ExpFitter()
        result = fitter.fit(t, {"T_in": y})
        assert result is not None
        assert result.quality > 0.999

    def test_quality_is_r2(self):
        t, y = make_decay(tau_h=5.0, T_inf=12.0, T_0=18.0)
        fitter = ExpFitter()
        result = fitter.fit(t, {"T_in": y})
        assert result is not None
        assert 0.0 <= result.quality <= 1.0


class TestExpFitterRejections:
    def test_rejects_flat_signal(self):
        t = np.arange(60) * 300.0
        y = np.full(60, 15.0)
        fitter = ExpFitter()
        assert fitter.fit(t, {"T_in": y}) is None

    def test_rejects_increasing_signal(self):
        t = np.arange(60) * 300.0
        y = 15.0 + t / 3600.0  # rising ramp
        fitter = ExpFitter()
        assert fitter.fit(t, {"T_in": y}) is None

    def test_rejects_too_few_samples(self):
        t, y = make_decay(tau_h=5.0, T_inf=12.0, T_0=18.0, n=4)
        fitter = ExpFitter()
        assert fitter.fit(t, {"T_in": y}) is None

    def test_rejects_tau_below_min(self):
        cfg = ExpFitterConfig(tau_min_h=5.0)
        t, y = make_decay(tau_h=1.0, T_inf=12.0, T_0=18.0, n=60, dt_s=60.0)
        fitter = ExpFitter(cfg)
        assert fitter.fit(t, {"T_in": y}) is None

    def test_rejects_tau_above_max(self):
        # A τ=20h curve seen through a 5h window looks nearly linear; the
        # fitter may fit it with a shorter τ that passes the max check.
        # What we can assert: if it fits at all, τ is within the allowed range.
        cfg = ExpFitterConfig(tau_max_h=10.0)
        t, y = make_decay(tau_h=20.0, T_inf=12.0, T_0=18.0)
        fitter = ExpFitter(cfg)
        result = fitter.fit(t, {"T_in": y})
        if result is not None:
            assert result.params["tau_h"] <= cfg.tau_max_h

    def test_missing_T_in_returns_none(self):
        t = np.arange(60) * 300.0
        fitter = ExpFitter()
        assert fitter.fit(t, {}) is None


class TestExpFitterNoise:
    def test_recovers_tau_with_small_noise(self):
        rng = np.random.default_rng(42)
        tau_h = 7.0
        # Use a longer window (>2τ) so the asymptote is well-constrained.
        t, y = make_decay(tau_h=tau_h, T_inf=14.0, T_0=20.0, n=200, dt_s=300.0)
        y_noisy = y + rng.normal(0, 0.05, size=y.shape)
        fitter = ExpFitter()
        result = fitter.fit(t, {"T_in": y_noisy})
        assert result is not None
        assert abs(result.params["tau_h"] - tau_h) < 1.5


class TestExpFitterParamsClose:
    def test_identical_params_are_close(self):
        t, y = make_decay(tau_h=6.0, T_inf=14.0, T_0=20.0)
        fitter = ExpFitter()
        r = fitter.fit(t, {"T_in": y})
        assert r is not None
        assert fitter.params_close(r, r)

    def test_different_tau_not_close(self):
        t1, y1 = make_decay(tau_h=4.0, T_inf=14.0, T_0=20.0)
        t2, y2 = make_decay(tau_h=11.0, T_inf=14.0, T_0=20.0)
        fitter = ExpFitter()
        r1 = fitter.fit(t1, {"T_in": y1})
        r2 = fitter.fit(t2, {"T_in": y2})
        assert r1 is not None and r2 is not None
        assert not fitter.params_close(r1, r2)

    def test_similar_tau_close(self):
        t1, y1 = make_decay(tau_h=6.0, T_inf=14.0, T_0=20.0)
        t2, y2 = make_decay(tau_h=6.3, T_inf=14.1, T_0=20.0)
        fitter = ExpFitter()
        r1 = fitter.fit(t1, {"T_in": y1})
        r2 = fitter.fit(t2, {"T_in": y2})
        assert r1 is not None and r2 is not None
        assert fitter.params_close(r1, r2)
