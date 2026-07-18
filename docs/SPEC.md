# SPEC: ai-flake-sleuth — Technical Specification

| Field | Value |
|---|---|
| **Status** | Approved |
| **PRD** | [docs/PRD.md](./PRD.md) |
| **Date** | 2026-07-17 |
| **Author** | Debashish Ghosal |
| **Target Ship** | 2026-07-25 |
| **Scope** | v1 = M1-M4 (diagnostic only) |

> This document specifies HOW each requirement in the PRD is implemented. PRD defines WHY and WHAT; SPEC defines HOW and tech choices.

---

## 1. Package Structure

```
ai-flake-sleuth/
├── pyproject.toml
├── README.md
├── LICENSE
├── .gitignore
├── docs/
│   ├── PRD.md
│   └── SPEC.md                    ← this file
├── src/
│   └── flake_sleuth/
│       ├── __init__.py            # Public API exports
│       ├── state.py               # LangGraph state (Pydantic BaseModel)
│       ├── graph.py               # M4: LangGraph StateGraph (nodes + conditional edges)
│       ├── github_client.py       # M1: GitHub Actions API client (PyGithub)
│       ├── log_parser.py          # M2: Log download + parse → structured test results
│       ├── classifier.py          # M3: Hybrid rules + LLM classifier (two-pass)
│       ├── correlator.py          # M4: Cross-run correlation (flake rate, error distribution)
│       ├── error_signature.py     # Error normalization + hash-based grouping
│       ├── report.py              # Report generation (CLI table + JSON + markdown)
│       ├── cli.py                 # CLI entry point (argparse)
│       ├── cache.py               # Optional API response cache
│       ├── config.py              # Config dataclass + defaults
│       ├── llm.py                 # LLM adapter (OMLX default + cloud escalation)
│       ├── exceptions.py          # All custom exceptions
│       └── types.py               # Shared data structures (RunInfo, TestResult, etc.)
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # Fixtures: mock GitHub API, sample logs, sample runs
│   ├── test_github_client.py
│   ├── test_log_parser.py
│   ├── test_classifier.py
│   ├── test_correlator.py
│   ├── test_error_signature.py
│   ├── test_report.py
│   ├── test_graph.py
│   ├── test_cli.py
│   ├── test_cache.py
│   ├── test_config.py
│   ├── test_llm.py
│   ├── fixtures/
│   │   ├── sample_runs.json       # Mock GitHub Actions run metadata
│   │   ├── sample_logs/           # Mock job log files (pytest, unittest formats)
│   │   │   ├── pytest_failed.txt
│   │   │   ├── unittest_failed.txt
│   │   │   ├── infra_timeout.txt
│   │   │   └── clean_run.txt
│   │   └── mock_github_api.py     # Mock client returning fixture data
│   └── integration/
│       └── test_pipeline_integration.py
└── reports/                       # Default output directory for field study
```

---

## 2. System Architecture

### 2.1 Architecture Diagram

```
                                    ai-flake-sleuth v1 — Architecture
╔════════════════════════════════════════════════════════════════════════════════════════════════════╗
║                                                                                                      ║
║   ┌─────────┐                                                                                        ║
║   │  User   │  ai-flake-sleuth --repo pytest-dev/pytest --runs 100 --format all --output ./reports/  ║
║   │  (CLI)  │──────┐                                                                                ║
║   └─────────┘      │                                                                                ║
║                    ▼                                                                                ║
║   ┌──────────────────────────────────────────────────────────────────────────────────────────────┐  ║
║   │                          CLI (cli.py — argparse)                                             │  ║
║   │  Parses args → builds Config → creates components → invokes LangGraph                        │  ║
║   └──────────────────────────────┬───────────────────────────────────────────────────────────────┘  ║
║                                  │                                                                    ║
║                                  ▼                                                                    ║
║   ┌──────────────────────────────────────────────────────────────────────────────────────────────┐  ║
║   │                    LangGraph StateGraph (graph.py)                                           │  ║
║   │                    State: FlakeSleuthState (Pydantic BaseModel)                              │  ║
║   │                                                                                              │  ║
║   │  ┌──────────────┐    conditional edge     ┌──────────────┐                                  │  ║
║   │  │  fetch_runs  │──────────────────────▶ │  parse_logs  │                                  │  ║
║   │  │  (M1)        │   route_after_fetch()   │  (M2)        │                                  │  ║
║   │  └──────┬───────┘                         └──────┬───────┘                                  │  ║
║   │         │                                        │                                          │  ║
║   │    ┌────┼────┐                                   │                                          │  ║
║   │    │    │    │                                   │                                          │  ║
║   │    ▼    ▼    ▼                                   ▼                                          │  ║
║   │  has   no   rate                          ┌──────────────┐                                  │  ║
║   │  fail  fail  limit                        │ preliminary  │  two-pass: build per-test        │  ║
║   │    │    │    │ retry                       │ _correlate   │  stats from all TestResults      │  ║
║   │    │    │    │                             └──────┬───────┘                                  │  ║
║   │    │    ▼    │                                    │                                          │  ║
║   │    │  ┌────────┐                                 ▼                                          │  ║
║   │    │  │ report │                          ┌──────────────┐                                  │  ║
║   │    │  │ (clean)│                          │  classify    │  two-pass: classify with          │  ║
║   │    │  └────────┘                          │  (M3)        │  cross-run context                │  ║
║   │    │                                        └──────┬───────┘                                  │  ║
║   │    ▼                                               │                                          │  ║
║   │  ┌──────────────┐                                  ▼                                          │  ║
║   │  │  report      │                          ┌──────────────┐                                  │  ║
║   │  │  (full)      │◀────────────────────────│  correlate   │  final aggregation +              │  ║
║   │  └──────────────┘                          │  (M4)        │  final_category                   │  ║
║   │                                            └──────────────┘                                  │  ║
║   └──────────────────────────────────────────────────────────────────────────────────────────────┘  ║
║         │                  │                    │                │                                    ║
║         ▼                  ▼                    ▼                ▼                                    ║
║   ┌───────────┐    ┌──────────────┐    ┌──────────────┐  ┌──────────────┐                           ║
║   │ GitHub    │    │ LogParser     │    │ Classifier   │  │ ReportGen    │                           ║
║   │ Client    │    │ (log_parser)  │    │ (classifier) │  │ (report)     │                           ║
║   │ (PyGithub)│    │               │    │              │  │              │                           ║
║   │           │    │ regex-first   │    │ rules-first  │  │ 3 formats:   │                           ║
║   │ fetch_    │    │ LLM-fallback  │    │ LLM-fallback │  │ table (rich) │                           ║
║   │ runs()    │    │               │    │ (ambiguous)  │  │ JSON         │                           ║
║   │ fetch_    │    │ pytest        │    │              │  │ markdown     │                           ║
║   │ logs()    │    │ unittest      │    │ real_bug     │  └──────────────┘                           ║
║   │           │    │ patterns      │    │ flaky        │                                              ║
║   │ rate-limit│    └──────────────┘    │ infra        │                                              ║
║   │ aware     │                        │ insuff. data │                                              ║
║   │ + cache   │                        └──────┬───────┘                                              ║
║   └─────┬─────┘                               │                                                      ║
║         │                                     ▼                                                      ║
║         │              ┌──────────────────────────────────────┐                                      ║
║         │              │  LLM Adapter (llm.py)                 │                                      ║
║         │              │                                      │                                      ║
║         │              │  OMLX (default, free)                 │                                      ║
║         │              │  ├── qwen2.5-coder:7b                 │                                      ║
║         │              │  └── llama3.1:8b                      │                                      ║
║         │              │                                      │                                      ║
║         │              │  Cloud escalation (ambiguous only)    │                                      ║
║         │              │  ├── OpenAI gpt-4o-mini              │                                      ║
║         │              │  └── DeepSeek v4-flash               │                                      ║
║         │              └──────────────────────────────────────┘                                      ║
║         │                                                                                            ║
║         ▼                                                                                            ║
║   ┌──────────────────────────────────────┐    ┌─────────────────────────────────────────────────┐  ║
║   │  GitHub Actions REST API             │    │  ErrorSignature (error_signature.py)             │  ║
║   │                                      │    │                                                 │  ║
║   │  /repos/{owner}/{repo}/actions/runs  │    │  normalize(error_text) → str                    │  ║
║   │  /repos/{repo}/actions/runs/{id}/logs│    │  signature(normalized) → sha256[:16]            │  ║
║   │  /repos/{repo}/actions/runs/{id}/jobs│    │                                                 │  ║
║   │  /rate_limit                         │    │  Strips: paths, line numbers, timestamps,       │  ║
║   │                                      │    │  memory addresses, PIDs, ports                  │  ║
║   │  Rate limit: 5,000/hr (auth)         │    │  Groups similar failures by hash                │  ║
║   │  Logs expire: 90 days                │    │                                                 │  ║
║   └──────────────────────────────────────┘    └─────────────────────────────────────────────────┘  ║
║                                                                                                      ║
║   ┌──────────────────────────────────────────────────────────────────────────────────────────────┐  ║
║   │  Output (--format all --output ./reports/)                                                   │  ║
║   │                                                                                              │  ║
║   │  flake-sleuth-{repo}-{timestamp}.txt   ← rich CLI table (8 columns)                         │  ║
║   │  flake-sleuth-{repo}-{timestamp}.json  ← agentic-ready JSON (v2 LangGraph state input)      │  ║
║   │  flake-sleuth-{repo}-{timestamp}.md    ← markdown for PRs/issues/articles                    │  ║
║   └──────────────────────────────────────────────────────────────────────────────────────────────┘  ║
║                                                                                                      ║
╚════════════════════════════════════════════════════════════════════════════════════════════════════╝
```

### 2.2 Data Flow Summary

```
User CLI
  │
  ▼
fetch_runs ──(no failures)──▶ report (clean)
  │
  │(has failures)
  ▼
parse_logs ──▶ preliminary_correlate ──▶ classify ──▶ correlate ──▶ report (full)
  │                │                       │              │              │
  │                │                       │              │              ├──▶ CLI table (rich)
  │                │                       │              │              ├──▶ JSON (agentic-ready)
  │                │                       │              │              └──▶ Markdown
  │                │                       │
  │                │                       ├──▶ rules: infra regex
  │                │                       ├──▶ rules: real_bug (dominant sig ≥ 90%)
  │                │                       ├──▶ rules: flaky (multiple sigs, rate < 50%)
  │                │                       └──▶ LLM: ambiguous cases only (OMLX → cloud)
  │                │
  │                └──▶ builds per-test stats from all parsed TestResults
  │                     (needed before classify can use cross-run context)
  │
  └──▶ GitHub Actions API (PyGithub)
        ├── fetch_runs: GET /actions/runs (paginated, rate-limit aware)
        ├── fetch_jobs: GET /actions/runs/{id}/jobs
        └── fetch_logs: GET /actions/runs/{id}/logs (zip download, 410 = expired)
```

### 2.3 Component Architecture

| Component | Responsibility | Key Interfaces |
|---|---|---|
| **GitHubClient** | Fetches runs + downloads job logs via GitHub Actions REST API. Rate-limit aware. | `fetch_runs(repo, n) → list[RunInfo]`, `fetch_logs(run_id) → dict[str, str]` |
| **LogParser** | Downloads log zip, extracts per-job logs, parses test results. Regex-first, LLM-fallback. | `parse(run_info, logs) → list[TestResult]` |
| **Classifier** | Classifies each test failure: real bug / flaky / infra. Hybrid rules + LLM. | `classify(test_result, context) → Classification` |
| **Correlator** | Aggregates per-test stats across runs: flake rate, error distribution, temporal pattern. | `correlate(all_test_results) → dict[str, TestStats]` |
| **ErrorSignature** | Normalizes error messages → hash-based signature for grouping. | `normalize(error_text) → str`, `signature(normalized) → str` |
| **ReportGenerator** | Generates CLI table (rich), JSON (agentic-ready), markdown. | `generate(stats, format) → str` |
| **FlakeSleuthGraph** | LangGraph StateGraph wiring all nodes with conditional edges. | `run(repo, options) → FlakeSleuthReport` |
| **Cache** | Optional file-based cache for API responses. | `get(key) → bytes | None`, `set(key, data)` |
| **LLMAdapter** | Calls OMLX (default) or cloud LLM for ambiguous classifications. | `classify_ambiguous(log_snippet, context) → str` |

### 2.4 Pipeline Step-by-Step

```
1. User: ai-flake-sleuth --repo pytest-dev/pytest --runs 100 --format all
2. fetch_runs node:
   a. GitHubClient.fetch_runs("pytest-dev/pytest", 100)
   b. Rate-limit aware (checks X-RateLimit-Remaining via PyGithub)
   c. Returns list[RunInfo] (status, conclusion, workflow, timestamp, run_id)
3. Conditional edge (route_after_fetch):
   a. No failures → skip to report node (clean report)
   b. Has failures → continue to parse_logs node
4. parse_logs node:
   a. For each failed run: GitHubClient.fetch_logs(run_id) → download zip
   b. LogParser.parse(run_info, logs) → list[TestResult] (regex-first, LLM-fallback)
   c. Skip expired logs (410 Gone) → log warning, adjust effective sample
5. preliminary_correlate node (two-pass):
   a. Group all TestResults by test_name
   b. Build preliminary TestStats per test (executions, failures, error signatures)
   c. Store in state.preliminary_stats — available to classify node
6. classify node (two-pass — uses cross-run context):
   a. For each TestResult: Classifier.classify(test_result, state.preliminary_stats)
   b. Rules-based first pass (infra regex, dominant signature, flake rate)
   c. If ambiguous → LLMAdapter.classify_ambiguous() → OMLX (free) → cloud escalation
   d. Returns Classification (category + evidence + confidence + classified_by)
7. correlate node:
   a. Correlator.correlate(all_test_results, classifications) → dict[test_name, TestStats]
   b. Per-test: final flake rate, error distribution, temporal pattern
   c. Enforce minimum 50 executions for flaky label (else INSUFFICIENT_DATA)
   d. Final category: majority vote across per-run classifications
8. report node:
   a. ReportGenerator.generate(report, "table") → rich table to stdout
   b. ReportGenerator.generate(report, "json") → JSON to file (agentic-ready)
   c. ReportGenerator.generate(report, "markdown") → markdown to file
9. Return FlakeSleuthReport (summary + per-test stats + data quality)
```

### 2.5 LangGraph StateGraph

```python
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field
from typing import Optional

class FlakeSleuthState(BaseModel):
    repo: str
    runs_requested: int
    runs: list[RunInfo] = Field(default_factory=list)
    failed_runs: list[RunInfo] = Field(default_factory=list)
    test_results: list[TestResult] = Field(default_factory=list)
    preliminary_stats: dict[str, TestStats] = Field(default_factory=dict)  # two-pass
    classifications: list[Classification] = Field(default_factory=list)
    per_test_stats: dict[str, TestStats] = Field(default_factory=dict)
    data_quality: Optional[DataQuality] = None
    report: Optional[FlakeSleuthReport] = None
    error: Optional[str] = None

graph = StateGraph(FlakeSleuthState)

# Nodes
graph.add_node("fetch_runs", fetch_runs_node)
graph.add_node("parse_logs", parse_logs_node)
graph.add_node("preliminary_correlate", preliminary_correlate_node)  # two-pass: build per-test stats
graph.add_node("classify", classify_node)          # two-pass: classify with cross-run context
graph.add_node("correlate", correlate_node)        # final correlation
graph.add_node("report", report_node)

# Edges
graph.set_entry_point("fetch_runs")
graph.add_conditional_edges("fetch_runs", route_after_fetch, {
    "has_failures": "parse_logs",
    "no_failures": "report",      # skip to clean report
    "rate_limited": "fetch_runs",  # retry after wait
    "error": END,
})
graph.add_edge("parse_logs", "preliminary_correlate")
graph.add_edge("preliminary_correlate", "classify")
graph.add_edge("classify", "correlate")
graph.add_edge("correlate", "report")
graph.add_edge("report", END)

def route_after_fetch(state: FlakeSleuthState) -> str:
    if state.get("error"):
        return "error"
    if not state.get("runs"):
        return "error"
    failed = [r for r in state["runs"] if r.conclusion == "failure"]
    state["failed_runs"] = failed
    if not failed:
        return "no_failures"
    # Rate limit check is handled inside fetch_runs_node via retry;
    # if it exhausted retries, it sets state["error"]
    return "has_failures"
```

---

## 3. Data Structures (`types.py`)

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional

# ─── GitHub API Types ───

@dataclass
class RunInfo:
    run_id: int
    workflow_name: str
    status: str                    # "completed", "in_progress", etc.
    conclusion: str                # "success", "failure", "cancelled", None
    timestamp: datetime
    html_url: str
    jobs: list[JobInfo] = field(default_factory=list)

@dataclass
class JobInfo:
    job_id: int
    name: str
    conclusion: str                # "success", "failure", None
    logs_url: str

# ─── Parsed Test Results ───

class TestStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"

@dataclass
class TestResult:
    test_name: str                 # "tests/test_auth.py::test_login_redirect"
    status: TestStatus
    error_message: str             # raw error text (empty if passed)
    stack_trace: str               # raw stack trace (empty if passed)
    timing_seconds: float          # test execution time
    run_id: int                    # which run this came from
    workflow_name: str
    job_name: str
    timestamp: datetime

# ─── Classification ───

class FailureCategory(Enum):
    REAL_BUG = "real_bug"
    FLAKY = "flaky"
    INFRA = "infra"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass
class Classification:
    test_name: str
    run_id: int
    category: FailureCategory
    evidence: str                  # human-readable justification
    confidence: float              # 0.0–1.0
    classified_by: str             # "rules" or "llm" or "llm:omlx:qwen2.5-coder:7b"

# ─── Cross-Run Correlation ───

@dataclass
class ErrorSignatureGroup:
    signature_hash: str            # normalized error hash
    sample_message: str            # one example of the normalized error
    count: int                     # how many runs had this signature
    first_seen: datetime
    last_seen: datetime

@dataclass
class TestStats:
    test_name: str
    total_executions: int          # runs where this test was executed
    total_failures: int            # runs where this test failed
    flake_rate: float              # total_failures / total_executions × 100
    failure_rate: float            # alias for flake_rate (0.0–1.0)
    error_signatures: list[ErrorSignatureGroup]
    dominant_signature: str | None # signature with highest count (for real-bug detection)
    dominant_signature_ratio: float  # dominant count / total failures
    classifications: list[Classification]  # per-run classifications
    final_category: FailureCategory  # aggregated classification
    first_seen_run: datetime
    last_seen_run: datetime
    workflows_affected: list[str]

# ─── Data Quality ───

@dataclass
class DataQuality:
    runs_requested: int
    runs_fetched: int
    runs_with_failures: int
    runs_with_logs: int            # runs where logs were downloadable
    runs_skipped_expired: int      # logs expired (410 Gone)
    runs_skipped_error: int        # log download failed for other reasons
    effective_sample: int          # runs with parseable logs
    workflows_analyzed: list[str]

# ─── Report ───

@dataclass
class FlakeSleuthReport:
    repo: str
    timestamp: datetime
    data_quality: DataQuality
    summary: ReportSummary
    flaky_tests: list[TestStats]
    real_bugs: list[TestStats]
    infra_issues: list[TestStats]
    insufficient_data: list[TestStats]

@dataclass
class ReportSummary:
    total_runs: int
    total_failures: int
    total_tests_analyzed: int
    flaky_count: int
    real_bug_count: int
    infra_count: int
    insufficient_data_count: int
    overall_pass_rate: float       # successful runs / total runs
    avg_flake_rate: float          # mean flake rate across flaky tests
```

---

## 4. Component Interfaces

### 4.1 GitHub Client (`github_client.py`)

```python
class GitHubClient:
    def __init__(
        self,
        token: str | None = None,    # defaults to os.environ["GITHUB_TOKEN"]
        cache: Cache | None = None,
        per_page: int = 100,
        max_retries: int = 3,
    ) -> None

    def fetch_runs(
        self,
        repo: str,                    # "owner/repo"
        n: int = 100,                 # number of recent runs
        workflow: str | None = None,  # filter by workflow name
        since: datetime | None = None,  # filter by date
    ) -> list[RunInfo]
        # GET /repos/{repo}/actions/runs?per_page={per_page}&page=1,2,...
        # Filters: workflow name, since date
        # Pagination: fetch pages until N runs collected or no more pages
        # Rate limit: check X-RateLimit-Remaining header before each request
        #   If < 10 remaining: sleep until X-RateLimit-Reset
        #   If 429 response: exponential backoff (2s, 4s, 8s)
        # Cache: if cache is set, check cache first for run metadata
        # Returns list[RunInfo] sorted by timestamp descending

    def fetch_run_jobs(
        self,
        repo: str,
        run_id: int,
    ) -> list[JobInfo]
        # GET /repos/{repo}/actions/runs/{run_id}/jobs
        # Returns jobs with their conclusion + logs URL

    def fetch_logs(
        self,
        repo: str,
        run_id: int,
    ) -> dict[str, str] | None
        # GET /repos/{repo}/actions/runs/{run_id}/logs
        # Response is a zip file → download, unzip, return {filename: content}
        # If 410 Gone (expired): return None, log warning
        # If 404: return None, log warning
        # Cache: cache the downloaded zip if cache is set
        # Returns None if logs unavailable

    def check_rate_limit(self) -> dict
        # GET /rate_limit
        # Returns {"remaining": int, "reset": int, "limit": int}
```

**Rate-limit handling:**
- Check `X-RateLimit-Remaining` after each API call
- If remaining < 10: sleep until `X-RateLimit-Reset` timestamp
- If 429 Too Many Requests: exponential backoff (2s, 4s, 8s) up to `max_retries`
- If all retries exhausted: raise `RateLimitExhaustedError`

### 4.2 Log Parser (`log_parser.py`)

```python
class LogParser:
    def __init__(
        self,
        llm_adapter: LLMAdapter | None = None,
    ) -> None

    def parse(
        self,
        run_info: RunInfo,
        logs: dict[str, str],       # {filename: content} from GitHubClient.fetch_logs
    ) -> list[TestResult]
        # 1. Identify job log files (match job names from run_info.jobs)
        # 2. For each failed job's log:
        #    a. Try regex patterns (pytest, unittest) — see §4.2.1
        #    b. If regex matches: extract test results
        #    c. If no regex match and llm_adapter is set: LLM fallback
        #    d. If no match and no LLM: log warning, skip
        # 3. Return list[TestResult] for this run
```

**4.2.1 Regex Patterns (v1 — Python frameworks):**

```python
PYTEST_PATTERNS = [
    # pytest verbose: "FAILED tests/test_foo.py::test_bar - AssertionError: ..."
    re.compile(
        r"^(FAILED|ERROR)\s+(.+?::\S+)\s*-\s*(.+)$",
        re.MULTILINE,
    ),
    # pytest short: "tests/test_foo.py::test_bar FAILED"
    re.compile(
        r"^(\S+::\S+)\s+(FAILED|ERROR|PASSED|SKIPPED)\s*$",
        re.MULTILINE,
    ),
]

UNITTEST_PATTERNS = [
    # unittest: "FAIL: test_bar (test_foo.TestClass)"
    re.compile(
        r"^(FAIL|ERROR|OK|SKIP):\s+(\S+)\s*\((\S+)\)",
        re.MULTILINE,
    ),
]
```

**4.2.2 LLM Fallback Prompt:**

```
You are a CI log parser. Extract test results from this CI log.

For each test mentioned, return JSON:
[
  {"test_name": "...", "status": "passed|failed|error|skipped", "error_message": "...", "stack_trace": "..."}
]

Rules:
- test_name should be the fully qualified name (file::test_name or module.test_name)
- Only include tests that appear in the log
- If no tests found, return []

Log:
---
{log_content}
---
```

### 4.3 Error Signature (`error_signature.py`)

```python
class ErrorSignatureNormalizer:
    # Patterns to strip during normalization
    NORMALIZE_PATTERNS: list[tuple[str, str]] = [
        (r"/Users/[^/\s]+/", "<PATH>/"),        # file paths
        (r"/home/[^/\s]+/", "<PATH>/"),
        (r"/tmp/[^/\s]+/", "<PATH>/"),
        (r"/runner/[^/\s]+/", "<PATH>/"),
        (r":\d+:", ":<LINE>:"),                  # line numbers
        (r"0x[0-9a-fA-F]+", "<ADDR>"),          # memory addresses
        (r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", "<TIMESTAMP>"),  # ISO timestamps
        (r"\d{10,13}", "<TIMESTAMP>"),          # epoch timestamps
        (r"pid\s*\d+", "pid <PID>"),            # process IDs
        (r"port\s*\d+", "port <PORT>"),         # port numbers
    ]

    @staticmethod
    def normalize(error_text: str) -> str:
        """Strip variable parts from error text to produce a stable signature."""
        normalized = error_text
        for pattern, replacement in ErrorSignatureNormalizer.NORMALIZE_PATTERNS:
            normalized = re.sub(pattern, replacement, normalized)
        return normalized.strip()

    @staticmethod
    def signature(normalized_text: str) -> str:
        """Produce a hash signature from normalized error text."""
        return hashlib.sha256(normalized_text.encode()).hexdigest()[:16]
```

### 4.4 Classifier (`classifier.py`)

```python
class Classifier:
    # Infra patterns — rules-based detection
    INFRA_PATTERNS = [
        r"timeout", r"timed?\s*out",
        r"out\s+of\s+memory", r"OOM", r"OOMKilled",
        r"killed", r"SIGKILL", r"SIGTERM",
        r"runner", r"self-hosted",
        r"network", r"connection\s+refused", r"ETIMEDOUT",
        r"ECONNRESET", r"ECONNREFUSED", r"ENOTFOUND",
        r"503", r"502", r"504",  # infra HTTP errors
    ]

    def __init__(
        self,
        llm_adapter: LLMAdapter | None = None,
    ) -> None

    def classify(
        self,
        test_result: TestResult,
        cross_run_context: dict | None = None,  # per-test stats from prior runs
    ) -> Classification:
        # Step 1: Infra check (rules-based)
        if self._matches_infra(test_result):
            return Classification(
                category=FailureCategory.INFRA,
                evidence=f"Infra pattern detected: {matched_pattern}",
                confidence=0.9,
                classified_by="rules",
            )

        # Step 2: Real bug check (needs cross-run context)
        if cross_run_context:
            stats = cross_run_context.get(test_result.test_name)
            if stats and stats.total_executions >= 50:
                if stats.dominant_signature_ratio >= 0.9 and stats.failure_rate > 0.5:
                    return Classification(
                        category=FailureCategory.REAL_BUG,
                        evidence=f"Dominant signature {stats.dominant_signature} "
                                 f"in {stats.dominant_signature_ratio:.0%} of failures, "
                                 f"failure rate {stats.failure_rate:.0%}",
                        confidence=0.85,
                        classified_by="rules",
                    )

        # Step 3: Flaky check (needs cross-run context)
        if cross_run_context:
            stats = cross_run_context.get(test_result.test_name)
            if stats and stats.total_executions >= 50:
                if len(stats.error_signatures) > 1 and stats.failure_rate < 0.5:
                    return Classification(
                        category=FailureCategory.FLAKY,
                        evidence=f"{len(stats.error_signatures)} distinct error signatures, "
                                 f"failure rate {stats.failure_rate:.0%}",
                        confidence=0.8,
                        classified_by="rules",
                    )
                if stats.total_executions < 50:
                    return Classification(
                        category=FailureCategory.INSUFFICIENT_DATA,
                        evidence=f"Only {stats.total_executions} executions (< 50 minimum)",
                        confidence=1.0,
                        classified_by="rules",
                    )

        # Step 4: Ambiguous → LLM fallback
        if self.llm_adapter:
            return self._classify_with_llm(test_result, cross_run_context)
        # No LLM available → default to flaky (conservative — don't assume real bug)
        return Classification(
            category=FailureCategory.FLAKY,
            evidence="Ambiguous classification, no LLM available for fallback",
            confidence=0.5,
            classified_by="rules",
        )
```

**Note:** The classifier needs cross-run context, but classification happens per-run in the graph. This is a two-pass design:
1. **First pass:** parse all logs → collect all TestResults → build preliminary error signatures
2. **Second pass:** classify each TestResult with cross-run context available

This means the classify node runs after a preliminary correlation pass. The graph handles this by having the classify node first build preliminary stats, then classify.

### 4.5 Correlator (`correlator.py`)

```python
class Correlator:
    def correlate(
        self,
        all_test_results: list[TestResult],
        classifications: list[Classification],
    ) -> dict[str, TestStats]
        # 1. Group TestResults by test_name
        # 2. For each test:
        #    a. Count total_executions (all results with this test_name)
        #    b. Count total_failures (status == FAILED or ERROR)
        #    c. Compute flake_rate = total_failures / total_executions × 100
        #    d. Group failures by error signature → ErrorSignatureGroup list
        #    e. Find dominant signature (highest count)
        #    f. Compute dominant_signature_ratio = dominant_count / total_failures
        #    g. Aggregate classifications → final_category (majority vote)
        #    h. Track first_seen, last_seen, workflows_affected
        # 3. Return dict[test_name, TestStats]

    def _final_category(
        self,
        classifications: list[Classification],
        total_executions: int,
    ) -> FailureCategory:
        # If total_executions < 50 → INSUFFICIENT_DATA
        # Else: majority vote across all per-run classifications
        # Tie-break: FLAKY > INFRA > REAL_BUG (conservative — don't assume real bug)
```

### 4.6 Report Generator (`report.py`)

```python
class ReportGenerator:
    def generate(
        self,
        report: FlakeSleuthReport,
        format: str,             # "table" | "json" | "markdown"
    ) -> str

    def _generate_table(self, report: FlakeSleuthReport) -> str
        # Uses rich library to render a terminal table
        # Sections: Summary, Flaky Tests, Real Bugs, Infra Issues, Data Quality
        # Columns (8): test_name | category | flake_rate | error_sigs |
        #              total_executions | workflow | dominant_error | last_seen

    def _generate_json(self, report: FlakeSleuthReport) -> str
        # Serializes FlakeSleuthReport to JSON
        # Schema designed as v2 LangGraph state input (agentic-ready)
        # See §5 for JSON schema

    def _generate_markdown(self, report: FlakeSleuthReport) -> str
        # Markdown report with:
        # # CI Health Report: {repo}
        # ## Summary (table)
        # ## Flaky Tests (table with flake rates + error distributions)
        # ## Real Bugs (table with reproducibility evidence)
        # ## Infra Issues (table with failure patterns)
        # ## Data Quality (runs fetched, skipped, effective sample)
```

### 4.7 LLM Adapter (`llm.py`)

```python
class LLMAdapter:
    def __init__(
        self,
        provider: str = "omlx",       # "omlx" | "openai" | "deepseek"
        model: str = "qwen2.5-coder:7b",
        endpoint: str = "http://localhost:11434",
        api_key: str | None = None,
        timeout: int = 60,
    ) -> None

    def classify_ambiguous(
        self,
        test_result: TestResult,
        cross_run_context: dict | None = None,
    ) -> Classification
        # Builds prompt with: test name, error message, stack trace,
        #   cross-run stats (if available)
        # Calls LLM → parses response → returns Classification
        # If LLM fails: falls back to rules-based "flaky" (conservative)
```

### 4.8 Cache (`cache.py`)

```python
class FileCache:
    def __init__(self, cache_dir: str | Path) -> None

    def _key(self, repo: str, identifier: str) -> Path
        # Returns cache file path: {cache_dir}/{repo}/{identifier}.json

    def get(self, repo: str, identifier: str) -> bytes | None
        # Returns cached data if exists, None otherwise

    def set(self, repo: str, identifier: str, data: bytes) -> None
        # Writes data to cache file

    def has(self, repo: str, identifier: str) -> bool

    def clear(self, repo: str | None = None) -> None
```

### 4.9 CLI (`cli.py`)

```python
# Implementation: argparse (stdlib — no click dependency)

# Usage:
#   ai-flake-sleuth --repo owner/repo [options]

# Required:
#   --repo owner/repo        Target repository

# Optional:
#   --runs N                 Recent runs to fetch (default: 100, min: 50)
#   --format FORMAT          table | json | markdown | all (default: table)
#   --output PATH            Output file path (default: stdout)
#   --workflow NAME          Filter to a specific workflow (default: all)
#   --since YYYY-MM-DD       Only analyze runs after this date
#   --cache DIR              Cache directory for API responses (default: off)
#   --llm PROVIDER           LLM provider for ambiguous classifications
#                              (omlx | openai | deepseek, default: omlx)
#   --no-llm                 Disable LLM fallback (rules-only)
#   --verbose                Enable debug logging
#   --version                Show version

def main():
    parser = argparse.ArgumentParser(prog="ai-flake-sleuth", ...)
    args = parser.parse_args()
    # 1. Build config from args
    # 2. Create GitHubClient (+ cache if --cache)
    # 3. Create LLMAdapter (unless --no-llm)
    # 4. Build LangGraph graph
    # 5. Run graph: graph.invoke(initial_state)
    # 6. Generate report(s) based on --format
    # 7. Output to stdout or file(s) based on --output
```

---

## 5. JSON Output Schema (Agentic-Ready)

The JSON output is designed as v2's LangGraph state input. v2 will read this JSON and feed it into the interrupt/quarantine loop.

```json
{
  "repo": "pytest-dev/pytest",
  "timestamp": "2026-07-17T12:00:00Z",
  "data_quality": {
    "runs_requested": 100,
    "runs_fetched": 98,
    "runs_with_failures": 31,
    "runs_with_logs": 28,
    "runs_skipped_expired": 3,
    "runs_skipped_error": 0,
    "effective_sample": 28,
    "workflows_analyzed": ["ci", "lint", "docs"]
  },
  "summary": {
    "total_runs": 98,
    "total_failures": 31,
    "total_tests_analyzed": 245,
    "flaky_count": 7,
    "real_bug_count": 3,
    "infra_count": 2,
    "insufficient_data_count": 12,
    "overall_pass_rate": 0.684,
    "avg_flake_rate": 0.143
  },
  "flaky_tests": [
    {
      "test_name": "tests/test_auth.py::test_login_redirect",
      "total_executions": 95,
      "total_failures": 14,
      "flake_rate": 14.74,
      "failure_rate": 0.1474,
      "error_signatures": [
        {
          "signature_hash": "a1b2c3d4e5f6a7b8",
          "sample_message": "AssertionError: expected <CODE>, got <CODE>",
          "count": 8,
          "first_seen": "2026-07-10T...",
          "last_seen": "2026-07-16T..."
        },
        {
          "signature_hash": "f7e6d5c4b3a2f1e0",
          "sample_message": "TimeoutError: <PATH>:<LINE>: connection timed out",
          "count": 6,
          "first_seen": "2026-07-12T...",
          "last_seen": "2026-07-15T..."
        }
      ],
      "dominant_signature": "a1b2c3d4e5f6a7b8",
      "dominant_signature_ratio": 0.571,
      "final_category": "flaky",
      "first_seen_run": "2026-06-15T...",
      "last_seen_run": "2026-07-16T...",
      "workflows_affected": ["ci"]
    }
  ],
  "real_bugs": [
    {
      "test_name": "tests/test_parser.py::test_edge_case",
      "total_executions": 98,
      "total_failures": 87,
      "flake_rate": 88.78,
      "failure_rate": 0.8878,
      "error_signatures": [
        {
          "signature_hash": "deadbeefcafe1234",
          "sample_message": "IndexError: list index out of range at <PATH>:<LINE>",
          "count": 87,
          "first_seen": "2026-06-15T...",
          "last_seen": "2026-07-16T..."
        }
      ],
      "dominant_signature": "deadbeefcafe1234",
      "dominant_signature_ratio": 1.0,
      "final_category": "real_bug",
      "first_seen_run": "2026-06-15T...",
      "last_seen_run": "2026-07-16T...",
      "workflows_affected": ["ci"]
    }
  ],
  "infra_issues": [
    {
      "test_name": "tests/test_integration.py::test_external_api",
      "total_executions": 98,
      "total_failures": 5,
      "flake_rate": 5.10,
      "failure_rate": 0.0510,
      "error_signatures": [
        {
          "signature_hash": "cafebabedead5678",
          "sample_message": "ConnectionRefusedError: <PATH>:<LINE>: connection refused",
          "count": 5,
          "first_seen": "2026-07-01T...",
          "last_seen": "2026-07-14T..."
        }
      ],
      "dominant_signature": "cafebabedead5678",
      "dominant_signature_ratio": 1.0,
      "final_category": "infra",
      "first_seen_run": "2026-07-01T...",
      "last_seen_run": "2026-07-14T...",
      "workflows_affected": ["ci"]
    }
  ],
  "insufficient_data": []
}
```

---

## 6. Error Handling

### 6.1 Custom Exceptions (`exceptions.py`)

```python
class FlakeSleuthError(Exception):
    """Base exception for all ai-flake-sleuth errors."""

class GitHubAPIError(FlakeSleuthError):
    """GitHub API request failed."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"GitHub API error {status_code}: {message}")

class RateLimitExhaustedError(FlakeSleuthError):
    """GitHub API rate limit exhausted after all retries."""
    def __init__(self, reset_at: int):
        self.reset_at = reset_at
        super().__init__(f"rate limit exhausted, resets at {reset_at}")

class LogExpiredError(FlakeSleuthError):
    """GitHub Actions logs expired (>90 days)."""
    def __init__(self, run_id: int):
        self.run_id = run_id
        super().__init__(f"logs for run {run_id} expired (410 Gone)")

class LogParseError(FlakeSleuthError):
    """Failed to parse test results from log."""
    def __init__(self, run_id: int, reason: str):
        self.run_id = run_id
        self.reason = reason
        super().__init__(f"log parse failed for run {run_id}: {reason}")

class LLMError(FlakeSleuthError):
    """LLM call failed for ambiguous classification."""
    def __init__(self, provider: str, error: str):
        self.provider = provider
        self.error = error
        super().__init__(f"LLM '{provider}' failed: {error}")

class GraphError(FlakeSleuthError):
    """LangGraph pipeline execution failed."""
    def __init__(self, node: str, error: str):
        self.node = node
        self.error = error
        super().__init__(f"graph error in node '{node}': {error}")
```

### 6.2 Retry Policy

| Layer | Retries | Backoff | When |
|---|---|---|---|
| GitHub API (runs) | 3 | Exponential (2s, 4s, 8s) | 429, 5xx |
| GitHub API (logs) | 2 | Exponential (2s, 4s) | 429, 5xx (not 410 — expired is permanent) |
| LLM call | 1 | 5s fixed | Timeout, connection error |

---

## 7. Dependencies

### Runtime Dependencies

| Package | Version | Purpose |
|---|---|---|
| `langgraph` | >=0.2 | StateGraph + conditional edges |
| `langchain-core` | >=0.3 | LangGraph dependency |
| `PyGithub` | >=2.4 | GitHub Actions API (pagination, rate limits, log downloads) |
| `requests` | >=2.32 | LLM API calls (OMLX + cloud) |
| `rich` | >=13 | CLI table rendering |
| `pydantic` | >=2 | State schema (LangGraph Pydantic support) |

### Dev Dependencies

| Package | Version | Purpose |
|---|---|---|
| `pytest` | >=8 | Testing |
| `pytest-cov` | >=5 | Coverage reporting |
| `ruff` | >=0.5 | Linting |
| `mypy` | >=1.10 | Type checking |

---

## 8. Testing Strategy

### 8.1 Test Layers

| Layer | Scope | Framework |
|---|---|---|
| Unit | Each component in isolation | pytest |
| Integration | Full pipeline end-to-end with mock GitHub API | pytest |
| Graph | LangGraph node routing, conditional edges | pytest |
| CLI | CLI invocation, output parsing | pytest + `subprocess` |
| Fixtures | Mock GitHub API responses, sample logs | JSON fixtures |

### 8.2 Mock GitHub Client

```python
class MockGitHubClient:
    """Test-only client returning fixture data without network calls."""
    def __init__(
        self,
        runs_fixture: str = "tests/fixtures/sample_runs.json",
        logs_dir: str = "tests/fixtures/sample_logs/",
    ) -> None

    def fetch_runs(self, repo, n=100, **kwargs) -> list[RunInfo]:
        # Load sample_runs.json, return first N RunInfo objects

    def fetch_logs(self, repo, run_id) -> dict[str, str] | None:
        # Load sample log files from logs_dir
        # Simulate expired logs for specific run IDs

    def check_rate_limit(self) -> dict:
        return {"remaining": 4999, "reset": 0, "limit": 5000}
```

### 8.3 Coverage Targets

| Module | Target |
|---|---|
| `github_client.py` | 90% (mocked HTTP) |
| `log_parser.py` | 95% (regex + LLM fallback) |
| `classifier.py` | 95% (rules + LLM + edge cases) |
| `correlator.py` | 95% (aggregation + flake rate) |
| `error_signature.py` | 100% (normalization + hash) |
| `report.py` | 90% (all 3 formats) |
| `graph.py` | 85% (node routing + conditional edges) |
| `cli.py` | 80% (arg parsing + integration) |
| `cache.py` | 90% (file I/O) |

---

## 9. Build Order (M1-M4)

| Step | Milestone | Files | Test Files |
|---|---|---|---|
| 1 | Scaffold | `pyproject.toml`, `types.py`, `exceptions.py`, `config.py` | `test_config.py` |
| 2 | M1: GitHub client | `github_client.py` | `test_github_client.py` |
| 3 | M2: Log parser | `log_parser.py`, `error_signature.py` | `test_log_parser.py`, `test_error_signature.py` |
| 4 | M3: Classifier | `classifier.py`, `llm.py` | `test_classifier.py`, `test_llm.py` |
| 5 | M4: Correlator | `correlator.py` | `test_correlator.py` |
| 6 | M4: Graph | `state.py`, `graph.py` | `test_graph.py` |
| 7 | Report | `report.py` | `test_report.py` |
| 8 | CLI | `cli.py`, `cache.py` | `test_cli.py`, `test_cache.py` |
| 9 | Integration | `tests/integration/` | Integration test |
| 10 | Field study | Run against 5 repos, validate | — |

---

## 10. Config (`config.py`)

```python
from dataclasses import dataclass

@dataclass
class FlakeSleuthConfig:
    # GitHub
    github_token: str | None = None     # defaults to os.environ["GITHUB_TOKEN"]
    per_page: int = 100
    max_retries: int = 3

    # Analysis
    runs: int = 100
    min_sample: int = 50                # minimum executions for flaky classification
    workflow: str | None = None
    since: str | None = None            # YYYY-MM-DD

    # LLM
    llm_provider: str = "omlx"
    llm_model: str = "qwen2.5-coder:7b"
    llm_endpoint: str = "http://localhost:11434"
    llm_enabled: bool = True

    # Output
    format: str = "table"               # table | json | markdown | all
    output: str | None = None           # file path or stdout

    # Cache
    cache_dir: str | None = None
```

---

## 11. Design Decisions (Q&A Summary)

| # | Question | Decision |
|---|----------|----------|
| 1 | Package import name | `flake_sleuth` (repo is `ai-flake-sleuth`, import path cleaner without `ai-` prefix) |
| 2 | GitHub API client | `PyGithub` — handles pagination, rate limits, log downloads. Access raw headers when needed for LangGraph conditional edge. |
| 3 | LangGraph state | Pydantic `BaseModel` — validation built-in, type-safe state updates |
| 4 | Classification approach | Two-pass: parse all → preliminary correlate → classify with cross-run context → final correlate. More accurate than single-pass. |
| 5 | LLM support | OMLX default + cloud escalation (OpenAI gpt-4o-mini / DeepSeek v4-flash) for ambiguous cases. Full tierforge-style adapter pattern. |
| 6 | CLI table columns | `test_name | category | flake_rate | error_sigs | total_executions | workflow | dominant_error | last_seen` (8 columns) |
| 7 | Output file naming | `flake-sleuth-{repo}-{timestamp}.{ext}` — includes repo + timestamp for field study organization |
| 8 | Field study validation | Deferred to separate field study test plan (see WBS) |
