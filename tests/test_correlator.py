from __future__ import annotations

from datetime import UTC, datetime

from flake_sleuth.correlator import Correlator
from flake_sleuth.types import (
    Classification,
    FailureCategory,
    TestResult,
    TestStatus,
)

NOW = datetime(2026, 7, 16, tzinfo=UTC)

PASSED = TestResult(
    test_name="tests/test_a.py::test_foo",
    status=TestStatus.PASSED,
    error_message="",
    stack_trace="",
    timing_seconds=0.1,
    run_id=1,
    workflow_name="CI",
    job_name="test",
    timestamp=NOW,
)

FAILED_A = TestResult(
    test_name="tests/test_a.py::test_foo",
    status=TestStatus.FAILED,
    error_message="AssertionError: assert 1 == 2",
    stack_trace="test_a.py:42: AssertionError",
    timing_seconds=0.1,
    run_id=2,
    workflow_name="CI",
    job_name="test",
    timestamp=NOW,
)

FAILED_B = TestResult(
    test_name="tests/test_b.py::test_bar",
    status=TestStatus.FAILED,
    error_message="KeyError: 'missing'",
    stack_trace="test_b.py:10: KeyError",
    timing_seconds=0.2,
    run_id=3,
    workflow_name="Lint",
    job_name="check",
    timestamp=NOW,
)

ERROR_RESULT = TestResult(
    test_name="tests/test_b.py::test_bar",
    status=TestStatus.ERROR,
    error_message="TimeoutError: connection timed out",
    stack_trace="test_b.py:15: TimeoutError",
    timing_seconds=30.0,
    run_id=4,
    workflow_name="Lint",
    job_name="check",
    timestamp=NOW,
)


class TestGroupBy:
    def test_groups_by_test_name(self) -> None:
        results = [PASSED, FAILED_A, FAILED_B]
        grouped = Correlator._group_by_test(results)
        assert set(grouped) == {"tests/test_a.py::test_foo", "tests/test_b.py::test_bar"}
        assert len(grouped["tests/test_a.py::test_foo"]) == 2
        assert len(grouped["tests/test_b.py::test_bar"]) == 1

    def test_empty_list(self) -> None:
        assert Correlator._group_by_test([]) == {}


class TestClassifyByTest:
    def test_groups_classifications_by_test(self) -> None:
        cls_a = Classification(
            test_name="tests/test_a.py::test_foo", run_id=1,
            category=FailureCategory.FLAKY, evidence="x", confidence=0.8,
            classified_by="rules",
        )
        cls_b = Classification(
            test_name="tests/test_b.py::test_bar", run_id=2,
            category=FailureCategory.REAL_BUG, evidence="y", confidence=0.9,
            classified_by="rules",
        )
        grouped = Correlator._classifications_by_test([cls_a, cls_b])
        assert len(grouped["tests/test_a.py::test_foo"]) == 1
        assert len(grouped["tests/test_b.py::test_bar"]) == 1

    def test_ignores_empty(self) -> None:
        assert Correlator._classifications_by_test([]) == {}


class TestBuildErrorSignatures:
    def test_groups_failures_by_signature(self) -> None:
        f1 = FAILED_A
        f2 = TestResult(
            test_name="tests/test_a.py::test_foo",
            status=TestStatus.FAILED,
            error_message="AssertionError: assert 1 == 2",
            stack_trace="other/path.py:99: AssertionError",
            timing_seconds=0.1,
            run_id=5,
            workflow_name="CI",
            job_name="test",
            timestamp=NOW,
        )
        sigs = Correlator._build_error_signatures([f1, f2])
        assert len(sigs) == 1
        assert sigs[0].count == 2

    def test_different_errors_different_signatures(self) -> None:
        sigs = Correlator._build_error_signatures([FAILED_A, FAILED_B])
        assert len(sigs) == 2

    def test_empty_list(self) -> None:
        assert Correlator._build_error_signatures([]) == []


class TestFinalCategory:
    def _cat(self) -> Correlator:
        return Correlator()

    def test_insufficient_data_below_50(self) -> None:
        cat = self._cat()._final_category([], 49)
        assert cat == FailureCategory.INSUFFICIENT_DATA

    def test_no_classifications_returns_flaky(self) -> None:
        cat = self._cat()._final_category([], 100)
        assert cat == FailureCategory.FLAKY

    def test_majority_wins(self) -> None:
        cls = [
            Classification("t", 1, FailureCategory.FLAKY, "", 0.8, "rules"),
            Classification("t", 2, FailureCategory.FLAKY, "", 0.8, "rules"),
            Classification("t", 3, FailureCategory.REAL_BUG, "", 0.9, "rules"),
        ]
        cat = self._cat()._final_category(cls, 100)
        assert cat == FailureCategory.FLAKY

    def test_tie_break_flaky_wins(self) -> None:
        cls = [
            Classification("t", 1, FailureCategory.FLAKY, "", 0.8, "rules"),
            Classification("t", 2, FailureCategory.REAL_BUG, "", 0.9, "rules"),
        ]
        cat = self._cat()._final_category(cls, 100)
        assert cat == FailureCategory.FLAKY

    def test_tie_break_infra_over_real_bug(self) -> None:
        cls = [
            Classification("t", 1, FailureCategory.INFRA, "", 0.9, "rules"),
            Classification("t", 2, FailureCategory.REAL_BUG, "", 0.9, "rules"),
        ]
        cat = self._cat()._final_category(cls, 100)
        assert cat == FailureCategory.INFRA


class TestCorrelate:
    def test_computes_stats(self) -> None:
        results = [PASSED, FAILED_A, FAILED_B, ERROR_RESULT]
        stats = Correlator().correlate(results, [])
        foo = stats["tests/test_a.py::test_foo"]
        assert foo.total_executions == 2
        assert foo.total_failures == 1
        assert foo.flake_rate == 50.0
        assert foo.failure_rate == 0.5

    def test_flake_rate_accounting(self) -> None:
        passed_many = [
            TestResult(
                test_name="t", status=TestStatus.PASSED,
                error_message="", stack_trace="",
                timing_seconds=0.1, run_id=i,
                workflow_name="CI", job_name="j", timestamp=NOW,
            )
            for i in range(8)
        ]
        failed_few = [
            TestResult(
                test_name="t", status=TestStatus.FAILED,
                error_message="error", stack_trace="",
                timing_seconds=0.1, run_id=100 + i,
                workflow_name="CI", job_name="j", timestamp=NOW,
            )
            for i in range(2)
        ]
        stats = Correlator().correlate(passed_many + failed_few, [])
        t = stats["t"]
        assert t.total_executions == 10
        assert t.total_failures == 2
        assert t.flake_rate == 20.0

    def test_tracks_workflows(self) -> None:
        r1 = TestResult(
            test_name="t", status=TestStatus.PASSED,
            error_message="", stack_trace="",
            timing_seconds=0.1, run_id=1,
            workflow_name="CI", job_name="j", timestamp=NOW,
        )
        r2 = TestResult(
            test_name="t", status=TestStatus.FAILED,
            error_message="err", stack_trace="",
            timing_seconds=0.1, run_id=2,
            workflow_name="Lint", job_name="j", timestamp=NOW,
        )
        stats = Correlator().correlate([r1, r2], [])
        t = stats["t"]
        assert set(t.workflows_affected) == {"CI", "Lint"}

    def test_dominant_signature_computed(self) -> None:
        same_error = TestResult(
            test_name="t", status=TestStatus.FAILED,
            error_message="AssertionError: assert 1 == 2",
            stack_trace="", timing_seconds=0.1, run_id=5,
            workflow_name="CI", job_name="j", timestamp=NOW,
        )
        r1 = TestResult(
            test_name="t", status=TestStatus.FAILED,
            error_message="TypeError: unexpected",
            stack_trace="", timing_seconds=0.1, run_id=6,
            workflow_name="CI", job_name="j", timestamp=NOW,
        )
        stats = Correlator().correlate([same_error, same_error, r1], [])
        t = stats["t"]
        assert t.total_failures == 3
        assert t.dominant_signature is not None
        assert t.dominant_signature_ratio >= 2 / 3

    def test_first_and_last_seen(self) -> None:
        early = TestResult(
            test_name="t", status=TestStatus.PASSED,
            error_message="", stack_trace="",
            timing_seconds=0.1, run_id=1,
            workflow_name="CI", job_name="j",
            timestamp=datetime(2026, 7, 10, tzinfo=UTC),
        )
        late = TestResult(
            test_name="t", status=TestStatus.FAILED,
            error_message="err", stack_trace="",
            timing_seconds=0.1, run_id=2,
            workflow_name="CI", job_name="j",
            timestamp=datetime(2026, 7, 15, tzinfo=UTC),
        )
        stats = Correlator().correlate([early, late], [])
        t = stats["t"]
        assert t.first_seen_run == early.timestamp
        assert t.last_seen_run == late.timestamp

    def test_classification_aggregated(self) -> None:
        many_passed = [
            TestResult(
                test_name=FAILED_A.test_name, status=TestStatus.PASSED,
                error_message="", stack_trace="",
                timing_seconds=0.1, run_id=i,
                workflow_name="CI", job_name="test", timestamp=NOW,
            )
            for i in range(49)
        ]
        results = many_passed + [FAILED_A, FAILED_A]
        cls = [
            Classification(
                FAILED_A.test_name, 1, FailureCategory.FLAKY, "", 0.8, "rules",
            ),
            Classification(
                FAILED_A.test_name, 2, FailureCategory.FLAKY, "", 0.8, "rules",
            ),
        ]
        stats = Correlator().correlate(results, cls)
        t = stats[FAILED_A.test_name]
        assert t.final_category == FailureCategory.FLAKY


class TestPreliminaryCorrelate:
    def test_returns_stats_without_classifications(self) -> None:
        results = [PASSED, FAILED_A]
        stats = Correlator().preliminary_correlate(results)
        assert len(stats) == 1
        foo = stats["tests/test_a.py::test_foo"]
        assert foo.classifications == []
        assert foo.total_executions == 2
        assert foo.total_failures == 1

    def test_final_category_defaults_with_few_executions(self) -> None:
        results = [PASSED, FAILED_A]
        stats = Correlator().preliminary_correlate(results)
        cat = stats["tests/test_a.py::test_foo"].final_category
        assert cat == FailureCategory.INSUFFICIENT_DATA
