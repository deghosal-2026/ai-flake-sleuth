from __future__ import annotations

import io
import os
import time
import zipfile
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from flake_sleuth.exceptions import (
    GitHubAPIError,
    LogExpiredError,
    RateLimitExhaustedError,
)
from flake_sleuth.github_client import GitHubClient


@pytest.fixture(autouse=True)
def _no_wait(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable _wait_if_needed for tests that don't explicitly test it."""
    if "test_wait_if_needed" not in request.node.name:
        monkeypatch.setattr(GitHubClient, "_wait_if_needed", lambda self: None)


# ─── Init ───


def test_init_no_token_raises() -> None:
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="GITHUB_TOKEN"):
            GitHubClient(token=None)


def test_init_with_token() -> None:
    client = GitHubClient(token="gh_test_token")
    assert client.token == "gh_test_token"


def test_init_from_env() -> None:
    with patch.dict(os.environ, {"GITHUB_TOKEN": "gh_env_token"}, clear=True):
        client = GitHubClient()
        assert client.token == "gh_env_token"


# ─── Rate limit ───


@patch("flake_sleuth.github_client.Github")
def test_check_rate_limit(mock_github: MagicMock) -> None:
    mock_rate = MagicMock()
    mock_rate.rate.remaining = 42
    mock_rate.rate.reset.timestamp.return_value = 1712345678.0
    mock_rate.rate.limit = 5000
    mock_github.return_value.get_rate_limit.return_value = mock_rate

    client = GitHubClient(token="gh_test")
    result = client.check_rate_limit()
    assert result["remaining"] == 42
    assert result["reset"] == 1712345678
    assert result["limit"] == 5000


@patch("flake_sleuth.github_client.Github")
@patch("flake_sleuth.github_client.time")
def test_wait_if_needed_sleeps(mock_time: MagicMock, _mock_github: MagicMock) -> None:
    mock_rate = MagicMock()
    mock_time.time.return_value = 1712345600.0
    mock_rate.rate.remaining = 5
    mock_rate.rate.reset.timestamp.return_value = mock_time.time.return_value + 10
    mock_rate.rate.limit = 5000
    _mock_github.return_value.get_rate_limit.return_value = mock_rate

    client = GitHubClient(token="gh_test")
    client._wait_if_needed()
    mock_time.sleep.assert_called_once()


@patch("flake_sleuth.github_client.Github")
def test_wait_if_needed_skips_when_ok(mock_github: MagicMock) -> None:
    mock_rate = MagicMock()
    mock_rate.rate.remaining = 500
    mock_rate.rate.reset.timestamp.return_value = time.time() + 60
    mock_rate.rate.limit = 5000
    mock_github.return_value.get_rate_limit.return_value = mock_rate

    client = GitHubClient(token="gh_test")
    client._wait_if_needed()


# ─── fetch_runs ───


@patch("flake_sleuth.github_client.Github")
def test_fetch_runs(mock_github: MagicMock) -> None:
    mock_run = MagicMock()
    mock_run.id = 1001
    mock_run.name = "CI"
    mock_run.status = "completed"
    mock_run.conclusion = "success"
    mock_run.created_at = datetime(2026, 7, 16, tzinfo=UTC)
    mock_run.html_url = "https://github.com/owner/repo/actions/runs/1001"

    mock_repo = MagicMock()
    mock_repo.get_workflow_runs.return_value = [mock_run]
    mock_github.return_value.get_repo.return_value = mock_repo

    client = GitHubClient(token="gh_test")
    runs = client.fetch_runs("owner/repo", n=10)
    assert len(runs) == 1
    assert runs[0].run_id == 1001
    assert runs[0].conclusion == "success"


@patch("flake_sleuth.github_client.Github")
def test_fetch_runs_with_workflow_filter(mock_github: MagicMock) -> None:
    mock_run = MagicMock()
    mock_run.id = 1002
    mock_run.name = "Lint"
    mock_run.status = "completed"
    mock_run.conclusion = "failure"
    mock_run.created_at = datetime(2026, 7, 16, tzinfo=UTC)
    mock_run.html_url = ""

    mock_wf = MagicMock()
    mock_wf.get_runs.return_value = [mock_run]
    mock_repo = MagicMock()
    mock_repo.get_workflow.return_value = mock_wf
    mock_github.return_value.get_repo.return_value = mock_repo

    client = GitHubClient(token="gh_test")
    runs = client.fetch_runs("owner/repo", n=10, workflow="lint.yml")
    assert len(runs) == 1
    mock_repo.get_workflow.assert_called_once_with("lint.yml")
    mock_wf.get_runs.assert_called_once()


@patch("flake_sleuth.github_client.Github")
def test_fetch_runs_with_since_filter(mock_github: MagicMock) -> None:
    mock_repo = MagicMock()
    mock_repo.get_workflow_runs.return_value = []
    mock_github.return_value.get_repo.return_value = mock_repo

    since = datetime(2026, 7, 1, tzinfo=UTC)
    client = GitHubClient(token="gh_test")
    runs = client.fetch_runs("owner/repo", n=10, since=since)
    assert runs == []
    mock_repo.get_workflow_runs.assert_called_once_with(created=since)


@patch("flake_sleuth.github_client.Github")
def test_fetch_runs_respects_limit(mock_github: MagicMock) -> None:
    mock_run = MagicMock()
    mock_run.id = 1
    mock_run.name = "CI"
    mock_run.status = "completed"
    mock_run.conclusion = "success"
    mock_run.created_at = datetime(2026, 7, 16, tzinfo=UTC)
    mock_run.html_url = ""

    mock_repo = MagicMock()
    mock_repo.get_workflow_runs.return_value = iter([mock_run] * 20)
    mock_github.return_value.get_repo.return_value = mock_repo

    client = GitHubClient(token="gh_test")
    runs = client.fetch_runs("owner/repo", n=5)
    assert len(runs) == 5


# ─── fetch_run_jobs ───


@patch("flake_sleuth.github_client.Github")
def test_fetch_run_jobs(mock_github: MagicMock) -> None:
    mock_job = MagicMock()
    mock_job.id = 10010
    mock_job.name = "test (3.11)"
    mock_job.conclusion = "failure"
    mock_job.logs_url = "https://api.github.com/logs"

    mock_run = MagicMock()
    mock_run.jobs.return_value = [mock_job]
    mock_repo = MagicMock()
    mock_repo.get_workflow_run.return_value = mock_run
    mock_github.return_value.get_repo.return_value = mock_repo

    client = GitHubClient(token="gh_test")
    jobs = client.fetch_run_jobs("owner/repo", 1001)
    assert len(jobs) == 1
    assert jobs[0].job_id == 10010
    assert jobs[0].name == "test (3.11)"
    assert jobs[0].conclusion == "failure"


# ─── fetch_logs ───


def _zip_bytes(content: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in content.items():
            zf.writestr(name, text)
    return buf.getvalue()


@patch("flake_sleuth.github_client.Github")
@patch("flake_sleuth.github_client.requests")
@patch("flake_sleuth.github_client.time")
def test_fetch_logs_success(
    mock_time: MagicMock,
    mock_requests: MagicMock,
    _mock_github: MagicMock,
) -> None:
    raw_zip = _zip_bytes({"test_log.txt": "test passed"})

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = raw_zip
    mock_requests.get.return_value = mock_resp

    client = GitHubClient(token="gh_test")
    logs = client.fetch_logs("owner/repo", 1001)
    assert logs is not None
    assert "test_log.txt" in logs
    assert logs["test_log.txt"] == "test passed"


@patch("flake_sleuth.github_client.Github")
@patch("flake_sleuth.github_client.requests")
@patch("flake_sleuth.github_client.time")
def test_fetch_logs_404_returns_none(
    mock_time: MagicMock,
    mock_requests: MagicMock,
    _mock_github: MagicMock,
) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_requests.get.return_value = mock_resp

    client = GitHubClient(token="gh_test")
    logs = client.fetch_logs("owner/repo", 1001)
    assert logs is None


@patch("flake_sleuth.github_client.Github")
@patch("flake_sleuth.github_client.requests")
@patch("flake_sleuth.github_client.time")
def test_fetch_logs_410_raises_expired(
    mock_time: MagicMock,
    mock_requests: MagicMock,
    _mock_github: MagicMock,
) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 410
    mock_requests.get.return_value = mock_resp

    client = GitHubClient(token="gh_test")
    with pytest.raises(LogExpiredError):
        client.fetch_logs("owner/repo", 1001)


@patch("flake_sleuth.github_client.Github")
@patch("flake_sleuth.github_client.requests")
@patch("flake_sleuth.github_client.time")
def test_fetch_logs_429_exhausts_retries(
    mock_time: MagicMock,
    mock_requests: MagicMock,
    _mock_github: MagicMock,
) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.headers = {}
    mock_requests.get.return_value = mock_resp

    client = GitHubClient(token="gh_test", max_retries=1)
    with pytest.raises(RateLimitExhaustedError):
        client.fetch_logs("owner/repo", 1001)
    assert mock_requests.get.call_count == 2  # initial + 1 retry


@patch("flake_sleuth.github_client.Github")
@patch("flake_sleuth.github_client.requests")
@patch("flake_sleuth.github_client.time")
def test_fetch_logs_401_raises(
    mock_time: MagicMock,
    mock_requests: MagicMock,
    _mock_github: MagicMock,
) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.reason = "Unauthorized"
    mock_requests.get.return_value = mock_resp

    client = GitHubClient(token="gh_test")
    with pytest.raises(GitHubAPIError, match="401"):
        client.fetch_logs("owner/repo", 1001)


@patch("flake_sleuth.github_client.Github")
@patch("flake_sleuth.github_client.requests")
@patch("flake_sleuth.github_client.time")
def test_fetch_logs_5xx_retries_then_raises(
    mock_time: MagicMock,
    mock_requests: MagicMock,
    _mock_github: MagicMock,
) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.reason = "Service Unavailable"
    mock_requests.get.return_value = mock_resp

    client = GitHubClient(token="gh_test", max_retries=1)
    with pytest.raises(GitHubAPIError, match="503"):
        client.fetch_logs("owner/repo", 1001)
    assert mock_requests.get.call_count == 2


@patch("flake_sleuth.github_client.Github")
@patch("flake_sleuth.github_client.requests")
@patch("flake_sleuth.github_client.time")
def test_fetch_logs_5xx_retry_then_success(
    mock_time: MagicMock,
    mock_requests: MagicMock,
    _mock_github: MagicMock,
) -> None:
    raw_zip = _zip_bytes({"log.txt": "ok"})

    mock_503 = MagicMock(status_code=503, reason="Service Unavailable")
    mock_200 = MagicMock(status_code=200, content=raw_zip)
    mock_requests.get.side_effect = [mock_503, mock_200]

    client = GitHubClient(token="gh_test", max_retries=1)
    logs = client.fetch_logs("owner/repo", 1001)
    assert logs is not None
    assert "log.txt" in logs


@patch("flake_sleuth.github_client.Github")
@patch("flake_sleuth.github_client.requests")
@patch("flake_sleuth.github_client.time")
def test_fetch_logs_request_exception_retries_then_raises(
    mock_time: MagicMock,
    mock_requests: MagicMock,
    _mock_github: MagicMock,
) -> None:
    # The patched mock doesn't have a real RequestException class, so we
    # inject one so that the except clause in fetch_logs can catch it.
    mock_requests.RequestException = type("RequestException", (Exception,), {})
    mock_requests.get.side_effect = mock_requests.RequestException("connection reset")

    client = GitHubClient(token="gh_test", max_retries=1)
    with pytest.raises(GitHubAPIError):
        client.fetch_logs("owner/repo", 1001)
    assert mock_requests.get.call_count == 2


@patch("flake_sleuth.github_client.Github")
@patch("flake_sleuth.github_client.requests")
@patch("flake_sleuth.github_client.time")
def test_fetch_logs_request_exception_then_success(
    mock_time: MagicMock,
    mock_requests: MagicMock,
    _mock_github: MagicMock,
) -> None:
    mock_requests.RequestException = type("RequestException", (Exception,), {})
    raw_zip = _zip_bytes({"log.txt": "recovered"})
    mock_requests.get.side_effect = [
        mock_requests.RequestException("timeout"),
        MagicMock(status_code=200, content=raw_zip),
    ]

    client = GitHubClient(token="gh_test", max_retries=1)
    logs = client.fetch_logs("owner/repo", 1001)
    assert logs is not None
    assert "log.txt" in logs


@patch("flake_sleuth.github_client.Github")
@patch("flake_sleuth.github_client.requests")
@patch("flake_sleuth.github_client.time")
def test_fetch_logs_caches_on_success(
    mock_time: MagicMock,
    mock_requests: MagicMock,
    _mock_github: MagicMock,
) -> None:
    import tempfile

    from flake_sleuth.cache import FileCache

    raw_zip = _zip_bytes({"log.txt": "test"})

    mock_resp = MagicMock(status_code=200, content=raw_zip)
    mock_requests.get.return_value = mock_resp

    with tempfile.TemporaryDirectory() as tmpdir:
        cache = FileCache(tmpdir)
        client = GitHubClient(token="gh_test", cache=cache)
        logs = client.fetch_logs("owner/repo", 1001)
        assert logs is not None
        assert cache.has("owner/repo", "logs_1001")


@patch("flake_sleuth.github_client.Github")
@patch("flake_sleuth.github_client.requests")
@patch("flake_sleuth.github_client.time")
def test_fetch_logs_cache_hit(
    mock_time: MagicMock,
    mock_requests: MagicMock,
    _mock_github: MagicMock,
) -> None:
    import tempfile

    from flake_sleuth.cache import FileCache

    raw_zip = _zip_bytes({"cached_log.txt": "cached"})

    with tempfile.TemporaryDirectory() as tmpdir:
        cache = FileCache(tmpdir)
        cache.set("owner/repo", "logs_1001", raw_zip)
        client = GitHubClient(token="gh_test", cache=cache)
        logs = client.fetch_logs("owner/repo", 1001)
        assert logs is not None
        assert "cached_log.txt" in logs
        mock_requests.get.assert_not_called()


# ─── _unzip_bytes ───


def test_unzip_bytes() -> None:
    raw = _zip_bytes({"a.txt": "alpha", "b.txt": "beta"})
    result = GitHubClient._unzip_bytes(raw)
    assert result == {"a.txt": "alpha", "b.txt": "beta"}


# ─── _parse_reset_header ───


def test_parse_reset_header_valid() -> None:
    from flake_sleuth.github_client import _parse_reset_header

    assert _parse_reset_header("1712345678") == 1712345678


def test_parse_reset_header_none() -> None:
    from flake_sleuth.github_client import _parse_reset_header

    result = _parse_reset_header(None)
    assert result >= int(time.time())


def test_parse_reset_header_invalid() -> None:
    from flake_sleuth.github_client import _parse_reset_header

    result = _parse_reset_header("not_a_number")
    assert result >= int(time.time())
