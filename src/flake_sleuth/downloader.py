"""Downloader module for Phase 1 of the field study.

Fetches run metadata and log archives from GitHub Actions, saves them
to disk in a structured layout, and supports resume via a manifest file.

Data layout:
    data/{repo}/manifest.json
    data/{repo}/runs/{run_id}.json
    data/{repo}/logs/{run_id}.zip

The manifest tracks download progress so re-running a partially-completed
download picks up where it left off without re-fetching completed runs.
"""

from __future__ import annotations

import json
import logging
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from github import Github

from flake_sleuth.types import JobInfo, RunInfo

logger = logging.getLogger(__name__)


class DownloadResult:
    """Summary of a download operation."""

    def __init__(
        self,
        repo: str,
        runs_fetched: int,
        runs_downloaded: int,
        runs_skipped_expired: int,
        runs_skipped_error: int,
        runs_with_failures: int,
        runs_with_logs: int,
        status: str,
    ) -> None:
        self.repo = repo
        self.runs_fetched = runs_fetched
        self.runs_downloaded = runs_downloaded
        self.runs_skipped_expired = runs_skipped_expired
        self.runs_skipped_error = runs_skipped_error
        self.runs_with_failures = runs_with_failures
        self.runs_with_logs = runs_with_logs
        self.status = status

    def __str__(self) -> str:
        """Human-readable summary of the download result."""
        return (
            f"repo={self.repo}, runs_fetched={self.runs_fetched}, "
            f"runs_downloaded={self.runs_downloaded}, "
            f"runs_with_logs={self.runs_with_logs}, "
            f"skipped_expired={self.runs_skipped_expired}, "
            f"skipped_error={self.runs_skipped_error}, "
            f"status={self.status}"
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the result to a dictionary."""
        return {
            "repo": self.repo,
            "runs_fetched": self.runs_fetched,
            "runs_downloaded": self.runs_downloaded,
            "runs_skipped_expired": self.runs_skipped_expired,
            "runs_skipped_error": self.runs_skipped_error,
            "runs_with_failures": self.runs_with_failures,
            "runs_with_logs": self.runs_with_logs,
            "status": self.status,
        }


class Downloader:
    """Downloads GitHub Actions runs and logs to disk with resume support.

    Each run's metadata is saved as JSON and its log archive as a ZIP.
    A manifest.json file tracks progress so partial downloads can resume.
    """

    def __init__(
        self,
        token: str,
        data_dir: str = "./data/",
        per_page: int = 100,
        max_retries: int = 3,
        workers: int = 4,
    ) -> None:
        self.token = token
        self.data_dir = Path(data_dir)
        self.per_page = per_page
        self.max_retries = max_retries
        self.workers = workers
        self._gh: Github | None = None

    @property
    def gh(self) -> Github:
        """Lazily initialize the PyGithub client."""
        if self._gh is None:
            self._gh = Github(self.token, per_page=self.per_page)
        return self._gh

    def _repo_dir(self, repo: str) -> Path:
        return self.data_dir / repo.replace("/", "_")

    def _runs_dir(self, repo: str) -> Path:
        d = self._repo_dir(repo) / "runs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _logs_dir(self, repo: str) -> Path:
        d = self._repo_dir(repo) / "logs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _manifest_path(self, repo: str) -> Path:
        return self._repo_dir(repo) / "manifest.json"

    # ── Manifest ──────────────────────────────────────────────────────

    def _load_manifest(self, repo: str) -> dict[str, Any] | None:
        """Load manifest from disk, returning None if not found."""
        path = self._manifest_path(repo)
        if not path.exists():
            return None
        data: dict[str, Any] = json.loads(path.read_text())
        return data

    def _save_manifest(self, repo: str, manifest: dict[str, Any]) -> None:
        path = self._manifest_path(repo)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, indent=2, default=str))

    def _init_manifest(self, repo: str, runs_requested: int) -> dict[str, Any]:
        existing = self._load_manifest(repo)
        if existing:
            return existing
        return {
            "repo": repo,
            "runs_requested": runs_requested,
            "runs_fetched": 0,
            "runs_downloaded": 0,
            "runs_skipped_expired": 0,
            "runs_skipped_error": 0,
            "runs_with_failures": 0,
            "runs_with_logs": 0,
            "status": "in_progress",
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "last_run_id_processed": None,
            "processed_run_ids": [],
            "offsets_downloaded": [],
        }

    # ── Download ──────────────────────────────────────────────────────

    def download(
        self,
        repo: str,
        n: int = 100,
        workflow: str | None = None,
        force: bool = False,
        all_runs: bool = False,
        offset: int = 0,
    ) -> DownloadResult:
        """Download runs and logs for a repo. Resumable with batch offsets.

        Fetches *n* runs starting from *offset* (skips the first *offset*
        runs from the API). Each batch's progress is tracked in the manifest
        so re-running picks up where it left off.

        1. Fetch run metadata from GitHub API (paginated, skip *offset* runs).
        2. Save each run's metadata as JSON.
        3. Download log ZIPs for failed runs (or all runs if *all_runs*).
        4. Update manifest throughout.

        When *all_runs* is True, logs are downloaded for successful runs
        too. This catches flaky tests that retried and passed.
        """
        self._repo_dir(repo).mkdir(parents=True, exist_ok=True)

        if force:
            self._clear_data(repo)

        manifest = self._init_manifest(repo, n + offset)

        # Track which offset ranges have been downloaded
        ranges = manifest.get("offsets_downloaded", [])
        current_range = [offset, offset + n]
        if current_range in ranges:
            logger.info(
                "Offset range %d-%d already downloaded for %s",
                offset, offset + n, repo,
            )
            manifest["status"] = "complete"
            self._save_manifest(repo, manifest)
            return self._result_from_manifest(repo, manifest)

        # Reset to in_progress for this new batch
        manifest["status"] = "in_progress"

        # Fetch run metadata (skip offset runs)
        runs = self._fetch_runs(repo, n, workflow, offset=offset)
        manifest["runs_fetched"] = manifest.get("runs_fetched", 0) + len(runs)
        failed_runs = [r for r in runs if r.conclusion == "failure"]
        manifest["runs_with_failures"] = manifest.get("runs_with_failures", 0) + len(failed_runs)

        # Save run metadata
        processed_ids = set(manifest.get("processed_run_ids", []))
        for run in runs:
            self._save_run(repo, run)

        # Determine which runs to download logs for
        if all_runs:
            runs_to_log = runs
        else:
            runs_to_log = failed_runs

        # Download logs (parallel)
        to_download = [
            r for r in runs_to_log
            if str(r.run_id) not in processed_ids
        ]
        if to_download:
            results = self._download_logs_parallel(repo, to_download)
            for run_id, status in results.items():
                if status == "ok":
                    manifest["runs_with_logs"] = manifest.get("runs_with_logs", 0) + 1
                    manifest["runs_downloaded"] = manifest.get("runs_downloaded", 0) + 1
                elif status == "expired":
                    manifest["runs_skipped_expired"] = manifest.get("runs_skipped_expired", 0) + 1
                elif status == "error":
                    manifest["runs_skipped_error"] = manifest.get("runs_skipped_error", 0) + 1
                processed_ids.add(str(run_id))
                manifest["last_run_id_processed"] = run_id

        manifest["processed_run_ids"] = list(processed_ids)
        manifest["runs_downloaded"] = manifest.get("runs_downloaded", 0)
        ranges.append(current_range)
        manifest["offsets_downloaded"] = ranges
        manifest["status"] = "complete"
        manifest["completed_at"] = datetime.now().isoformat()
        self._save_manifest(repo, manifest)

        return self._result_from_manifest(repo, manifest)

    def _fetch_runs(
        self,
        repo: str,
        n: int,
        workflow: str | None = None,
        offset: int = 0,
    ) -> list[RunInfo]:
        """Fetch run metadata from GitHub API (paginated, skip *offset* runs)."""
        repo_obj = self.gh.get_repo(repo)

        if workflow:
            wf = repo_obj.get_workflow(workflow)
            run_generator = wf.get_runs()
        else:
            run_generator = repo_obj.get_workflow_runs()

        runs: list[RunInfo] = []
        skipped = 0
        for gh_run in run_generator:
            if skipped < offset:
                skipped += 1
                continue
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

    def _save_run(self, repo: str, run: RunInfo) -> None:
        """Save a RunInfo (with jobs) as JSON."""
        # Fetch jobs for this run
        jobs = self._fetch_jobs(repo, run.run_id)
        run.jobs = jobs

        data = {
            "run_id": run.run_id,
            "workflow_name": run.workflow_name,
            "status": run.status,
            "conclusion": run.conclusion,
            "timestamp": run.timestamp.isoformat() if run.timestamp else None,
            "html_url": run.html_url,
            "jobs": [
                {
                    "job_id": j.job_id,
                    "name": j.name,
                    "conclusion": j.conclusion,
                    "logs_url": j.logs_url,
                }
                for j in jobs
            ],
        }
        path = self._runs_dir(repo) / f"{run.run_id}.json"
        path.write_text(json.dumps(data, indent=2))

    def _fetch_jobs(self, repo: str, run_id: int) -> list[JobInfo]:
        """Fetch job metadata for a run."""
        repo_obj = self.gh.get_repo(repo)
        run = repo_obj.get_workflow_run(run_id)
        jobs: list[JobInfo] = []
        for gh_job in run.jobs():
            jobs.append(
                JobInfo(
                    job_id=gh_job.id,
                    name=gh_job.name,
                    conclusion=gh_job.conclusion or "",
                    logs_url=str(gh_job.logs_url) if hasattr(gh_job, "logs_url") else "",
                )
            )
        return jobs

    def _download_logs_parallel(
        self,
        repo: str,
        runs: list[RunInfo],
    ) -> dict[int, str]:
        """Download log ZIPs in parallel. Returns {run_id: status}."""
        results: dict[int, str] = {}
        logs_dir = self._logs_dir(repo)

        def _dl(run: RunInfo) -> tuple[int, str]:
            zip_path = logs_dir / f"{run.run_id}.zip"
            if zip_path.exists() and self._is_valid_zip(zip_path):
                return run.run_id, "ok"
            return self._download_single_log(repo, run.run_id, zip_path)

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(_dl, r): r for r in runs}
            for future in as_completed(futures):
                run = futures[future]
                try:
                    run_id, status = future.result()
                    results[run_id] = status
                except Exception as exc:
                    logger.warning("Failed to download logs for run %d: %s", run.run_id, exc)
                    results[run.run_id] = "error"

        return results

    def _download_single_log(
        self,
        repo: str,
        run_id: int,
        zip_path: Path,
    ) -> tuple[int, str]:
        """Download a single run's log ZIP with retry."""
        url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/logs"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.get(url, headers=headers, timeout=120)
            except requests.RequestException as exc:
                logger.warning(
                    "log download failed (attempt %d/%d): %s",
                    attempt + 1, self.max_retries + 1, exc,
                )
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                continue

            if resp.status_code == 410:
                return run_id, "expired"
            if resp.status_code == 404:
                return run_id, "error"
            if resp.status_code == 429:
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                return run_id, "error"
            if resp.status_code >= 500:
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                return run_id, "error"
            if resp.status_code in (200, 202):
                zip_path.write_bytes(resp.content)
                return run_id, "ok"

            return run_id, "error"

        return run_id, "error"

    @staticmethod
    def _is_valid_zip(path: Path) -> bool:
        """Check if a file is a valid ZIP archive."""
        try:
            with zipfile.ZipFile(path) as zf:
                return len(zf.namelist()) > 0
        except (zipfile.BadZipFile, Exception):
            return False

    def _clear_data(self, repo: str) -> None:
        """Remove all downloaded data for a repo."""
        import shutil
        d = self._repo_dir(repo)
        if d.exists():
            shutil.rmtree(d)

    def _result_from_manifest(
        self,
        repo: str,
        manifest: dict[str, Any],
    ) -> DownloadResult:
        return DownloadResult(
            repo=repo,
            runs_fetched=manifest.get("runs_fetched", 0),
            runs_downloaded=manifest.get("runs_downloaded", 0),
            runs_skipped_expired=manifest.get("runs_skipped_expired", 0),
            runs_skipped_error=manifest.get("runs_skipped_error", 0),
            runs_with_failures=manifest.get("runs_with_failures", 0),
            runs_with_logs=manifest.get("runs_with_logs", 0),
            status=manifest.get("status", "unknown"),
        )

    # ── Load (for Phase 2: analyze) ───────────────────────────────────

    def load_data(
        self,
        repo: str,
        offset: int = 0,
        batch_size: int | None = None,
    ) -> tuple[list[RunInfo], list[RunInfo]]:
        """Load downloaded data from disk for analysis.

        Returns (all_runs, failed_runs). When *offset* and *batch_size*
        are provided, only loads runs in the [offset, offset+batch_size)
        range — enabling batch analysis.

        Raises FileNotFoundError if no data exists for the repo.
        """
        runs_dir = self._runs_dir(repo)
        if not runs_dir.exists() or not any(runs_dir.glob("*.json")):
            raise FileNotFoundError(f"No data found in {runs_dir}")

        all_paths = sorted(runs_dir.glob("*.json"))

        # Apply offset + batch_size
        if batch_size is not None:
            end = offset + batch_size
            all_paths = all_paths[offset:end]
        elif offset > 0:
            all_paths = all_paths[offset:]

        runs: list[RunInfo] = []
        for path in all_paths:
            data = json.loads(path.read_text())
            jobs = [
                JobInfo(
                    job_id=j["job_id"],
                    name=j["name"],
                    conclusion=j["conclusion"],
                    logs_url=j["logs_url"],
                )
                for j in data.get("jobs", [])
            ]
            runs.append(
                RunInfo(
                    run_id=data["run_id"],
                    workflow_name=data["workflow_name"],
                    status=data["status"],
                    conclusion=data["conclusion"],
                    timestamp=datetime.fromisoformat(data["timestamp"])
                    if data.get("timestamp")
                    else datetime.now(),
                    html_url=data.get("html_url", ""),
                    jobs=jobs,
                )
            )

        failed_runs = [r for r in runs if r.conclusion == "failure"]
        return runs, failed_runs

    def load_logs(self, repo: str, run_id: int) -> dict[str, str] | None:
        """Load and unzip a run's log archive from disk.

        Returns {filename: content} or None if the ZIP doesn't exist
        or is corrupt.
        """
        zip_path = self._logs_dir(repo) / f"{run_id}.zip"
        if not zip_path.exists():
            return None
        if not self._is_valid_zip(zip_path):
            logger.warning("Corrupt ZIP for run %d, removing", run_id)
            zip_path.unlink()
            return None

        result: dict[str, str] = {}
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                result[name] = zf.read(name).decode("utf-8", errors="replace")
        return result

    # ── Pre-flight ────────────────────────────────────────────────────

    def verify_rate_limit(self) -> dict[str, int]:
        """Check GitHub API rate limit status."""
        data = self.gh.get_rate_limit()
        return {
            "remaining": data.rate.remaining,
            "reset": int(data.rate.reset.timestamp()),
            "limit": data.rate.limit,
        }

    def smoke_test(self, repo: str, n: int = 3) -> bool:
        """Quick smoke test: fetch 3 runs and verify download works."""
        try:
            runs = self._fetch_runs(repo, n)
            if not runs:
                logger.warning("No runs found for %s", repo)
                return False
            logger.info("Smoke test OK: fetched %d runs for %s", len(runs), repo)
            return True
        except Exception as exc:
            logger.error("Smoke test failed for %s: %s", repo, exc)
            return False
