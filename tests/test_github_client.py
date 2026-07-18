"""Tests for GitHubClient in github_client.py.

Most tests use the MockGitHubClient to avoid real network calls.
Real API tests are marked as integration and run separately.
"""

from __future__ import annotations

from datetime import UTC, datetime

from tests.fixtures.mock_github_api import MockGitHubClient


def test_mock_fetch_runs_default() -> None:
    """Mock client returns all fixture runs by default."""
    client = MockGitHubClient()
    runs = client.fetch_runs("pytest-dev/pytest")
    assert len(runs) == 10


def test_mock_fetch_runs_limit() -> None:
    """Mock client respects the n parameter."""
    client = MockGitHubClient()
    runs = client.fetch_runs("pytest-dev/pytest", n=3)
    assert len(runs) == 3


def test_mock_fetch_runs_workflow_filter() -> None:
    """Mock client filters by workflow name."""
    client = MockGitHubClient()
    runs = client.fetch_runs("pytest-dev/pytest", workflow="CI")
    assert all(r.workflow_name == "CI" for r in runs)


def test_mock_fetch_runs_since_filter() -> None:
    """Mock client filters by since date."""
    client = MockGitHubClient()
    since = datetime(2026, 7, 15, tzinfo=UTC)
    runs = client.fetch_runs("pytest-dev/pytest", since=since)
    assert all(r.timestamp >= since for r in runs)


def test_mock_fetch_run_jobs() -> None:
    """Mock client returns a single job per run."""
    client = MockGitHubClient()
    jobs = client.fetch_run_jobs("pytest-dev/pytest", 1001)
    assert len(jobs) == 1
    assert jobs[0].job_id == 10010
    assert jobs[0].conclusion == "failure"


def test_mock_fetch_logs_successful_run() -> None:
    """Mock client returns clean_run log for successful runs."""
    client = MockGitHubClient()
    logs = client.fetch_logs("pytest-dev/pytest", 1003)
    assert logs is not None
    assert "3 passed" in logs["job_log.txt"]


def test_mock_fetch_logs_failed_run() -> None:
    """Mock client returns pytest_failed log for CI failures."""
    client = MockGitHubClient()
    logs = client.fetch_logs("pytest-dev/pytest", 1001)
    assert logs is not None
    assert "FAILED" in logs["job_log.txt"]


def test_mock_fetch_logs_expired() -> None:
    """Mock client returns None for expired log runs."""
    client = MockGitHubClient()
    logs = client.fetch_logs("pytest-dev/pytest", 1006)
    assert logs is None


def test_mock_fetch_logs_unknown_run() -> None:
    """Mock client returns None for run IDs not in the fixture."""
    client = MockGitHubClient()
    logs = client.fetch_logs("pytest-dev/pytest", 9999)
    assert logs is None


def test_mock_check_rate_limit() -> None:
    """Mock rate-limit returns healthy status."""
    client = MockGitHubClient()
    status = client.check_rate_limit()
    assert status["remaining"] == 4999
    assert status["limit"] == 5000
