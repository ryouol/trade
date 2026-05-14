"""Polymarket US WS+REST bridge.

Wraps the official `polymarket-us` SDK (`pip install polymarket-us`) and:

  - Authenticates via Ed25519 using key_id + base64 secret.
  - Subscribes to /v1/ws/markets (public book + trades) and /v1/ws/private
    (authenticated order/fill stream).
  - Publishes normalized market data and execution reports to NATS in the
    protobuf schema defined under packages/schemas/proto/.
  - Exposes an Executor that enforces invariants on every order:
      * manualOrderIndicator = MANUAL_ORDER_INDICATOR_AUTOMATIC
      * client_order_id == intent_id (idempotent retries)
      * 20 rps global token-bucket throttle (per API key)

This module imports the SDK lazily so unit tests can run without it.
"""

from .connector import PolyUsConnector
from .executor import PolyUsExecutor
from .throttle import TokenBucket

__all__ = ["PolyUsConnector", "PolyUsExecutor", "TokenBucket"]
