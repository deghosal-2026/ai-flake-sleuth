from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from flake_sleuth.cli import build_parser, main


class TestBuildParser:
    def test_parser_created(self) -> None:
        parser = build_parser()
        assert parser is not None
        assert parser.prog == "ai-flake-sleuth"

    def test_repo_required(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--repo", "owner/repo"])
        assert args.repo == "owner/repo"

    def test_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--repo", "owner/repo"])
        assert args.runs == 100
        assert args.format == "table"
        assert args.output is None
        assert args.workflow is None
        assert args.since is None
        assert args.cache is None
        assert args.llm == "omlx"
        assert args.no_llm is False
        assert args.verbose is False

    def test_version_flag(self) -> None:
        parser = build_parser()
        with patch("sys.argv", ["prog", "--version"]):
            import sys
            with patch.object(sys, "exit"):
                try:
                    parser.parse_args(["--version"])
                except SystemExit:
                    pass

    def test_all_flags(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "--repo", "test/repo",
            "--runs", "50",
            "--format", "json",
            "--output", "./reports/",
            "--workflow", "CI",
            "--since", "2026-07-01",
            "--cache", ".cache/",
            "--llm", "openai",
            "--no-llm",
            "--verbose",
        ])
        assert args.repo == "test/repo"
        assert args.runs == 50
        assert args.format == "json"
        assert args.output == "./reports/"
        assert args.workflow == "CI"
        assert args.since == "2026-07-01"
        assert args.cache == ".cache/"
        assert args.llm == "openai"
        assert args.no_llm is True
        assert args.verbose is True


class TestMain:
    def test_version_exits_zero(self) -> None:
        rc = main(["--version"])
        assert rc == 0

    def test_missing_token_returns_one(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            rc = main(["--repo", "test/repo"])
            assert rc == 1

    @patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"}, clear=True)
    @patch("flake_sleuth.cli.compile_graph")
    def test_invokes_graph(self, mock_compile: MagicMock) -> None:
        from datetime import datetime

        from flake_sleuth.types import (
            DataQuality,
            FlakeSleuthReport,
            ReportSummary,
        )
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {
            "report": FlakeSleuthReport(
                repo="test/repo",
                timestamp=datetime.now(),
                data_quality=DataQuality(
                    runs_requested=10, runs_fetched=10, runs_with_failures=0,
                    runs_with_logs=10, runs_skipped_expired=0,
                    runs_skipped_error=0, effective_sample=10,
                    workflows_analyzed=["CI"],
                ),
                summary=ReportSummary(
                    total_runs=10, total_failures=0, total_tests_analyzed=0,
                    flaky_count=0, real_bug_count=0, infra_count=0,
                    insufficient_data_count=0, overall_pass_rate=1.0,
                    avg_flake_rate=0.0,
                ),
                flaky_tests=[], real_bugs=[], infra_issues=[],
                insufficient_data=[],
            ),
            "error": None,
        }
        mock_compile.return_value = mock_graph
        rc = main(["--repo", "test/repo"])
        assert rc == 0
        mock_graph.invoke.assert_called_once()

    @patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"}, clear=True)
    @patch("flake_sleuth.cli.compile_graph")
    def test_handles_graph_error(self, mock_compile: MagicMock) -> None:
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"error": "something went wrong"}
        mock_compile.return_value = mock_graph
        rc = main(["--repo", "test/repo"])
        assert rc == 1

    @patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"}, clear=True)
    @patch("flake_sleuth.cli.compile_graph")
    def test_handles_missing_report(self, mock_compile: MagicMock) -> None:
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"report": None}
        mock_compile.return_value = mock_graph
        rc = main(["--repo", "test/repo"])
        assert rc == 1
