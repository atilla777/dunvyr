"""Primitive in-process sliding-window rate limit for campaign creation.

State is intentionally per-process and separate from the identity bucket: the
MVP runs a single server process and no external store is introduced. A restart
resets the counters, which is an accepted limitation of the primitive limiter.
"""

from __future__ import annotations

import math
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from dunvyr.campaigns.application.ports import Clock


@dataclass(frozen=True, slots=True)
class CampaignRateLimitPolicy:
    limit: int = 10
    window: timedelta = timedelta(seconds=60)


class CampaignSlidingWindowRateLimiter:
    def __init__(self, *, policy: CampaignRateLimitPolicy, clock: Clock) -> None:
        self._policy = policy
        self._clock = clock
        self._events: dict[str, list[datetime]] = defaultdict(list)
        self._lock = threading.Lock()

    def hit(self, key: str) -> int | None:
        """Record a request; return retry-after seconds if the limit is exceeded."""
        now = self._clock()
        cutoff = now - self._policy.window
        with self._lock:
            events = [event for event in self._events[key] if event > cutoff]
            if len(events) >= self._policy.limit:
                self._events[key] = events
                retry_after = (events[0] + self._policy.window - now).total_seconds()
                return max(1, math.ceil(retry_after))
            events.append(now)
            self._events[key] = events
            return None
