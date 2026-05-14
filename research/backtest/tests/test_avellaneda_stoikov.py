"""Numerical sanity tests for the Avellaneda-Stoikov MM quoter."""

from __future__ import annotations

import math

import pytest

from backtest.avellaneda_stoikov import (
    ASParams,
    fit_kappa_from_fills,
    optimal_half_spread,
    quote,
    reservation_price,
)


def _params(**overrides: float) -> ASParams:
    defaults: dict[str, float] = dict(
        fair_value=0.50,
        inventory=0.0,
        sigma_sq=0.001,         # ~1% vol
        time_to_resolution=1.0,  # 1 unit of time
        gamma=0.1,
        kappa=100.0,
    )
    defaults.update(overrides)
    return ASParams(**defaults)


def test_zero_inventory_centers_on_fair_value() -> None:
    q = quote(_params(inventory=0.0))
    assert q.reservation_price == pytest.approx(0.50, abs=1e-9)
    assert q.bid < 0.50 < q.ask
    assert q.ask - q.bid == pytest.approx(2 * q.half_spread, abs=1e-9)


def test_long_inventory_skews_quotes_down() -> None:
    q_long = quote(_params(inventory=10.0))
    q_flat = quote(_params(inventory=0.0))
    # Long inventory → r < v → both quotes shift down → bid shifts more than ask
    assert q_long.reservation_price < q_flat.reservation_price
    assert q_long.bid < q_flat.bid
    assert q_long.ask < q_flat.ask


def test_short_inventory_skews_quotes_up() -> None:
    q_short = quote(_params(inventory=-10.0))
    q_flat = quote(_params(inventory=0.0))
    assert q_short.reservation_price > q_flat.reservation_price
    assert q_short.bid > q_flat.bid
    assert q_short.ask > q_flat.ask


def test_higher_vol_widens_spread() -> None:
    q_low = quote(_params(sigma_sq=0.0005))
    q_high = quote(_params(sigma_sq=0.005))
    assert q_high.half_spread > q_low.half_spread


def test_higher_time_to_resolution_widens_spread() -> None:
    q_short = quote(_params(time_to_resolution=0.1))
    q_long = quote(_params(time_to_resolution=10.0))
    assert q_long.half_spread > q_short.half_spread


def test_higher_kappa_tightens_spread() -> None:
    """κ is order-arrival decay — higher κ means quotes can be tighter."""
    q_low_k = quote(_params(kappa=10.0))
    q_hi_k = quote(_params(kappa=1000.0))
    assert q_hi_k.half_spread < q_low_k.half_spread


def test_boundary_widening_when_extreme() -> None:
    q_mid = quote(_params(fair_value=0.50))
    q_edge = quote(_params(fair_value=0.95))
    assert q_edge.widened
    # Effective half-spread at edge is 1.5x the base widening; before clipping
    # it should exceed the centered version.
    # (After clipping the *quoted* spread can compress, so we check the
    # half_spread field — that's pre-clip.)
    assert q_edge.half_spread > q_mid.half_spread


def test_quotes_always_clipped_to_unit_interval() -> None:
    # Crank vol way up so naive bid/ask would leave [0.01, 0.99].
    q = quote(_params(fair_value=0.5, sigma_sq=10.0, time_to_resolution=10.0))
    assert 0.01 <= q.bid <= 0.99
    assert 0.01 <= q.ask <= 0.99


def test_quote_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        quote(_params(fair_value=0.0))
    with pytest.raises(ValueError):
        quote(_params(fair_value=1.0))
    with pytest.raises(ValueError):
        quote(_params(sigma_sq=-1.0))
    with pytest.raises(ValueError):
        quote(_params(gamma=-0.1))


def test_optimal_half_spread_matches_formula() -> None:
    p = _params(gamma=0.1, kappa=50.0, sigma_sq=0.002, time_to_resolution=0.5)
    expected = (1.0 / 0.1) * math.log1p(0.1 / 50.0) + 0.1 * 0.002 * 0.5 / 2.0
    assert optimal_half_spread(p) == pytest.approx(expected, abs=1e-12)


def test_reservation_price_matches_formula() -> None:
    p = _params(fair_value=0.55, inventory=3.0, gamma=0.2,
                sigma_sq=0.001, time_to_resolution=2.0)
    expected = 0.55 - 3.0 * 0.2 * 0.001 * 2.0
    assert reservation_price(p) == pytest.approx(expected, abs=1e-12)


def test_fit_kappa_from_fills_recovers_decay() -> None:
    import numpy as np
    rng = np.random.default_rng(42)
    true_A, true_kappa = 5.0, 80.0
    distances = np.linspace(0.005, 0.05, 30)
    # Synthetic fill_times: 1 / (A * exp(-κδ))
    fill_times = 1.0 / (true_A * np.exp(-true_kappa * distances))
    A, kappa = fit_kappa_from_fills(distances.tolist(), fill_times.tolist())
    assert kappa == pytest.approx(true_kappa, rel=0.05)
    assert A == pytest.approx(true_A, rel=0.05)
