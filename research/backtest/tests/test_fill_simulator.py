"""Tests for the conservative fill simulator."""

from __future__ import annotations

import pytest

from backtest.fill_simulator import (
    FillType,
    Role,
    simulate_marketable,
    simulate_resting_fill_from_trade_print,
)


def test_marketable_fills_through_levels() -> None:
    # Asks at 0.50 (qty 5), 0.51 (qty 10).
    f = simulate_marketable(
        venue="kalshi", side="buy_yes", target_qty=8, limit_price=0.51,
        book_levels=[(0.50, 5), (0.51, 10)],
    )
    assert f.qty_filled == 8
    assert f.fill_type is FillType.FULL
    # avg = (5*0.50 + 3*0.51) / 8 = (2.5 + 1.53) / 8 = 0.50375
    assert f.avg_price == pytest.approx(0.50375, abs=1e-4)
    assert f.role is Role.TAKER


def test_marketable_partial_when_book_exhausted_at_limit() -> None:
    f = simulate_marketable(
        venue="kalshi", side="buy_yes", target_qty=10, limit_price=0.50,
        book_levels=[(0.50, 5), (0.51, 10)],
    )
    assert f.qty_filled == 5
    assert f.fill_type is FillType.PARTIAL


def test_marketable_no_fill_if_limit_below_book() -> None:
    f = simulate_marketable(
        venue="kalshi", side="buy_yes", target_qty=10, limit_price=0.49,
        book_levels=[(0.50, 5), (0.51, 10)],
    )
    assert f.qty_filled == 0
    assert f.fill_type is FillType.NONE


def test_resting_buy_fills_when_print_at_or_below_limit() -> None:
    f = simulate_resting_fill_from_trade_print(
        venue="poly_us", side="buy_yes", target_qty=10, limit_price=0.50,
        trade_price=0.49, trade_qty=15,
    )
    assert f.qty_filled == 10
    assert f.fill_type is FillType.FULL
    assert f.role is Role.MAKER


def test_resting_sell_does_not_fill_when_print_below_limit() -> None:
    f = simulate_resting_fill_from_trade_print(
        venue="kalshi", side="sell_yes", target_qty=10, limit_price=0.55,
        trade_price=0.54, trade_qty=15,
    )
    assert f.qty_filled == 0


def test_pm_us_resting_fill_is_rebate() -> None:
    f = simulate_resting_fill_from_trade_print(
        venue="poly_us", side="buy_yes", target_qty=10, limit_price=0.50,
        trade_price=0.50, trade_qty=10,
    )
    # PM US maker fee is negative (rebate)
    assert f.fee_dollars < 0
