"""Conservative fill simulation from recorded order books.

For paper mode we replay the live book and simulate fills the same way an
exchange would. We're intentionally pessimistic:

  * A marketable order fills at the first quote AT or BEYOND our limit
    (i.e. walking the book), with full slippage charged.
  * A resting order fills only when a contra trade prints AT a worse-or-equal
    price (i.e. someone hits/lifts us). We do NOT credit "we would have been
    next in queue" fills.
  * Fees match the cost model (taker for marketable, maker for resting).

This is the baseline; production strategies should run shadow mode to
verify the simulator's predictions against actual fills.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .cost_model import Role, kalshi_fee_dollars, pm_us_fee_dollars


class FillType(str, Enum):
    NONE = "none"
    PARTIAL = "partial"
    FULL = "full"


@dataclass(frozen=True, slots=True)
class SimFill:
    qty_filled: int
    avg_price: float
    fee_dollars: float
    role: Role
    fill_type: FillType


def simulate_marketable(
    *,
    venue: str,
    side: str,                       # "buy_yes" or "sell_yes"
    target_qty: int,
    limit_price: float,
    book_levels: list[tuple[float, int]],  # (price, qty), best first
) -> SimFill:
    """Walk the contra side of the book up to `limit_price`."""
    if side not in ("buy_yes", "sell_yes"):
        raise ValueError(f"unknown side {side!r}")
    remaining = target_qty
    filled = 0
    notional = 0.0
    for price, qty in book_levels:
        if side == "buy_yes" and price > limit_price:
            break
        if side == "sell_yes" and price < limit_price:
            break
        take = min(remaining, qty)
        filled += take
        notional += take * price
        remaining -= take
        if remaining == 0:
            break
    if filled == 0:
        return SimFill(0, 0.0, 0.0, Role.TAKER, FillType.NONE)
    avg = notional / filled
    fee = (
        kalshi_fee_dollars(filled, avg, Role.TAKER)
        if venue == "kalshi"
        else pm_us_fee_dollars(filled, avg, Role.TAKER)
    )
    return SimFill(
        qty_filled=filled,
        avg_price=avg,
        fee_dollars=fee,
        role=Role.TAKER,
        fill_type=FillType.FULL if remaining == 0 else FillType.PARTIAL,
    )


def simulate_resting_fill_from_trade_print(
    *,
    venue: str,
    side: str,                  # "buy_yes" or "sell_yes" — our resting order
    target_qty: int,
    limit_price: float,
    trade_price: float,
    trade_qty: int,
) -> SimFill:
    """Assume our resting order would have filled iff a print crosses it."""
    crosses = (
        (side == "buy_yes" and trade_price <= limit_price)
        or (side == "sell_yes" and trade_price >= limit_price)
    )
    if not crosses:
        return SimFill(0, 0.0, 0.0, Role.MAKER, FillType.NONE)
    take = min(target_qty, trade_qty)
    fee = (
        kalshi_fee_dollars(take, limit_price, Role.MAKER)
        if venue == "kalshi"
        else pm_us_fee_dollars(take, limit_price, Role.MAKER)
    )
    return SimFill(
        qty_filled=take,
        avg_price=limit_price,
        fee_dollars=fee,
        role=Role.MAKER,
        fill_type=FillType.FULL if take == target_qty else FillType.PARTIAL,
    )
