"""Command-line interface for ai-flake-sleuth.

Supports two modes:
  1. Legacy mode:  ai-flake-sleuth --repo owner/repo [options]
  2. Two-phase mode:
       ai-flake-sleuth download --repo owner/repo --runs 500 --data-dir ./data/
       ai-flake-sleuth analyze --repo owner/repo --data-dir ./data/ --llm omlx
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from flake_sleuth import __version__
from flake_sleuth.config import FlakeSleuthConfig
from flake_sleuth.graph import compile_graph
from flake_sleuth.report import ReportGenerator
from flake_sleuth.state import FlakeSleuthState

logger = logging.getLogger(__name__)


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add args shared by all subcommands and legacy mode."""
    parser.add_argument("--repo", help="Target repository (owner/repo)")
    parser.add_argument("--github-token", help="GitHub token (default: GITHUB_TOKEN env)")
    parser.add_argument(
        "--runs", type=int, default=100, help="Recent runs to fetch (default: 100)",
    )
    parser.add_argument("--workflow", help="Filter to a specific workflow")
    parser.add_argument(
        "--since", help="Only analyze runs after this date (YYYY-MM-DD)",
    )
    parser.add_argument("--cache", help="Cache directory for API responses")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser for the CLI.

    Uses subcommands for download/analyze, but falls back to legacy
    mode when --repo is passed without a subcommand (backward compat).
    """
    parser = argparse.ArgumentParser(
        prog="ai-flake-sleuth",
        description="Diagnose flaky CI tests using a LangGraph agent",
    )

    parser.add_argument(
        "--version", action="store_true",
        help="Show version and exit",
    )

    subparsers = parser.add_subparsers(dest="command")

    # ── download subcommand ──────────────────────────────────────────
    download_parser = subparsers.add_parser(
        "download",
        help="Phase 1: fetch runs + logs from GitHub (resumable)",
    )
    _add_common_args(download_parser)
    download_parser.add_argument(
        "--data-dir", default="./data/",
        help="Directory to save downloaded data (default: ./data/)",
    )
    download_parser.add_argument(
        "--force", action="store_true",
        help="Re-download even if data already exists",
    )
    download_parser.add_argument(
        "--workers", type=int, default=4,
        help="Parallel download workers (default: 4)",
    )
    download_parser.add_argument(
        "--all-runs", action="store_true",
        help="Download logs for successful runs too (catches flaky tests that retried+passed)",
    )
    download_parser.add_argument(
        "--offset", type=int, default=0,
        help="Skip first N runs from API (for batch downloading, default: 0)",
    )

    # ── analyze subcommand ───────────────────────────────────────────
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Phase 2: analyze downloaded data (no network needed)",
    )
    _add_common_args(analyze_parser)
    analyze_parser.add_argument(
        "--data-dir", default="./data/",
        help="Directory containing downloaded data (default: ./data/)",
    )
    analyze_parser.add_argument(
        "--llm", default="omlx", choices=["omlx", "openai", "deepseek", "opencode"],
        help="LLM provider for ambiguous classifications (default: omlx)",
    )
    analyze_parser.add_argument(
        "--llm-model", default=None,
        help="LLM model name (default: provider-specific)",
    )
    analyze_parser.add_argument(
        "--llm-endpoint", default=None,
        help="LLM API endpoint (default: provider-specific)",
    )
    analyze_parser.add_argument(
        "--no-llm", action="store_true",
        help="Disable LLM fallback (rules-only classification)",
    )
    analyze_parser.add_argument(
        "--force-llm", action="store_true",
        help="Skip rules, classify ALL failures via LLM",
    )
    analyze_parser.add_argument(
        "--limit", type=int, default=0,
        help="Max LLM calls to make (0 = no limit, for testing)",
    )
    analyze_parser.add_argument(
        "--llm-max-tokens", type=int, default=4096,
        help="Max completion tokens for LLM (default: 4096; raise for reasoning models)",
    )
    analyze_parser.add_argument(
        "--no-thinking", action="store_true",
        help="Disable reasoning/thinking mode (Qwen3 etc.) for direct JSON output",
    )
    analyze_parser.add_argument(
        "--llm-log-dir", default=None,
        help="Directory for structured LLM call logs",
    )
    analyze_parser.add_argument(
        "--format", choices=["table", "json", "markdown", "all"],
        default="table", help="Output format (default: table)",
    )
    analyze_parser.add_argument(
        "--output", default=None,
        help="Output directory (default: ./runs/{repo}/{llm}/batch-{offset}-{end}/)",
    )
    analyze_parser.add_argument(
        "--offset", type=int, default=0,
        help="Start analyzing from run N (for batch analysis, default: 0)",
    )
    analyze_parser.add_argument(
        "--batch-size", type=int, default=None,
        help="Analyze only N runs starting from --offset (for batch analysis)",
    )

    # ── preflight subcommand ─────────────────────────────────────────
    preflight_parser = subparsers.add_parser(
        "preflight",
        help="Validate environment: tokens, API keys, Ollama, disk space",
    )
    preflight_parser.add_argument(
        "--repos", nargs="*", default=[],
        help="Repos to smoke-test (fetch 1 run each to verify API access)",
    )
    preflight_parser.add_argument(
        "--llm-providers", nargs="*", default=["omlx", "openai", "deepseek"],
        help="LLM providers to validate keys for",
    )
    preflight_parser.add_argument(
        "--data-dir", default="./data/",
        help="Data directory (used for disk space check)",
    )

    # ── verify subcommand ────────────────────────────────────────────
    verify_parser = subparsers.add_parser(
        "verify",
        help="Validate downloaded data before analysis",
    )
    verify_parser.add_argument("--repo", required=True, help="Target repository (owner/repo)")
    verify_parser.add_argument(
        "--data-dir", default="./data/",
        help="Directory containing downloaded data",
    )

    # ── legacy mode: add common + legacy-specific args to top-level ──
    _add_common_args(parser)
    parser.add_argument(
        "--format", choices=["table", "json", "markdown", "all"],
        default="table", help="Output format (default: table)",
    )
    parser.add_argument("--output", help="Output file path or directory (default: stdout)")
    parser.add_argument(
        "--llm", default="omlx", choices=["omlx", "openai", "deepseek", "opencode"],
        help="LLM provider for ambiguous classifications (default: omlx)",
    )
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM fallback")
    parser.add_argument("--force-llm", action="store_true", help="Skip rules, classify all via LLM")

    return parser


def _default_llm_model(provider: str) -> str:
    """Return the default model for a given provider."""
    defaults: dict[str, str] = {
        "omlx": "qwen2.5-coder:7b",
        "openai": "gpt-4o-mini",
        "deepseek": "deepseek-chat",
        "opencode": "deepseek-v4-flash",
    }
    return defaults.get(provider, "qwen2.5-coder:7b")


def _default_llm_endpoint(provider: str) -> str:
    """Return the default endpoint for a given provider."""
    defaults: dict[str, str] = {
        "omlx": "http://localhost:11434",
        "openai": "https://api.openai.com",
        "deepseek": "https://api.deepseek.com",
        "opencode": "https://opencode.ai/zen",
    }
    return defaults.get(provider, "http://localhost:11434")


def main(argv: list[str] | None = None) -> int:
    """Entry point: parse args, dispatch to download/analyze/legacy."""
    parser = build_parser()

    # --version should work even without --repo
    if argv and "--version" in argv:
        print(f"ai-flake-sleuth v{__version__}")
        return 0

    args = parser.parse_args(argv)

    log_level = logging.DEBUG if getattr(args, "verbose", False) else logging.WARNING
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    # Dispatch based on subcommand
    if args.command == "download":
        return _run_download(args)
    elif args.command == "analyze":
        return _run_analyze(args)
    elif args.command == "preflight":
        return _run_preflight(args)
    elif args.command == "verify":
        return _run_verify(args)
    else:
        # Legacy mode: single-pipeline (download + analyze in one shot)
        return _run_legacy(args)


def _resolve_token(args: argparse.Namespace) -> str | None:
    token = getattr(args, "github_token", None)
    return token or os.environ.get("GITHUB_TOKEN")


def _run_legacy(args: argparse.Namespace) -> int:
    """Legacy single-pipeline mode: fetch + analyze in one invocation."""
    if not args.repo:
        print("Error: --repo is required.", file=sys.stderr)
        print("Usage: ai-flake-sleuth --repo owner/repo [options]", file=sys.stderr)
        print("   or: ai-flake-sleuth download --repo owner/repo [options]", file=sys.stderr)
        print("   or: ai-flake-sleuth analyze --repo owner/repo [options]", file=sys.stderr)
        return 1

    config = FlakeSleuthConfig.from_args(args)
    config.github_token = config.github_token or _resolve_token(args)

    if not config.github_token:
        print("Error: GITHUB_TOKEN is required.", file=sys.stderr)
        print("Set GITHUB_TOKEN env var or pass --github-token.", file=sys.stderr)
        return 1

    state = FlakeSleuthState(repo=args.repo)
    graph = compile_graph(config, repo_name=args.repo)
    final_state = graph.invoke(state)

    if final_state.get("error"):
        print(f"Error: {final_state['error']}", file=sys.stderr)
        return 1

    report = final_state.get("report")
    if report is None:
        print("No report generated.", file=sys.stderr)
        return 1

    generator = ReportGenerator()
    formats = ["table", "json", "markdown"] if config.format == "all" else [config.format]

    for fmt in formats:
        output = generator.generate(report, fmt)
        if config.output:
            _write_output(config.output, output, fmt, report.repo)
        else:
            print(output)
            if fmt != formats[-1]:
                print()

    return 0


def _run_download(args: argparse.Namespace) -> int:
    """Phase 1: Download runs + logs from GitHub with resume support."""
    if not args.repo:
        print("Error: --repo is required for download.", file=sys.stderr)
        return 1

    config = FlakeSleuthConfig.from_args(args)
    config.github_token = config.github_token or _resolve_token(args)

    if not config.github_token:
        print("Error: GITHUB_TOKEN is required.", file=sys.stderr)
        return 1

    from flake_sleuth.downloader import Downloader

    downloader = Downloader(
        token=config.github_token,
        data_dir=args.data_dir,
        per_page=config.per_page,
        max_retries=config.max_retries,
        workers=config.workers,
    )

    try:
        result = downloader.download(
            repo=args.repo,
            n=config.runs,
            workflow=config.workflow,
            force=config.force,
            all_runs=getattr(args, "all_runs", False),
            offset=getattr(args, "offset", 0),
        )
    except Exception as exc:
        print(f"Download error: {exc}", file=sys.stderr)
        return 1

    print(f"Download complete: {result}")
    return 0


def _run_analyze(args: argparse.Namespace) -> int:
    """Phase 2: Analyze downloaded data (no network needed).

    Supports batch analysis via --offset and --batch-size. Each batch's
    outputs (reports, LLM logs, LLM cache) are preserved in a dedicated
    directory so re-runs don't overwrite and results can be compared.
    """
    if not args.repo:
        print("Error: --repo is required for analyze.", file=sys.stderr)
        return 1

    # Fill in provider-specific defaults
    if args.no_llm and getattr(args, "force_llm", False):
        print("Error: --no-llm and --force-llm are mutually exclusive.", file=sys.stderr)
        return 1
    provider_label = "no-llm" if args.no_llm else args.llm
    llm_model = args.llm_model or _default_llm_model(args.llm)
    llm_endpoint = args.llm_endpoint or _default_llm_endpoint(args.llm)

    offset = getattr(args, "offset", 0)
    batch_size = getattr(args, "batch_size", None)

    # Compute batch end for directory naming
    if batch_size is not None:
        batch_end = offset + batch_size
        batch_label = f"batch-{offset:04d}-{batch_end:04d}"
    else:
        batch_label = f"batch-{offset:04d}-all"

    # Determine output directory structure:
    #   {output}/{repo}/{provider}/{batch_label}/
    # This preserves every run's outputs separately for comparison.
    safe_repo = args.repo.replace("/", "_")
    if args.output:
        output_base = Path(args.output)
    else:
        output_base = Path("./runs")

    run_output_dir = output_base / safe_repo / provider_label / batch_label
    run_output_dir.mkdir(parents=True, exist_ok=True)

    # LLM log dir and cache dir live inside the run output dir
    llm_log_dir = str(run_output_dir / "llm-logs")

    # Build a namespace with all fields for config
    import types
    ns = types.SimpleNamespace(
        github_token=args.github_token,
        runs=args.runs,
        workflow=args.workflow,
        since=args.since,
        cache_dir=getattr(args, "cache", None),
        llm_provider=args.llm,
        llm_model=llm_model,
        llm_endpoint=llm_endpoint,
        no_llm=args.no_llm,
        force_llm=getattr(args, "force_llm", False),
        llm_limit=getattr(args, "limit", 0),
        llm_max_tokens=getattr(args, "llm_max_tokens", 4096),
        llm_disable_thinking=getattr(args, "no_thinking", False),
        llm_log_dir=llm_log_dir,
        format=args.format,
        output=str(run_output_dir),
        verbose=args.verbose,
        data_dir=args.data_dir,
    )
    config = FlakeSleuthConfig.from_args(ns)

    # LLM cache is per-repo per-provider (shared across batches).
    # graph.py builds this path from config.data_dir + llm_provider,
    # so we just ensure config.data_dir is set correctly below.

    from flake_sleuth.downloader import Downloader

    downloader = Downloader(
        token=config.github_token or "",
        data_dir=args.data_dir,
        per_page=config.per_page,
        max_retries=config.max_retries,
        workers=1,
    )

    try:
        runs, failed_runs = downloader.load_data(
            args.repo,
            offset=offset,
            batch_size=batch_size,
        )
    except FileNotFoundError:
        print(
            f"No downloaded data found for {args.repo} in {args.data_dir}.",
            file=sys.stderr,
        )
        print(f"Run 'ai-flake-sleuth download --repo {args.repo}' first.", file=sys.stderr)
        return 1

    if not runs:
        print(
            f"No runs found for {args.repo} (offset={offset}).",
            file=sys.stderr,
        )
        return 1

    print(f"Analyzing {len(runs)} runs ({len(failed_runs)} with failures) for {args.repo}")
    print(f"  LLM: {provider_label} ({llm_model})")
    print(f"  Batch: {batch_label}")
    print(f"  Output: {run_output_dir}")

    # Build graph and run analysis with loaded data
    from flake_sleuth.types import DataQuality

    workflows = {r.workflow_name for r in runs}
    state = FlakeSleuthState(
        repo=args.repo,
        runs=runs,
        failed_runs=failed_runs,
        data_quality=DataQuality(
            runs_requested=len(runs),
            runs_fetched=len(runs),
            runs_with_failures=len(failed_runs),
            runs_with_logs=len(failed_runs),
            runs_skipped_expired=0,
            runs_skipped_error=0,
            effective_sample=len(failed_runs),
            workflows_analyzed=sorted(workflows),
        ),
    )

    # Override the LLM cache dir in config so graph picks it up
    config.data_dir = args.data_dir

    graph = compile_graph(config, skip_download=True, repo_name=args.repo)

    # Patch the LLM adapter's cache_dir after graph build
    # (graph.py reads config.data_dir to build the cache path, but we
    # need the per-provider path)
    # This is handled by graph.py reading config.data_dir + llm_provider
    # We just need to make sure the path matches
    final_state = graph.invoke(state)

    if final_state.get("error"):
        print(f"Error: {final_state['error']}", file=sys.stderr)
        return 1

    report = final_state.get("report")
    if report is None:
        print("No report generated.", file=sys.stderr)
        return 1

    generator = ReportGenerator()
    formats = ["table", "json", "markdown"] if config.format == "all" else [config.format]

    for fmt in formats:
        output = generator.generate(report, fmt)
        ext = {"table": "txt", "json": "json", "markdown": "md"}.get(fmt, "txt")
        out_file = run_output_dir / f"report.{ext}"
        out_file.write_text(output)
        print(f"  Wrote {fmt} report to {out_file}")

    # Write a batch summary for easy comparison
    summary = {
        "repo": args.repo,
        "provider": provider_label,
        "model": llm_model if not args.no_llm else "N/A",
        "batch": batch_label,
        "offset": offset,
        "batch_size": batch_size,
        "runs_analyzed": len(runs),
        "runs_with_failures": len(failed_runs),
        "flaky_count": len(report.flaky_tests),
        "real_bug_count": len(report.real_bugs),
        "infra_count": len(report.infra_issues),
        "insufficient_data_count": len(report.insufficient_data),
        "overall_pass_rate": report.summary.overall_pass_rate,
        "avg_flake_rate": report.summary.avg_flake_rate,
        "llm_call_count": report.summary.llm_call_count,
        "llm_truncated_count": report.summary.llm_truncated_count,
        "llm_parse_error_count": report.summary.llm_parse_error_count,
        "llm_fallback_count": report.summary.llm_fallback_count,
        "output_dir": str(run_output_dir),
    }
    summary_file = run_output_dir / "summary.json"
    summary_file.write_text(json.dumps(summary, indent=2, default=str))
    print(f"  Wrote summary to {summary_file}")

    return 0


def _run_preflight(args: argparse.Namespace) -> int:
    """Validate environment before starting the field study."""
    from flake_sleuth.config import _resolve_llm_api_key
    from flake_sleuth.downloader import Downloader

    failures: list[str] = []

    # 1. GitHub token
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        print(f"  [OK] GITHUB_TOKEN is set ({len(token)} chars)")
    else:
        print("  [FAIL] GITHUB_TOKEN is not set")
        failures.append("GITHUB_TOKEN")

    # 2. LLM API keys
    for provider in args.llm_providers:
        key = _resolve_llm_api_key(provider)
        if provider == "omlx":
            print(f"  [OK] {provider}: no key needed (local)")
        elif key:
            print(f"  [OK] {provider}: API key set ({len(key)} chars)")
        else:
            print(f"  [WARN] {provider}: API key not set — analyze with this provider will fail")
            failures.append(f"{provider}_API_KEY")

    # 3. GitHub API smoke test
    if token and args.repos:
        downloader = Downloader(
            token=token,
            data_dir=args.data_dir,
            workers=1,
        )
        try:
            rate = downloader.verify_rate_limit()
            print(f"  [OK] GitHub API: {rate['remaining']}/{rate['limit']} requests remaining")
        except Exception as exc:
            print(f"  [FAIL] GitHub API check failed: {exc}")
            failures.append("github_api")

        for repo in args.repos:
            ok = downloader.smoke_test(repo, n=1)
            if ok:
                print(f"  [OK] Smoke test: {repo}")
            else:
                print(f"  [FAIL] Smoke test: {repo}")
                failures.append(f"smoke_{repo}")

    # 4. Disk space
    data_path = Path(args.data_dir)
    data_path.mkdir(parents=True, exist_ok=True)
    stat = os.statvfs(str(data_path))
    free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
    if free_gb >= 6:
        print(f"  [OK] Disk space: {free_gb:.1f} GB free (need ≥6 GB)")
    else:
        print(f"  [WARN] Disk space: {free_gb:.1f} GB free (need ≥6 GB)")
        failures.append("disk_space")

    if failures:
        print(f"\n  {len(failures)} issue(s) found: {', '.join(failures)}")
        return 1
    print("\n  All pre-flight checks passed.")
    return 0


def _run_verify(args: argparse.Namespace) -> int:
    """Validate downloaded data before running analysis."""
    from flake_sleuth.downloader import Downloader

    downloader = Downloader(
        token="",
        data_dir=args.data_dir,
        workers=1,
    )

    # Check manifest
    manifest = downloader._load_manifest(args.repo)
    if not manifest:
        print(f"  [FAIL] No manifest found for {args.repo} in {args.data_dir}")
        return 1

    print(f"  Manifest status: {manifest.get('status')}")
    print(f"  Runs fetched: {manifest.get('runs_fetched', 0)}")
    print(f"  Runs with failures: {manifest.get('runs_with_failures', 0)}")
    print(f"  Runs with logs: {manifest.get('runs_with_logs', 0)}")
    print(f"  Skipped (expired): {manifest.get('runs_skipped_expired', 0)}")
    print(f"  Skipped (error): {manifest.get('runs_skipped_error', 0)}")

    # Count files on disk
    runs_dir = downloader._runs_dir(args.repo)
    logs_dir = downloader._logs_dir(args.repo)
    run_files = list(runs_dir.glob("*.json"))
    log_files = list(logs_dir.glob("*.zip"))

    print(f"  Run JSON files on disk: {len(run_files)}")
    print(f"  Log ZIP files on disk: {len(log_files)}")

    # Validate ZIPs
    bad_zips: list[str] = []
    for zf in log_files:
        if not Downloader._is_valid_zip(zf):
            bad_zips.append(zf.name)

    if bad_zips:
        print(f"  [WARN] {len(bad_zips)} corrupt ZIP(s): {bad_zips[:5]}")
    else:
        print("  All ZIP files valid")

    # Check if we have parseable data
    failed_runs = [r for r in run_files
                   if json.loads(r.read_text()).get("conclusion") == "failure"]
    if not failed_runs:
        print("  [WARN] No failed runs found — analysis will produce a clean report")
    else:
        print(f"  {len(failed_runs)} failed runs ready for analysis")

    effective = min(len(log_files), len(failed_runs))
    print(f"  Effective sample: {effective} runs with logs + failures")

    if manifest.get("status") != "complete":
        print("  [FAIL] Download is not complete — re-run download to resume")
        return 1

    print("\n  Data verified — ready for analysis.")
    return 0


def _write_output(output_path: str, content: str, fmt: str, repo: str) -> None:
    from datetime import datetime
    from pathlib import Path

    path = Path(output_path)
    if path.is_dir():
        ext = {"table": "txt", "json": "json", "markdown": "md"}.get(fmt, "txt")
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        safe_repo = repo.replace("/", "_")
        filename = f"flake-sleuth-{safe_repo}-{ts}.{ext}"
        full_path = path / filename
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        print(f"Wrote {fmt} report to {full_path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        print(f"Wrote {fmt} report to {path}")
