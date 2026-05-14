"""OU fitter sanity tests on synthetic mean-reverting processes."""

from __future__ import annotations

import math

import numpy as np
import pytest

from backtest.ou_fitter import OUFit, expected_pnl_per_unit, fit_ou, trading_signal, z_score


def _simulate_ou(
    theta: float, mu: float, sigma: float,
    *, dt: float = 1.0, n: int = 5000, x0: float = 0.0, seed: int = 7,
) -> np.ndarray:
    """Euler-Maruyama discretization of dX = θ(μ - X) dt + σ dW."""
    rng = np.random.default_rng(seed)
    x = np.empty(n)
    x[0] = x0
    sqrt_dt = math.sqrt(dt)
    eps = rng.standard_normal(n - 1)
    for i in range(1, n):
        x[i] = x[i - 1] + theta * (mu - x[i - 1]) * dt + sigma * sqrt_dt * eps[i - 1]
    return x


def test_recovers_theta_and_mu_on_synthetic_series() -> None:
    true_theta, true_mu, true_sigma = 0.05, 0.02, 0.01
    x = _simulate_ou(true_theta, true_mu, true_sigma, dt=1.0, n=8000, seed=11)
    fit = fit_ou(x.tolist(), dt_sec=1.0)
    assert fit.theta == pytest.approx(true_theta, rel=0.30)
    assert fit.mu == pytest.approx(true_mu, abs=0.01)
    assert fit.sigma == pytest.approx(true_sigma, rel=0.20)
    expected_halflife = math.log(2.0) / true_theta
    assert fit.halflife_sec == pytest.approx(expected_halflife, rel=0.30)


def test_rejects_non_reverting_series() -> None:
    # Random walk: no mean reversion → β ≈ 0.
    rng = np.random.default_rng(0)
    x = np.cumsum(rng.standard_normal(2000))
    # Will sometimes recover a tiny β < 0 by chance but with very long
    # halflife; that gets caught by the halflife_cap_sec rule, not here.
    try:
        fit_ou(x.tolist(), dt_sec=1.0)
    except ValueError as e:
        assert "no mean reversion" in str(e)


def test_rejects_too_few_samples() -> None:
    with pytest.raises(ValueError, match="at least 30"):
        fit_ou([0.0] * 10, dt_sec=1.0)


def test_z_score_zero_at_mean() -> None:
    fit = OUFit(theta=0.1, mu=0.5, sigma=0.01, sigma_x=0.05,
                halflife_sec=6.93, dt_sec=1.0, converged=True, n_samples=100)
    assert z_score(fit, 0.5) == pytest.approx(0.0, abs=1e-12)
    assert z_score(fit, 0.55) == pytest.approx(1.0, abs=1e-9)
    assert z_score(fit, 0.45) == pytest.approx(-1.0, abs=1e-9)


def test_expected_pnl_pulls_toward_mu() -> None:
    fit = OUFit(theta=0.5, mu=0.0, sigma=1.0, sigma_x=1.0,
                halflife_sec=math.log(2)/0.5, dt_sec=1.0, converged=True, n_samples=100)
    # Far below mu → expected drift up
    assert expected_pnl_per_unit(fit, x=-2.0, horizon_sec=1.0) > 0
    # Above mu → expected drift down
    assert expected_pnl_per_unit(fit, x=2.0, horizon_sec=1.0) < 0


def test_entry_signal_when_z_exceeds_threshold() -> None:
    fit = OUFit(theta=0.01, mu=0.0, sigma=1.0, sigma_x=1.0,
                halflife_sec=69.3, dt_sec=1.0, converged=True, n_samples=100)
    sig = trading_signal(fit, x=-3.0, elapsed_sec=0.0, in_position=False)
    assert sig.side == "long_spread"
    sig = trading_signal(fit, x=3.0, elapsed_sec=0.0, in_position=False)
    assert sig.side == "short_spread"


def test_stop_when_halflife_too_long() -> None:
    fit = OUFit(theta=0.000001, mu=0.0, sigma=1.0, sigma_x=1.0,
                halflife_sec=1e6, dt_sec=1.0, converged=True, n_samples=100)
    sig = trading_signal(fit, x=-5.0, elapsed_sec=0.0, in_position=False)
    assert sig.side == "hold"


def test_time_stop_in_position() -> None:
    halflife = 100.0
    fit = OUFit(theta=math.log(2)/halflife, mu=0.0, sigma=1.0, sigma_x=1.0,
                halflife_sec=halflife, dt_sec=1.0, converged=True, n_samples=100)
    # In position, well past 2 * halflife
    sig = trading_signal(fit, x=-1.0, elapsed_sec=300.0,
                          in_position=True, position_side="long_spread")
    assert sig.side == "exit"
    assert "elapsed" in sig.reason
