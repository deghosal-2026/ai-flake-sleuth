"""Tests for FlakeSleuthConfig in config.py."""

from __future__ import annotations

from flake_sleuth.config import FlakeSleuthConfig


def test_default_config() -> None:
    """Default config uses expected defaults."""
    config = FlakeSleuthConfig()
    assert config.runs == 100
    assert config.min_sample == 50
    assert config.llm_provider == "omlx"
    assert config.format == "table"
    assert config.per_page == 100
    assert config.max_retries == 3
    assert config.no_llm is False
    assert config.verbose is False
    assert config.llm_max_tokens == 4096


def test_config_from_args() -> None:
    """from_args builds config from a namespace-like object."""

    class FakeArgs:
        github_token = "test-token"
        per_page = 50
        max_retries = 5
        runs = 200
        min_sample = 30
        workflow = "CI"
        since = "2026-07-01"
        llm_provider = "openai"
        llm_model = "gpt-4o-mini"
        llm_endpoint = "https://api.openai.com/v1"
        no_llm = False
        format = "json"
        output = "./reports/"
        cache_dir = "./.cache"
        verbose = True

    config = FlakeSleuthConfig.from_args(FakeArgs())
    assert config.github_token == "test-token"
    assert config.runs == 200
    assert config.llm_provider == "openai"
    assert config.format == "json"
    assert config.cache_dir == "./.cache"
    assert config.verbose is True


def test_config_no_llm_flag() -> None:
    """no_llm flag disables the LLM adapter."""

    class FakeArgs:
        no_llm = True
        github_token = None
        per_page = 100
        max_retries = 3
        runs = 100
        min_sample = 50
        workflow = None
        since = None
        llm_provider = "omlx"
        llm_model = "qwen2.5-coder:7b"
        llm_endpoint = "http://localhost:11434"
        format = "table"
        output = None
        cache_dir = None
        verbose = False

    config = FlakeSleuthConfig.from_args(FakeArgs())
    assert config.no_llm is True
