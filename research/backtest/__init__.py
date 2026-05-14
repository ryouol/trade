"""Quant primitives for `trade`.

These modules are the reference Python implementations of the math
documented in the README. They are used by the backtest harness and by
unit tests. The C++ ports (under services/cpp) must remain bit-for-bit
consistent against the same inputs.

Modules:
  cost_model         — fees, gas, slippage, carry, expected round-trip PnL
  avellaneda_stoikov — inventory-aware MM quoting for binaries
  ou_fitter          — Ornstein-Uhlenbeck fit for pair stat-arb
  fair_value         — precision-weighted Bayesian aggregator
  var                — Monte Carlo portfolio VaR
  fill_simulator     — conservative fill sim from recorded books
"""

from . import avellaneda_stoikov, cost_model, fair_value, fill_simulator, ou_fitter, var

__all__ = [
    "avellaneda_stoikov",
    "cost_model",
    "fair_value",
    "fill_simulator",
    "ou_fitter",
    "var",
]
