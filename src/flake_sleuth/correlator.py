"""Cross-run test statistics correlator.

Groups TestResults by test name, aggregates failure counts and flake rates,
builds error-signature distributions, and computes a majority-vote final
category for each test.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from flake_sleuth.error_signature import ErrorSignatureNormalizer
from flake_sleuth.types import (
    Classification,
    ErrorSignatureGroup,
    FailureCategory,
    TestResult,
    TestStats,
)

logger = logging.getLogger(__name__)

_TIE_BREAK: dict[FailureCategory, int] = {
    FailureCategory.FLAKY: 3,
    FailureCategory.INFRA: 2,
    FailureCategory.REAL_BUG: 1,
}


class Correlator:
    """Aggregate per-test statistics across multiple CI runs.

    Groups TestResults by test name, computes flake rates, error-signature
    distributions, and majority-vote final categories.
    """

    def __init__(self, min_sample: int = 50, force_llm: bool = False) -> None:
        self.min_sample = min_sample
        self.force_llm = force_llm

    def correlate(
        self,
        all_test_results: list[TestResult],
        classifications: list[Classification],
    ) -> dict[str, TestStats]:
        """Full correlation with classifications for final_category."""
        grouped = self._group_by_test(all_test_results)
        class_map = self._classifications_by_test(classifications)

        stats: dict[str, TestStats] = {}
        for test_name, results in grouped.items():
            stats[test_name] = self._build_stats(
                test_name, results, class_map.get(test_name, []), len(results)
            )
        return stats

    def preliminary_correlate(
        self,
        all_test_results: list[TestResult],
    ) -> dict[str, TestStats]:
        """Preliminary pass without classifications (two-pass design)."""
        return self.correlate(all_test_results, [])

    @staticmethod
    def _group_by_test(
        results: list[TestResult],
    ) -> dict[str, list[TestResult]]:
        grouped: dict[str, list[TestResult]] = defaultdict(list)
        for r in results:
            grouped[r.test_name].append(r)
        return dict(grouped)

    @staticmethod
    def _classifications_by_test(
        classifications: list[Classification],
    ) -> dict[str, list[Classification]]:
        grouped: dict[str, list[Classification]] = defaultdict(list)
        for c in classifications:
            grouped[c.test_name].append(c)
        return dict(grouped)

    def _build_stats(
        self,
        test_name: str,
        all_results: list[TestResult],
        classifications: list[Classification],
        total_executions: int,
    ) -> TestStats:
        failures = [
            r for r in all_results
            if r.status.name in ("FAILED", "ERROR")
        ]
        total_failures = len(failures)
        flake_rate = (total_failures / total_executions * 100) if total_executions else 0.0
        failure_rate = total_failures / total_executions if total_executions else 0.0

        error_sigs = self._build_error_signatures(failures)
        dominant = max(error_sigs, key=lambda g: g.count) if error_sigs else None
        dominant_signature = dominant.signature_hash if dominant else None
        dominant_signature_ratio = (
            dominant.count / total_failures if dominant and total_failures else 0.0
        )

        first_seen = min(r.timestamp for r in all_results)
        last_seen = max(r.timestamp for r in all_results)
        workflows = list({r.workflow_name for r in all_results})

        final_category = self._final_category(classifications, total_executions)

        return TestStats(
            test_name=test_name,
            total_executions=total_executions,
            total_failures=total_failures,
            flake_rate=flake_rate,
            failure_rate=failure_rate,
            error_signatures=error_sigs,
            dominant_signature=dominant_signature,
            dominant_signature_ratio=dominant_signature_ratio,
            classifications=classifications,
            final_category=final_category,
            first_seen_run=first_seen,
            last_seen_run=last_seen,
            workflows_affected=workflows,
        )

    @staticmethod
    def _build_error_signatures(
        failures: list[TestResult],
    ) -> list[ErrorSignatureGroup]:
        sig_map: dict[str, list[TestResult]] = defaultdict(list)
        normalizer = ErrorSignatureNormalizer()
        for f in failures:
            normalized = normalizer.normalize(f.error_message or "")
            sig = normalizer.signature(normalized)
            sig_map[sig].append(f)

        groups: list[ErrorSignatureGroup] = []
        for sig, members in sig_map.items():
            sample = members[0].error_message or "(no error message)"
            timestamps = [m.timestamp for m in members]
            groups.append(
                ErrorSignatureGroup(
                    signature_hash=sig,
                    sample_message=sample,
                    count=len(members),
                    first_seen=min(timestamps),
                    last_seen=max(timestamps),
                )
            )
        return sorted(groups, key=lambda g: g.count, reverse=True)

    def _final_category(
        self,
        classifications: list[Classification],
        total_executions: int,
    ) -> FailureCategory:
        if not self.force_llm and total_executions < self.min_sample:
            return FailureCategory.INSUFFICIENT_DATA
        if not classifications:
            return FailureCategory.FLAKY
        votes: dict[FailureCategory, int] = defaultdict(int)
        for c in classifications:
            votes[c.category] += 1
        max_count = max(votes.values())
        tied = [cat for cat, count in votes.items() if count == max_count]
        if len(tied) == 1:
            return tied[0]
        return max(tied, key=lambda cat: _TIE_BREAK.get(cat, 0))
