"""Cost model for round-trip PnL on Kalshi and Polymarket US.

The model is intentionally pessimistic — fees and slippage are accounted for
fully, and you should only trade if the expected PnL clears the model with a
margin equal to 2× the slippage standard deviation.

Fee references (May 2026):

* Kalshi: taker = ceil(7¢ × C × p × (1 − p)) per trade, where C is the number
  of contracts and p is the contract price in dollars. Maker = 25% of taker.
* Polymarket US: 0.30% taker / 0.20% maker REBATE on contract premium.

Carry on locked capital is K · r_f · Δt / 365 — small but real for slow
markets.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

# Constants — refresh from venues quarterly.
KALSHI_TAKER_RATE: float = 0.07          # the 7¢ coefficient
KALSHI_MAKER_MULTIPLIER: float = 0.25    # maker = 25% of taker
PM_US_TAKER_BPS: float = 30.0            # 0.30% on contract premium
PM_US_MAKER_REBATE_BPS: float = 20.0     # 0.20% rebate (negative fee)
POLY_INTL_GAS_USD: float = 0.01          # approx Polygon gas per onchain op


class Role(str, Enum):
    MAKER = "maker"
    TAKER = "taker"


@dataclass(frozen=True, slots=True)
class TradeCost:
    """All values in dollars. Signed: + = you pay, − = you receive (rebate)."""
    venue: str
    count: int                # contracts
    price: float              # YES price in [0.01, 0.99]
    role: Role
    fee_dollars: float        # per-trade total fee
    gas_dollars: float = 0.0
    slippage_dollars: float = 0.0
    carry_dollars: float = 0.0

    @property
    def total_cost(self) -> float:
        return self.fee_dollars + self.gas_dollars + self.slippage_dollars + self.carry_dollars

    @property
    def fee_per_contract_cents(self) -> float:
        return 100.0 * self.fee_dollars / max(self.count, 1)


def kalshi_fee_dollars(count: int, price: float, role: Role = Role.TAKER) -> float:
    """Kalshi fee per trade in dollars. Rounded up to the nearest cent.

    Implemented in integer cents to avoid float drift — 0.07 is not exactly
    representable in binary float so naïve `math.ceil(0.07 * 100 * 0.5 * 0.5
    * 100)` rounds up to 176¢ instead of 175¢ for the canonical 100×$0.50
    example.
    """
    if count <= 0:
        return 0.0
    if not 0.0 < price < 1.0:
        raise ValueError(f"price must be in (0, 1), got {price}")
    raw_cents = KALSHI_TAKER_RATE * count * price * (1.0 - price) * 100.0
    if role is Role.MAKER:
        raw_cents *= KALSHI_MAKER_MULTIPLIER
    # Snap to 9 decimal places (1e-11 cents) to absorb 0.07's binary-float
    # imprecision before ceil. No real fee is meaningful below this.
    fee_cents = math.ceil(round(raw_cents, 9))
    return fee_cents / 100.0


def pm_us_fee_dollars(count: int, price: float, role: Role = Role.TAKER) -> float:
    """Polymarket US fee/rebate in dollars. Signed: makers receive credit."""
    if count <= 0:
        return 0.0
    if not 0.0 < price < 1.0:
        raise ValueError(f"price must be in (0, 1), got {price}")
    notional = count * price
    bps = PM_US_TAKER_BPS if role is Role.TAKER else -PM_US_MAKER_REBATE_BPS
    return notional * (bps / 10_000.0)


def expected_round_trip_pnl_dollars(
    *,
    venue: str,
    count: int,
    entry_price: float,
    exit_price: float,
    entry_role: Role,
    exit_role: Role,
    slippage_dollars: float = 0.0,
    carry_dollars: float = 0.0,
) -> tuple[float, dict[str, float]]:
    """PnL of buying `count` YES contracts at entry_price and selling at exit_price.

    Returns (pnl_dollars, breakdown).
    """
    if venue == "kalshi":
        fee_in = kalshi_fee_dollars(count, entry_price, entry_role)
        fee_out = kalshi_fee_dollars(count, exit_price, exit_role)
        gas = 0.0
    elif venue == "poly_us":
        fee_in = pm_us_fee_dollars(count, entry_price, entry_role)
        fee_out = pm_us_fee_dollars(count, exit_price, exit_role)
        gas = 0.0
    elif venue == "poly_intl":
        fee_in = pm_us_fee_dollars(count, entry_price, entry_role)  # similar order
        fee_out = pm_us_fee_dollars(count, exit_price, exit_role)
        gas = 2 * POLY_INTL_GAS_USD  # one onchain op per leg
    else:
        raise ValueError(f"unknown venue {venue!r}")

    gross = count * (exit_price - entry_price)
    pnl = gross - fee_in - fee_out - gas - slippage_dollars - carry_dollars
    breakdown = {
        "gross": gross,
        "fee_in": fee_in,
        "fee_out": fee_out,
        "gas": gas,
        "slippage": slippage_dollars,
        "carry": carry_dollars,
        "pnl": pnl,
    }
    return pnl, breakdown


@dataclass(frozen=True, slots=True)
class LockedArbInputs:
    """Cross-venue locked arb: buy YES on venue_a + buy NO on venue_b."""
    venue_a: str
    venue_b: str
    count: int
    pa_yes: float      # price you pay for YES on venue_a
    pb_no: float       # price you pay for NO on venue_b
    role_a: Role = Role.TAKER
    role_b: Role = Role.TAKER
    rho: float = 0.97  # probability the two venues resolve the same way
    slippage_dollars: float = 0.0
    carry_dollars: float = 0.0


def expected_locked_arb_pnl_dollars(inp: LockedArbInputs) -> tuple[float, dict[str, float]]:
    """Expected PnL accounting for resolution-mismatch probability rho.

    On match: payoff = $1 per pair, cost = (pa_yes + pb_no) - fees - carry
    On mismatch (1-rho): both legs lose; payoff = 0, cost stays the same
    """
    def fee(venue: str, count: int, price: float, role: Role) -> float:
        return (
            kalshi_fee_dollars(count, price, role)
            if venue == "kalshi"
            else pm_us_fee_dollars(count, price, role)
        )

    fee_a = fee(inp.venue_a, inp.count, inp.pa_yes, inp.role_a)
    fee_b = fee(inp.venue_b, inp.count, inp.pb_no, inp.role_b)
    cost = inp.count * (inp.pa_yes + inp.pb_no) + fee_a + fee_b
    payoff_match = inp.count * 1.0
    payoff_mismatch = 0.0
    e_payoff = inp.rho * payoff_match + (1.0 - inp.rho) * payoff_mismatch
    pnl = e_payoff - cost - inp.slippage_dollars - inp.carry_dollars
    worst_case_loss = cost - payoff_mismatch  # i.e. lose all premium + fees
    breakdown = {
        "expected_payoff": e_payoff,
        "cost": cost,
        "fee_a": fee_a,
        "fee_b": fee_b,
        "worst_case_loss": worst_case_loss,
        "pnl": pnl,
    }
    return pnl, breakdown


def slippage_from_book_walk(
    side_levels: list[tuple[float, int]],
    target_qty: int,
) -> tuple[float, float]:
    """Walk one side of the book, return (avg_fill_price, slippage_vs_top).

    side_levels: ordered list of (price, qty) — best price first.
    """
    if target_qty <= 0:
        return 0.0, 0.0
    top = side_levels[0][0]
    remaining = target_qty
    cost = 0.0
    for price, qty in side_levels:
        take = min(remaining, qty)
        cost += take * price
        remaining -= take
        if remaining == 0:
            break
    if remaining > 0:
        # Not enough depth; treat the rest as filling at the worst level.
        worst = side_levels[-1][0]
        cost += remaining * worst
    filled = target_qty - max(remaining, 0)
    avg = cost / max(filled, 1)
    return avg, (avg - top)


def carry_dollars(capital_locked: float, days: float, r_f: float = 0.05) -> float:
    """Opportunity cost of locked capital. r_f default 5% annual (rough)."""
    return capital_locked * r_f * (days / 365.0)
