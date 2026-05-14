"""WS bridge: Polymarket US → NATS.

Public market data lives at wss://api.polymarket.us/v1/ws/markets and is
unauthenticated. The authenticated user channel is /v1/ws/private and
requires Ed25519-signed handshake headers (handled by the SDK).

This connector translates inbound JSON messages into the proto schemas under
packages/schemas/proto/marketdata.proto and publishes them on NATS subjects
md.poly_us.<slug>.{book,trade,heartbeat}.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator

import structlog
import websockets

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

PUBLIC_WS_URL: str = "wss://api.polymarket.us/v1/ws/markets"
PRIVATE_WS_URL: str = "wss://api.polymarket.us/v1/ws/private"
REST_BASE: str = "https://api.polymarket.us"


@dataclass(frozen=True, slots=True)
class PolyUsConfig:
    key_id: str
    secret_b64: str            # base64-encoded Ed25519 private key (from polymarket.us/developer)
    market_slugs: tuple[str, ...]
    nats_url: str = "nats://localhost:4222"
    public_ws_url: str = PUBLIC_WS_URL
    private_ws_url: str = PRIVATE_WS_URL
    reconnect_initial_s: float = 1.0
    reconnect_max_s: float = 30.0
    heartbeat_period_s: float = 5.0


class PolyUsConnector:
    """Subscribes to PM US WS and re-publishes to NATS.

    Lazily imports `polymarket_us` to keep the module importable for tests.
    """

    def __init__(self, config: PolyUsConfig) -> None:
        self._cfg = config
        self._nc: Any = None
        self._sdk_client: Any = None
        self._running = False

    async def _connect_nats(self) -> None:
        from nats.aio.client import Client as NATSClient

        nc = NATSClient()
        await nc.connect(servers=[self._cfg.nats_url], name="poly-us-connector")
        self._nc = nc

    async def _init_sdk(self) -> None:
        """Create an authenticated SDK client for the private channel + REST."""
        try:
            from polymarket_us import PolymarketUS  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError(
                "polymarket-us SDK not installed. `uv pip install polymarket-us`"
            ) from e
        self._sdk_client = PolymarketUS(key_id=self._cfg.key_id, secret_key=self._cfg.secret_b64)
        await self._sdk_client.authenticate()

    async def _subscribe_public(self) -> AsyncIterator[dict[str, Any]]:
        """Yield raw JSON messages from the public WS, with reconnect."""
        backoff = self._cfg.reconnect_initial_s
        while self._running:
            try:
                async with websockets.connect(self._cfg.public_ws_url) as ws:
                    sub = {"type": "subscribe", "channels": ["orderbook", "trades"],
                           "markets": list(self._cfg.market_slugs)}
                    await ws.send(json.dumps(sub))
                    logger.info("public_ws_subscribed", markets=len(self._cfg.market_slugs))
                    backoff = self._cfg.reconnect_initial_s
                    async for raw in ws:
                        try:
                            yield json.loads(raw)
                        except json.JSONDecodeError:
                            logger.warning("public_ws_bad_json", raw=raw[:200])
            except Exception as e:
                logger.warning("public_ws_dropped", error=str(e), backoff_s=backoff)
                await asyncio.sleep(backoff)
                backoff = min(self._cfg.reconnect_max_s, backoff * 2)

    async def _publish_book(self, market_slug: str, msg: dict[str, Any]) -> None:
        """Convert a PM US book message → BookDelta proto → NATS publish."""
        # NOTE: actual proto encoding will land once codegen is wired up.
        # For now publish JSON to NATS so downstream services can iterate.
        if self._nc is None:
            return
        subject = f"md.poly_us.{market_slug}.book"
        await self._nc.publish(subject, json.dumps(msg).encode())

    async def _publish_trade(self, market_slug: str, msg: dict[str, Any]) -> None:
        if self._nc is None:
            return
        subject = f"md.poly_us.{market_slug}.trade"
        await self._nc.publish(subject, json.dumps(msg).encode())

    async def _emit_heartbeat(self) -> None:
        while self._running:
            if self._nc is not None:
                hb = {"ts_ms": int(asyncio.get_event_loop().time() * 1000), "connected": True}
                await self._nc.publish("md.poly_us.heartbeat", json.dumps(hb).encode())
            await asyncio.sleep(self._cfg.heartbeat_period_s)

    async def run(self) -> None:
        self._running = True
        await self._connect_nats()
        await self._init_sdk()
        hb_task = asyncio.create_task(self._emit_heartbeat())
        try:
            async for msg in self._subscribe_public():
                channel = msg.get("channel")
                slug = msg.get("market") or msg.get("marketSlug", "")
                if channel == "orderbook":
                    await self._publish_book(slug, msg)
                elif channel == "trades":
                    await self._publish_trade(slug, msg)
        finally:
            self._running = False
            hb_task.cancel()
            if self._nc is not None:
                await self._nc.drain()

    async def stop(self) -> None:
        self._running = False
