"""GitHub Actions API client for fetching runs and logs.

Uses PyGithub for paginated run retrieval and raw ``requests`` for
log zip downloads.  Rate-limit aware with configurable retry/backoff.
"""

from __future__ import annotations

import io
import logging
import os
import time
import zipfile
from datetime import datetime
from typing import Any

import requests
from github import Github

from flake_sleuth.cache import FileCache
from flake_sleuth.exceptions import (
    GitHubAPIError,
    LogExpiredError,
    RateLimitExhaustedError,
)
from flake_sleuth.types import JobInfo, RunInfo

logger = logging.getLogger(__name__)


class GitHubClient:
    """Client for the GitHub Actions REST API.

    Handles pagination, rate-limit tracking, exponential backoff on 429s,
    log zip download / extraction, and optional caching.
    """

    def __init__(
        self,
        token: str | None = None,
        cache: FileCache | None = None,
        per_page: int = 100,
        max_retries: int = 3,
    ) -> None:
        # Resolve token: explicit argument takes precedence, fall back to env.
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("GITHUB_TOKEN is required — set the env var or pass it explicitly")
        self._gh = Github(self.token, per_page=per_page)
        self.cache = cache
        self.per_page = per_page
        self.max_retries = max_retries

    # ── Rate-limit helpers ──────────────────────────────────────────────

    def check_rate_limit(self) -> dict[str, int]:
        """Return current rate-limit status from the GitHub API."""
        data = self._gh.get_rate_limit()
        return {
            "remaining": data.rate.remaining,
            "reset": int(data.rate.reset.timestamp()),
            "limit": data.rate.limit,
        }

    def _wait_if_needed(self) -> None:
        """Sleep until rate-limit reset if fewer than 10 requests remain.

        Called before each API request to avoid hitting the 429 wall.
        """
        status = self.check_rate_limit()
        if status["remaining"] < 10:
            wait = max(0, status["reset"] - time.time()) + 1
            logger.warning(
                "rate limit low (%d remaining), sleeping %.0fs",
                status["remaining"],
                wait,
            )
            time.sleep(wait)

    # ── Run fetching ────────────────────────────────────────────────────

    def fetch_runs(
        self,
        repo: str,
        n: int = 100,
        workflow: str | None = None,
        since: datetime | None = None,
    ) -> list[RunInfo]:
        """Fetch up to *n* recent workflow runs for *repo*.

        Results are sorted by creation time descending (GitHub API default).
        When *since* is provided, PyGithub's ``created`` filter is used so the
        API only returns runs after that date — avoids iterating every run.
        """
        self._wait_if_needed()
        repo_obj = self._gh.get_repo(repo)
        runs: list[RunInfo] = []

        # Build filter kwargs that PyGithub passes to the API.
        # Use Any because PyGithub's overloaded signatures accept heterogeneous types.
        kwargs: dict[str, Any] = {}
        if since:
            # PyGithub accepts a datetime for the ``created`` filter.
            kwargs["created"] = since

        if workflow:
            wf = repo_obj.get_workflow(workflow)
            run_generator = wf.get_runs(**kwargs)
        else:
            run_generator = repo_obj.get_workflow_runs(**kwargs)

        for gh_run in run_generator:
            runs.append(
                RunInfo(
                    run_id=gh_run.id,
                    workflow_name=gh_run.name or gh_run.workflow_url,
                    status=gh_run.status,
                    conclusion=gh_run.conclusion or "",
                    timestamp=gh_run.created_at,
                    html_url=gh_run.html_url,
                )
            )
            if len(runs) >= n:
                break
        return runs

    def fetch_run_jobs(self, repo: str, run_id: int) -> list[JobInfo]:
        """Fetch job-level metadata for a given run."""
        self._wait_if_needed()
        repo_obj = self._gh.get_repo(repo)
        run = repo_obj.get_workflow_run(run_id)
        jobs: list[JobInfo] = []
        for gh_job in run.jobs():
            jobs.append(
                JobInfo(
                    job_id=gh_job.id,
                    name=gh_job.name,
                    conclusion=gh_job.conclusion or "",
                    # PyGithub may return a callable for logs_url in some
                    # versions; coerce to str to be safe.
                    logs_url=str(gh_job.logs_url) if hasattr(gh_job, "logs_url") else "",
                )
            )
        return jobs

    # ── Log downloading ─────────────────────────────────────────────────

    def fetch_logs(self, repo: str, run_id: int) -> dict[str, str] | None:
        """Download and unzip the log archive for a given run.

        Returns ``None`` when logs are not found (404).
        Raises ``LogExpiredError`` when logs have expired (410 Gone) so
        callers can track expired runs separately for data-quality metrics.
        """
        self._wait_if_needed()

        # Serve from cache when available.
        if self.cache:
            cached = self.cache.get(repo, f"logs_{run_id}")
            if cached is not None:
                logger.info("cache hit for logs of run %d", run_id)
                return self._unzip_bytes(cached)

        url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/logs"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.get(url, headers=headers, timeout=60)
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning(
                    "log download failed (attempt %d/%d): %s",
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                )
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                continue

            # 410 Gone — logs have expired (permanent, don't retry).
            if resp.status_code == 410:
                raise LogExpiredError(run_id)

            # 404 — logs not found (possibly a different error shape).
            if resp.status_code == 404:
                logger.warning("logs not found for run %d", run_id)
                return None

            # 429 — rate limited; backoff or give up.
            if resp.status_code == 429:
                if attempt < self.max_retries:
                    delay = 2 ** attempt
                    logger.warning(
                        "429 fetching logs (attempt %d/%d), sleeping %ds",
                        attempt + 1,
                        self.max_retries + 1,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                # Read the real reset time from response headers.
                reset_ts = _parse_reset_header(resp.headers.get("X-RateLimit-Reset"))
                raise RateLimitExhaustedError(reset_ts)

            # 5xx — server error; retry if attempts remain.
            if resp.status_code >= 500:
                if attempt < self.max_retries:
                    delay = 2 ** attempt
                    logger.warning(
                        "%d fetching logs (attempt %d/%d), sleeping %ds",
                        resp.status_code,
                        attempt + 1,
                        self.max_retries + 1,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                raise GitHubAPIError(resp.status_code, resp.reason or "server error")

            # 200 / 202 — success; cache and return.
            if resp.status_code in (200, 202):
                raw = resp.content
                if self.cache:
                    self.cache.set(repo, f"logs_{run_id}", raw)
                return self._unzip_bytes(raw)

            # Any other 4xx (401, 403, etc.) — raise immediately, no retry.
            if 400 <= resp.status_code < 500:
                raise GitHubAPIError(
                    resp.status_code,
                    resp.reason or f"unexpected status {resp.status_code}",
                )

        # All retries exhausted without a definitive outcome.
        raise GitHubAPIError(
            0,
            f"log download failed after {self.max_retries + 1} attempts: {last_exc}",
        )

    @staticmethod
    def _unzip_bytes(raw: bytes) -> dict[str, str]:
        """Unzip the raw log archive into a ``{filename: content}`` dict."""
        result: dict[str, str] = {}
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            for name in zf.namelist():
                result[name] = zf.read(name).decode("utf-8", errors="replace")
        return result


def _parse_reset_header(value: str | None) -> int:
    """Parse the ``X-RateLimit-Reset`` header into an epoch-seconds int.

    Falls back to ``now + 60`` when the header is missing.
    """
    if value is not None:
        try:
            return int(value)
        except (ValueError, TypeError):
            pass
    return int(time.time()) + 60
