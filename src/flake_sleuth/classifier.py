"""Rule-based and LLM-assisted classifier for CI test failures.

Assigns each failed test to one of four categories (REAL_BUG, FLAKY, INFRA,
INSUFFICIENT_DATA) using a six-step pipeline: infra regex patterns first,
then cross-run statistics, then optional LLM escalation, and finally a
conservative FLAKY default.
"""

from __future__ import annotations

import logging
import re

from flake_sleuth.llm import LLMAdapter
from flake_sleuth.types import (
    Classification,
    FailureCategory,
    TestResult,
    TestStats,
)

logger = logging.getLogger(__name__)


class Classifier:
    """Classify test failures as REAL_BUG, FLAKY, INFRA, or INSUFFICIENT_DATA.

    Uses a hybrid approach:
    1. Rules-based infra detection (always fires first)
    2. Rules-based real-bug / flaky detection (needs cross-run context)
    3. LLM fallback for ambiguous cases
    4. Conservative FLAKY default when nothing else matches
    """

    INFRA_PATTERNS: list[str] = [
        r"timeout",
        r"timed?\s*out",
        r"out\s+of\s+memory",
        r"OOM",
        r"OOMKilled",
        r"killed",
        r"SIGKILL",
        r"SIGTERM",
        r"runner",
        r"self-hosted",
        r"network",
        r"connection\s+refused",
        r"ETIMEDOUT",
        r"ECONNRESET",
        r"ECONNREFUSED",
        r"ENOTFOUND",
        r"503",
        r"502",
        r"504",
    ]

    def __init__(
        self,
        llm_adapter: LLMAdapter | None = None,
        min_sample: int = 50,
        force_llm: bool = False,
    ) -> None:
        self.llm_adapter = llm_adapter
        self.min_sample = min_sample
        self.force_llm = force_llm
        self._compiled: list[re.Pattern[str]] = [
            re.compile(p, re.IGNORECASE) for p in self.INFRA_PATTERNS
        ]

    def _matches_infra(self, test_result: TestResult) -> tuple[bool, str | None]:
        """Check if error message matches any infra pattern.

        Returns (True, matched_pattern) on first match, (False, None) otherwise.
        Checks both error_message and stack_trace for broader coverage.
        """
        haystack = f"{test_result.error_message}\n{test_result.stack_trace}"
        for pattern in self._compiled:
            if pattern.search(haystack):
                return True, pattern.pattern
        return False, None

    def classify(
        self,
        test_result: TestResult,
        cross_run_context: dict[str, TestStats] | None = None,
    ) -> Classification:
        """Run the six-step classification pipeline.

        1. Infra check (rules)
        2. Real bug check (cross-run context)
        3. Flaky check (cross-run context)
        4. Insufficient data (cross-run context)
        5. LLM fallback
        6. Conservative FLAKY default
        """
        # When force_llm is True, skip all rules and go straight to LLM
        if self.force_llm:
            if self.llm_adapter:
                return self.llm_adapter.classify_ambiguous(
                    test_result, cross_run_context
                )
            return Classification(
                test_name=test_result.test_name,
                run_id=test_result.run_id,
                category=FailureCategory.FLAKY,
                evidence="force_llm enabled but no LLM adapter available",
                confidence=0.5,
                classified_by="rules",
            )

        # Step 1: Infra check (rules-based)
        matched, pattern = self._matches_infra(test_result)
        if matched:
            return Classification(
                test_name=test_result.test_name,
                run_id=test_result.run_id,
                category=FailureCategory.INFRA,
                evidence=f"Infra pattern detected: {pattern}",
                confidence=0.9,
                classified_by="rules",
            )

        if cross_run_context:
            stats = cross_run_context.get(test_result.test_name)

            # Step 2: Insufficient data (fewer than min_sample executions)
            if stats and stats.total_executions < self.min_sample:
                return Classification(
                    test_name=test_result.test_name,
                    run_id=test_result.run_id,
                    category=FailureCategory.INSUFFICIENT_DATA,
                    evidence=f"Only {stats.total_executions} executions "
                    f"(< 50 minimum)",
                    confidence=1.0,
                    classified_by="rules",
                )

            if stats and stats.total_executions >= self.min_sample:
                # Step 3: Real bug check
                if (
                    stats.dominant_signature_ratio >= 0.9
                    and stats.failure_rate > 0.5
                ):
                    return Classification(
                        test_name=test_result.test_name,
                        run_id=test_result.run_id,
                        category=FailureCategory.REAL_BUG,
                        evidence=(
                            f"Dominant signature {stats.dominant_signature} "
                            f"in {stats.dominant_signature_ratio:.0%} of failures, "
                            f"failure rate {stats.failure_rate:.0%}"
                        ),
                        confidence=0.85,
                        classified_by="rules",
                    )

                # Step 4: Flaky check
                if (
                    len(stats.error_signatures) > 1
                    and stats.failure_rate < 0.5
                ):
                    return Classification(
                        test_name=test_result.test_name,
                        run_id=test_result.run_id,
                        category=FailureCategory.FLAKY,
                        evidence=(
                            f"{len(stats.error_signatures)} distinct error "
                            f"signatures, failure rate {stats.failure_rate:.0%}"
                        ),
                        confidence=0.8,
                        classified_by="rules",
                    )

        # Step 5: LLM fallback for ambiguous cases
        if self.llm_adapter:
            return self.llm_adapter.classify_ambiguous(
                test_result, cross_run_context
            )

        # Step 6: No LLM available — conservative default
        return Classification(
            test_name=test_result.test_name,
            run_id=test_result.run_id,
            category=FailureCategory.FLAKY,
            evidence="Ambiguous classification, no LLM available for fallback",
            confidence=0.5,
            classified_by="rules",
        )
