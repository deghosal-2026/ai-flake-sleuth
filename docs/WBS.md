# WBS: ai-flake-sleuth — Work Breakdown Structure

| Field | Value |
|---|---|
| **Status** | Approved |
| **PRD** | [docs/PRD.md](./PRD.md) |
| **SPEC** | [docs/SPEC.md](./SPEC.md) |
| **Author** | Debashish Ghosal |
| **Date** | 2026-07-18 |
| **Target** | Friday 2026-07-25 (code + field study + blog post) |
| **Scope** | v1 = M1-M4 (diagnostic only) |
| **Total Effort** | ~6 days |

---

## M1: Scaffold + GitHub Client (Sat Jul 19, ~1 day) ✅

**Done criteria:** `GitHubClient.fetch_runs("pytest-dev/pytest", 10)` returns 10 `RunInfo` objects from the real GitHub API. Rate-limit check works. Log download returns a dict of `{filename: content}` for a real failed run.

### M1.1 — Scaffold project ✅

- [x] `pyproject.toml` with metadata, deps (`PyGithub>=2.4`, `requests>=2.32`, `rich>=13`, `pydantic>=2`, `langgraph>=0.2`, `langchain-core>=0.3`)
- [x] `pyproject.toml` `[project.optional-dependencies] dev` with `pytest`, `pytest-cov`, `ruff`, `mypy`
- [x] `pyproject.toml` `[tool.mypy]` config targeting `src/`
- [x] `pyproject.toml` `[tool.ruff]` config matching tierforge conventions
- [x] `src/flake_sleuth/` package dir
- [x] `src/flake_sleuth/__init__.py` with public API exports
- [x] `tests/`, `tests/fixtures/`, `tests/integration/` dirs
- [x] `.github/workflows/ci.yml` — test (Python 3.11, 3.12), lint (ruff), type-check (mypy)
- [x] Confirm `.gitignore` covers: `__pycache__/`, `*.pyc`, `.env`, `*.egg-info/`, `dist/`, `build/`, `.venv/`, `venv/`, `*.log`, `reports/`

**Done check:** `pip install -e ".[dev]"` works. `pytest` runs with 0 tests collected (no failures).

### M1.2 — Data structures (`types.py`) ✅

- [x] `RunInfo` dataclass (run_id, workflow_name, status, conclusion, timestamp, html_url, jobs)
- [x] `JobInfo` dataclass (job_id, name, conclusion, logs_url)
- [x] `TestStatus` enum (PASSED, FAILED, ERROR, SKIPPED)
- [x] `TestResult` dataclass (test_name, status, error_message, stack_trace, timing_seconds, run_id, workflow_name, job_name, timestamp)
- [x] `FailureCategory` enum (REAL_BUG, FLAKY, INFRA, INSUFFICIENT_DATA)
- [x] `Classification` dataclass (test_name, run_id, category, evidence, confidence, classified_by)
- [x] `ErrorSignatureGroup` dataclass (signature_hash, sample_message, count, first_seen, last_seen)
- [x] `TestStats` dataclass (test_name, total_executions, total_failures, flake_rate, failure_rate, error_signatures, dominant_signature, dominant_signature_ratio, classifications, final_category, first_seen_run, last_seen_run, workflows_affected)
- [x] `DataQuality` dataclass (runs_requested, runs_fetched, runs_with_failures, runs_with_logs, runs_skipped_expired, runs_skipped_error, effective_sample, workflows_analyzed)
- [x] `FlakeSleuthReport` dataclass (repo, timestamp, data_quality, summary, flaky_tests, real_bugs, infra_issues, insufficient_data)
- [x] `ReportSummary` dataclass (total_runs, total_failures, total_tests_analyzed, flaky_count, real_bug_count, infra_count, insufficient_data_count, overall_pass_rate, avg_flake_rate)

**Done check:** `pytest tests/test_types.py` passes. All fields match SPEC §3.

### M1.3 — Custom exceptions (`exceptions.py`) ✅

- [x] `FlakeSleuthError` base
- [x] `GitHubAPIError(status_code, message)`
- [x] `RateLimitExhaustedError(reset_at)`
- [x] `LogExpiredError(run_id)`
- [x] `LogParseError(run_id, reason)`
- [x] `LLMError(provider, error)`
- [x] `GraphError(node, error)`

**Done check:** All exceptions are subclasses of `FlakeSleuthError`. Each carries SPEC-defined fields.

### M1.4 — Config (`config.py`) ✅

- [x] `FlakeSleuthConfig` dataclass matching SPEC §10
- [x] Defaults: runs=100, min_sample=50, llm_provider="omlx", format="table"
- [x] Build from CLI args helper: `Config.from_args(namespace)`

**Done check:** `Config()` produces valid defaults. `Config.from_args()` maps all CLI flags.

### M1.5 — GitHub client (`github_client.py`) ✅

- [x] `GitHubClient.__init__(token, cache, per_page, max_retries)` — token defaults to `os.environ["GITHUB_TOKEN"]`
- [x] `fetch_runs(repo, n, workflow, since) → list[RunInfo]` — uses PyGithub for pagination
- [x] `fetch_run_jobs(repo, run_id) → list[JobInfo]`
- [x] `fetch_logs(repo, run_id) → dict[str, str] | None` — download zip, unzip, return {filename: content}
- [x] `check_rate_limit() → dict` — returns remaining, reset, limit
- [x] Rate-limit handling: check remaining before each request; if < 10, sleep until reset; 429 → exponential backoff (2s, 4s, 8s)
- [x] Expired logs (410 Gone) → return None, log warning
- [x] Cache integration: if cache set, check cache first

**Done check:** `GitHubClient(token=os.environ["GITHUB_TOKEN"]).fetch_runs("pytest-dev/pytest", 10)` returns 10 real `RunInfo` objects. `fetch_logs()` on a recent failed run returns a non-empty dict.
- [x] CLI coverage: 100% (157 tests), ruff clean, mypy clean

### M1.6 — Cache (`cache.py`) ✅

- [x] `FileCache.__init__(cache_dir)`
- [x] `get(repo, identifier) → bytes | None`
- [x] `set(repo, identifier, data)`
- [x] `has(repo, identifier) → bool`
- [x] `clear(repo)`

**Done check:** Cache write → read round-trip works. Cache miss returns None.

### M1.7 — Test fixtures ✅

- [x] `tests/fixtures/sample_runs.json` — 10 mock run metadata entries (mix of success/failure/expired)
- [x] `tests/fixtures/sample_logs/pytest_failed.txt` — realistic pytest verbose output
- [x] `tests/fixtures/sample_logs/unittest_failed.txt` — realistic unittest output
- [x] `tests/fixtures/sample_logs/infra_timeout.txt` — infra failure (timeout/OOM)
- [x] `tests/fixtures/sample_logs/clean_run.txt` — all passing
- [x] `tests/fixtures/mock_github_api.py` — `MockGitHubClient` returning fixture data

**Done check:** Mock client loads fixtures and returns correct types. All test files are realistic enough to exercise regex patterns.

---

## M2: Log Parser + Error Signature (Sun Jul 20, ~1 day) ✅

**Done criteria:** `LogParser.parse(run_info, logs)` extracts `TestResult` objects from pytest and unittest log formats. Regex handles 80%+ of cases. LLM fallback works for non-standard formats. Error signature normalization produces stable hashes for similar errors.

### M2.1 — Error signature normalizer (`error_signature.py`) ✅

- [x] `ErrorSignatureNormalizer.NORMALIZE_PATTERNS` — strip paths, line numbers, timestamps, memory addresses, PIDs, ports
- [x] `normalize(error_text) → str` — apply all patterns
- [x] `signature(normalized_text) → str` — sha256[:16] hash
- [x] Test: same error with different paths/timestamps → same signature
- [x] Test: different errors → different signatures

**Done check:** `pytest tests/test_error_signature.py` passes. Normalization is deterministic.

### M2.2 — Log parser (`log_parser.py`) ✅

- [x] `LogParser.__init__(llm_adapter)`
- [x] `parse(run_info, logs) → list[TestResult]`
- [x] Pytest regex patterns (SPEC §4.2.1):
  - [x] `FAILED|ERROR tests/...::test_name - error_message`
  - [x] `tests/...::test_name FAILED|ERROR|PASSED|SKIPPED`
- [x] Unittest regex patterns:
  - [x] `FAIL|ERROR|OK|SKIP: test_name (module.Class)`  (dot format: `name (module.Class) ... FAIL`)
- [x] Job log identification: match log filenames to job names from `run_info.jobs`
- [x] LLM fallback: if no regex match and `llm_adapter` is set, call LLM with SPEC §4.2.2 prompt
- [x] No match + no LLM → log warning, skip
- [x] Stack trace extraction: capture lines after error message up to next test or EOF

**Done check:** `pytest tests/test_log_parser.py` passes. Parser correctly extracts test results from all 4 fixture log files (pytest, unittest, infra, clean).

### M2.3 — LLM adapter (`llm.py`) ✅

- [x] `LLMAdapter.__init__(provider, model, endpoint, api_key, timeout)` — defaults to OMLX
- [x] OMLX adapter: POST to `{endpoint}/v1/chat/completions`, no auth header, free
- [x] Cloud escalation: OpenAI-compatible adapter (DeepSeek, OpenAI) — Bearer auth from env
- [x] `classify_ambiguous(test_result, cross_run_context) → Classification`
- [x] Prompt: SPEC §4.2.2 format + cross-run stats (if available)
- [x] Response parsing: extract category + evidence from LLM JSON response
- [x] Fallback: if LLM fails, return `Classification(category=FLAKY, confidence=0.5, classified_by="rules")`
- [ ] Pricing table for cloud models (gpt-4o-mini, deepseek-v4-flash)

---

## M3: Classifier (Mon Jul 21, ~1 day) ✅

**Done criteria:** `Classifier.classify(test_result, cross_run_context)` returns correct `Classification` for all 4 categories. Rules-based path handles infra, real-bug, and flaky. LLM escalation only for ambiguous cases. Two-pass design works with preliminary stats.

### M3.1 — Classifier rules (`classifier.py`) ✅

- [x] `Classifier.__init__(llm_adapter)`
- [x] `INFRA_PATTERNS` — regex list (timeout, OOM, killed, network, connection refused, ETIMEDOUT, ECONNRESET, 502/503/504)
- [x] `_matches_infra(test_result) → tuple[bool, str | None]` — returns (matched, pattern)
- [x] `classify(test_result, cross_run_context) → Classification`:
  - [x] Step 1: Infra check (rules) → INFRA
  - [x] Step 2: Real bug check (needs cross-run context): dominant_signature_ratio ≥ 0.9 AND failure_rate > 0.5 → REAL_BUG
  - [x] Step 3: Flaky check (needs cross-run context): multiple signatures AND failure_rate < 0.5 → FLAKY
  - [x] Step 4: Insufficient data: total_executions < 50 → INSUFFICIENT_DATA
  - [x] Step 5: Ambiguous → LLM fallback
  - [x] Step 6: No LLM → default to FLAKY (conservative)
- [x] Each classification includes `evidence`, `confidence`, `classified_by`

**Done check:** `pytest tests/test_classifier.py` passes. All 4 categories tested with fixture data. Rules path produces correct category without LLM. LLM path is only triggered for ambiguous cases.

### M3.2 — Two-pass integration ✅

- [x] Verify classifier works with `preliminary_stats` dict (from M4.1 preliminary_correlate)
- [x] Test: same test result classified differently with and without cross-run context
- [x] Test: real bug correctly identified only when dominant signature ratio is high

**Done check:** Classifier correctly uses cross-run context from preliminary stats to distinguish real-bug from flaky.

---

## M4: Correlator + Graph + Report (Tue Jul 22, ~1.5 days) ✅

**Done criteria:** Full pipeline runs end-to-end: `graph.invoke(initial_state)` produces a `FlakeSleuthReport` with all test stats. LangGraph conditional edges work (skip-if-no-failures, rate-limit retry). Report generates in all 3 formats (CLI table, JSON, markdown). Coverage at 95.52%.

### M4.1 — Correlator (`correlator.py`) ✅

- [x] `Correlator.correlate(all_test_results, classifications) → dict[str, TestStats]`
- [x] Group TestResults by test_name
- [x] Per-test: count total_executions, total_failures, compute flake_rate
- [x] Group failures by error signature → `ErrorSignatureGroup` list
- [x] Find dominant signature (highest count) → dominant_signature_ratio
- [x] Aggregate classifications → final_category (majority vote)
- [x] Tie-break: FLAKY > INFRA > REAL_BUG (conservative)
- [x] Track first_seen, last_seen, workflows_affected
- [x] `preliminary_correlate(all_test_results) → dict[str, TestStats]` — for two-pass (no classifications yet)

**Done check:** `pytest tests/test_correlator.py` passes (22 tests). Flake rate calculation correct. Error distribution grouped correctly. final_category majority vote works.

### M4.2 — LangGraph state (`state.py`) ✅

- [x] `FlakeSleuthState` Pydantic BaseModel matching SPEC §2.5
- [x] Fields: repo, runs_requested, runs, failed_runs, test_results, preliminary_stats, classifications, per_test_stats, data_quality, report, error
- [x] All list/dict fields have `Field(default_factory=...)`

**Done check:** State can be instantiated with defaults. Pydantic validation catches type errors (5 tests).

### M4.3 — LangGraph graph (`graph.py`) ✅

- [x] `build_graph() → CompiledGraph`
- [x] Nodes: `fetch_runs`, `parse_logs`, `preliminary_correlate`, `classify`, `correlate`, `report`
- [x] `fetch_runs_node(state) → dict` — calls GitHubClient, populates state.runs + state.failed_runs + state.data_quality
- [x] `parse_logs_node(state) → dict` — for each failed run, fetch + parse logs → state.test_results
- [x] `preliminary_correlate_node(state) → dict` — Correlator.preliminary_correlate → state.preliminary_stats
- [x] `classify_node(state) → dict` — Classifier.classify for each TestResult with state.preliminary_stats → state.classifications
- [x] `correlate_node(state) → dict` — Correlator.correlate → state.per_test_stats + build FlakeSleuthReport
- [x] `report_node(state) → dict` — builds clean FlakeSleuthReport for no-failures path
- [x] `route_after_fetch(state) → str` — conditional edge: "has_failures" | "no_failures" | "error"
- [x] Entry point: fetch_runs
- [x] Edges: fetch_runs → (conditional) → parse_logs → preliminary_correlate → classify → correlate → report → END
- [x] No-failures path: fetch_runs → report → END (clean report, fixed bug)
- [x] Error handling: node exceptions set state.error → END

**Done check:** `pytest tests/test_graph.py` passes (8 tests). Graph routes correctly for has-failures, no-failures, and error cases. Two-pass pipeline (preliminary_correlate → classify) works. Fixes: shared GitHubClient, report_node builds clean report, overall_pass_rate counts only successes.

### M4.4 — Report generator (`report.py`) ✅

- [x] `ReportGenerator.generate(report, format) → str`
- [x] `_generate_table(report) → str` — sections: Summary, Flaky Tests, Real Bugs, Infra Issues, Insufficient Data, Data Quality
- [x] `_generate_json(report) → str` — JSON matching SPEC §5 schema (agentic-ready)
- [x] `_generate_markdown(report) → str` — markdown with summary table + per-category tables + data quality section
- [x] Clean report (no failures): "No failures in N runs across M workflows. CI health: clean."
- [x] File naming: `flake-sleuth-{repo}-{timestamp}.{ext}` when `--output` is a directory

**Done check:** `pytest tests/test_report.py` passes (19 tests). All 3 formats generate valid output. Clean report renders correctly. JSON handles Enum serialization properly (fix: isinstance(obj, Enum) → obj.name). Insufficient Data section added to table format.

### M4.5 — CLI (`cli.py`) ✅

- [x] argparse with all flags from SPEC §4.9:
  - [x] `--repo` (required), `--github-token`, `--runs`, `--format`, `--output`, `--workflow`, `--since`, `--cache`, `--llm`, `--no-llm`, `--verbose`, `--version`
- [x] `main()` — parse args → build Config → create components → build graph → invoke → generate reports
- [x] Output to stdout (table) or files (json/markdown/all)
- [x] `--format all --output ./reports/` writes 3 files with naming convention
- [x] Error handling: missing GITHUB_TOKEN, API errors, graph errors → clear error messages + exit code 1

**Done check:** `pytest tests/test_cli.py` passes (10 tests). `--version` works without `--repo`. `_write_output` creates parent directories.

### M4.6 — Integration tests ✅

- [x] `tests/integration/test_pipeline_integration.py`:
  - [x] Full pipeline with MockGitHubClient → FlakeSleuthReport
  - [x] Has-failures path: fetch → parse → preliminary_correlate → classify → correlate → report
  - [x] No-failures path: fetch → report (clean)
  - [x] Expired logs: skipped, data_quality reflects effective sample
  - [x] All 3 report formats generated
- [x] `pytest --cov=flake_sleuth --cov-report=term-missing` meets coverage targets (SPEC §8.3) — **96.44% (224 tests)**

**Done check:** Integration tests pass (11 tests). Coverage at 96.44%. ruff and mypy clean. `pip install -e .` works in clean venv.

---

## M5: Field Study (Thu Jul 17 – Fri Jul 18, ~2 days)

**Done criteria:** Agent run against 5 public repos. Downloads complete (2,300 runs, 110 failures). Analysis pending.

### M5.1 — Architecture rewrite (two-phase design) ✅

- [x] Split single-pipeline into `download` + `analyze` subcommands
- [x] New `downloader.py`: resumable, parallel, offset-based batching, manifest tracking
- [x] `preflight` + `verify` subcommands for validation
- [x] LLM adapter: temperature=0, graceful fallback, response cache, structured logging
- [x] LLM tokens from env vars only (`OPENAI_API_KEY`, `DEEPSEEK_API_KEY`)
- [x] Classifier dedup (memoize per test_name)
- [x] Permissive unittest regex for Django's test runner
- [x] 253 tests passing, ruff clean, mypy clean

### M5.2 — Field study plan (`docs/field-study-plan.md`) ✅

- [x] Document test objectives: accuracy, discovery, coverage + speed
- [x] Target repos (5): pytest-dev/pytest, django/django, fastapi/fastapi, langchain-ai/langchain, vercel/next.js
- [x] Per-repo parameters: runs=500, format=all, data-dir=./data/, --all-runs
- [x] 4 LLM runs per repo: OMLX, GPT-4o-mini, DeepSeek, rules-only baseline
- [x] Batch workflow with offsets (100-run chunks, resume via manifest)
- [x] Output preserved per repo per LLM per batch in `runs/` directory
- [x] LLM cost table (20→200→2000→20000 calls) for article
- [x] Accuracy validation methodology: 10 per repo × 4 runs = 200 samples
- [x] Disk space, rate limit budget, risk mitigation tables

**Done check:** Plan document written and reviewed.

### M5.3 — Download phase (Phase 1) ✅

| Repo | Framework | Runs | Logs | Failures | Status |
|---|---|---|---|---|---|
| fastapi/fastapi | pytest | 500 | 500 | 21 | ✅ Analyzed |
| langchain-ai/langchain | pytest | 500 | 500 | 28 | ✅ Analyzed |
| pytest-dev/pytest | pytest | 342 | 298 | 23 | ✅ Analyzed |
| vercel/next.js | Turbopack | 500 | 479 | 18 | ✅ Analyzed |
| django/django | unittest | 500 | 500 | 17 | ❌ Skipped (prompt overflow) |
| jestjs/jest | Jest | 300 | 300 | 45 | ✅ Analyzed |
| vuejs/core | Vitest | 300 | 294 | 21 | ✅ Analyzed |
| encode/django-rest-framework | pytest | 300 | 174 | 36 | ✅ Analyzed |
| microsoft/playwright | Playwright | 150 | 145 | 36 | ✅ Clean CI |
| golang/go | Go test | 150 | 150 | 6 | ✅ Clean CI |
| django-import-export | pytest | 288 | 23 | 53 | ✅ Clean CI |
| gin-gonic/gin | Go test | 100 | 100 | 3 | ✅ Clean CI |
| rails/rails | Minitest | 100 | 100 | 0 | ✅ Clean CI |
| rubocop/rubocop | RSpec | 150 | 147 | 9 | ✅ Analyzed |
| laravel/laravel | PHPUnit | 150 | 147 | 0 | ✅ Clean CI |
| expressjs/express | Mocha | 100 | 86 | 3 | ✅ Clean CI |
| cypress-io/cypress | Cypress | 100 | 37 | 1 | ✅ Analyzed |
| spring-projects/spring-boot | JUnit | 100 | 94 | 14 | ✅ Analyzed |
| reduxjs/redux-toolkit | Jest | 100 | 92 | 7 | ✅ Analyzed |
| react-hook-form | Playwright | 100 | 100 | 11 | ✅ Clean CI |
| facebook/react | Jest | 100 | 87 | 3 | ✅ Analyzed |

**Totals: 21 repos, ~4,500 runs, ~3,800 logs, ~4.5 GB**

### M5.4 — Analysis phase (Phase 2) ✅

**OMLX runs (Qwen3.5-9B-MLX-4bit, --no-thinking):**

| Repo | Tests | FLAKY | REAL_BUG | INFRA | Degraded |
|---|---|---|---|---|---|
| fastapi/fastapi | 21 | 18 | 0 | 3 | 0 ✅ |
| pytest-dev/pytest | 38 | 38 | 0 | 0 | 0 ✅ |
| langchain-ai/langchain | 44 | 44 | 0 | 0 | 0 ✅ |
| jestjs/jest | 48 | 48 | 0 | 0 | 0 ✅ |
| vuejs/core | 14 | 13 | 1 | 0 | 0 ✅ |
| vercel/next.js | 71 | 71 | 0 | 0 | 1 ✅ |
| encode/django-rest-framework | 12 | 12 | 0 | 0 | 0 ✅ |
| rubocop/rubocop | 88 | 88 | 0 | 0 | 74 ⚠️ |
| reduxjs/redux-toolkit | 768 | 768 | 0 | 0 | 0 ✅ |
| cypress-io/cypress | 2 | 2 | 0 | 0 | 0 ✅ |
| spring-projects/spring-boot | 1 | 1 | 0 | 0 | 0 ✅ |
| facebook/react | 26 | 26 | 0 | 0 | 0 ✅ |

**GPT-5 Nano runs (OpenCode Zen, cloud):**

| Repo | Tests | FLAKY | REAL_BUG | INFRA | Degraded |
|---|---|---|---|---|---|
| fastapi/fastapi | 21 | 8 | 13 | 0 | 0 ✅ |
| pytest-dev/pytest | 38 | 38 | 0 | 0 | 0 ✅ |
| langchain-ai/langchain | 44 | 44 | 0 | 0 | 0 ✅ |
| jestjs/jest | 322 | 322 | 0 | 0 | 0 ✅ |
| vercel/next.js | 220 | 185 | 35 | 0 | 1 ✅ |
| encode/django-rest-framework | 12 | 12 | 0 | 0 | 0 ✅ |
| rubocop/rubocop | 88 | 80 | 8 | 0 | 3 ✅ |
| facebook/react | 26 | 26 | 0 | 0 | 0 ✅ |

- [x] Analyze all repos with OMLX
- [x] Analyze 8 repos with GPT-5 Nano
- [x] Attempted DeepSeek V4 Flash (failed on 7/8 repos — 400 errors)
- [x] Record runtime per LLM per repo
- [x] Compile cross-model comparison
- [x] 15 parsers built for 12 frameworks
- [x] 11 bugs found and fixed

### M5.5 — Field study analysis + accuracy report ✅

- [x] Compile discovery results: 56 REAL_BUGs found by GPT-5 Nano
- [x] Write `docs/field-study-results.md` with all findings
- [ ] Capture screenshots of CLI table output for the article
- [ ] Manual accuracy validation (56 REAL_BUG disagreements need human review)
- [ ] Capture example error distributions from real flaky tests found

**Done check:** Accuracy ≥ 90%. Discovery count documented. Results document complete.

---

## M6: Hashnode Article (Fri Jul 25, ~0.5 day)

**Done criteria:** Article published on Hashnode + cross-posted to dev.to. Article includes field study data, architecture diagram, and honest limitations.

**Depends on:** M7 (repo public first — articles link to live repo)

### M6.1 — Hashnode article

- [ ] Title: "Before You Quarantine: Building the Diagnostic Layer for AI-Driven Flaky Test Triage"
- [ ] Structure:
  - [ ] Hook: flaky tests destroy CI trust (use research data from PRD §1.5)
  - [ ] Problem: 51% of devs see flaky tests weekly, 73% lose trust in test results
  - [ ] Approach: fetch → classify → correlate (LangGraph conditional edges)
  - [ ] Architecture: diagram from SPEC §2.1
  - [ ] Field study results: 5 repos, 500 runs, accuracy, discovery, speed
  - [ ] Real examples: error distributions from flaky tests found
  - [ ] Honest limitations: Python-only, hash-based (not semantic), needs 50+ runs
  - [ ] What's next: v2 interrupt loop + quarantine governance
- [ ] Link to GitHub repo
- [ ] Written (saved to vault: `training/articles-published/before-you-quarantine/hashnode.md`)

### M6.2 — Dev.to cross-post

- [ ] Shorter, story-driven version
- [ ] Focus: "I ran an AI agent against 5 open-source repos and found X flaky tests"
- [ ] Tags include `discuss`
- [ ] Link to GitHub repo + Hashnode article
- [ ] Written (saved to vault: `training/articles-published/before-you-quarantine/devto.md`)

### M6.3 — Community push

- [ ] Post link to Hacker News (CI/testing angle)
- [ ] Post link to r/Python (flaky test detection angle)
- [ ] Post link to LangChain Discord (LangGraph use case)
- [ ] Post link to CNCF Slack (DevOps tooling)

**Done check:** Both articles written and saved. Publishing deferred until repo is public (M7).

---

## M7: Going Public (Mon Jul 28, ~0.5 day)

**Done criteria:** Repo flipped from private to public. All OSS hygiene in place. First tagged release on GitHub. Issue/PR templates ready for community contributions.

### M7.1 — Security sweep ✅

- [x] Scan for secrets: clean — no secrets in git history
- [x] `.gitignore` covers: `__pycache__/`, `*.pyc`, `.env`, `*.egg-info/`, `dist/`, `build/`, `.venv/`, `venv/`, `*.log`, `reports/`, `data/`, `runs/`
- [x] GITHUB_TOKEN is read from env var, not hardcoded
- [x] No `.env` file ever committed
- [x] README uses `your_token_here` placeholder patterns
- [x] Field study reports contain only public repo data

### M7.2 — OSS community files ✅

- [x] `CONTRIBUTING.md` — setup, tests, lint, type check, commit convention, PR process, parser guide
- [x] `CODE_OF_CONDUCT.md` — Contributor Covenant v2.1
- [x] `.github/ISSUE_TEMPLATE/bug_report.md` — version, steps, expected/actual
- [x] `.github/ISSUE_TEMPLATE/feature_request.md` — problem, solution, alternatives
- [x] `.github/PULL_REQUEST_TEMPLATE.md` — issue link, description, test plan, checklist

### M7.3 — Repo settings

- [ ] **Visibility:** Private → Public (owner action)
- [ ] **Description:** "LangGraph agent that diagnoses flaky CI tests. Fetches GitHub Actions run history, classifies failures (real bug vs flaky vs infra), produces a CI health report."
- [ ] **Topics:** `flaky-tests`, `ci`, `github-actions`, `langgraph`, `python`, `testing`, `devops`, `open-source`
- [ ] **Branch protection:** `main` — require PR review before merge
- [x] **License:** MIT (in place)

### M7.4 — Release & tags ✅

- [x] Tag `v0.1.0` pushed
- [x] GitHub Release created with description, features, installation, and field study results link
- [ ] Verify `git clone` + `pip install -e ".[dev]"` + `pytest` works from clean checkout

### M7.5 — README polish (final pass) ✅

- [x] Badges: needs adding
- [x] Quick start section: install → set token → run command
- [x] Research data section from PRD
- [x] Field study results summary
- [x] Link to `docs/` directory
- [x] v2 roadmap section

### M7.6 — PyPI publish (optional — defer if not ready)

- [ ] Deferred

**Done check:** Most items complete. Repo visibility, branch protection, and PyPI publish pending owner action.

---

## M8: Vault + Plan Update (after public, ~0.5 day)

**Done criteria:** my-2nd-brain vault updated with project completion status, metrics, and article links.

### M8.1 — Project note update

- [ ] Update `vault/projects/46-Build-Flakiness-Triage.md`:
  - [ ] Status → `complete`
  - [ ] Add `date-complete: 2026-07-28`
  - [ ] Add metrics: tests written, coverage, field study results
  - [ ] Add GitHub URL (already linked)
  - [ ] Add article URLs
  - [ ] Update `next-action` → "v2: interrupt loop + quarantine (M5-M8)"

### M8.2 — 6-month plan update

- [ ] Update `_6-MONTH-PLAN.md` Week 3:
  - [ ] Mark all Week 3 tasks as `[x]`
  - [ ] Add completion summary to Cycle 3 section
  - [ ] Update metrics in `_METRICS.md`

### M8.3 — Daily journal

- [ ] Write daily journal entry for ship day
- [ ] Include: what was built, field study results, article published, repo went public

**Done check:** Vault reflects project completion. Plan shows Week 3 done.

---

## Summary

| Milestone | Day | Effort | Dependencies |
|---|---|---|---|
| M1: Scaffold + GitHub Client | Sat Jul 19 | 1 day | — | ✅
| M2: Log Parser + Error Signature | Sun Jul 20 | 1 day | M1 | ✅
| M3: Classifier | Mon Jul 21 | 1 day | M2 | ✅
| M4: Correlator + Graph + Report | Tue Jul 22 | 1.5 days | M3 | ✅
| M5: Field Study | Wed-Thu Jul 23-24 | 1.5 days | M4 |
| M6: Hashnode Article | Fri Jul 25 | 0.5 day | M7 |
| M7: Going Public | Mon Jul 28 | 0.5 day | M4, M5 |
| M8: Vault + Plan Update | after public | 0.5 day | M7 |

**Alpha (Sat):** M1 — GitHub client fetching real runs + logs ✅
**Beta (Sun):** M2 — Parser extracting test results from real logs ✅
**Core (Mon):** M3 — Classifier distinguishing real bug / flaky / infra ✅
**RC (Tue):** M4 — Full pipeline running end-to-end with reports ✅
**Field (Wed-Thu):** M5 — 5 repos analyzed, accuracy validated
**Article (Fri):** M6 — Hashnode + dev.to written
**Launch (Mon):** M7 — Repo public, release tagged
**Close (Mon PM):** M8 — Vault updated, plan marked complete
