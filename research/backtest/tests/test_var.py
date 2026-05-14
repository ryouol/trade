"""Sanity tests for Monte Carlo portfolio VaR."""

from __future__ import annotations

import pytest

from backtest.var import Position, monte_carlo_var


def test_empty_portfolio_zero_var() -> None:
    out = monte_carlo_var([], samples=100)
    assert out.var_99_dollars == 0.0
    assert out.var_95_dollars == 0.0


def test_single_position_var_bounded_by_capital_at_risk() -> None:
    # Buy 100 YES at $0.40. Max loss if NO = $40. Max gain if YES = $60.
    pos = Position(
        market_id="m1", group="g1",
        p_estimate=0.50, contracts_yes=100, cost_basis_dollars=40.0,
    )
    out = monte_carlo_var([pos], samples=10_000, rng_seed=1)
    # 99% VaR should be on the loss side, bounded by $40.
    assert 30.0 <= out.var_99_dollars <= 40.0 + 1.0


def test_uncorrelated_independent_markets_reduce_var_vs_concentration() -> None:
    """Diversified portfolio should have lower per-dollar VaR than concentrated."""
    # 10 independent markets at p=0.5, each with $10 at risk
    diversified = [
        Position(market_id=f"m{i}", group=f"g{i}", p_estimate=0.5,
                 contracts_yes=10, cost_basis_dollars=5.0)
        for i in range(10)
    ]
    # One concentrated $50-at-risk market
    concentrated = [
        Position(market_id="m_big", group="g_big", p_estimate=0.5,
                 contracts_yes=100, cost_basis_dollars=50.0),
    ]
    div = monte_carlo_var(diversified, samples=20_000,
                          rho_within_group=0.5, rho_across_groups=0.0, rng_seed=2)
    conc = monte_carlo_var(concentrated, samples=20_000, rng_seed=2)
    # Diversified VaR should be meaningfully smaller than concentrated VaR.
    assert div.var_99_dollars < conc.var_99_dollars


def test_grouped_positions_correlated_within_group() -> None:
    """Positions in the same group share more risk than across groups.

    With 5 positions at p=0.5, the 1% tail saturates to max loss for both
    groupings (probability of all-NO is 1/32 ≈ 3.1%, well above the 1%
    cutoff). The 5% (var_95) percentile is where the correlation structure
    actually discriminates: same_group gets all-NO at 5%, diff_groups gets
    a less-bad outcome.
    """
    same_group = [
        Position(market_id=f"m{i}", group="g_shared", p_estimate=0.5,
                 contracts_yes=10, cost_basis_dollars=5.0)
        for i in range(5)
    ]
    diff_groups = [
        Position(market_id=f"m{i}", group=f"g{i}", p_estimate=0.5,
                 contracts_yes=10, cost_basis_dollars=5.0)
        for i in range(5)
    ]
    g1 = monte_carlo_var(same_group, samples=20_000,
                          rho_within_group=0.9, rho_across_groups=0.05, rng_seed=3)
    g2 = monte_carlo_var(diff_groups, samples=20_000,
                          rho_within_group=0.5, rho_across_groups=0.05, rng_seed=3)
    assert g1.var_95_dollars > g2.var_95_dollars
