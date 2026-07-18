"""Tests for custom exceptions defined in exceptions.py."""

from __future__ import annotations

from flake_sleuth.exceptions import (
    FlakeSleuthError,
    GitHubAPIError,
    GraphError,
    LLMError,
    LogExpiredError,
    LogParseError,
    RateLimitExhaustedError,
)


def test_all_exceptions_inherit_base() -> None:
    """Every custom exception is a subclass of FlakeSleuthError."""
    assert issubclass(GitHubAPIError, FlakeSleuthError)
    assert issubclass(RateLimitExhaustedError, FlakeSleuthError)
    assert issubclass(LogExpiredError, FlakeSleuthError)
    assert issubclass(LogParseError, FlakeSleuthError)
    assert issubclass(LLMError, FlakeSleuthError)
    assert issubclass(GraphError, FlakeSleuthError)


def test_github_api_error() -> None:
    """GitHubAPIError carries status_code and message."""
    err = GitHubAPIError(404, "Not Found")
    assert err.status_code == 404
    assert "404" in str(err)


def test_rate_limit_exhausted() -> None:
    """RateLimitExhaustedError carries reset_at."""
    err = RateLimitExhaustedError(1712345678)
    assert err.reset_at == 1712345678
    assert "rate limit" in str(err).lower()


def test_log_expired() -> None:
    """LogExpiredError carries run_id."""
    err = LogExpiredError(1001)
    assert err.run_id == 1001
    assert "410" in str(err)


def test_log_parse_error() -> None:
    """LogParseError carries run_id and reason."""
    err = LogParseError(1001, "no regex match")
    assert err.run_id == 1001
    assert "no regex match" in str(err)


def test_llm_error() -> None:
    """LLMError carries provider and error."""
    err = LLMError("omlx", "connection refused")
    assert err.provider == "omlx"
    assert "connection refused" in str(err)


def test_graph_error() -> None:
    """GraphError carries node and error."""
    err = GraphError("fetch_runs", "rate limit exhausted")
    assert err.node == "fetch_runs"
    assert "rate limit exhausted" in str(err)
