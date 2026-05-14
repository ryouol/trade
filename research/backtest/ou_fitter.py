"""Ornstein-Uhlenbeck fit for cross-venue stat-arb pairs.

For a spread series x_t = c_a(t) - c_b(t), we fit:

    x_{t+Δt} - x_t = α + β · x_t + ε
    θ = -β / Δt        (speed of mean reversion)
    μ = -α / β         (long-run mean)
    σ² = Var(ε) / Δt   (innovation variance)
    half-life τ = ln(2) / θ
    stationary σ_x = σ / √(2θ)
    z-score = (x - μ) / σ_x

Trading rules wired from the fit:

  Entry  : |z| > entry_z      (default 2)
  Exit   : |z| < exit_z       (default 0.5)
  Stop   : |z| > stop_z       (default 4)  OR  elapsed > 2 · halflife
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True, slots=True)
class OUFit:
    theta: float
    mu: float
    sigma: float            # innovation sigma (per √dt)
    sigma_x: float          # stationary sigma
    halflife_sec: float
    dt_sec: float
    converged: bool
    n_samples: int


def fit_ou(x: Sequence[float], dt_sec: float) -> OUFit:
    """Fit OU parameters via AR(1) on the spread series.

    `x`        : array-like spread observations sampled uniformly.
    `dt_sec`   : seconds between consecutive samples.

    Raises ValueError if the fit is degenerate (β ≥ 0 means no reversion).
    """
    x_arr = np.asarray(x, dtype=float)
    if x_arr.size < 30:
        raise ValueError(f"need at least 30 samples, got {x_arr.size}")
    if dt_sec <= 0.0:
        raise ValueError("dt_sec must be positive")

    x_t = x_arr[:-1]
    dx = x_arr[1:] - x_arr[:-1]

    # OLS: dx = α + β x_t + ε
    A = np.vstack([np.ones_like(x_t), x_t]).T
    coef, _, _, _ = np.linalg.lstsq(A, dx, rcond=None)
    alpha, beta = float(coef[0]), float(coef[1])

    if beta >= 0.0:
        raise ValueError(
            f"β = {beta:.4f} ≥ 0 — series shows no mean reversion; "
            "reject this pair"
        )

    theta = -beta / dt_sec
    mu = -alpha / beta
    residuals = dx - (alpha + beta * x_t)
    var_eps = float(np.var(residuals, ddof=2))
    sigma = math.sqrt(var_eps / dt_sec)
    sigma_x = sigma / math.sqrt(2.0 * theta)
    halflife = math.log(2.0) / theta

    return OUFit(
        theta=theta,
        mu=mu,
        sigma=sigma,
        sigma_x=sigma_x,
        halflife_sec=halflife,
        dt_sec=dt_sec,
        converged=True,
        n_samples=int(x_arr.size),
    )


def z_score(fit: OUFit, x: float) -> float:
    return (x - fit.mu) / max(fit.sigma_x, 1e-12)


def expected_pnl_per_unit(fit: OUFit, x: float, horizon_sec: float) -> float:
    """E[x_T - x_t] = (μ - x_t)(1 - exp(-θ(T-t)))"""
    return (fit.mu - x) * (1.0 - math.exp(-fit.theta * horizon_sec))


@dataclass(frozen=True, slots=True)
class OUSignal:
    side: str         # "long_spread", "short_spread", "exit", "hold"
    reason: str       # for audit log


def trading_signal(
    fit: OUFit,
    x: float,
    elapsed_sec: float,
    *,
    entry_z: float = 2.0,
    exit_z: float = 0.5,
    stop_z: float = 4.0,
    time_stop_multiplier: float = 2.0,
    halflife_cap_sec: float = 12 * 3600.0,
    in_position: bool = False,
    position_side: str = "",
) -> OUSignal:
    """Map the current spread to a trading action."""
    if fit.halflife_sec > halflife_cap_sec:
        return OUSignal("hold", f"halflife {fit.halflife_sec:.0f}s > cap")
    z = z_score(fit, x)
    if not in_position:
        if z < -entry_z:
            return OUSignal("long_spread", f"z={z:.2f} < -{entry_z}")
        if z > entry_z:
            return OUSignal("short_spread", f"z={z:.2f} > {entry_z}")
        return OUSignal("hold", f"z={z:.2f} inside entry band")
    # in position
    if abs(z) > stop_z:
        return OUSignal("exit", f"|z|={abs(z):.2f} > stop {stop_z}")
    if elapsed_sec > time_stop_multiplier * fit.halflife_sec:
        return OUSignal("exit", f"elapsed {elapsed_sec:.0f}s > {time_stop_multiplier}τ")
    # Exit when z crosses back through opposite of entry side.
    if position_side == "long_spread" and z > -exit_z:
        return OUSignal("exit", f"z={z:.2f} returned across exit band")
    if position_side == "short_spread" and z < exit_z:
        return OUSignal("exit", f"z={z:.2f} returned across exit band")
    return OUSignal("hold", f"z={z:.2f} within stops")
