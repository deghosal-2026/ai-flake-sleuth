"""Tests for data structures defined in types.py."""

from __future__ import annotations

from datetime import datetime

from flake_sleuth.types import (
    Classification,
    DataQuality,
    ErrorSignatureGroup,
    FailureCategory,
    FlakeSleuthReport,
    JobInfo,
    ReportSummary,
    RunInfo,
    TestResult,
    TestStats,
    TestStatus,
)


def test_run_info_defaults() -> None:
    """RunInfo instantiates with an empty jobs list."""
    r = RunInfo(
        run_id=1,
        workflow_name="CI",
        status="completed",
        conclusion="success",
        timestamp=datetime(2026, 7, 16),
        html_url="https://github.com/owner/repo/actions/runs/1",
    )
    assert r.run_id == 1
    assert r.jobs == []


def test_job_info_basic() -> None:
    """JobInfo stores expected fields."""
    j = JobInfo(
        job_id=10, name="test", conclusion="failure", logs_url="https://example.com/logs"
    )
    assert j.name == "test"
    assert j.conclusion == "failure"


def test_test_status_enum() -> None:
    """TestStatus enum has the expected members."""
    assert TestStatus.PASSED.value == 1
    assert TestStatus.FAILED.value == 2
    assert TestStatus.ERROR.value == 3
    assert TestStatus.SKIPPED.value == 4


def test_failure_category_enum() -> None:
    """FailureCategory enum has the expected members."""
    assert FailureCategory.REAL_BUG.value == 1
    assert FailureCategory.FLAKY.value == 2
    assert FailureCategory.INFRA.value == 3
    assert FailureCategory.INSUFFICIENT_DATA.value == 4


def test_test_result_fields() -> None:
    """TestResult stores all parsed-log fields correctly."""
    tr = TestResult(
        test_name="tests/test_auth.py::test_login",
        status=TestStatus.FAILED,
        error_message="AssertionError: assert 200 == 302",
        stack_trace="tests/test_auth.py:42: AssertionError",
        timing_seconds=0.32,
        run_id=1001,
        workflow_name="CI",
        job_name="test (3.11)",
        timestamp=datetime(2026, 7, 16),
    )
    assert tr.test_name == "tests/test_auth.py::test_login"
    assert tr.status == TestStatus.FAILED
    assert tr.error_message == "AssertionError: assert 200 == 302"
    assert tr.timing_seconds == 0.32
    assert tr.run_id == 1001


def test_classification_fields() -> None:
    """Classification stores the required fields."""
    c = Classification(
        test_name="tests/test_auth.py::test_login",
        run_id=1001,
        category=FailureCategory.FLAKY,
        evidence="Multiple error signatures, failure rate 14%",
        confidence=0.8,
        classified_by="rules",
    )
    assert c.test_name == "tests/test_auth.py::test_login"
    assert c.category == FailureCategory.FLAKY
    assert c.confidence == 0.8


def test_error_signature_group_ordering() -> None:
    """ErrorSignatureGroup stores counts and time windows."""
    first = datetime(2026, 7, 10)
    last = datetime(2026, 7, 16)
    sig = ErrorSignatureGroup(
        signature_hash="a1b2c3d4",
        sample_message="AssertionError: expected 200, got 302",
        count=8,
        first_seen=first,
        last_seen=last,
    )
    assert sig.count == 8
    assert sig.first_seen == first
    assert sig.last_seen == last


def test_test_stats_aggregation_fields() -> None:
    """TestStats stores per-test aggregation fields."""
    stats = TestStats(
        test_name="tests/test_auth.py::test_login",
        total_executions=95,
        total_failures=14,
        flake_rate=14.74,
        failure_rate=0.1474,
        error_signatures=[],
        dominant_signature=None,
        dominant_signature_ratio=0.0,
        classifications=[],
        final_category=FailureCategory.FLAKY,
        first_seen_run=datetime(2026, 6, 15),
        last_seen_run=datetime(2026, 7, 16),
        workflows_affected=["CI"],
    )
    assert stats.flake_rate == 14.74
    assert stats.final_category == FailureCategory.FLAKY


def test_data_quality_counts() -> None:
    """DataQuality tracks effective sample correctly."""
    dq = DataQuality(
        runs_requested=100,
        runs_fetched=98,
        runs_with_failures=31,
        runs_with_logs=28,
        runs_skipped_expired=3,
        runs_skipped_error=0,
        effective_sample=28,
        workflows_analyzed=["CI", "Lint"],
    )
    assert dq.effective_sample == 28
    assert len(dq.workflows_analyzed) == 2


def test_report_summary_defaults() -> None:
    """ReportSummary holds top-level metrics."""
    rs = ReportSummary(
        total_runs=98,
        total_failures=31,
        total_tests_analyzed=245,
        flaky_count=7,
        real_bug_count=3,
        infra_count=2,
        insufficient_data_count=12,
        overall_pass_rate=0.684,
        avg_flake_rate=0.143,
    )
    assert rs.total_runs == 98
    assert rs.overall_pass_rate == 0.684


def test_flake_sleuth_report_container() -> None:
    """FlakeSleuthReport wraps all report sections."""
    report = FlakeSleuthReport(
        repo="pytest-dev/pytest",
        timestamp=datetime(2026, 7, 16),
        data_quality=DataQuality(
            runs_requested=100,
            runs_fetched=98,
            runs_with_failures=31,
            runs_with_logs=28,
            runs_skipped_expired=3,
            runs_skipped_error=0,
            effective_sample=28,
            workflows_analyzed=["CI", "Lint"],
        ),
        summary=ReportSummary(
            total_runs=98,
            total_failures=31,
            total_tests_analyzed=245,
            flaky_count=7,
            real_bug_count=3,
            infra_count=2,
            insufficient_data_count=12,
            overall_pass_rate=0.684,
            avg_flake_rate=0.143,
        ),
        flaky_tests=[],
        real_bugs=[],
        infra_issues=[],
        insufficient_data=[],
    )
    assert report.repo == "pytest-dev/pytest"
    assert len(report.flaky_tests) == 0
