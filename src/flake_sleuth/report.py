"""CI health report generator in table, JSON, and markdown formats.

Renders a FlakeSleuthReport with summary statistics, per-category test
lists (flaky, real bugs, infra, insufficient data), and data quality
metrics. The JSON format serializes to the SPEC §5 schema.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from enum import Enum

from flake_sleuth.types import FlakeSleuthReport, TestStats

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generate CI health reports in table, JSON, or markdown format."""

    def generate(
        self,
        report: FlakeSleuthReport,
        output_format: str = "table",
    ) -> str:
        """Render a FlakeSleuthReport in the requested output_format."""
        if output_format == "json":
            return self._generate_json(report)
        if output_format == "markdown":
            return self._generate_markdown(report)
        return self._generate_table(report)

    @staticmethod
    def _clean_message(report: FlakeSleuthReport) -> str:
        wf = report.data_quality.workflows_analyzed
        wf_count = len(wf)
        return (
            f"No failures in {report.summary.total_runs} runs across "
            f"{wf_count} workflow{'s' if wf_count != 1 else ''}. "
            f"CI health: clean."
        )

    def _generate_table(self, report: FlakeSleuthReport) -> str:
        lines: list[str] = []
        lines.append(f"=== FlakeSleuth Report: {report.repo} ===")
        lines.append(f"Generated: {report.timestamp.isoformat()}")
        lines.append("")

        if report.summary.total_failures == 0:
            lines.append(self._clean_message(report))
            return "\n".join(lines)

        s = report.summary
        lines.append("Summary:")
        lines.append(f"  Total runs: {s.total_runs}")
        lines.append(f"  Total failures: {s.total_failures}")
        lines.append(f"  Tests analyzed: {s.total_tests_analyzed}")
        lines.append(f"  Flaky: {s.flaky_count} | Real bugs: {s.real_bug_count} "
                      f"| Infra: {s.infra_count} | Insufficient data: {s.insufficient_data_count}")
        lines.append(f"  Pass rate: {s.overall_pass_rate:.1%}")
        degraded = s.llm_truncated_count + s.llm_parse_error_count + s.llm_fallback_count
        if s.llm_call_count > 0:
            lines.append(
                f"  LLM calls: {s.llm_call_count}"
                f" (degraded: {degraded} — "
                f"truncated {s.llm_truncated_count}, "
                f"parse-error {s.llm_parse_error_count}, "
                f"fallback {s.llm_fallback_count})"
            )
        lines.append("")
        lines.append(self._category_section("Flaky Tests", report.flaky_tests))
        lines.append(self._category_section("Real Bugs", report.real_bugs))
        lines.append(self._category_section("Infra Issues", report.infra_issues))
        lines.append(self._category_section("Insufficient Data", report.insufficient_data))
        lines.append("Data Quality:")
        dq = report.data_quality
        lines.append(f"  Runs requested: {dq.runs_requested}")
        lines.append(f"  Runs fetched: {dq.runs_fetched}")
        lines.append(f"  Effective sample: {dq.effective_sample}")
        lines.append(f"  Skipped (expired): {dq.runs_skipped_expired}")
        lines.append(f"  Skipped (error): {dq.runs_skipped_error}")
        return "\n".join(lines)

    @staticmethod
    def _category_section(title: str, tests: list[TestStats]) -> str:
        if not tests:
            return ""
        parts = [f"  {title}:"]
        for t in tests:
            parts.append(
                f"    {t.test_name} — {t.flake_rate:.1f}% flake rate, "
                f"{len(t.error_signatures)} sig(s), "
                f"last: {t.last_seen_run.date().isoformat()}"
            )
        return "\n".join(parts)

    def _generate_json(self, report: FlakeSleuthReport) -> str:
        def serialize(obj: object) -> object:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, Enum):
                return obj.name
            if hasattr(obj, "__dict__"):
                return obj.__dict__
            return str(obj)

        return json.dumps(report, default=serialize, indent=2)

    def _generate_markdown(self, report: FlakeSleuthReport) -> str:
        lines: list[str] = []
        lines.append(f"# FlakeSleuth Report: {report.repo}")
        lines.append("")
        lines.append(f"**Generated:** {report.timestamp.isoformat()}")
        lines.append("")

        if report.summary.total_failures == 0:
            lines.append(self._clean_message(report))
            lines.append("")
            dq = report.data_quality
            lines.append("## Data Quality")
            lines.append("| Metric | Value |")
            lines.append("|---|---|")
            lines.append(f"| Runs requested | {dq.runs_requested} |")
            lines.append(f"| Runs fetched | {dq.runs_fetched} |")
            return "\n".join(lines)

        s = report.summary
        lines.append("## Summary")
        lines.append("| Metric | Value |")
        lines.append("|---|---|")
        lines.append(f"| Total runs | {s.total_runs} |")
        lines.append(f"| Total failures | {s.total_failures} |")
        lines.append(f"| Tests analyzed | {s.total_tests_analyzed} |")
        lines.append(f"| Flaky | {s.flaky_count} |")
        lines.append(f"| Real bugs | {s.real_bug_count} |")
        lines.append(f"| Infra | {s.infra_count} |")
        lines.append(f"| Insufficient data | {s.insufficient_data_count} |")
        lines.append(f"| Pass rate | {s.overall_pass_rate:.1%} |")
        degraded = s.llm_truncated_count + s.llm_parse_error_count + s.llm_fallback_count
        if s.llm_call_count > 0:
            lines.append(f"| LLM calls | {s.llm_call_count} |")
            lines.append(
                f"| LLM degraded | {degraded} (truncated {s.llm_truncated_count}, "
                f"parse-error {s.llm_parse_error_count}, "
                f"fallback {s.llm_fallback_count}) |"
            )
        lines.append("")

        lines.append(self._markdown_category("Flaky Tests", report.flaky_tests))
        lines.append(self._markdown_category("Real Bugs", report.real_bugs))
        lines.append(self._markdown_category("Infra Issues", report.infra_issues))
        lines.append(self._markdown_category("Insufficient Data", report.insufficient_data))
        lines.append("")

        dq = report.data_quality
        lines.append("## Data Quality")
        lines.append("| Metric | Value |")
        lines.append("|---|---|")
        lines.append(f"| Runs requested | {dq.runs_requested} |")
        lines.append(f"| Runs fetched | {dq.runs_fetched} |")
        lines.append(f"| Runs with logs | {dq.runs_with_logs} |")
        lines.append(f"| Effective sample | {dq.effective_sample} |")
        lines.append(f"| Skipped (expired) | {dq.runs_skipped_expired} |")
        lines.append(f"| Skipped (error) | {dq.runs_skipped_error} |")
        return "\n".join(lines)

    @staticmethod
    def _markdown_category(title: str, tests: list[TestStats]) -> str:
        if not tests:
            return ""
        lines = [f"## {title}", ""]
        lines.append("| Test | Flake Rate | Signatures | Dominant Error | Last Seen |")
        lines.append("|---|---|---|---|---|")
        for t in tests:
            dom = t.dominant_signature or "—"
            lines.append(
                f"| {t.test_name} | {t.flake_rate:.1f}% | "
                f"{len(t.error_signatures)} | {dom[:32]} | "
                f"{t.last_seen_run.date().isoformat()} |"
            )
        return "\n".join(lines)
