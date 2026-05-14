"""Tests for the PM US executor — focused on invariants the risk engine
relies on (manualOrderIndicator, client_order_id, throttling, mode gating)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from poly_us_connector.executor import PolyUsExecutor


class _FakeSDK:
    def __init__(self) -> None:
        self.create_order = AsyncMock(return_value={"orderId": "abc"})
        self.preview_order = AsyncMock(return_value={"valid": True})
        self.cancel_order = AsyncMock(return_value={"canceled": True})
        self.cancel_all_orders = AsyncMock(return_value={"canceled": 7})


@pytest.fixture
def sdk() -> _FakeSDK:
    return _FakeSDK()


def _basic_kwargs(intent_id: str = "intent-xyz") -> dict[str, Any]:
    return {
        "market_slug": "super-bowl-lix-chiefs-vs-eagles",
        "side_intent": "ORDER_INTENT_BUY_LONG",
        "order_type": "ORDER_TYPE_LIMIT",
        "price_usd": "0.55",
        "quantity": 100,
        "intent_id": intent_id,
    }


async def test_payload_always_marks_automatic(sdk: _FakeSDK) -> None:
    exe = PolyUsExecutor(sdk, mode="live")
    await exe.place_order(**_basic_kwargs())
    payload = sdk.create_order.await_args.args[0]
    assert payload["manualOrderIndicator"] == "MANUAL_ORDER_INDICATOR_AUTOMATIC"


async def test_payload_uses_intent_id_as_client_order_id(sdk: _FakeSDK) -> None:
    exe = PolyUsExecutor(sdk, mode="live")
    await exe.place_order(**_basic_kwargs(intent_id="my-intent-77"))
    payload = sdk.create_order.await_args.args[0]
    assert payload["clientOrderId"] == "my-intent-77"


async def test_paper_mode_does_not_call_sdk(sdk: _FakeSDK) -> None:
    exe = PolyUsExecutor(sdk, mode="paper")
    out = await exe.place_order(**_basic_kwargs())
    assert out["status"] == "paper"
    sdk.create_order.assert_not_awaited()


async def test_disabled_mode_does_not_call_sdk(sdk: _FakeSDK) -> None:
    exe = PolyUsExecutor(sdk, mode="disabled")
    out = await exe.place_order(**_basic_kwargs())
    assert out["status"] == "paper"  # treated the same: no traffic
    sdk.create_order.assert_not_awaited()


async def test_shadow_mode_calls_preview(sdk: _FakeSDK) -> None:
    exe = PolyUsExecutor(sdk, mode="shadow")
    out = await exe.place_order(**_basic_kwargs())
    assert out["status"] == "shadow"
    sdk.preview_order.assert_awaited_once()
    sdk.create_order.assert_not_awaited()


async def test_post_only_sets_participate_dont_initiate(sdk: _FakeSDK) -> None:
    exe = PolyUsExecutor(sdk, mode="live")
    await exe.place_order(**_basic_kwargs(), post_only=True)
    payload = sdk.create_order.await_args.args[0]
    assert payload["participateDontInitiate"] is True


async def test_gtd_requires_good_till_ts(sdk: _FakeSDK) -> None:
    exe = PolyUsExecutor(sdk, mode="live")
    with pytest.raises(ValueError, match="good_till_ts"):
        await exe.place_order(**_basic_kwargs(), tif="TIME_IN_FORCE_GOOD_TILL_DATE")


async def test_market_order_with_slippage_includes_tolerance(sdk: _FakeSDK) -> None:
    exe = PolyUsExecutor(sdk, mode="live")
    await exe.place_order(
        **(_basic_kwargs() | {"order_type": "ORDER_TYPE_MARKET"}),
        slippage_ticks=5,
    )
    payload = sdk.create_order.await_args.args[0]
    assert payload["slippageTolerance"]["ticks"] == 5
