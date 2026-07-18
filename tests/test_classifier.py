from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from flake_sleuth.classifier import Classifier
from flake_sleuth.types import (
    Classification,
    ErrorSignatureGroup,
    FailureCategory,
    TestResult,
    TestStatus,
)

NOW = datetime(2026, 7, 16, tzinfo=UTC)

PASSED_RESULT = TestResult(
    test_name="tests/test_auth.py::test_login",
    status=TestStatus.PASSED,
    error_message="",
    stack_trace="",
    timing_seconds=0.0,
    run_id=1001,
    workflow_name="CI",
    job_name="test (3.11)",
    timestamp=NOW,
)

FAILED_RESULT = TestResult(
    test_name="tests/test_auth.py::test_login",
    status=TestStatus.FAILED,
    error_message="AssertionError: assert 200 == 302",
    stack_trace="tests/test_auth.py:42: AssertionError",
    timing_seconds=0.0,
    run_id=1001,
    workflow_name="CI",
    job_name="test (3.11)",
    timestamp=NOW,
)

INFRA_RESULT = TestResult(
    test_name="tests/test_integration.py::test_external_api",
    status=TestStatus.FAILED,
    error_message=(
        "requests.exceptions.ConnectionError: "
        "Connection to api.example.com timed out. (connect timeout=5)"
    ),
    stack_trace="tests/test_integration.py:23: ConnectionError",
    timing_seconds=0.0,
    run_id=1002,
    workflow_name="CI",
    job_name="test (3.11)",
    timestamp=NOW,
)


def _make_context(
    total_executions: int = 100,
    total_failures: int = 10,
    dominant_ratio: float = 0.5,
    failure_rate: float = 0.1,
    num_signatures: int = 3,
) -> dict:
    from flake_sleuth.types import TestStats

    sigs = [
        ErrorSignatureGroup(
            signature_hash=f"sig{i}",
            sample_message=f"error {i}",
            count=total_failures // num_signatures
            + (1 if i < total_failures % num_signatures else 0),
            first_seen=NOW,
            last_seen=NOW,
        )
        for i in range(num_signatures)
    ]
    stats = TestStats(
        test_name="tests/test_auth.py::test_login",
        total_executions=total_executions,
        total_failures=total_failures,
        flake_rate=total_failures / total_executions * 100,
        failure_rate=failure_rate,
        error_signatures=sigs,
        dominant_signature=sigs[0].signature_hash if sigs else None,
        dominant_signature_ratio=dominant_ratio,
        classifications=[],
        final_category=FailureCategory.FLAKY,
        first_seen_run=NOW,
        last_seen_run=NOW,
        workflows_affected=["CI"],
    )
    return {"tests/test_auth.py::test_login": stats}


# ─── _matches_infra ───


class TestMatchesInfra:

    def test_timeout_matches(self) -> None:
        c = Classifier()
        matched, pattern = c._matches_infra(INFRA_RESULT)
        assert matched
        assert pattern is not None

    def test_timeout_in_error_message(self) -> None:
        c = Classifier()
        tr = TestResult(
            test_name="test",
            status=TestStatus.FAILED,
            error_message="timed out",
            stack_trace="",
            timing_seconds=0.0,
            run_id=1,
            workflow_name="CI",
            job_name="test",
            timestamp=NOW,
        )
        matched, _ = c._matches_infra(tr)
        assert matched

    def test_oom_matches(self) -> None:
        c = Classifier()
        tr = TestResult(
            test_name="test",
            status=TestStatus.FAILED,
            error_message="out of memory",
            stack_trace="",
            timing_seconds=0.0,
            run_id=1,
            workflow_name="CI",
            job_name="test",
            timestamp=NOW,
        )
        matched, pattern = c._matches_infra(tr)
        assert matched
        assert pattern is not None
        assert "memory" in pattern

    def test_oom_killed_matches(self) -> None:
        c = Classifier()
        tr = TestResult(
            test_name="test",
            status=TestStatus.FAILED,
            error_message="OOMKilled",
            stack_trace="",
            timing_seconds=0.0,
            run_id=1,
            workflow_name="CI",
            job_name="test",
            timestamp=NOW,
        )
        matched, _ = c._matches_infra(tr)
        assert matched

    def test_connection_refused_matches(self) -> None:
        c = Classifier()
        tr = TestResult(
            test_name="test",
            status=TestStatus.FAILED,
            error_message="connection refused",
            stack_trace="",
            timing_seconds=0.0,
            run_id=1,
            workflow_name="CI",
            job_name="test",
            timestamp=NOW,
        )
        matched, _ = c._matches_infra(tr)
        assert matched

    def test_http_503_matches(self) -> None:
        c = Classifier()
        tr = TestResult(
            test_name="test",
            status=TestStatus.FAILED,
            error_message="HTTP 503 Service Unavailable",
            stack_trace="",
            timing_seconds=0.0,
            run_id=1,
            workflow_name="CI",
            job_name="test",
            timestamp=NOW,
        )
        matched, _ = c._matches_infra(tr)
        assert matched

    def test_normal_error_does_not_match(self) -> None:
        c = Classifier()
        matched, _ = c._matches_infra(FAILED_RESULT)
        assert not matched

    def test_empty_error_does_not_match(self) -> None:
        c = Classifier()
        matched, _ = c._matches_infra(PASSED_RESULT)
        assert not matched

    def test_stack_trace_also_searched(self) -> None:
        c = Classifier()
        tr = TestResult(
            test_name="test",
            status=TestStatus.FAILED,
            error_message="Some error",
            stack_trace="requests.exceptions.ConnectionError: ETIMEDOUT",
            timing_seconds=0.0,
            run_id=1,
            workflow_name="CI",
            job_name="test",
            timestamp=NOW,
        )
        matched, _ = c._matches_infra(tr)
        assert matched


# ─── classify ───


class TestClassifyInfra:

    def test_infra_always_detected_first(self) -> None:
        c = Classifier()
        result = c.classify(INFRA_RESULT)
        assert result.category == FailureCategory.INFRA
        assert result.confidence == 0.9
        assert result.classified_by == "rules"

    def test_infra_even_with_cross_run_context(self) -> None:
        c = Classifier()
        ctx = _make_context()
        result = c.classify(INFRA_RESULT, ctx)
        assert result.category == FailureCategory.INFRA

    def test_infra_provides_evidence(self) -> None:
        c = Classifier()
        result = c.classify(INFRA_RESULT)
        assert "Infra pattern" in result.evidence
        assert result.evidence.count(":") == 1


class TestClassifyInsufficientData:

    def test_below_threshold(self) -> None:
        c = Classifier()
        ctx = _make_context(total_executions=10, dominant_ratio=0.0, failure_rate=0.1)
        result = c.classify(FAILED_RESULT, ctx)
        assert result.category == FailureCategory.INSUFFICIENT_DATA
        assert result.confidence == 1.0
        assert "10 executions" in result.evidence

    def test_edge_at_49(self) -> None:
        c = Classifier()
        ctx = _make_context(total_executions=49, dominant_ratio=0.0, failure_rate=0.1)
        result = c.classify(FAILED_RESULT, ctx)
        assert result.category == FailureCategory.INSUFFICIENT_DATA


class TestClassifyRealBug:

    def test_high_dominance_high_failure(self) -> None:
        c = Classifier()
        ctx = _make_context(
            total_executions=100,
            total_failures=80,
            dominant_ratio=0.95,
            failure_rate=0.8,
            num_signatures=2,
        )
        result = c.classify(FAILED_RESULT, ctx)
        assert result.category == FailureCategory.REAL_BUG
        assert result.confidence == 0.85

    def test_evidence_includes_ratio(self) -> None:
        c = Classifier()
        ctx = _make_context(
            total_executions=100,
            total_failures=80,
            dominant_ratio=0.95,
            failure_rate=0.8,
        )
        result = c.classify(FAILED_RESULT, ctx)
        assert "95%" in result.evidence
        assert "80%" in result.evidence

    def test_not_real_bug_below_dominance_threshold(self) -> None:
        c = Classifier()
        ctx = _make_context(
            total_executions=100,
            total_failures=10,
            dominant_ratio=0.5,
            failure_rate=0.1,
        )
        result = c.classify(FAILED_RESULT, ctx)
        assert result.category != FailureCategory.REAL_BUG


class TestClassifyFlaky:

    def test_multiple_signatures_low_failure(self) -> None:
        c = Classifier()
        ctx = _make_context(
            total_executions=100,
            total_failures=10,
            dominant_ratio=0.4,
            failure_rate=0.1,
            num_signatures=5,
        )
        result = c.classify(FAILED_RESULT, ctx)
        assert result.category == FailureCategory.FLAKY
        assert result.confidence == 0.8

    def test_evidence_mentions_signatures(self) -> None:
        c = Classifier()
        ctx = _make_context(
            total_executions=100,
            total_failures=10,
            dominant_ratio=0.4,
            failure_rate=0.1,
            num_signatures=5,
        )
        result = c.classify(FAILED_RESULT, ctx)
        assert "5 distinct error signatures" in result.evidence
        assert "10%" in result.evidence

    def test_not_flaky_when_single_signature(self) -> None:
        c = Classifier()
        ctx = _make_context(
            total_executions=100,
            total_failures=10,
            dominant_ratio=1.0,
            failure_rate=0.1,
            num_signatures=1,
        )
        result = c.classify(FAILED_RESULT, ctx)
        assert result.category == FailureCategory.FLAKY
        assert "Ambiguous" in result.evidence


class TestClassifyDefault:
    """Tests for ambiguous cases with no LLM available."""

    def test_no_context_defaults_to_flaky(self) -> None:
        c = Classifier()
        result = c.classify(FAILED_RESULT)
        assert result.category == FailureCategory.FLAKY
        assert result.confidence == 0.5

    def test_context_present_but_no_match_defaults_to_flaky(self) -> None:
        c = Classifier()
        ctx = _make_context(
            total_executions=100,
            total_failures=50,
            dominant_ratio=0.8,
            failure_rate=0.5,
            num_signatures=1,
        )
        result = c.classify(FAILED_RESULT, ctx)
        assert result.category == FailureCategory.FLAKY
        assert result.classified_by == "rules"


class TestClassifyLLMFallback:
    """Tests for LLM fallback on ambiguous cases."""

    def test_calls_llm_when_configured(self) -> None:
        mock_llm = MagicMock()
        mock_llm.classify_ambiguous.return_value = Classification(
            test_name="tests/test_auth.py::test_login",
            run_id=1001,
            category=FailureCategory.FLAKY,
            evidence="LLM classified",
            confidence=0.7,
            classified_by="llm:omlx:qwen2.5-coder:7b",
        )
        c = Classifier(llm_adapter=mock_llm)
        result = c.classify(FAILED_RESULT)
        assert result.category == FailureCategory.FLAKY
        mock_llm.classify_ambiguous.assert_called_once()

    def test_llm_not_called_when_infra_matches(self) -> None:
        mock_llm = MagicMock()
        c = Classifier(llm_adapter=mock_llm)
        c.classify(INFRA_RESULT)
        mock_llm.classify_ambiguous.assert_not_called()

    def test_llm_not_called_when_real_bug_matches(self) -> None:
        mock_llm = MagicMock()
        c = Classifier(llm_adapter=mock_llm)
        ctx = _make_context(
            total_executions=100,
            total_failures=80,
            dominant_ratio=0.95,
            failure_rate=0.8,
        )
        c.classify(FAILED_RESULT, ctx)
        mock_llm.classify_ambiguous.assert_not_called()

    def test_llm_receives_cross_run_context(self) -> None:
        mock_llm = MagicMock()
        mock_llm.classify_ambiguous.return_value = Classification(
            test_name="tests/test_auth.py::test_login",
            run_id=1001,
            category=FailureCategory.FLAKY,
            evidence="LLM classified",
            confidence=0.7,
            classified_by="llm:omlx",
        )
        c = Classifier(llm_adapter=mock_llm)
        # Context where no rule matches: single signature, failure_rate=0.5,
        # dominant_ratio=0.8 (not high enough for real bug).
        ctx = _make_context(
            total_executions=100,
            total_failures=50,
            dominant_ratio=0.8,
            failure_rate=0.5,
            num_signatures=1,
        )
        c.classify(FAILED_RESULT, ctx)
        mock_llm.classify_ambiguous.assert_called_once_with(FAILED_RESULT, ctx)


# ─── Two-pass Integration (M3.2) ───


class TestTwoPass:

    def test_same_result_different_with_context(self) -> None:
        """Same test result classified differently with and without context."""
        c = Classifier()
        # Without context — can't determine, falls through
        result_no_ctx = c.classify(FAILED_RESULT)
        # With context showing real bug
        ctx_bug = _make_context(
            total_executions=100,
            total_failures=80,
            dominant_ratio=0.95,
            failure_rate=0.8,
        )
        result_with_ctx = c.classify(FAILED_RESULT, ctx_bug)
        assert result_no_ctx.category != result_with_ctx.category
        # No-context defaults to FLAKY, with-context should be REAL_BUG
        assert result_with_ctx.category == FailureCategory.REAL_BUG

    def test_real_bug_requires_high_dominance(self) -> None:
        """Real bug only classified when dominant signature ratio is high."""
        c = Classifier()
        # Low dominance
        ctx_low = _make_context(
            total_executions=100,
            total_failures=30,
            dominant_ratio=0.5,
            failure_rate=0.3,
        )
        result_low = c.classify(FAILED_RESULT, ctx_low)
        assert result_low.category != FailureCategory.REAL_BUG
        # High dominance
        ctx_high = _make_context(
            total_executions=100,
            total_failures=80,
            dominant_ratio=0.95,
            failure_rate=0.8,
        )
        result_high = c.classify(FAILED_RESULT, ctx_high)
        assert result_high.category == FailureCategory.REAL_BUG

    def test_classification_fields_set(self) -> None:
        """Every classification carries test_name, run_id, evidence, confidence."""
        c = Classifier()
        for result in [c.classify(FAILED_RESULT), c.classify(INFRA_RESULT)]:
            assert result.test_name
            assert result.run_id > 0
            assert result.evidence
            assert 0.0 <= result.confidence <= 1.0
            assert result.classified_by
