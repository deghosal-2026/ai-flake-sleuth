"""Mock GitHub client that returns fixture data without network calls.

Used by integration tests and unit tests to avoid real API dependencies.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from flake_sleuth.types import JobInfo, RunInfo

FIXTURES_DIR = Path(__file__).resolve().parent


class MockGitHubClient:
    """Test-only client returning fixture data without network calls.

    Reads sample runs from ``sample_runs.json`` and sample logs from
    ``sample_logs/`` to simulate GitHub API responses.

    Accepts (and silently ignores) the same kwargs as ``GitHubClient``
    so it can be used as a drop-in replacement via ``@patch``.
    """

    def __init__(
        self,
        runs_fixture: str = "sample_runs.json",
        logs_dir: str = "sample_logs",
        **kwargs: object,  # accept GitHubClient-style token/cache/per_page/max_retries
    ) -> None:
        self.runs_fixture = FIXTURES_DIR / runs_fixture
        self.logs_dir = FIXTURES_DIR / logs_dir
        self._runs_data: list[dict] | None = None

    def _load_runs(self) -> list[dict]:
        """Load and cache the sample runs fixture."""
        if self._runs_data is None:
            with open(self.runs_fixture) as f:
                data: list[dict] = json.load(f)
            # Parse timestamps string -> aware datetime once at load time.
            for item in data:
                item["_ts"] = datetime.fromisoformat(item["timestamp"])
            self._runs_data = data
        return self._runs_data

    @staticmethod
    def _make_aware(dt: datetime) -> datetime:
        """Ensure a datetime is timezone-aware (assume UTC if naive)."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt

    def fetch_runs(
        self,
        repo: str,
        n: int = 100,
        workflow: str | None = None,
        since: datetime | None = None,
    ) -> list[RunInfo]:
        """Return up to *n* RunInfo objects from the fixture."""
        raw_runs = self._load_runs()
        runs: list[RunInfo] = []
        since_aware = self._make_aware(since) if since else None
        for item in raw_runs:
            ts = item["_ts"]
            if since_aware and ts < since_aware:
                continue
            if workflow and item["workflow_name"] != workflow:
                continue
            runs.append(
                RunInfo(
                    run_id=item["run_id"],
                    workflow_name=item["workflow_name"],
                    status=item["status"],
                    conclusion=item["conclusion"],
                    timestamp=ts,
                    html_url=item["html_url"],
                )
            )
            if len(runs) >= n:
                break
        return runs

    def fetch_run_jobs(self, repo: str, run_id: int) -> list[JobInfo]:
        """Return mock jobs for a given run ID."""
        return [
            JobInfo(
                job_id=run_id * 10,
                name="test (3.11)",
                conclusion="failure",
                logs_url=f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/logs",
            )
        ]

    def fetch_logs(
        self, repo: str, run_id: int
    ) -> dict[str, str] | None:
        """Return fixture log content for *run_id*.

        Simulates expired/unavailable logs for run IDs 1006 and 1010.
        Unknown run IDs (not in the fixture) return ``None``.
        Successful runs return ``clean_run.txt``; failed runs map to a
        format-specific log file based on the workflow name.
        """
        # Simulate expired logs for specific runs.
        if run_id in (1006, 1010):
            return None  # expired or unavailable

        # Look up the run in our fixture to determine log type.
        raw_runs = self._load_runs()
        run_info = next((r for r in raw_runs if r["run_id"] == run_id), None)
        if not run_info:
            return None  # unknown run_id — no log available
        if run_info["conclusion"] == "success":
            return {"job_log.txt": (self.logs_dir / "clean_run.txt").read_text()}

        # Failed runs — map to log file based on workflow.
        log_map = {
            "CI": "pytest_failed.txt",
            "Lint": "unittest_failed.txt",
        }
        log_file = log_map.get(run_info["workflow_name"], "pytest_failed.txt")
        log_path = self.logs_dir / log_file
        if not log_path.exists():
            return None
        return {"job_log.txt": log_path.read_text()}

    def check_rate_limit(self) -> dict[str, int]:
        """Return a fake rate-limit status (always healthy)."""
        return {"remaining": 4999, "reset": 0, "limit": 5000}
