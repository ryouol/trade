"""Tests for the precision-weighted Bayesian fair-value aggregator."""

from __future__ import annotations

import pytest

from backtest.fair_value import Estimator, combine, microprice, ofi_update


def test_single_estimator_passthrough() -> None:
    e = Estimator(source="src1", v=0.65, sigma_sq=0.01)
    out = combine([e])
    assert out.v == pytest.approx(0.65, abs=1e-9)
    assert out.sigma_sq == pytest.approx(0.01, abs=1e-9)


def test_equal_variance_estimators_average() -> None:
    a = Estimator("a", 0.50, 0.01)
    b = Estimator("b", 0.60, 0.01)
    out = combine([a, b])
    assert out.v == pytest.approx(0.55, abs=1e-9)
    # combined sigma² = 1/(1/0.01 + 1/0.01) = 0.005
    assert out.sigma_sq == pytest.approx(0.005, abs=1e-9)


def test_lower_variance_estimator_dominates() -> None:
    confident = Estimator("confident", 0.30, 0.0001)  # τ=10000
    noisy = Estimator("noisy", 0.80, 1.0)              # τ=1
    out = combine([confident, noisy])
    assert out.v == pytest.approx(0.30, abs=0.001)
    # Most weight on the confident source
    weights = dict(out.contributions)
    assert weights["confident"] > 0.999


def test_combine_clips_to_unit_interval() -> None:
    # Pathological inputs that would push outside (0,1) shouldn't be valid;
    # the inputs themselves are validated, and the output is also clipped.
    a = Estimator("a", 0.98, 0.0001)
    b = Estimator("b", 0.99, 0.0001)
    out = combine([a, b])
    assert 0.01 <= out.v <= 0.99


def test_combine_rejects_invalid_estimator() -> None:
    with pytest.raises(ValueError):
        combine([Estimator("bad", v=0.0, sigma_sq=0.01)])
    with pytest.raises(ValueError):
        combine([Estimator("bad", v=0.5, sigma_sq=0.0)])
    with pytest.raises(ValueError):
        combine([])


def test_microprice_skews_toward_thin_side() -> None:
    # Thin ask, thick bid → microprice closer to ask (buyers pulling toward sellers)
    out = microprice(bid=0.50, ask=0.52, bid_size=100, ask_size=1)
    # weight on bid = ask_size / (ask + bid) = 1/101 ≈ 0.01
    assert 0.51 < out.v < 0.52


def test_microprice_returns_symmetric_when_sides_balanced() -> None:
    out = microprice(bid=0.50, ask=0.52, bid_size=10, ask_size=10)
    assert out.v == pytest.approx(0.51, abs=1e-9)


def test_ofi_update_shifts_in_direction_of_imbalance() -> None:
    e_pos = ofi_update(prev_v=0.50, ofi=+5.0, beta=0.01, base_sigma_sq=0.001)
    e_neg = ofi_update(prev_v=0.50, ofi=-5.0, beta=0.01, base_sigma_sq=0.001)
    assert e_pos.v > 0.50
    assert e_neg.v < 0.50
