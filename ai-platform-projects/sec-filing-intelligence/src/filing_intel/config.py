"""Runtime configuration, read once from the environment.

Kept deliberately small: anything that varies per request belongs on the request
model, not here.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["anthropic", "bedrock", "replay", "demo"]
EffortLevel = Literal["low", "medium", "high", "xhigh", "max"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FILING_INTEL_", env_file=".env", extra="ignore"
    )

    provider: ProviderName = "replay"
    model: str = "claude-opus-5"
    effort: EffortLevel = "high"
    max_tokens: int = 16000

    # Redis is optional everywhere. Unset means "use the in-process cache",
    # which implements the same interface with the same TTL semantics.
    redis_url: str | None = None
    cache_ttl_seconds: int = 3600
    session_ttl_seconds: int = 86400

    sec_user_agent: str = "filing-intel/0.1 (contact@example.com)"
    sec_base_url: str = "https://data.sec.gov"
    sec_www_url: str = "https://www.sec.gov"
    http_timeout_seconds: float = 30.0

    # Directory of recorded model responses used by the replay provider.
    replay_dir: str = "tests/fixtures/replay"
    # When True, a replay miss records a real call instead of raising.
    replay_record: bool = False

    agent_max_tool_calls: int = Field(default=8, ge=1, le=40)

    #: Requests per client per minute on the research routes. A public
    #: instance is reachable by anyone, and each research call fans out into
    #: several EDGAR requests.
    rate_limit_per_minute: int = Field(default=6, ge=1, le=600)

    #: Refuse to start with a live model provider while exposed publicly.
    #: An unauthenticated endpoint backed by a real API key is someone else's
    #: budget to spend.
    public_demo: bool = False

    #: Origins allowed to call the API from a browser. The Vite dev server
    #: runs on 5173; a deployment serving the built UI from the same origin
    #: needs none of these.
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    @field_validator("sec_user_agent")
    @classmethod
    def _require_contact(cls, v: str) -> str:
        # EDGAR rejects generic agents with a 403, and the failure is opaque.
        # Catching it here turns a confusing runtime 403 into a startup error.
        if "@" not in v:
            raise ValueError(
                "sec_user_agent must include a contact email; SEC EDGAR returns 403 otherwise"
            )
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
