"""Rate limiting for a publicly reachable instance.

Two things need protecting and they are not the same. SEC EDGAR asks callers to
stay under a request rate and will block a noisy one, which is a shared-resource
problem. A live model provider costs real money per call, which is a spend
problem. The second is far more expensive to get wrong, so a public deployment
should run the demo provider; this limiter is the second line, not the first.

Deliberately in-process: it resets on restart and does not coordinate across
replicas. That is the right amount of machinery for one small instance, and the
wrong amount for a real service, which would use Redis or a gateway.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from fastapi import HTTPException, Request


@dataclass
class SlidingWindowLimiter:
    """Allows `limit` requests per `window_seconds`, tracked per client."""

    limit: int
    window_seconds: float
    #: Bounds memory: a busy instance must not accumulate a deque per IP seen.
    max_clients: int = 2048
    _hits: dict[str, deque[float]] = field(default_factory=dict, repr=False)

    def _prune(self, now: float) -> None:
        stale = [key for key, times in self._hits.items()
                 if not times or now - times[-1] > self.window_seconds * 2]
        for key in stale:
            del self._hits[key]
        if len(self._hits) > self.max_clients:
            # Drop the least recently active rather than refusing new clients.
            oldest = sorted(self._hits, key=lambda k: self._hits[k][-1])
            for key in oldest[: len(self._hits) - self.max_clients]:
                del self._hits[key]

    def check(self, client: str) -> tuple[bool, float]:
        """Return (allowed, seconds until a slot frees)."""
        now = time.monotonic()
        times = self._hits.setdefault(client, deque())
        while times and now - times[0] >= self.window_seconds:
            times.popleft()

        if len(times) >= self.limit:
            return False, self.window_seconds - (now - times[0])

        times.append(now)
        if len(self._hits) > self.max_clients // 2:
            self._prune(now)
        return True, 0.0


def client_key(request: Request) -> str:
    """Identify the caller, trusting the proxy header platforms set.

    Render, Fly and Hugging Face all terminate TLS in front of the app, so
    `request.client.host` is the proxy. The left-most X-Forwarded-For entry is
    the original client. It is spoofable -- this is abuse-dampening, not
    authentication.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce(limiter: SlidingWindowLimiter, request: Request) -> None:
    allowed, retry_after = limiter.check(client_key(request))
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit reached. Try again in {retry_after:.0f}s.",
            headers={"Retry-After": str(max(1, int(retry_after)))},
        )
