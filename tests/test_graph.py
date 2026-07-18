from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from flake_sleuth.config import FlakeSleuthConfig
from flake_sleuth.graph import build_graph, compile_graph, route_after_fetch
from flake_sleuth.state import FlakeSleuthState
from flake_sleuth.types import RunInfo

NOW = datetime(2026, 7, 16, tzinfo=UTC)

RUN_OK = RunInfo(
    run_id=1, workflow_name="CI", status="completed",
    conclusion="success", timestamp=NOW, html_url="",
)

RUN_FAILED = RunInfo(
    run_id=2, workflow_name="CI", status="completed",
    conclusion="failure", timestamp=NOW, html_url="",
)


class TestRouteAfterFetch:
    def test_error_returns_error(self) -> None:
        state = FlakeSleuthState(error="oops")
        assert route_after_fetch(state) == "error"

    def test_no_runs_returns_error(self) -> None:
        state = FlakeSleuthState(runs=[])
        assert route_after_fetch(state) == "error"

    def test_no_failures_returns_no_failures(self) -> None:
        state = FlakeSleuthState(runs=[RUN_OK], failed_runs=[])
        assert route_after_fetch(state) == "no_failures"

    def test_has_failures_returns_has_failures(self) -> None:
        state = FlakeSleuthState(runs=[RUN_OK, RUN_FAILED], failed_runs=[RUN_FAILED])
        assert route_after_fetch(state) == "has_failures"


class TestBuildGraph:
    def test_node_names_are_correct(self) -> None:
        graph = build_graph(FlakeSleuthConfig())
        names = list(graph.nodes.keys())
        assert names == [
            "fetch_runs",
            "parse_logs",
            "preliminary_correlate",
            "classify",
            "correlate",
            "report",
        ]

    def test_compile_succeeds(self) -> None:
        graph = compile_graph(FlakeSleuthConfig())
        assert graph is not None


class TestGraphInvocation:
    @patch("flake_sleuth.graph.GitHubClient")
    def test_fetch_runs_populates_state(
        self,
        mock_client: MagicMock,
    ) -> None:
        mock_client.return_value.fetch_runs.return_value = [RUN_OK, RUN_FAILED]
        graph = compile_graph(FlakeSleuthConfig())
        state = FlakeSleuthState(repo="test/repo")
        result = graph.invoke(state)
        assert len(result.get("runs", [])) == 2
        assert len(result.get("failed_runs", [])) == 1
        assert result["data_quality"].runs_fetched == 2

    @patch("flake_sleuth.graph.GitHubClient")
    def test_fetch_runs_handles_errors(
        self,
        mock_client: MagicMock,
    ) -> None:
        mock_client.return_value.fetch_runs.side_effect = ValueError("API error")
        graph = compile_graph(FlakeSleuthConfig())
        state = FlakeSleuthState(repo="test/repo")
        result = graph.invoke(state)
        assert "error" in result

    @patch("flake_sleuth.graph.GitHubClient")
    @patch("flake_sleuth.graph.LogParser")
    def test_no_failures_skips_parsing(
        self,
        mock_parser: MagicMock,
        mock_client: MagicMock,
    ) -> None:
        mock_client.return_value.fetch_runs.return_value = [RUN_OK]
        graph = compile_graph(FlakeSleuthConfig())
        state = FlakeSleuthState(repo="test/repo")
        result = graph.invoke(state)
        assert result.get("error") is None
        assert result.get("report") is not None
        assert result["report"].summary.total_failures == 0
        mock_parser.return_value.parse.assert_not_called()

    @patch("flake_sleuth.graph.GitHubClient")
    def test_graph_invocation_returns_state(
        self,
        mock_client: MagicMock,
    ) -> None:
        mock_client.return_value.fetch_runs.return_value = []
        graph = compile_graph(FlakeSleuthConfig())
        state = FlakeSleuthState(repo="test/repo")
        result = graph.invoke(state)
        assert isinstance(result, dict)
