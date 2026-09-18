"""Error taxonomy.

Every failure the platform can produce maps onto one of these, so telemetry can
group failures by cause rather than by whatever string the underlying library
happened to raise.
"""

from __future__ import annotations


class FilingIntelError(Exception):
    """Base class for every error this package raises deliberately."""

    #: Stable, low-cardinality label recorded on telemetry events.
    kind = "unknown"


class ConfigError(FilingIntelError):
    kind = "config"


class ProviderError(FilingIntelError):
    """A model provider refused, failed, or was unreachable."""

    kind = "provider"


class ProviderRefusal(ProviderError):
    """The model declined the request (`stop_reason == "refusal"`)."""

    kind = "refusal"

    def __init__(self, message: str, category: str | None = None) -> None:
        super().__init__(message)
        self.category = category


class ReplayMiss(ProviderError):
    """Replay mode was asked for a request that has no recorded fixture."""

    kind = "replay_miss"


class UpstreamDataError(FilingIntelError):
    """SEC EDGAR or a price source returned something unusable."""

    kind = "upstream_data"


class ToolExecutionError(FilingIntelError):
    kind = "tool_execution"


class ToolNotPermitted(ToolExecutionError):
    """A caller asked for a tool outside its granted capability set."""

    kind = "tool_not_permitted"


class ToolInputInvalid(ToolExecutionError):
    """Tool arguments failed their Pydantic contract."""

    kind = "tool_input_invalid"
