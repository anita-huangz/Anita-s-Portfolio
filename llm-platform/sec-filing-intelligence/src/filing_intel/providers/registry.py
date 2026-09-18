"""Provider selection.

One place decides which backend a request goes to, so swapping Anthropic for
Bedrock -- or for replay in CI -- is a config change, not a code change.
"""

from __future__ import annotations

from ..config import Settings
from ..errors import ConfigError
from .anthropic_provider import AnthropicProvider, BedrockProvider
from .base import ModelProvider
from .replay import ReplayProvider


def build_provider(settings: Settings) -> ModelProvider:
    """Construct the configured provider.

    In replay mode with recording enabled, the replay provider wraps a live
    Anthropic client so a fixture miss records instead of failing.
    """
    if settings.provider == "anthropic":
        return AnthropicProvider()
    if settings.provider == "bedrock":
        return BedrockProvider(aws_region=_require_region(settings))
    if settings.provider == "demo":
        # Real EDGAR data, stub model. Lets the whole stack run with no key.
        from .demo import DemoProvider

        return DemoProvider()
    if settings.provider == "replay":
        recorder = AnthropicProvider() if settings.replay_record else None
        return ReplayProvider(settings.replay_dir, record_with=recorder)
    raise ConfigError(f"unknown provider: {settings.provider!r}")


def _require_region(settings: Settings) -> str:
    import os

    region = os.environ.get("AWS_REGION")
    if not region:
        raise ConfigError("provider=bedrock requires AWS_REGION to be set")
    return region
