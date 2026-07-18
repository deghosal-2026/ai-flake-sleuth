"""Shared data structures for ai-flake-sleuth.

All dataclasses and enums used across the pipeline — from raw GitHub API
responses through parsed test results, classifications, cross-run correlation,
and final report generation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto

# ─── GitHub API Types ───

# These two dataclasses mirror the GitHub Actions REST API response shapes
# for workflow runs and their constituent jobs.


@dataclass
class JobInfo:
    """Metadata about a single job within a GitHub Actions run."""

    job_id: int          # GitHub's internal job identifier
    name: str            # Human-readable job name, e.g. "test (3.11)"
    conclusion: str      # "success", "failure", "cancelled", or ""
    logs_url: str        # API URL to download the raw log for this job


@dataclass
class RunInfo:
    """Metadata about a single GitHub Actions workflow run."""

    run_id: int                    # Unique run identifier from GitHub
    workflow_name: str             # Name of the workflow that was triggered
    status: str                    # "completed", "in_progress", "queued", etc.
    conclusion: str                # "success", "failure", "cancelled", ""
    timestamp: datetime            # When the run was created (ISO-8601)
    html_url: str                  # Link to the run in the GitHub UI
    jobs: list[JobInfo] = field(default_factory=list)  # Jobs, populated lazily


# ─── Parsed Test Results ───

# After downloading a job log, the log parser extracts individual test outcomes
# into these structures. The pipeline operates on TestResult everywhere.


class TestStatus(Enum):
    """Outcome of a single test execution within a CI run."""

    __test__ = False  # Prevent pytest from collecting this as a test class

    PASSED = auto()
    FAILED = auto()
    ERROR = auto()
    SKIPPED = auto()


@dataclass
class TestResult:
    """Parsed result of a single test from a CI job log."""

    __test__ = False  # Prevent pytest from collecting this as a test class

    test_name: str               # Fully qualified name, e.g. "tests/test_auth.py::test_login"
    status: TestStatus           # PASSED / FAILED / ERROR / SKIPPED
    error_message: str           # Raw error text (empty when passed)
    stack_trace: str             # Full stack trace (empty when passed)
    timing_seconds: float        # Wall-clock execution time in seconds
    run_id: int                  # Links back to the originating run
    workflow_name: str           # Workflow this test was executed under
    job_name: str                # Job this test was executed under
    timestamp: datetime          # When the originating run was created


# ─── Classification ───

# The classifier assigns one of these categories to each failed test.
# INSUFFICIENT_DATA is used when fewer than 50 executions exist.


class FailureCategory(Enum):
    """The category assigned to a test failure after classification."""

    REAL_BUG = auto()           # Reproducible — dominant error signature, high failure rate
    FLAKY = auto()              # Intermittent — multiple distinct errors, low failure rate
    INFRA = auto()              # Environment — timeout, OOM, network, runner issues
    INSUFFICIENT_DATA = auto()  # Fewer than 50 executions — can't classify reliably


@dataclass
class Classification:
    """The result of classifying a single test failure."""

    test_name: str              # Which test was classified
    run_id: int                 # Which run this classification applies to
    category: FailureCategory   # REAL_BUG / FLAKY / INFRA / INSUFFICIENT_DATA
    evidence: str               # Human-readable justification for the category
    confidence: float           # 0.0–1.0 — how sure the classifier is
    classified_by: str          # "rules" or "llm" or "llm:omlx:qwen2.5-coder:7b"


# ─── Cross-Run Correlation ───

# The correlator groups all TestResults and Classifications by test name,
# producing aggregated TestStats. Error signatures let us distinguish
# repeated failures (real bug) from varying failures (flaky).


@dataclass
class ErrorSignatureGroup:
    """A group of failures sharing the same normalized error signature."""

    signature_hash: str          # SHA-256[:16] of the normalized error text
    sample_message: str          # One example of the raw error message
    count: int                   # How many runs produced this signature
    first_seen: datetime         # Earliest run with this signature
    last_seen: datetime          # Most recent run with this signature


@dataclass
class TestStats:
    """Aggregated statistics for a single test across multiple CI runs."""

    __test__ = False  # Prevent pytest from collecting this as a test class

    test_name: str
    total_executions: int                           # Total times the test was executed
    total_failures: int                             # Times the test failed
    flake_rate: float                               # Failures as pct: failures / exec * 100
    failure_rate: float                             # Same ratio as flake_rate, 0.0–1.0
    error_signatures: list[ErrorSignatureGroup]     # Distinct error groups for failures
    dominant_signature: str | None                  # Signature with the highest count
    dominant_signature_ratio: float                 # dominant_count / total_failures
    classifications: list[Classification]           # Per-run classifications for this test
    final_category: FailureCategory                 # Majority-vote aggregated category
    first_seen_run: datetime                        # First run the test appeared in
    last_seen_run: datetime                         # Most recent run with this test
    workflows_affected: list[str]                   # Workflows this test ran under


# ─── Data Quality ───

# Tracks how much of the requested data was actually usable. Logs expire
# after 90 days, so effective_sample may be < runs_fetched.


@dataclass
class DataQuality:
    """Tracks data quality metrics about the fetched CI run sample."""

    runs_requested: int          # Value of --runs flag
    runs_fetched: int            # Actual number of runs returned by the API
    runs_with_failures: int      # Runs whose conclusion is "failure"
    runs_with_logs: int          # Runs where log download succeeded
    runs_skipped_expired: int    # Runs skipped due to 410 Gone (expired logs)
    runs_skipped_error: int      # Runs skipped for other errors (404, network)
    effective_sample: int        # runs_with_logs — the real analysis sample size
    workflows_analyzed: list[str]  # Distinct workflow names encountered


# ─── Report ───

# The final report the agent produces. Designed to be serialised to JSON
# in a schema that v2 can consume as LangGraph state input.


@dataclass
class ReportSummary:
    """High-level summary statistics for the CI health report."""

    total_runs: int
    total_failures: int
    total_tests_analyzed: int
    flaky_count: int
    real_bug_count: int
    infra_count: int
    insufficient_data_count: int
    overall_pass_rate: float     # successful runs / total runs
    avg_flake_rate: float        # mean flake rate across all flaky tests
    # LLM outcome audit (degraded calls that fell back to a default FLAKY):
    llm_call_count: int = 0          # total LLM calls attempted
    llm_truncated_count: int = 0     # cut off (finish_reason=length)
    llm_parse_error_count: int = 0   # response not parseable as JSON
    llm_fallback_count: int = 0      # call failed (network/timeout/error)


@dataclass
class FlakeSleuthReport:
    """Top-level report produced by the agent."""

    repo: str
    timestamp: datetime
    data_quality: DataQuality
    summary: ReportSummary
    flaky_tests: list[TestStats]
    real_bugs: list[TestStats]
    infra_issues: list[TestStats]
    insufficient_data: list[TestStats]
