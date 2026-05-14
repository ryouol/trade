"""Cost-model correctness tests.

These pin the fee math against Kalshi's published formula and PM US's
0.30%/0.20% schedule. If the venue changes its fee, these tests fail loudly
— the constants live in cost_model.py and must be refreshed there.
"""

from __future__ import annotations

import math

import pytest

from backtest.cost_model import (
    LockedArbInputs,
    Role,
    carry_dollars,
    expected_locked_arb_pnl_dollars,
    expected_round_trip_pnl_dollars,
    kalshi_fee_dollars,
    pm_us_fee_dollars,
    slippage_from_book_walk,
)


# --- Kalshi -----------------------------------------------------------------

def test_kalshi_fee_at_50_cents_for_100_contracts() -> None:
    """Kalshi published example: 100 contracts at $0.50 = $1.75 taker fee."""
    fee = kalshi_fee_dollars(100, 0.50, Role.TAKER)
    assert fee == pytest.approx(1.75, abs=0.01)


def test_kalshi_fee_at_10_cents_for_100_contracts() -> None:
    """Published example: 100 × $0.10 ≈ 0.63¢/contract = $0.63."""
    fee = kalshi_fee_dollars(100, 0.10, Role.TAKER)
    assert fee == pytest.approx(0.63, abs=0.01)


def test_kalshi_taker_rounds_up_to_cent() -> None:
    """7¢ × 1 × 0.5 × 0.5 = 1.75¢ — rounds up to 2¢ for 1 contract."""
    assert kalshi_fee_dollars(1, 0.50, Role.TAKER) == 0.02


def test_kalshi_maker_is_25pct_of_taker() -> None:
    taker = kalshi_fee_dollars(100, 0.50, Role.TAKER)
    maker = kalshi_fee_dollars(100, 0.50, Role.MAKER)
    # Within rounding to the cent.
    assert maker == pytest.approx(taker * 0.25, abs=0.02)


def test_kalshi_rejects_boundary_price() -> None:
    with pytest.raises(ValueError):
        kalshi_fee_dollars(10, 0.0, Role.TAKER)
    with pytest.raises(ValueError):
        kalshi_fee_dollars(10, 1.0, Role.TAKER)


# --- Polymarket US ----------------------------------------------------------

def test_pm_us_taker_is_30bps_of_notional() -> None:
    fee = pm_us_fee_dollars(100, 0.55, Role.TAKER)
    # notional = 100 * 0.55 = 55; fee = 55 * 0.003 = 0.165
    assert fee == pytest.approx(0.165, abs=1e-9)


def test_pm_us_maker_is_20bps_rebate() -> None:
    fee = pm_us_fee_dollars(100, 0.55, Role.MAKER)
    # rebate: -55 * 0.002 = -0.11
    assert fee == pytest.approx(-0.11, abs=1e-9)


def test_pm_us_round_trip_make_make_is_negative_40bps() -> None:
    """Quoting both legs and earning the rebate on both = -40bps round-trip cost
    (i.e. you get paid 40bps on entry notional)."""
    fee_in = pm_us_fee_dollars(100, 0.50, Role.MAKER)
    fee_out = pm_us_fee_dollars(100, 0.50, Role.MAKER)
    notional = 100 * 0.50
    total_bps = 1e4 * (fee_in + fee_out) / notional
    assert total_bps == pytest.approx(-40.0, abs=0.1)


def test_pm_us_round_trip_take_take_is_60bps() -> None:
    fee_in = pm_us_fee_dollars(100, 0.50, Role.TAKER)
    fee_out = pm_us_fee_dollars(100, 0.50, Role.TAKER)
    notional = 100 * 0.50
    total_bps = 1e4 * (fee_in + fee_out) / notional
    assert total_bps == pytest.approx(60.0, abs=0.1)


# --- Round-trip PnL ---------------------------------------------------------

def test_expected_round_trip_kalshi_buy_low_sell_high() -> None:
    pnl, b = expected_round_trip_pnl_dollars(
        venue="kalshi", count=100,
        entry_price=0.40, exit_price=0.45,
        entry_role=Role.TAKER, exit_role=Role.TAKER,
    )
    assert b["gross"] == pytest.approx(5.0, abs=1e-9)  # 100 * 0.05
    # fees are positive; pnl < gross
    assert pnl < b["gross"]


def test_locked_arb_with_mismatch_risk() -> None:
    inp = LockedArbInputs(
        venue_a="kalshi", venue_b="poly_us",
        count=100, pa_yes=0.48, pb_no=0.50,
        role_a=Role.TAKER, role_b=Role.TAKER,
        rho=0.97,
    )
    pnl, b = expected_locked_arb_pnl_dollars(inp)
    # Match payoff = $100; mismatch payoff = 0; expected = 0.97 * 100 = $97
    assert b["expected_payoff"] == pytest.approx(97.0, abs=1e-9)
    # Cost > entry premiums alone (fees on both legs)
    assert b["cost"] > 100 * (0.48 + 0.50)


# --- Slippage from book walk ------------------------------------------------

def test_slippage_walks_book_correctly() -> None:
    # bids at 0.50 (qty 5), 0.49 (qty 10), 0.48 (qty 20)
    levels = [(0.50, 5), (0.49, 10), (0.48, 20)]
    avg, slip = slippage_from_book_walk(levels, target_qty=12)
    # 5 @ 0.50 + 7 @ 0.49 = 2.50 + 3.43 = 5.93 ; avg = 0.4942
    assert avg == pytest.approx(0.4942, abs=1e-4)
    assert slip < 0  # walking down a bid stack — selling, so avg below top


# --- Carry ------------------------------------------------------------------

def test_carry_default_5pct_annual() -> None:
    # $10,000 locked for 30 days at 5%: 10000 * 0.05 * 30/365 ≈ $41.10
    c = carry_dollars(10_000.0, 30.0)
    assert c == pytest.approx(41.10, abs=0.05)


def test_carry_zero_for_zero_days() -> None:
    assert carry_dollars(10_000.0, 0.0) == 0.0
