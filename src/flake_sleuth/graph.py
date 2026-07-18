"""LangGraph state graph for the flake-sleuth pipeline.

Defines the node functions (fetch_runs, parse_logs, preliminary_correlate,
classify, correlate, report) and the conditional routing that skips parsing
when there are no failed runs.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph

from flake_sleuth.cache import FileCache
from flake_sleuth.classifier import Classifier
from flake_sleuth.config import FlakeSleuthConfig
from flake_sleuth.correlator import Correlator
from flake_sleuth.github_client import GitHubClient
from flake_sleuth.llm import LLMAdapter
from flake_sleuth.log_parser import LogParser
from flake_sleuth.state import FlakeSleuthState
from flake_sleuth.types import (
    Classification,
    DataQuality,
    FlakeSleuthReport,
    ReportSummary,
    TestResult,
)

logger = logging.getLogger(__name__)


def route_after_fetch(state: FlakeSleuthState) -> str:
    """Conditional edge: determine next node after fetch_runs."""
    if state.error:
        return "error"
    if not state.runs:
        return "error"
    if not state.failed_runs:
        return "no_failures"
    return "has_failures"


def build_graph(
    config: FlakeSleuthConfig,
    skip_download: bool = False,
    repo_name: str | None = None,
) -> StateGraph[FlakeSleuthState]:
    """Build the LangGraph state graph for the flake-sleuth pipeline.

    Each node function is defined inside ``build_graph`` so it has access to
    *config* — this avoids threading config through the state object.

    When *skip_download* is True, the graph starts at ``parse_logs`` instead
    of ``fetch_runs``. This is used by the two-phase analyze command, which
    loads data from disk instead of hitting the GitHub API.
    """
    # -- Shared resources (lazily initialised so graph tests without a
    #    GITHUB_TOKEN can still inspect the graph structure) -------------

    _cache: FileCache | None = None
    if config.cache_dir:
        _cache = FileCache(config.cache_dir)

    _client: GitHubClient | None = None

    def _get_client() -> GitHubClient:
        nonlocal _client
        if _client is None:
            _client = GitHubClient(
                token=config.github_token,
                cache=_cache,
                per_page=config.per_page,
                max_retries=config.max_retries,
            )
        return _client

    llm_adapter: LLMAdapter | None = None
    if not config.no_llm:
        llm_cache_dir: str | None = None
        if config.data_dir:
            cache_path = Path(config.data_dir) / "llm-cache" / config.llm_provider
            if repo_name:
                cache_path = cache_path / repo_name.replace("/", "_")
            llm_cache_dir = str(cache_path)
        llm_adapter = LLMAdapter(
            provider=config.llm_provider,
            model=config.llm_model,
            endpoint=config.llm_endpoint,
            api_key=config.llm_api_key,
            max_tokens=config.llm_max_tokens,
            disable_thinking=config.llm_disable_thinking,
            llm_log_dir=config.llm_log_dir,
            cache_dir=llm_cache_dir,
        )

    # -- Node implementations --------------------------------------------

    def fetch_runs_node(state: FlakeSleuthState) -> dict[str, Any]:
        client = _get_client()

        try:
            since: datetime | None = None
            if config.since:
                since = datetime.fromisoformat(config.since)

            runs = client.fetch_runs(
                state.repo,
                n=config.runs,
                workflow=config.workflow,
                since=since,
            )
        except Exception as exc:
            return {"error": str(exc)}

        failed = [r for r in runs if r.conclusion == "failure"]

        workflows = {r.workflow_name for r in runs}
        data_quality = DataQuality(
            runs_requested=config.runs,
            runs_fetched=len(runs),
            runs_with_failures=len(failed),
            runs_with_logs=0,
            runs_skipped_expired=0,
            runs_skipped_error=0,
            effective_sample=0,
            workflows_analyzed=sorted(workflows),
        )

        return {
            "runs": runs,
            "failed_runs": failed,
            "data_quality": data_quality,
        }

    def parse_logs_node(state: FlakeSleuthState) -> dict[str, Any]:
        parser = LogParser()
        dq = state.data_quality
        all_results: list[TestResult] = []
        skipped_expired = dq.runs_skipped_expired if dq else 0
        skipped_error = dq.runs_skipped_error if dq else 0
        logs_ok = dq.runs_with_logs if dq else 0

        if skip_download:
            # Phase 2: load logs from disk via Downloader
            from flake_sleuth.downloader import Downloader

            downloader = Downloader(
                token=config.github_token or "",
                data_dir=config.data_dir or "./data/",
                per_page=config.per_page,
                max_retries=config.max_retries,
                workers=1,
            )
            for run in state.failed_runs:
                try:
                    logs = downloader.load_logs(state.repo, run.run_id)
                except Exception:
                    skipped_error += 1
                    continue
                if logs is None:
                    skipped_expired += 1
                    continue
                try:
                    parsed = parser.parse(run, logs)
                    all_results.extend(parsed)
                    logs_ok += 1
                except Exception:
                    skipped_error += 1
        else:
            # Legacy mode: fetch logs from GitHub API
            client = _get_client()
            for run in state.failed_runs:
                try:
                    logs = client.fetch_logs(state.repo, run.run_id)
                except Exception:
                    skipped_error += 1
                    continue

                if logs is None:
                    skipped_expired += 1
                    continue

                try:
                    parsed = parser.parse(run, logs)
                    all_results.extend(parsed)
                    logs_ok += 1
                except Exception:
                    skipped_error += 1

        workflows = {r.workflow_name for r in state.runs}
        return {
            "test_results": all_results,
            "data_quality": DataQuality(
                runs_requested=dq.runs_requested if dq else config.runs,
                runs_fetched=dq.runs_fetched if dq else 0,
                runs_with_failures=dq.runs_with_failures if dq else 0,
                runs_with_logs=logs_ok,
                runs_skipped_expired=skipped_expired,
                runs_skipped_error=skipped_error,
                effective_sample=logs_ok,
                workflows_analyzed=sorted(workflows),
            ),
        }

    def preliminary_correlate_node(state: FlakeSleuthState) -> dict[str, Any]:
        correlator = Correlator(
            min_sample=config.min_sample,
            force_llm=config.force_llm,
        )
        return {
            "preliminary_stats": correlator.preliminary_correlate(
                state.test_results,
            ),
        }

    def classify_node(state: FlakeSleuthState) -> dict[str, Any]:
        classifier = Classifier(
            llm_adapter=llm_adapter,
            min_sample=config.min_sample,
            force_llm=config.force_llm,
        )
        classifications: list[Classification] = []
        # Dedup: classify once per unique test_name, reuse for all results.
        seen: dict[str, Classification] = {}
        classified_count = 0
        for result in state.test_results:
            if result.status.name in ("FAILED", "ERROR"):
                if result.test_name in seen:
                    classifications.append(seen[result.test_name])
                    continue
                cls = classifier.classify(result, state.preliminary_stats)
                seen[result.test_name] = cls
                classifications.append(cls)
                classified_count += 1
                # Print each classification as it happens
                print(
                    f"  [{classified_count}] {result.test_name[:70]} -> "
                    f"{cls.category.name} (by {cls.classified_by})"
                )
                # Respect --limit if set
                if config.llm_limit and classified_count >= config.llm_limit:
                    print(f"  --limit {config.llm_limit} reached, stopping classification")
                    break
        return {"classifications": classifications}

    def correlate_node(state: FlakeSleuthState) -> dict[str, Any]:
        correlator = Correlator(
            min_sample=config.min_sample,
            force_llm=config.force_llm,
        )
        per_test_stats = correlator.correlate(
            state.test_results,
            state.classifications,
        )

        all_tests = list(per_test_stats.values())
        flaky = [t for t in all_tests if t.final_category.name == "FLAKY"]
        real_bugs = [t for t in all_tests if t.final_category.name == "REAL_BUG"]
        infra = [t for t in all_tests if t.final_category.name == "INFRA"]
        insufficient = [
            t for t in all_tests if t.final_category.name == "INSUFFICIENT_DATA"
        ]

        total_failures = sum(t.total_failures for t in all_tests)

        # Audit LLM outcome quality from classified_by prefixes.
        # Dedup by test_name (classify_node already deduplicates, but
        # state.classifications contains one entry per result, so a test
        # that failed in 3 runs appears 3× with the same classified_by).
        seen_llm: dict[str, str] = {}
        for cls in state.classifications:
            if cls.test_name not in seen_llm:
                seen_llm[cls.test_name] = cls.classified_by
        llm_call_count = sum(1 for v in seen_llm.values() if v.startswith("llm"))
        llm_truncated_count = sum(
            1 for v in seen_llm.values() if v.startswith("llm-truncated")
        )
        llm_parse_error_count = sum(
            1 for v in seen_llm.values() if v.startswith("llm-parse-error")
        )
        llm_fallback_count = sum(
            1 for v in seen_llm.values() if v.startswith("llm-fallback")
        )

        dq = state.data_quality
        report = FlakeSleuthReport(
            repo=state.repo,
            timestamp=datetime.now(),
            data_quality=dq if dq else DataQuality(
                runs_requested=config.runs, runs_fetched=0,
                runs_with_failures=0, runs_with_logs=0,
                runs_skipped_expired=0, runs_skipped_error=0,
                effective_sample=0, workflows_analyzed=[],
            ),
            summary=ReportSummary(
                total_runs=len(state.runs),
                total_failures=total_failures,
                total_tests_analyzed=len(all_tests),
                flaky_count=len(flaky),
                real_bug_count=len(real_bugs),
                infra_count=len(infra),
                insufficient_data_count=len(insufficient),
            overall_pass_rate=(
                sum(1 for r in state.runs if r.conclusion == "success") / len(state.runs)
                if state.runs
                else 0.0
            ),
                avg_flake_rate=(
                    sum(t.flake_rate for t in flaky) / len(flaky)
                    if flaky
                    else 0.0
                ),
                llm_call_count=llm_call_count,
                llm_truncated_count=llm_truncated_count,
                llm_parse_error_count=llm_parse_error_count,
                llm_fallback_count=llm_fallback_count,
            ),
            flaky_tests=flaky,
            real_bugs=real_bugs,
            infra_issues=infra,
            insufficient_data=insufficient,
        )

        return {
            "per_test_stats": per_test_stats,
            "report": report,
        }

    def report_node(state: FlakeSleuthState) -> dict[str, Any]:
        if state.report is not None:
            return {}
        report = FlakeSleuthReport(
            repo=state.repo,
            timestamp=datetime.now(),
            data_quality=state.data_quality or DataQuality(
                runs_requested=config.runs, runs_fetched=0,
                runs_with_failures=0, runs_with_logs=0,
                runs_skipped_expired=0, runs_skipped_error=0,
                effective_sample=0, workflows_analyzed=[],
            ),
            summary=ReportSummary(
                total_runs=len(state.runs),
                total_failures=0, total_tests_analyzed=0,
                flaky_count=0, real_bug_count=0, infra_count=0,
                insufficient_data_count=0,
                overall_pass_rate=1.0,
                avg_flake_rate=0.0,
            ),
            flaky_tests=[], real_bugs=[], infra_issues=[],
            insufficient_data=[],
        )
        return {"report": report}

    # -- Build graph -----------------------------------------------------

    graph = StateGraph(FlakeSleuthState)

    graph.add_node("fetch_runs", fetch_runs_node)
    graph.add_node("parse_logs", parse_logs_node)
    graph.add_node("preliminary_correlate", preliminary_correlate_node)
    graph.add_node("classify", classify_node)
    graph.add_node("correlate", correlate_node)
    graph.add_node("report", report_node)

    if skip_download:
        # Phase 2: data already loaded into state, start at parse_logs
        graph.set_entry_point("parse_logs")
        graph.add_edge("parse_logs", "preliminary_correlate")
        graph.add_edge("preliminary_correlate", "classify")
        graph.add_edge("classify", "correlate")
        graph.add_edge("correlate", "report")
        graph.add_edge("report", END)
    else:
        # Legacy/full mode: start at fetch_runs
        graph.set_entry_point("fetch_runs")
        graph.add_conditional_edges(
            "fetch_runs",
            route_after_fetch,
            {
                "has_failures": "parse_logs",
                "no_failures": "report",
                "error": END,
            },
        )
        graph.add_edge("parse_logs", "preliminary_correlate")
        graph.add_edge("preliminary_correlate", "classify")
        graph.add_edge("classify", "correlate")
        graph.add_edge("correlate", "report")
        graph.add_edge("report", END)

    return graph


def compile_graph(
    config: FlakeSleuthConfig,
    skip_download: bool = False,
    repo_name: str | None = None,
) -> Any:
    """Convenience: build + compile the graph."""
    return build_graph(
        config, skip_download=skip_download, repo_name=repo_name
    ).compile()
