"""Tests for the Downloader module in downloader.py.

Covers: download, resume, selective download, manifest management,
load_data, load_logs, ZIP validation, pre-flight checks, and the
--all-runs flag. All network calls are mocked.
"""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from flake_sleuth.downloader import Downloader, DownloadResult

# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> str:
    """Return a temporary data directory path."""
    return str(tmp_path / "data")


@pytest.fixture
def downloader(tmp_data_dir: str) -> Downloader:
    """Return a Downloader with a temp data dir and mock token."""
    return Downloader(
        token="fake-token",
        data_dir=tmp_data_dir,
        per_page=10,
        max_retries=2,
        workers=2,
    )


def _make_mock_run(run_id: int, conclusion: str = "failure") -> MagicMock:
    """Create a mock PyGithub WorkflowRun object."""
    mock_run = MagicMock()
    mock_run.id = run_id
    mock_run.name = "CI"
    mock_run.status = "completed"
    mock_run.conclusion = conclusion
    mock_run.created_at = datetime(2026, 7, 16, 10, 0, tzinfo=UTC)
    mock_run.html_url = f"https://github.com/test/repo/actions/runs/{run_id}"
    return mock_run


def _make_mock_job(job_id: int, conclusion: str = "failure") -> MagicMock:
    """Create a mock PyGithub WorkflowJob object."""
    mock_job = MagicMock()
    mock_job.id = job_id
    mock_job.name = "test (3.11)"
    mock_job.conclusion = conclusion
    mock_job.logs_url = f"https://api.github.com/repos/test/actions/runs/{job_id}/logs"
    return mock_job


def _make_mock_repo(runs: list[MagicMock] | None = None) -> MagicMock:
    """Create a mock PyGithub Repository with get_workflow_runs."""
    repo = MagicMock()
    run_gen = iter(runs or [_make_mock_run(1001)])
    repo.get_workflow_runs.return_value = run_gen
    return repo


def _make_zip_bytes() -> bytes:
    """Return a valid ZIP archive containing one log file."""
    import io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("job_log.txt", "test_foo FAILED\n1 failed in 0.5s")
    return buf.getvalue()


# ── DownloadResult ─────────────────────────────────────────────────────


def test_download_result_str() -> None:
    """DownloadResult.__str__ includes key fields."""
    result = DownloadResult(
        repo="pytest-dev/pytest",
        runs_fetched=100,
        runs_downloaded=80,
        runs_skipped_expired=15,
        runs_skipped_error=5,
        runs_with_failures=50,
        runs_with_logs=45,
        status="complete",
    )
    s = str(result)
    assert "runs_fetched=100" in s
    assert "status=complete" in s


def test_download_result_to_dict() -> None:
    """DownloadResult.to_dict returns all fields."""
    result = DownloadResult(
        repo="test/repo",
        runs_fetched=10,
        runs_downloaded=8,
        runs_skipped_expired=1,
        runs_skipped_error=1,
        runs_with_failures=5,
        runs_with_logs=4,
        status="complete",
    )
    d = result.to_dict()
    assert d["repo"] == "test/repo"
    assert d["runs_fetched"] == 10
    assert d["status"] == "complete"


# ── Manifest ───────────────────────────────────────────────────────────


def test_manifest_created_on_download(downloader: Downloader) -> None:
    """A manifest.json is created after download."""
    runs = [_make_mock_run(1001, "failure"), _make_mock_run(1002, "success")]
    repo = _make_mock_repo(runs)
    downloader.gh.get_repo = MagicMock(return_value=repo)

    mock_job = _make_mock_job(10010)
    repo.get_workflow_run.return_value.jobs.return_value = [mock_job]

    zip_bytes = _make_zip_bytes()
    with patch("flake_sleuth.downloader.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = zip_bytes
        mock_get.return_value = mock_resp

        downloader.download("test/repo", n=2)

    manifest_path = downloader._manifest_path("test/repo")
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["status"] == "complete"
    assert manifest["runs_fetched"] == 2
    assert manifest["runs_with_failures"] == 1


def test_manifest_skips_completed_download(downloader: Downloader) -> None:
    """Re-running download on a completed manifest is a no-op."""
    # Write a completed manifest first
    manifest = {
        "repo": "test/repo",
        "runs_requested": 10,
        "runs_fetched": 10,
        "runs_downloaded": 8,
        "runs_skipped_expired": 1,
        "runs_skipped_error": 1,
        "runs_with_failures": 5,
        "runs_with_logs": 4,
        "status": "complete",
        "started_at": "2026-07-22T10:00:00Z",
        "completed_at": "2026-07-22T10:05:00Z",
        "last_run_id_processed": 1010,
        "processed_run_ids": ["1001", "1002"],
        "offsets_downloaded": [[0, 10]],
    }
    downloader._save_manifest("test/repo", manifest)

    result = downloader.download("test/repo", n=10)
    assert result.status == "complete"
    assert result.runs_fetched == 10


def test_manifest_resume_from_in_progress(downloader: Downloader) -> None:
    """Resume picks up from in_progress manifest."""
    manifest = {
        "repo": "test/repo",
        "runs_requested": 3,
        "runs_fetched": 0,
        "runs_downloaded": 0,
        "runs_skipped_expired": 0,
        "runs_skipped_error": 0,
        "runs_with_failures": 0,
        "runs_with_logs": 0,
        "status": "in_progress",
        "started_at": "2026-07-22T10:00:00Z",
        "completed_at": None,
        "last_run_id_processed": None,
        "processed_run_ids": ["1001"],
    }
    downloader._save_manifest("test/repo", manifest)

    runs = [_make_mock_run(1001, "failure"), _make_mock_run(1002, "failure")]
    repo = _make_mock_repo(runs)
    downloader.gh.get_repo = MagicMock(return_value=repo)
    repo.get_workflow_run.return_value.jobs.return_value = [_make_mock_job(10010)]

    with patch("flake_sleuth.downloader.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = _make_zip_bytes()
        mock_get.return_value = mock_resp

        result = downloader.download("test/repo", n=3)

    # run 1001 should be skipped (in processed_run_ids), 1002 downloaded
    assert result.status == "complete"


# ── Run metadata saving ────────────────────────────────────────────────


def test_run_metadata_saved_as_json(downloader: Downloader) -> None:
    """Each run's metadata is saved as a separate JSON file."""
    runs = [_make_mock_run(1001, "failure"), _make_mock_run(1002, "success")]
    repo = _make_mock_repo(runs)
    downloader.gh.get_repo = MagicMock(return_value=repo)
    repo.get_workflow_run.return_value.jobs.return_value = [_make_mock_job(10010)]

    with patch("flake_sleuth.downloader.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = _make_zip_bytes()
        mock_get.return_value = mock_resp

        downloader.download("test/repo", n=2)

    runs_dir = downloader._runs_dir("test/repo")
    assert (runs_dir / "1001.json").exists()
    assert (runs_dir / "1002.json").exists()

    run_data = json.loads((runs_dir / "1001.json").read_text())
    assert run_data["run_id"] == 1001
    assert run_data["conclusion"] == "failure"
    assert len(run_data["jobs"]) == 1
    assert run_data["jobs"][0]["job_id"] == 10010


def test_force_clears_existing_data(downloader: Downloader) -> None:
    """--force removes existing data before downloading."""
    # Create existing data
    runs_dir = downloader._runs_dir("test/repo")
    (runs_dir / "old.json").write_text("{}")

    runs = [_make_mock_run(2001, "failure")]
    repo = _make_mock_repo(runs)
    downloader.gh.get_repo = MagicMock(return_value=repo)
    repo.get_workflow_run.return_value.jobs.return_value = [_make_mock_job(20010)]

    with patch("flake_sleuth.downloader.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = _make_zip_bytes()
        mock_get.return_value = mock_resp

        downloader.download("test/repo", n=1, force=True)

    assert not (runs_dir / "old.json").exists()
    assert (runs_dir / "2001.json").exists()


# ── Log download ───────────────────────────────────────────────────────


def test_log_zip_saved_to_disk(downloader: Downloader) -> None:
    """Log ZIPs are saved to logs/ directory."""
    runs = [_make_mock_run(1001, "failure")]
    repo = _make_mock_repo(runs)
    downloader.gh.get_repo = MagicMock(return_value=repo)
    repo.get_workflow_run.return_value.jobs.return_value = [_make_mock_job(10010)]

    zip_bytes = _make_zip_bytes()
    with patch("flake_sleuth.downloader.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = zip_bytes
        mock_get.return_value = mock_resp

        downloader.download("test/repo", n=1)

    log_path = downloader._logs_dir("test/repo") / "1001.zip"
    assert log_path.exists()
    assert log_path.read_bytes() == zip_bytes


def test_expired_log_skipped(downloader: Downloader) -> None:
    """410 Gone response is recorded as 'expired', not retried."""
    runs = [_make_mock_run(1001, "failure")]
    repo = _make_mock_repo(runs)
    downloader.gh.get_repo = MagicMock(return_value=repo)
    repo.get_workflow_run.return_value.jobs.return_value = [_make_mock_job(10010)]

    with patch("flake_sleuth.downloader.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 410
        mock_get.return_value = mock_resp

        result = downloader.download("test/repo", n=1)

    assert result.runs_skipped_expired == 1
    assert result.runs_with_logs == 0


def test_404_log_recorded_as_error(downloader: Downloader) -> None:
    """404 response is recorded as 'error'."""
    runs = [_make_mock_run(1001, "failure")]
    repo = _make_mock_repo(runs)
    downloader.gh.get_repo = MagicMock(return_value=repo)
    repo.get_workflow_run.return_value.jobs.return_value = [_make_mock_job(10010)]

    with patch("flake_sleuth.downloader.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        result = downloader.download("test/repo", n=1)

    assert result.runs_skipped_error == 1


def test_429_retries_then_succeeds(downloader: Downloader) -> None:
    """429 triggers retry, then succeeds on second attempt."""
    runs = [_make_mock_run(1001, "failure")]
    repo = _make_mock_repo(runs)
    downloader.gh.get_repo = MagicMock(return_value=repo)
    repo.get_workflow_run.return_value.jobs.return_value = [_make_mock_job(10010)]

    zip_bytes = _make_zip_bytes()
    with patch("flake_sleuth.downloader.requests.get") as mock_get:
        # First call: 429, second call: 200
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.content = zip_bytes
        mock_get.side_effect = [resp_429, resp_200]

        result = downloader.download("test/repo", n=1)

    assert result.runs_with_logs == 1
    assert mock_get.call_count == 2


def test_existing_zip_skips_download(downloader: Downloader) -> None:
    """If a valid ZIP already exists, it's not re-downloaded."""
    runs = [_make_mock_run(1001, "failure")]
    repo = _make_mock_repo(runs)
    downloader.gh.get_repo = MagicMock(return_value=repo)
    repo.get_workflow_run.return_value.jobs.return_value = [_make_mock_job(10010)]

    # Pre-create the ZIP
    log_path = downloader._logs_dir("test/repo") / "1001.zip"
    log_path.write_bytes(_make_zip_bytes())

    with patch("flake_sleuth.downloader.requests.get") as mock_get:
        result = downloader.download("test/repo", n=1)
        mock_get.assert_not_called()

    assert result.runs_with_logs >= 1


# ── --all-runs flag ────────────────────────────────────────────────────


def test_all_runs_downloads_successful_run_logs(downloader: Downloader) -> None:
    """--all-runs downloads logs for successful runs too."""
    runs = [_make_mock_run(1001, "failure"), _make_mock_run(1002, "success")]
    repo = _make_mock_repo(runs)
    downloader.gh.get_repo = MagicMock(return_value=repo)
    repo.get_workflow_run.return_value.jobs.return_value = [_make_mock_job(10010)]

    zip_bytes = _make_zip_bytes()
    with patch("flake_sleuth.downloader.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = zip_bytes
        mock_get.return_value = mock_resp

        downloader.download("test/repo", n=2, all_runs=True)

    # Both runs should have logs
    assert (downloader._logs_dir("test/repo") / "1001.zip").exists()
    assert (downloader._logs_dir("test/repo") / "1002.zip").exists()


def test_default_only_downloads_failed_run_logs(downloader: Downloader) -> None:
    """Without --all-runs, only failed runs get log downloads."""
    runs = [_make_mock_run(1001, "failure"), _make_mock_run(1002, "success")]
    repo = _make_mock_repo(runs)
    downloader.gh.get_repo = MagicMock(return_value=repo)
    repo.get_workflow_run.return_value.jobs.return_value = [_make_mock_job(10010)]

    zip_bytes = _make_zip_bytes()
    with patch("flake_sleuth.downloader.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = zip_bytes
        mock_get.return_value = mock_resp

        downloader.download("test/repo", n=2, all_runs=False)

    assert (downloader._logs_dir("test/repo") / "1001.zip").exists()
    assert not (downloader._logs_dir("test/repo") / "1002.zip").exists()


# ── Load data (Phase 2) ────────────────────────────────────────────────


def test_load_data_returns_runs(downloader: Downloader) -> None:
    """load_data reads runs from disk and returns RunInfo objects."""
    runs = [_make_mock_run(1001, "failure"), _make_mock_run(1002, "success")]
    repo = _make_mock_repo(runs)
    downloader.gh.get_repo = MagicMock(return_value=repo)
    repo.get_workflow_run.return_value.jobs.return_value = [_make_mock_job(10010)]

    with patch("flake_sleuth.downloader.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = _make_zip_bytes()
        mock_get.return_value = mock_resp
        downloader.download("test/repo", n=2)

    loaded_runs, failed_runs = downloader.load_data("test/repo")
    assert len(loaded_runs) == 2
    assert len(failed_runs) == 1
    assert loaded_runs[0].run_id == 1001
    assert loaded_runs[0].conclusion == "failure"
    assert len(loaded_runs[0].jobs) == 1


def test_load_data_raises_on_missing(downloader: Downloader) -> None:
    """load_data raises FileNotFoundError when no data exists."""
    with pytest.raises(FileNotFoundError, match="No data found"):
        downloader.load_data("nonexistent/repo")


def test_load_logs_returns_dict(downloader: Downloader) -> None:
    """load_logs unzips a log archive and returns {filename: content}."""
    runs = [_make_mock_run(1001, "failure")]
    repo = _make_mock_repo(runs)
    downloader.gh.get_repo = MagicMock(return_value=repo)
    repo.get_workflow_run.return_value.jobs.return_value = [_make_mock_job(10010)]

    with patch("flake_sleuth.downloader.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = _make_zip_bytes()
        mock_get.return_value = mock_resp
        downloader.download("test/repo", n=1)

    logs = downloader.load_logs("test/repo", 1001)
    assert logs is not None
    assert "job_log.txt" in logs
    assert "FAILED" in logs["job_log.txt"]


def test_load_logs_returns_none_on_missing(downloader: Downloader) -> None:
    """load_logs returns None when the ZIP doesn't exist."""
    result = downloader.load_logs("test/repo", 9999)
    assert result is None


def test_load_logs_returns_none_on_corrupt_zip(downloader: Downloader) -> None:
    """load_logs returns None and removes a corrupt ZIP."""
    log_path = downloader._logs_dir("test/repo") / "1001.zip"
    log_path.write_bytes(b"not a real zip")

    result = downloader.load_logs("test/repo", 1001)
    assert result is None
    assert not log_path.exists()


# ── ZIP validation ─────────────────────────────────────────────────────


def test_is_valid_zip_accepts_real_zip() -> None:
    """_is_valid_zip returns True for a valid ZIP."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        with zipfile.ZipFile(tmp, "w") as zf:
            zf.writestr("test.txt", "hello")
        tmp_path = Path(tmp.name)

    assert Downloader._is_valid_zip(tmp_path) is True
    tmp_path.unlink()


def test_is_valid_zip_rejects_bad_data() -> None:
    """_is_valid_zip returns False for non-ZIP data."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(b"not a zip file")
        tmp_path = Path(tmp.name)

    assert Downloader._is_valid_zip(tmp_path) is False
    tmp_path.unlink()


# ── Pre-flight ─────────────────────────────────────────────────────────


def test_verify_rate_limit(downloader: Downloader) -> None:
    """verify_rate_limit returns a dict with remaining/reset/limit."""
    mock_rate = MagicMock()
    mock_rate.rate.remaining = 4999
    mock_rate.rate.reset = datetime(2026, 7, 22, 15, 0, tzinfo=UTC)
    mock_rate.rate.limit = 5000
    downloader.gh.get_rate_limit = MagicMock(return_value=mock_rate)

    result = downloader.verify_rate_limit()
    assert result["remaining"] == 4999
    assert result["limit"] == 5000


def test_smoke_test_success(downloader: Downloader) -> None:
    """smoke_test returns True when runs can be fetched."""
    runs = [_make_mock_run(1001), _make_mock_run(1002)]
    repo = _make_mock_repo(runs)
    downloader.gh.get_repo = MagicMock(return_value=repo)

    assert downloader.smoke_test("test/repo", n=2) is True


def test_smoke_test_failure(downloader: Downloader) -> None:
    """smoke_test returns False when fetch fails."""
    downloader.gh.get_repo = MagicMock(side_effect=Exception("API down"))
    assert downloader.smoke_test("test/repo") is False


# ── Offset / batch download ────────────────────────────────────────────


def test_download_with_offset_skips_runs(downloader: Downloader) -> None:
    """--offset skips the first N runs from the API."""
    runs = [
        _make_mock_run(1001, "failure"),
        _make_mock_run(1002, "failure"),
        _make_mock_run(1003, "failure"),
        _make_mock_run(1004, "failure"),
    ]
    repo = _make_mock_repo(runs)
    downloader.gh.get_repo = MagicMock(return_value=repo)
    repo.get_workflow_run.return_value.jobs.return_value = [_make_mock_job(10010)]

    with patch("flake_sleuth.downloader.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = _make_zip_bytes()
        mock_get.return_value = mock_resp

        downloader.download("test/repo", n=2, offset=2)

    # Should only have runs 1003 and 1004 (skipped first 2)
    runs_dir = downloader._runs_dir("test/repo")
    assert (runs_dir / "1003.json").exists()
    assert (runs_dir / "1004.json").exists()
    assert not (runs_dir / "1001.json").exists()
    assert not (runs_dir / "1002.json").exists()


def test_download_offset_recorded_in_manifest(downloader: Downloader) -> None:
    """Manifest tracks which offset ranges have been downloaded."""
    runs = [_make_mock_run(1001, "failure"), _make_mock_run(1002, "failure")]
    repo = _make_mock_repo(runs)
    downloader.gh.get_repo = MagicMock(return_value=repo)
    repo.get_workflow_run.return_value.jobs.return_value = [_make_mock_job(10010)]

    with patch("flake_sleuth.downloader.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = _make_zip_bytes()
        mock_get.return_value = mock_resp

        downloader.download("test/repo", n=2, offset=0)

    manifest = json.loads(downloader._manifest_path("test/repo").read_text())
    assert [0, 2] in manifest["offsets_downloaded"]


def test_download_same_offset_skipped(downloader: Downloader) -> None:
    """Re-downloading the same offset range is a no-op."""
    runs = [_make_mock_run(1001, "failure"), _make_mock_run(1002, "failure")]
    repo = _make_mock_repo(runs)
    downloader.gh.get_repo = MagicMock(return_value=repo)
    repo.get_workflow_run.return_value.jobs.return_value = [_make_mock_job(10010)]

    with patch("flake_sleuth.downloader.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = _make_zip_bytes()
        mock_get.return_value = mock_resp

        downloader.download("test/repo", n=2, offset=0)
        # Second download with same offset should not fetch again
        downloader.download("test/repo", n=2, offset=0)
        # requests.get should only be called for the first download
        # (2 failed runs × 1 download each = 2 calls, not 4)
        assert mock_get.call_count <= 2


# ── Load data with offset / batch ──────────────────────────────────────


def test_load_data_with_offset(downloader: Downloader) -> None:
    """load_data with offset skips the first N run files."""
    runs = [
        _make_mock_run(1001, "failure"),
        _make_mock_run(1002, "success"),
        _make_mock_run(1003, "failure"),
        _make_mock_run(1004, "success"),
    ]
    repo = _make_mock_repo(runs)
    downloader.gh.get_repo = MagicMock(return_value=repo)
    repo.get_workflow_run.return_value.jobs.return_value = [_make_mock_job(10010)]

    with patch("flake_sleuth.downloader.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = _make_zip_bytes()
        mock_get.return_value = mock_resp
        downloader.download("test/repo", n=4)

    loaded, failed = downloader.load_data("test/repo", offset=2)
    assert len(loaded) == 2
    assert loaded[0].run_id == 1003


def test_load_data_with_batch_size(downloader: Downloader) -> None:
    """load_data with batch_size limits the number of runs loaded."""
    runs = [
        _make_mock_run(1001, "failure"),
        _make_mock_run(1002, "success"),
        _make_mock_run(1003, "failure"),
        _make_mock_run(1004, "success"),
    ]
    repo = _make_mock_repo(runs)
    downloader.gh.get_repo = MagicMock(return_value=repo)
    repo.get_workflow_run.return_value.jobs.return_value = [_make_mock_job(10010)]

    with patch("flake_sleuth.downloader.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = _make_zip_bytes()
        mock_get.return_value = mock_resp
        downloader.download("test/repo", n=4)

    loaded, failed = downloader.load_data("test/repo", offset=1, batch_size=2)
    assert len(loaded) == 2
    assert loaded[0].run_id == 1002
    assert loaded[1].run_id == 1003
