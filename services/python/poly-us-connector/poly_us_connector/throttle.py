"""Async token-bucket throttle. Enforces the 20 rps PM US global cap."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


@dataclass
class TokenBucket:
    """Classic token bucket.

    Capacity = bucket size (max burst). Rate = tokens added per second.
    Default for Polymarket US: capacity=20, rate=20.0 (20 rps global).
    """

    capacity: float
    rate: float
    _tokens: float = 0.0
    _last_ts: float = 0.0
    _lock: asyncio.Lock = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._tokens = self.capacity
        self._last_ts = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, cost: float = 1.0) -> None:
        """Block until `cost` tokens are available."""
        if cost > self.capacity:
            raise ValueError(f"cost {cost} exceeds bucket capacity {self.capacity}")
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_ts
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
                self._last_ts = now
                if self._tokens >= cost:
                    self._tokens -= cost
                    return
                wait_s = (cost - self._tokens) / self.rate
            await asyncio.sleep(wait_s)
