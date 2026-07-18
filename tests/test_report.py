from __future__ import annotations

from datetime import UTC, datetime

from flake_sleuth.report import ReportGenerator
from flake_sleuth.types import (
    DataQuality,
    ErrorSignatureGroup,
    FailureCategory,
    FlakeSleuthReport,
    ReportSummary,
    TestStats,
)

NOW = datetime(2026, 7, 16, tzinfo=UTC)

EMPTY_REPORT = FlakeSleuthReport(
    repo="test/repo",
    timestamp=NOW,
    data_quality=DataQuality(
        runs_requested=10, runs_fetched=10, runs_with_failures=0,
        runs_with_logs=10, runs_skipped_expired=0, runs_skipped_error=0,
        effective_sample=10, workflows_analyzed=["CI"],
    ),
    summary=ReportSummary(
        total_runs=10, total_failures=0, total_tests_analyzed=0,
        flaky_count=0, real_bug_count=0, infra_count=0,
        insufficient_data_count=0, overall_pass_rate=1.0, avg_flake_rate=0.0,
    ),
    flaky_tests=[],
    real_bugs=[],
    infra_issues=[],
    insufficient_data=[],
)

ERR_SIG = ErrorSignatureGroup(
    signature_hash="abc123", sample_message="AssertionError",
    count=5, first_seen=NOW, last_seen=NOW,
)

FLAKY_STATS = TestStats(
    test_name="tests/test_a.py::test_foo",
    total_executions=100, total_failures=10,
    flake_rate=10.0, failure_rate=0.1,
    error_signatures=[ERR_SIG],
    dominant_signature="abc123", dominant_signature_ratio=1.0,
    classifications=[], final_category=FailureCategory.FLAKY,
    first_seen_run=NOW, last_seen_run=NOW,
    workflows_affected=["CI"],
)

FAILURE_REPORT = FlakeSleuthReport(
    repo="test/repo",
    timestamp=NOW,
    data_quality=DataQuality(
        runs_requested=10, runs_fetched=10, runs_with_failures=3,
        runs_with_logs=8, runs_skipped_expired=1, runs_skipped_error=1,
        effective_sample=8, workflows_analyzed=["CI", "Lint"],
    ),
    summary=ReportSummary(
        total_runs=10, total_failures=3, total_tests_analyzed=1,
        flaky_count=1, real_bug_count=0, infra_count=0,
        insufficient_data_count=0, overall_pass_rate=0.7, avg_flake_rate=10.0,
    ),
    flaky_tests=[FLAKY_STATS],
    real_bugs=[],
    infra_issues=[],
    insufficient_data=[],
)


class TestCleanReport:
    def test_table_shows_clean_message(self) -> None:
        output = ReportGenerator().generate(EMPTY_REPORT, "table")
        assert "CI health: clean" in output

    def test_markdown_shows_clean_message(self) -> None:
        output = ReportGenerator().generate(EMPTY_REPORT, "markdown")
        assert "CI health: clean" in output

    def test_json_all_formats_work(self) -> None:
        json_out = ReportGenerator().generate(EMPTY_REPORT, "json")
        assert '"repo": "test/repo"' in json_out


class TestFailureReport:
    def test_table_contains_summary(self) -> None:
        output = ReportGenerator().generate(FAILURE_REPORT, "table")
        assert "Summary:" in output
        assert "Flaky Tests:" in output
        assert "10.0%" in output
        assert "Data Quality:" in output

    def test_markdown_contains_sections(self) -> None:
        output = ReportGenerator().generate(FAILURE_REPORT, "markdown")
        assert "## Summary" in output
        assert "## Flaky Tests" in output
        assert "## Data Quality" in output

    def test_json_serializes(self) -> None:
        output = ReportGenerator().generate(FAILURE_REPORT, "json")
        assert '"repo": "test/repo"' in output
        assert '"flaky_count": 1' in output
        assert '"test_name": "tests/test_a.py::test_foo"' in output


class TestDefaultFormat:
    def test_defaults_to_table(self) -> None:
        output = ReportGenerator().generate(EMPTY_REPORT)
        assert "CI health: clean" in output


class TestCategorySection:
    def test_empty_returns_empty_string(self) -> None:
        result = ReportGenerator._category_section("Flaky Tests", [])
        assert result == ""

    def test_non_empty_contains_test_name(self) -> None:
        result = ReportGenerator._category_section("Flaky Tests", [FLAKY_STATS])
        assert "test_foo" in result
        assert "10.0%" in result


class TestMarkdownCategory:
    def test_empty_returns_empty_string(self) -> None:
        result = ReportGenerator._markdown_category("Flaky Tests", [])
        assert result == ""

    def test_non_empty_contains_table(self) -> None:
        result = ReportGenerator._markdown_category("Flaky Tests", [FLAKY_STATS])
        assert "## Flaky Tests" in result
        assert "Flake Rate" in result
        assert "10.0%" in result


class TestLLMDegradedSummary:
    """Degraded LLM outcome counts surface in table and markdown."""

    DEGRADED_REPORT = FlakeSleuthReport(
        repo="test/repo",
        timestamp=NOW,
        data_quality=DataQuality(
            runs_requested=10, runs_fetched=10, runs_with_failures=5,
            runs_with_logs=8, runs_skipped_expired=1, runs_skipped_error=1,
            effective_sample=8, workflows_analyzed=["CI"],
        ),
        summary=ReportSummary(
            total_runs=10, total_failures=5, total_tests_analyzed=5,
            flaky_count=3, real_bug_count=1, infra_count=1,
            insufficient_data_count=0, overall_pass_rate=0.5, avg_flake_rate=20.0,
            llm_call_count=5, llm_truncated_count=2,
            llm_parse_error_count=1, llm_fallback_count=0,
        ),
        flaky_tests=[FLAKY_STATS],
        real_bugs=[],
        infra_issues=[],
        insufficient_data=[],
    )

    def test_table_shows_llm_degraded(self) -> None:
        output = ReportGenerator().generate(self.DEGRADED_REPORT, "table")
        assert "LLM calls: 5" in output
        assert "degraded: 3" in output
        assert "truncated 2" in output
        assert "parse-error 1" in output

    def test_markdown_shows_llm_degraded(self) -> None:
        output = ReportGenerator().generate(self.DEGRADED_REPORT, "markdown")
        assert "| LLM calls | 5 |" in output
        assert "| LLM degraded | 3" in output

    def test_no_llm_section_when_zero_calls(self) -> None:
        output = ReportGenerator().generate(FAILURE_REPORT, "table")
        assert "LLM calls" not in output
