"""Precision-weighted Bayesian aggregator for fair value v_t.

Inputs: any number of independent estimators (v_i, σ_i²).
Output: combined (v, σ²) where:

    v   = (Σ τ_i v_i) / (Σ τ_i)
    σ²  = 1 / (Σ τ_i)             with τ_i = 1 / σ_i²

This is the optimal MMSE combiner for Gaussian estimators. We clip outputs
to (0.01, 0.99) since binary contracts can't trade at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class Estimator:
    source: str
    v: float
    sigma_sq: float


@dataclass(frozen=True, slots=True)
class FairValue:
    v: float
    sigma_sq: float
    contributions: tuple[tuple[str, float], ...]  # (source, precision_weight)


def combine(estimators: Iterable[Estimator]) -> FairValue:
    """Combine estimators by precision (inverse variance) weighting."""
    est_list = list(estimators)
    if not est_list:
        raise ValueError("at least one estimator required")
    weighted_sum = 0.0
    precision_sum = 0.0
    weights = []
    for e in est_list:
        if not 0.0 < e.v < 1.0:
            raise ValueError(f"estimator {e.source!r} v={e.v} outside (0, 1)")
        if e.sigma_sq <= 0.0:
            raise ValueError(f"estimator {e.source!r} sigma_sq={e.sigma_sq} must be > 0")
        tau = 1.0 / e.sigma_sq
        weighted_sum += tau * e.v
        precision_sum += tau
        weights.append((e.source, tau))
    v = weighted_sum / precision_sum
    sigma_sq = 1.0 / precision_sum
    contributions = tuple((s, w / precision_sum) for s, w in weights)
    return FairValue(
        v=max(0.01, min(0.99, v)),
        sigma_sq=sigma_sq,
        contributions=contributions,
    )


def microprice(bid: float, ask: float, bid_size: float, ask_size: float) -> Estimator:
    """Microprice = imbalance-weighted mid:

        c_micro = (S_ask · c_bid + S_bid · c_ask) / (S_ask + S_bid)

    Variance proxy = (c_ask - c_bid)² / 12 (uniform over the spread).
    """
    if bid_size <= 0.0 or ask_size <= 0.0:
        raise ValueError("sizes must be positive")
    if not (0.0 < bid < ask < 1.0):
        raise ValueError(f"need 0 < bid={bid} < ask={ask} < 1")
    v = (ask_size * bid + bid_size * ask) / (ask_size + bid_size)
    spread = ask - bid
    sigma_sq = (spread * spread) / 12.0
    return Estimator(source="microprice", v=v, sigma_sq=max(sigma_sq, 1e-8))


def ofi_update(
    prev_v: float,
    ofi: float,
    beta: float,
    base_sigma_sq: float,
) -> Estimator:
    """Order-flow-imbalance push.

    Δv = β · OFI, variance scaled by β² · base_sigma_sq.
    """
    return Estimator(
        source="ofi",
        v=max(0.001, min(0.999, prev_v + beta * ofi)),
        sigma_sq=max(beta * beta * base_sigma_sq, 1e-8),
    )
