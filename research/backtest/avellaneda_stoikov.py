"""Avellaneda-Stoikov market-making for binary contracts.

Reservation price:  r = v - q · γ · σ² · (T - t)
Optimal half-spread:  δ* = (1/γ) · ln(1 + γ/κ) + γ σ² (T - t) / 2

For binaries we clip quotes to [0.01, 0.99] and apply an extra widening
factor when |c - 0.5| > 0.4 because adverse selection spikes at boundaries.

Parameter guidance:
  γ ≈ 0.1            risk aversion; lower = tighter quotes, more inventory risk
  κ ∈ [50, 500]      order arrival decay; fit from your own fill data
  σ²                 short-window EWMA variance of fair value (λ ≈ 0.94)
  T - t              time to resolution in the same units as σ²
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ASParams:
    """Inputs to one quote calculation."""
    fair_value: float            # v in [0, 1]
    inventory: float             # q (signed, + = long YES, in contracts)
    sigma_sq: float              # σ² over the same horizon as time_to_resolution
    time_to_resolution: float    # T - t (same time unit as sigma_sq)
    gamma: float = 0.1
    kappa: float = 100.0


@dataclass(frozen=True, slots=True)
class ASQuote:
    bid: float
    ask: float
    reservation_price: float
    half_spread: float
    widened: bool


def reservation_price(p: ASParams) -> float:
    """r = v - q · γ · σ² · (T - t)"""
    return p.fair_value - p.inventory * p.gamma * p.sigma_sq * p.time_to_resolution


def optimal_half_spread(p: ASParams) -> float:
    """δ* = (1/γ) ln(1 + γ/κ) + γ σ² (T - t) / 2"""
    base = (1.0 / p.gamma) * math.log1p(p.gamma / p.kappa)
    risk = p.gamma * p.sigma_sq * p.time_to_resolution / 2.0
    return base + risk


def quote(p: ASParams, *, boundary_widen: bool = True) -> ASQuote:
    """Compute the bid/ask quote pair, clipped to [0.01, 0.99].

    `boundary_widen` adds an extra spread term when |c - 0.5| > 0.4 to handle
    binary adverse selection near the resolution boundaries.
    """
    if not 0.0 < p.fair_value < 1.0:
        raise ValueError(f"fair_value must be in (0, 1), got {p.fair_value}")
    if p.sigma_sq < 0.0:
        raise ValueError("sigma_sq must be non-negative")
    if p.time_to_resolution < 0.0:
        raise ValueError("time_to_resolution must be non-negative")
    if p.gamma <= 0.0 or p.kappa <= 0.0:
        raise ValueError("gamma and kappa must be positive")

    r = reservation_price(p)
    delta = optimal_half_spread(p)
    widened = False
    if boundary_widen and abs(p.fair_value - 0.5) > 0.4:
        # Multiply spread by 1.5 when extreme; tunable per strategy.
        delta *= 1.5
        widened = True
    bid = max(0.01, min(0.99, r - delta))
    ask = max(0.01, min(0.99, r + delta))
    if ask < bid:
        # If reservation + delta crosses, pin to mid.
        mid = (bid + ask) / 2.0
        bid = ask = mid
    return ASQuote(
        bid=bid,
        ask=ask,
        reservation_price=r,
        half_spread=delta,
        widened=widened,
    )


def fit_kappa_from_fills(distances: list[float], fill_times: list[float]) -> tuple[float, float]:
    """Estimate (A, κ) in P(fill in Δt | distance δ) ≈ A · exp(-κδ).

    Fit log(fills_per_sec) = log(A) - κ · δ via least-squares.
    Returns the fitted (A, κ).
    """
    import numpy as np

    if len(distances) != len(fill_times) or len(distances) < 3:
        raise ValueError("need at least 3 (distance, fill_time) pairs")
    d = np.asarray(distances, dtype=float)
    t = np.asarray(fill_times, dtype=float)
    if np.any(t <= 0.0):
        raise ValueError("fill_times must all be positive")
    y = np.log(1.0 / t)  # log(fills/sec)
    coeffs = np.polyfit(d, y, 1)
    slope, intercept = float(coeffs[0]), float(coeffs[1])
    return math.exp(intercept), -slope
