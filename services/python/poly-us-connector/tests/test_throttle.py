"""Token-bucket correctness for the 20 rps PM US throttle."""

from __future__ import annotations

import asyncio
import time

import pytest

from poly_us_connector.throttle import TokenBucket


async def test_burst_then_steady_state() -> None:
    bucket = TokenBucket(capacity=5.0, rate=10.0)  # 10 rps, burst 5
    # First 5 calls are instant (burst).
    t0 = time.monotonic()
    for _ in range(5):
        await bucket.acquire()
    burst_dt = time.monotonic() - t0
    assert burst_dt < 0.05

    # 6th call must wait ~0.1 s for refill.
    t0 = time.monotonic()
    await bucket.acquire()
    waited = time.monotonic() - t0
    assert 0.08 <= waited <= 0.2


async def test_cost_greater_than_capacity_raises() -> None:
    bucket = TokenBucket(capacity=5.0, rate=10.0)
    with pytest.raises(ValueError, match="exceeds bucket capacity"):
        await bucket.acquire(cost=10)


async def test_concurrent_acquires_serialize_correctly() -> None:
    bucket = TokenBucket(capacity=2.0, rate=4.0)  # 4 rps, burst 2
    t0 = time.monotonic()
    await asyncio.gather(*(bucket.acquire() for _ in range(6)))
    elapsed = time.monotonic() - t0
    # 6 tokens at 4 rps with burst 2 = ~ (6-2)/4 = 1.0 s
    assert 0.9 <= elapsed <= 1.3
