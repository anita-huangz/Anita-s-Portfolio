"""Conversation session state.

Sessions hold the message history and the accumulated usage for a line of
questioning, so a follow-up question reuses the prior turns (and their cached
prefix) instead of restarting the research from scratch.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from pydantic import Field

from ..contracts import Strict, TokenUsage
from .store import CacheBackend


class Session(Strict):
    session_id: str
    ticker: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    estimated_cost_usd: float = 0.0
    turns: int = 0


class SessionStore:
    """Sessions on top of whichever cache backend is configured."""

    def __init__(self, backend: CacheBackend, ttl_seconds: int = 86_400) -> None:
        self._backend = backend
        self._ttl = ttl_seconds

    @staticmethod
    def _key(session_id: str) -> str:
        return f"filing_intel:session:{session_id}"

    async def get(self, session_id: str) -> Session | None:
        raw = await self._backend.get(self._key(session_id))
        if raw is None:
            return None
        try:
            return Session.model_validate_json(raw)
        except ValueError:
            # A malformed or schema-drifted session is discarded rather than
            # poisoning every subsequent turn.
            await self._backend.delete(self._key(session_id))
            return None

    async def get_or_create(self, session_id: str | None, ticker: str | None = None) -> Session:
        if session_id:
            existing = await self.get(session_id)
            if existing is not None:
                return existing
        return Session(session_id=session_id or uuid.uuid4().hex, ticker=ticker)

    async def save(self, session: Session) -> None:
        await self._backend.set(
            self._key(session.session_id),
            json.dumps(session.model_dump(mode="json"), sort_keys=True, default=str),
            self._ttl,
        )

    async def delete(self, session_id: str) -> None:
        await self._backend.delete(self._key(session_id))
