"""End-to-end pipeline integration tests using MockGitHubClient.

Exercises the full LangGraph pipeline from fetch through report generation
without hitting the real GitHub API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

from flake_sleuth.config import FlakeSleuthConfig
from flake_sleuth.graph import compile_graph
from flake_sleuth.report import ReportGenerator
from flake_sleuth.state import FlakeSleuthState
from tests.fixtures.mock_github_api import MockGitHubClient

NOW = datetime.fromisoformat("2026-07-16T12:00:00Z")


def _make_config(**overrides: Any) -> FlakeSleuthConfig:
    kwargs: dict[str, Any] = {
        "github_token": "fake-token",
        "runs": 100,
        "min_sample": 50,
        "llm_provider": "omlx",
        "no_llm": True,
    }
    kwargs.update(overrides)
    return FlakeSleuthConfig(**kwargs)


def _make_clean_mock() -> MockGitHubClient:
    """Return a MockGitHubClient whose fetch_runs returns only successes."""
    mock = MockGitHubClient()

    def _all_success(
        repo: str, n: int = 100,
        workflow: str | None = None,
        since: datetime | None = None,
    ) -> list:
        runs = MockGitHubClient().fetch_runs(repo, n, workflow, since)
        for r in runs:
            r.conclusion = "success"
        return runs

    mock.fetch_runs = _all_success  # type: ignore[method-assign]
    return mock


class TestHasFailuresPath:
    """Full pipeline with a mix of failed, successful, and expired runs."""

    @patch("flake_sleuth.graph.GitHubClient", MockGitHubClient)
    def test_full_pipeline_produces_report(self) -> None:
        config = _make_config()
        graph = compile_graph(config)
        state = FlakeSleuthState(repo="test/repo")
        result = graph.invoke(state)

        assert result.get("error") is None
        report = result.get("report")
        assert report is not None
        assert report.repo == "test/repo"

    @patch("flake_sleuth.graph.GitHubClient", MockGitHubClient)
    def test_data_quality_tracks_expired_logs(self) -> None:
        config = _make_config()
        graph = compile_graph(config)
        state = FlakeSleuthState(repo="test/repo")
        result = graph.invoke(state)

        dq = result["report"].data_quality
        assert dq.runs_fetched == 10
        assert dq.runs_with_failures >= 4
        assert dq.runs_skipped_expired >= 2
        assert dq.runs_with_logs >= 4
        assert dq.effective_sample >= 4

    @patch("flake_sleuth.graph.GitHubClient", MockGitHubClient)
    def test_report_contains_all_formats(self) -> None:
        config = _make_config()
        graph = compile_graph(config)
        state = FlakeSleuthState(repo="test/repo")
        result = graph.invoke(state)

        report = result["report"]
        generator = ReportGenerator()

        table_output = generator.generate(report, "table")
        assert "=== FlakeSleuth Report: test/repo ===" in table_output
        assert "Summary:" in table_output

        json_output = generator.generate(report, "json")
        assert '"repo": "test/repo"' in json_output

        md_output = generator.generate(report, "markdown")
        assert "# FlakeSleuth Report: test/repo" in md_output

    @patch("flake_sleuth.graph.GitHubClient", MockGitHubClient)
    def test_summary_stats_are_populated(self) -> None:
        config = _make_config()
        graph = compile_graph(config)
        state = FlakeSleuthState(repo="test/repo")
        result = graph.invoke(state)

        s = result["report"].summary
        assert s.total_runs >= 10
        assert s.total_failures >= 0
        assert s.total_tests_analyzed >= 0
        assert s.flaky_count + s.real_bug_count + s.infra_count + s.insufficient_data_count > 0

    @patch("flake_sleuth.graph.GitHubClient", MockGitHubClient)
    def test_classifications_produced(self) -> None:
        config = _make_config()
        graph = compile_graph(config)
        state = FlakeSleuthState(repo="test/repo")
        result = graph.invoke(state)

        assert len(result.get("classifications", [])) > 0

    @patch("flake_sleuth.graph.GitHubClient", MockGitHubClient)
    def test_per_test_stats_exist(self) -> None:
        config = _make_config()
        graph = compile_graph(config)
        state = FlakeSleuthState(repo="test/repo")
        result = graph.invoke(state)

        stats = result.get("per_test_stats", {})
        assert len(stats) > 0
        for test_name, ts in stats.items():
            assert ts.total_executions > 0


class TestNoFailuresPath:
    """Pipeline when all runs pass — should produce a clean report."""

    @patch("flake_sleuth.graph.GitHubClient")
    def test_clean_report_produced(self, mock_client_class: MagicMock) -> None:
        mock_client = _make_clean_mock()
        mock_client_class.return_value = mock_client

        config = _make_config()
        graph = compile_graph(config)
        state = FlakeSleuthState(repo="test/repo")
        result = graph.invoke(state)

        assert result.get("error") is None
        report = result.get("report")
        assert report is not None
        assert report.summary.total_failures == 0

    @patch("flake_sleuth.graph.GitHubClient")
    def test_clean_message_in_table(self, mock_client_class: MagicMock) -> None:
        mock_client = _make_clean_mock()
        mock_client_class.return_value = mock_client

        config = _make_config()
        graph = compile_graph(config)
        state = FlakeSleuthState(repo="test/repo")
        result = graph.invoke(state)

        output = ReportGenerator().generate(result["report"], "table")
        assert "No failures" in output
        assert "CI health: clean" in output


class TestAllRunsExpired:
    """Pipeline when all failed runs have expired logs."""

    @patch("flake_sleuth.graph.GitHubClient")
    def test_expired_logs_handled(self, mock_client_class: MagicMock) -> None:
        mock_client = MockGitHubClient()
        mock_client.fetch_logs = (  # type: ignore[method-assign]
            lambda repo, run_id: None
        )
        mock_client_class.return_value = mock_client

        config = _make_config()
        graph = compile_graph(config)
        state = FlakeSleuthState(repo="test/repo")
        result = graph.invoke(state)

        assert result.get("error") is None
        report = result.get("report")
        assert report is not None
        dq = report.data_quality
        assert dq.runs_skipped_expired >= 1
        assert dq.effective_sample == 0


class TestGraphRoutes:
    """Verify graph routing works end-to-end."""

    @patch("flake_sleuth.graph.GitHubClient", MockGitHubClient)
    def test_has_failures_route_parses_logs(self) -> None:
        config = _make_config()
        graph = compile_graph(config)
        state = FlakeSleuthState(repo="test/repo")
        result = graph.invoke(state)

        assert result.get("error") is None
        # With failures present, parsers should produce test_results.
        assert len(result.get("test_results", [])) > 0

    @patch("flake_sleuth.graph.GitHubClient")
    def test_no_failures_route_skips_parsing(self, mock_client_class: MagicMock) -> None:
        mock_client = _make_clean_mock()
        mock_client_class.return_value = mock_client

        config = _make_config()
        graph = compile_graph(config)
        state = FlakeSleuthState(repo="test/repo")
        result = graph.invoke(state)

        test_results = result.get("test_results", [])
        assert len(test_results) == 0
        assert result.get("report") is not None
        assert result["report"].summary.total_failures == 0
