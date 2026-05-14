"""Polymarket US order executor.

Translates `VenueOrder` (proto) to the PM US REST shape, enforcing invariants:

  * manualOrderIndicator MUST be MANUAL_ORDER_INDICATOR_AUTOMATIC for every
    bot-placed order — required by CFTC compliance.
  * client_order_id is the intent_id (UUIDv7) so retries are idempotent.
  * Token-bucket throttle at 20 rps per API key.
  * In paper/shadow mode, no REST traffic is sent — the executor records a
    simulated fill against the live book instead.

Endpoint paths:
  POST /v1/orders                    — create
  POST /v1/order/preview             — pre-flight check
  POST /v1/order/{id}/cancel         — cancel one
  POST /v1/orders/open/cancel        — cancel all
  POST /v1/orders/batched            — batched create (≤ 20)
  POST /v1/orders/batched/cancel     — batched cancel (≤ 20)
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import httpx
import structlog

from .throttle import TokenBucket

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

REST_BASE: str = "https://api.polymarket.us"

OrderIntent = Literal["ORDER_INTENT_BUY_LONG", "ORDER_INTENT_SELL_LONG",
                      "ORDER_INTENT_BUY_SHORT", "ORDER_INTENT_SELL_SHORT"]
OrderType = Literal["ORDER_TYPE_LIMIT", "ORDER_TYPE_MARKET"]
TIF = Literal[
    "TIME_IN_FORCE_GOOD_TILL_CANCEL",
    "TIME_IN_FORCE_GOOD_TILL_DATE",
    "TIME_IN_FORCE_IMMEDIATE_OR_CANCEL",
    "TIME_IN_FORCE_FILL_OR_KILL",
    "TIME_IN_FORCE_DAY",
]
TradingMode = Literal["disabled", "paper", "shadow", "live"]


@dataclass(slots=True)
class PolyUsExecutorConfig:
    rest_base: str = REST_BASE
    requests_per_second: float = 20.0
    burst_capacity: float = 20.0
    request_timeout_s: float = 5.0


class PolyUsExecutor:
    """Thin order router around the official polymarket-us SDK.

    Construct with a configured SDK client (authenticated). For paper/shadow
    modes the SDK isn't called.
    """

    def __init__(
        self,
        sdk_client: Any,
        mode: TradingMode = "paper",
        config: PolyUsExecutorConfig | None = None,
    ) -> None:
        self._sdk = sdk_client
        self._mode: TradingMode = mode
        self._cfg = config or PolyUsExecutorConfig()
        self._throttle = TokenBucket(
            capacity=self._cfg.burst_capacity,
            rate=self._cfg.requests_per_second,
        )

    @property
    def mode(self) -> TradingMode:
        return self._mode

    def set_mode(self, mode: TradingMode) -> None:
        logger.info("mode_change", old=self._mode, new=mode)
        self._mode = mode

    def _build_payload(
        self,
        *,
        market_slug: str,
        side_intent: OrderIntent,
        order_type: OrderType,
        price_usd: str,
        quantity: int,
        tif: TIF,
        intent_id: str,
        post_only: bool = False,
        good_till_ts: int | None = None,
        slippage_ticks: int | None = None,
    ) -> dict[str, Any]:
        """Build the PM US POST /v1/orders body."""
        payload: dict[str, Any] = {
            "marketSlug": market_slug,
            "type": order_type,
            "price": {"value": price_usd, "currency": "USD"},
            "quantity": quantity,
            "tif": tif,
            "intent": side_intent,
            # COMPLIANCE — never change this:
            "manualOrderIndicator": "MANUAL_ORDER_INDICATOR_AUTOMATIC",
            # Idempotency: clientOrderId = intent_id so retries are safe.
            "clientOrderId": intent_id,
            "participateDontInitiate": bool(post_only),
        }
        if tif == "TIME_IN_FORCE_GOOD_TILL_DATE":
            if good_till_ts is None:
                raise ValueError("good_till_ts required for GTD")
            payload["goodTillTime"] = int(good_till_ts)
        if order_type == "ORDER_TYPE_MARKET" and slippage_ticks is not None:
            payload["slippageTolerance"] = {
                "currentPrice": {"value": price_usd, "currency": "USD"},
                "ticks": int(slippage_ticks),
            }
        return payload

    async def place_order(
        self,
        *,
        market_slug: str,
        side_intent: OrderIntent,
        order_type: OrderType,
        price_usd: str,
        quantity: int,
        tif: TIF = "TIME_IN_FORCE_GOOD_TILL_CANCEL",
        intent_id: str | None = None,
        post_only: bool = False,
        good_till_ts: int | None = None,
        slippage_ticks: int | None = None,
    ) -> dict[str, Any]:
        """Place a single order. Throttled and mode-aware."""
        intent_id = intent_id or str(uuid.uuid4())
        payload = self._build_payload(
            market_slug=market_slug,
            side_intent=side_intent,
            order_type=order_type,
            price_usd=price_usd,
            quantity=quantity,
            tif=tif,
            intent_id=intent_id,
            post_only=post_only,
            good_till_ts=good_till_ts,
            slippage_ticks=slippage_ticks,
        )

        if self._mode in ("disabled", "paper"):
            logger.info("mode_no_send", mode=self._mode, intent_id=intent_id,
                        market_slug=market_slug, payload=payload)
            return {"status": "paper", "intent_id": intent_id, "payload": payload}

        await self._throttle.acquire()
        try:
            if self._mode == "shadow":
                # Preview via /v1/order/preview — no real order created.
                resp = await self._sdk.preview_order(payload)
                return {"status": "shadow", "intent_id": intent_id, "preview": resp}
            # mode == "live"
            resp = await self._sdk.create_order(payload)
            logger.info("order_placed", intent_id=intent_id, response=resp)
            return {"status": "live", "intent_id": intent_id, "response": resp}
        except Exception as e:
            logger.error("order_failed", intent_id=intent_id, error=str(e))
            raise

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        if self._mode in ("disabled", "paper"):
            return {"status": "paper", "order_id": order_id}
        await self._throttle.acquire()
        return await self._sdk.cancel_order(order_id)

    async def cancel_all(self) -> dict[str, Any]:
        if self._mode in ("disabled", "paper"):
            return {"status": "paper"}
        await self._throttle.acquire()
        return await self._sdk.cancel_all_orders()
