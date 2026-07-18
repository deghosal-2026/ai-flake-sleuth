"""Configuration for ai-flake-sleuth.

Holds all user-facing and internal configuration with sensible defaults.
Buildable from argparse namespace for CLI integration.

All API keys are read from environment variables — never hardcoded.
Provider-specific keys are resolved at runtime based on the chosen LLM
provider, so the same config works for OMLX (no key), OpenAI, and DeepSeek
without any provider-specific branching in the LLM adapter.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


def _resolve_llm_api_key(provider: str) -> str | None:
    """Resolve the API key for the given LLM provider from env vars.

    Each provider has its own env var. OMLX (local) needs no key.
    This keeps keys out of code and config files — env vars only.
    """
    env_map: dict[str, str] = {
        "openai": "OPENAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "omlx": "OMLX_API_KEY",
        "opencode": "OPENCODE_API_KEY",
    }
    env_var = env_map.get(provider, "LLM_API_KEY")
    return os.environ.get(env_var)


@dataclass
class FlakeSleuthConfig:
    """Central configuration object for the agent pipeline."""

    # ── GitHub ──────────────────────────────────────────────────────────
    github_token: str | None = field(
        default_factory=lambda: os.environ.get("GITHUB_TOKEN")
    )
    per_page: int = 100
    max_retries: int = 3

    # ── Analysis ────────────────────────────────────────────────────────
    runs: int = 100
    min_sample: int = 50       # Minimum executions for flaky classification
    workflow: str | None = None
    since: str | None = None   # ISO date string

    # ── LLM ─────────────────────────────────────────────────────────────
    llm_provider: str = "omlx"
    llm_model: str = "qwen2.5-coder:7b"
    llm_endpoint: str = "http://localhost:11434"
    llm_api_key: str | None = None  # Resolved from env in from_args()
    llm_log_dir: str | None = None  # Directory for structured LLM call logs
    no_llm: bool = False
    force_llm: bool = False   # Skip rules, classify everything via LLM
    llm_limit: int = 0        # Max LLM calls (0 = no limit)
    llm_max_tokens: int = 4096  # Max completion tokens (reasoning models need room)
    llm_disable_thinking: bool = False  # Suppress reasoning trace (Qwen3 etc.)

    # ── Output ──────────────────────────────────────────────────────────
    format: str = "table"
    output: str | None = None
    cache_dir: str | None = None
    data_dir: str | None = None     # Directory for downloaded data (Phase 1)

    # ── Runtime ─────────────────────────────────────────────────────────
    verbose: bool = False
    force: bool = False              # Re-download even if data exists
    workers: int = 4                 # Parallel download workers

    @classmethod
    def from_args(cls, namespace: object) -> FlakeSleuthConfig:
        """Build a config from an argparse namespace object.

        Only copies attributes that actually exist on the namespace,
        preserving dataclass defaults (including env-var fallbacks)
        for flags the user didn't pass. Resolves LLM API key from the
        appropriate env var based on the chosen provider.
        """
        kwargs: dict[str, Any] = {}
        for field_name in cls.__dataclass_fields__:
            if hasattr(namespace, field_name):
                kwargs[field_name] = getattr(namespace, field_name)

        config = cls(**kwargs)

        # Resolve LLM API key from env if not explicitly provided.
        if not config.llm_api_key and not config.no_llm:
            config.llm_api_key = _resolve_llm_api_key(config.llm_provider)

        return config
