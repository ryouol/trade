"""Monte Carlo portfolio VaR for prediction-market positions.

Each open position is binary: at resolution, YES pays $1 and NO pays $0.
We sample joint outcomes for N=10000 draws and compute the percentile loss.

For now we model correlations with a simple Gaussian copula on event groups
(e.g. all NFL games one weekend, all primaries in one state). Each group
shares a latent z-score that pushes their probabilities up or down together.

This is a first-order risk model — refine the copula once you have real
multi-event positions to fit against.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class Position:
    market_id: str
    group: str               # e.g. "nfl_week_5", "iowa_2026_senate"
    p_estimate: float        # your estimate of P(YES) at horizon
    contracts_yes: int       # signed; + long YES, - short YES
    cost_basis_dollars: float  # paid premium (sunk)


@dataclass(frozen=True, slots=True)
class VaRResult:
    var_99_dollars: float
    var_95_dollars: float
    expected_shortfall_99_dollars: float
    mean_pnl_dollars: float
    samples: int


def monte_carlo_var(
    positions: list[Position],
    *,
    samples: int = 10_000,
    rho_within_group: float = 0.5,
    rho_across_groups: float = 0.05,
    rng_seed: int | None = None,
) -> VaRResult:
    """Run a copula-based Monte Carlo over joint binary resolutions.

    PnL per position on a YES outcome  = contracts_yes · ($1 - cost_basis/$contract)
    PnL on a NO outcome                = -cost_basis_per_contract · contracts_yes
    """
    if not positions:
        return VaRResult(0.0, 0.0, 0.0, 0.0, samples=samples)

    rng = np.random.default_rng(rng_seed)
    n = len(positions)
    groups = {p.group for p in positions}
    group_idx = {g: i for i, g in enumerate(sorted(groups))}
    n_groups = len(groups)

    # Latent z per group and a global z. Map to per-position uniform via copula.
    global_z = rng.standard_normal(samples)
    group_z = rng.standard_normal((samples, n_groups))
    pos_z = rng.standard_normal((samples, n))

    # Combine via simple correlation structure.
    z = (
        np.sqrt(rho_across_groups) * global_z[:, None]
        + np.sqrt(max(rho_within_group - rho_across_groups, 0.0))
            * np.array([group_z[:, group_idx[p.group]] for p in positions]).T
        + np.sqrt(1.0 - rho_within_group) * pos_z
    )
    # Standard-normal CDF without scipy.
    u = 0.5 * (1.0 + _erf(z / np.sqrt(2.0)))

    ps = np.array([p.p_estimate for p in positions])
    is_yes = u < ps  # shape (samples, n)

    pnl = np.zeros(samples)
    for j, pos in enumerate(positions):
        cost_per_contract = pos.cost_basis_dollars / max(abs(pos.contracts_yes), 1)
        payoff_yes = (1.0 - cost_per_contract) * pos.contracts_yes
        payoff_no = -cost_per_contract * pos.contracts_yes
        pnl += np.where(is_yes[:, j], payoff_yes, payoff_no)

    var_99 = float(-np.percentile(pnl, 1.0))
    var_95 = float(-np.percentile(pnl, 5.0))
    es_99 = float(-pnl[pnl <= np.percentile(pnl, 1.0)].mean()) if (pnl <= np.percentile(pnl, 1.0)).any() else var_99
    return VaRResult(
        var_99_dollars=var_99,
        var_95_dollars=var_95,
        expected_shortfall_99_dollars=es_99,
        mean_pnl_dollars=float(pnl.mean()),
        samples=samples,
    )


def _erf(x: np.ndarray) -> np.ndarray:
    """Abramowitz-Stegun 7.1.26 approximation. Vectorized; relative error < 1.5e-7."""
    a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    p = 0.3275911
    sign = np.sign(x)
    ax = np.abs(x)
    t = 1.0 / (1.0 + p * ax)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * np.exp(-ax * ax)
    return sign * y
