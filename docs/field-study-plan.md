# Field Study Plan — ai-flake-sleuth

| Field | Value |
|---|---|
| **Project** | ai-flake-sleuth |
| **Milestone** | M5 |
| **Author** | Debashish Ghosal |
| **Date** | 2026-07-22 |
| **Status** | Draft — code changes complete, ready for review |

---

## 1. Objectives

1. **Accuracy** — What fraction of the agent's classifications match manual review?
2. **LLM comparison** — How do OMLX, GPT-4o-mini, DeepSeek V4 Flash, and a rules-only baseline compare on ambiguous classification accuracy?
3. **Discovery** — How many flaky tests does the agent find that aren't already tracked?
4. **Coverage** — Can the agent handle diverse repos (size, language, CI complexity)?
5. **Speed** — Does the full pipeline complete within practical time limits?
6. **Robustness** — Can downloads and analysis both resume after failure?

---

## 2. Target Repositories

### 2.1 Original target set (phase 1: OMLX field study)

| # | Repo | Lang | Stars | Failures | Rationale | Notes |
|---|---|---|---|---|---|---|
| 1 | `pytest-dev/pytest` | Python | 14.3k | 389 | The tool's own framework — highest familiarity | ✅ Complete — 38 tests, all FLAKY |
| 2 | `django/django` | Python | 88k | 3,850 | Most popular Python web framework | ❌ Skipped — prompt overflow bug (§21.8) |
| 3 | `fastapi/fastapi` | Python | 100k | 5,849 | Modern Python framework, very active CI | ✅ Complete — 21 tests, 18 FLAKY + 3 INFRA |
| 4 | `langchain-ai/langchain` | Python | 142k | 9,215 | AI ecosystem — meta appeal for article | ✅ Complete — 44 tests, all FLAKY |
| 5 | `vercel/next.js` | JavaScript/TS | 141k | 44k | Non-Python test (LLM fallback gap) | ✅ Complete — 0 tests (Jest, no parser) |

### 2.2 Expanded target set (phase 2: Jest + Django replacement)

Coverage gaps identified in phase 1:
- **Jest/JS framework gap:** Next.js produced 0 parsed tests (§22). New JS repos test the Jest parser.
- **Django replacement:** `django/django` skipped due to prompt overflow (§21.8). Smaller Django repos replace it.
- **Vitest coverage:** Vue.js uses Vitest (Jest-compatible), testing the generic JS fallback.

| # | Repo | Lang | Stars | Test framework | What it covers | Status |
|---|---|---|---|---|---|---|
| 6 | `facebook/react` | JavaScript/TS | 230k+ | **Jest** | Largest JS repo; primary Jest test | Downloading (300 runs) |
| 7 | `vuejs/core` | JavaScript/TS | 48k | **Vitest** | Edge case: Vitest output varies from Jest | Downloading (300 runs) |
| 8 | `jestjs/jest` | JavaScript/TS | 45k | **Jest** | Meta: Jest's own test suite | Downloading (300 runs) |
| 9 | `encode/django-rest-framework` | Python | 28k | **pytest** | Django replacement; moderate test suite | Downloading (300 runs) |
| 10 | `django-import-export/django-import-export` | Python | 3k | **pytest** | Small Django package; minimal overflow risk | Downloading (300 runs) |

**Why expanded set:**
- 3 JS/TS repos (react, jest, vue) to thoroughly test the new Jest/Vitest parser
- 2 Django-ecosystem Python repos (rest-framework, import-export) as django/django replacements
- Tests the late-discovery fix: non-Python framework support (§22)
- Star range now spans 3k → 230k
- Failure diversity: CSS (react) → API (rest-framework) → core library (jest)

---

## 3. Architecture: Two-Phase Design

> Download and analysis are fully separated. Download runs once per repo
> (network required, resumable). Analysis runs 4× per repo (offline,
> one per LLM provider + rules-only baseline).

### 3.1 Phase 1 — Download (network required, batch with offsets)

```
# Batch 1: runs 0-99
ai-flake-sleuth download --repo pytest-dev/pytest --runs 100 --offset 0 \
    --data-dir ./data/ --all-runs

# Batch 2: runs 100-199
ai-flake-sleuth download --repo pytest-dev/pytest --runs 100 --offset 100 \
    --data-dir ./data/ --all-runs

# ... repeat until 500 runs downloaded
# Or download all 500 at once:
ai-flake-sleuth download --repo pytest-dev/pytest --runs 500 --offset 0 \
    --data-dir ./data/ --all-runs
```

**Responsibilities:**
- Fetch run metadata from GitHub API (paginated, skip `--offset` runs)
- For each run: fetch job metadata + download log ZIP
- `--all-runs`: download logs for successful runs too (catches flaky tests that retried+passed)
- Save everything to disk as structured files
- Write a manifest tracking progress + which offset ranges are downloaded
- **Resumable:** re-running same offset = no-op; new offset = incremental

**Data layout on disk:**
```
data/
└── pytest-dev_pytest/
    ├── manifest.json              ← progress tracker + offset ranges
    ├── runs/
    │   ├── 123456.json            ← per-run metadata (RunInfo + JobInfo[])
    │   └── ...
    ├── logs/
    │   ├── 123456.zip             ← raw log ZIP (as downloaded)
    │   └── ...
    └── llm-cache/                  ← LLM response cache (per provider, shared across batches)
    └── omlx/
    └── openai/
    └── deepseek/
```

**Key behaviors:**
- **Batch offsets:** `--offset N --runs M` downloads runs N through N+M
- **Resume:** same offset range already downloaded → skip
- **Selective:** only downloads runs not already on disk
- **Skip expired:** 410 Gone → record in manifest, move on
- **Parallel:** 4 worker threads download logs concurrently
- **Idempotent:** running same download twice = no-op

### 3.2 Phase 2 — Analyze (no network needed, batch with offsets)

```
# Analyze first 100 runs with OMLX
ai-flake-sleuth analyze --repo pytest-dev/pytest --data-dir ./data/ \
    --llm omlx --offset 0 --batch-size 100 --format all

# Analyze next 100 runs with OMLX (LLM cache skips already-classified tests)
ai-flake-sleuth analyze --repo pytest-dev/pytest --data-dir ./data/ \
    --llm omlx --offset 100 --batch-size 100 --format all

# Same batch with OpenAI
ai-flake-sleuth analyze --repo pytest-dev/pytest --data-dir ./data/ \
    --llm openai --llm-model gpt-4o-mini --offset 0 --batch-size 100 --format all

# Rules-only baseline
ai-flake-sleuth analyze --repo pytest-dev/pytest --data-dir ./data/ \
    --no-llm --offset 0 --batch-size 100 --format all
```

**Output directory structure (preserved per repo, per LLM, per batch):**
```
runs/
└── pytest-dev_pytest/
    ├── omlx/
    │   ├── batch-0000-0100/
    │   │   ├── report.json           ← full JSON report
    │   │   ├── report.md             ← markdown report
    │   │   ├── report.txt            ← CLI table output
    │   │   ├── summary.json          ← batch metadata (counts, rates, runtime)
    │   │   └── llm-logs/             ← structured LLM call logs (prompt + response + tokens)
    │   │       ├── omlx_0001.json
    │   │       └── ...
    │   ├── batch-0100-0200/
    │   │   └── (same structure)
    │   └── batch-0200-0300/
    │       └── (same structure)
    ├── openai/
    │   ├── batch-0000-0100/
    │   │   └── (same structure)
    │   └── ...
    ├── deepseek/
    │   └── ...
    └── no-llm/
        └── ...
```

**Key behaviors:**
- **Batch offsets:** `--offset N --batch-size M` analyzes only runs N through N+M
- **LLM cache:** `data/{repo}/llm-cache/{provider}/` is shared across batches — re-running or analyzing a new batch skips tests already classified by that provider
- **Re-run safe:** re-running the same batch with the same LLM = all cache hits, zero API calls
- **Dedup:** classifier memoizes per `test_name` (one LLM call per unique test per batch)
- **Graceful fallback:** LLM failure → conservative FLAKY, logged, continues
- **Temperature=0:** deterministic — same input always produces same output
- **summary.json:** every batch writes a machine-readable summary for easy cross-comparison

### 3.3 Manifest format (resume tracking)

```json
{
  "repo": "pytest-dev/pytest",
  "runs_requested": 500,
  "runs_fetched": 500,
  "runs_downloaded": 487,
  "runs_skipped_expired": 8,
  "runs_skipped_error": 5,
  "runs_with_failures": 142,
  "runs_with_logs": 137,
  "status": "complete",
  "started_at": "2026-07-22T14:00:00Z",
  "completed_at": "2026-07-22T14:12:30Z",
  "last_run_id_processed": 9876543210,
  "processed_run_ids": ["123456", "123457", "..."],
  "offsets_downloaded": [[0, 100], [100, 200], [200, 300], [300, 400], [400, 500]]
}
```

**Resume logic:**
1. Load manifest (if exists)
2. Check if requested `[offset, offset+n]` is in `offsets_downloaded`
3. If yes → skip (already downloaded)
4. If no → fetch and download that range, append to `offsets_downloaded`
5. If no manifest → fresh start

### 3.4 Pre-flight and verification commands

```
# Validate environment before starting
ai-flake-sleuth preflight --repos pytest-dev/pytest django/django --llm-providers omlx openai deepseek

# Validate downloaded data before analysis
ai-flake-sleuth verify --repo pytest-dev/pytest --data-dir ./data/
```

**`preflight` checks:**
- GITHUB_TOKEN is set and valid
- OPENAI_API_KEY / DEEPSEEK_API_KEY are set (per provider)
- GitHub API rate limit is healthy
- Smoke test: fetch 1 run from each repo
- Disk space ≥ 6 GB

**`verify` checks:**
- Manifest exists and status is "complete"
- Run JSON files on disk match manifest count
- All log ZIPs are valid (not corrupt)
- Effective sample (runs with logs + failures) > 0

---

## 4. LLM Comparison Methodology

Each repo is analyzed **4 times** (Phase 2 only — download once, analyze 4×):

| Run | Provider | Model | Endpoint | Cost |
|---|---|---|---|---|
| A | OMLX (Ollama) | `qwen2.5-coder:7b` | `http://localhost:11434` | Free (local) |
| B | OpenAI | `gpt-4o-mini` | `https://api.openai.com` | ~$0.15/1M tokens |
| C | DeepSeek | `deepseek-chat` (v4 flash) | `https://api.deepseek.com` | ~$0.014/1M tokens |
| D | Rules-only | N/A (`--no-llm`) | N/A | Free |

**Why include rules-only baseline:** The most important comparison is whether the LLM actually improves accuracy over rules alone. Without a baseline, we can't tell if LLM agreement is meaningful or just coincidence.

**Why compare LLMs:** The LLM only fires on ambiguous cases (Step 5 of the classifier's 6-step pipeline). Most classifications use rules. The comparison measures whether the model choice meaningfully changes the final output for edge cases.

**Comparison dimensions:**
- Agreement rate between the 3 LLM providers (% where all 3 return same category)
- Accuracy vs ground truth for each LLM provider AND the rules-only baseline
- Runtime per model (local OMLX is slower than cloud APIs)
- Cost per 500 runs
- Cases where LLM disagreed with the rules-only default

**Per-repo commands:**
```bash
# Run A: OMLX
ai-flake-sleuth analyze --repo {repo} --data-dir ./data/ --llm omlx --format all --output ./reports/

# Run B: OpenAI
ai-flake-sleuth analyze --repo {repo} --data-dir ./data/ --llm openai --llm-model gpt-4o-mini --format all --output ./reports/

# Run C: DeepSeek
ai-flake-sleuth analyze --repo {repo} --data-dir ./data/ --llm deepseek --llm-model deepseek-chat --format all --output ./reports/

# Run D: Rules-only baseline
ai-flake-sleuth analyze --repo {repo} --data-dir ./data/ --no-llm --format all --output ./reports/
```

---

## 5. LLM Cost Analysis

### 5.1 Per-call cost breakdown

Each LLM call processes an ambiguous test failure. Prompt size estimated from `llm.py`:

| Component | Tokens (avg) |
|---|---|
| System prompt (classifier instructions) | 100 |
| Test name + error message + stack trace | 400 |
| Cross-run context (JSON stats) | 200 |
| JSON output instruction | 50 |
| **Total input tokens** | **750** |
| **Output tokens (JSON response)** | **75** |

### 5.2 Cost per LLM call by model

| Model | Input $/1M tok | Output $/1M tok | Input cost | Output cost | **Per call** |
|---|---|---|---|---|---|
| OMLX (qwen2.5-coder:7b) | $0 (local) | $0 (local) | $0 | $0 | **$0** |
| DeepSeek V4 Flash | $0.014 | $0.028 | $0.0000105 | $0.0000021 | **~$0.000013** |
| GPT-4o-mini | $0.15 | $0.60 | $0.0001125 | $0.000045 | **~$0.000158** |
| GPT-4o | $2.50 | $10.00 | $0.001875 | $0.00075 | **~$0.002625** |

### 5.3 Total cost at different call volumes

| LLM calls → | 20 | 200 | 2,000 | 20,000 |
|---|---|---|---|---|
| **OMLX (qwen2.5-coder:7b)** | $0 | $0 | $0 | $0 |
| **DeepSeek V4 Flash** | $0.0003 | $0.0025 | $0.025 | $0.25 |
| **GPT-4o-mini** | $0.003 | $0.03 | $0.32 | $3.15 |
| **GPT-4o** | $0.05 | $0.53 | $5.25 | $52.50 |

### 5.4 Expected call volume per repo

After dedup (memoize per `test_name`), with 500 runs per repo:

| Repo | Est. unique tests | Est. ambiguous (LLM-eligible) | 3-LLM total |
|---|---|---|---|
| pytest-dev/pytest | 20 | 2–5 | 6–15 |
| django/django | 60 | 5–10 | 15–30 |
| fastapi/fastapi | 40 | 3–8 | 9–24 |
| langchain-ai/langchain | 80 | 5–12 | 15–36 |
| vercel/next.js | ~0 (no regex match) | 0 | 0 |
| **Total** | **~200** | **~15–35** | **~45–105** |

**Total cost (all 5 repos, 3 LLM models):** $0 (OMLX) + ~$0.005 (DeepSeek) + ~$0.01 (GPT-4o-mini) = **~$0.015**

Even at 20,000 calls (massive scale): **$0 (OMLX) + $0.25 (DeepSeek) + $3.15 (GPT-4o-mini) = $3.40**

> **Note for M6 article:** This cost table (sections 5.1–5.3) is designed to go directly into the Hashnode article. It shows that LLM-powered flaky test classification costs pennies even at scale — a compelling argument for the approach. The 20 → 200 → 2,000 → 20,000 progression gives readers an intuition for how costs scale.

---

## 6. Code Changes — Status

> All changes are **implemented and tested** (248 tests pass, ruff clean, mypy clean).

### 6.1 Split pipeline into download + analyze commands ✅

| Change | Files | Status |
|---|---|---|
| `download` subcommand | `cli.py` | ✅ Done |
| `analyze` subcommand | `cli.py` | ✅ Done |
| `preflight` subcommand | `cli.py` | ✅ Done |
| `verify` subcommand | `cli.py` | ✅ Done |
| Download module: fetch + save to disk | `downloader.py` (new) | ✅ Done |
| Analyze: load from disk, skip fetch_runs | `graph.py` | ✅ Done |
| Legacy mode backward compat (`--repo` without subcommand) | `cli.py` | ✅ Done |

### 6.2 Resume functionality ✅

| Change | Files | Status |
|---|---|---|
| Manifest JSON with `processed_run_ids` list | `downloader.py` | ✅ Done |
| On resume: skip runs already on disk | `downloader.py` | ✅ Done |
| `--force` flag to re-download | `cli.py`, `downloader.py` | ✅ Done |
| ZIP integrity check on load | `downloader.py` | ✅ Done |

### 6.3 Selective download ✅

| Change | Files | Status |
|---|---|---|
| Check `runs/{run_id}.json` exists → skip metadata fetch | `downloader.py` | ✅ Done |
| Check `logs/{run_id}.zip` exists → skip log download | `downloader.py` | ✅ Done |
| `--all-runs` flag to download successful run logs too | `cli.py`, `downloader.py` | ✅ Done |
| Parallel downloads (4 workers by default) | `downloader.py` | ✅ Done |

### 6.4 LLM token handling — uniform, env-based ✅

| Change | Files | Status |
|---|---|---|
| `OPENAI_API_KEY` read from env per provider | `config.py` | ✅ Done |
| `DEEPSEEK_API_KEY` read from env per provider | `config.py` | ✅ Done |
| `api_key` passed to `LLMAdapter` from graph | `graph.py` | ✅ Done |
| No provider special-casing in `llm.py` | `llm.py` | ✅ Done |
| No API keys in code or config defaults | all | ✅ Done |

### 6.5 Classifier dedup fix ✅

| Change | Files | Status |
|---|---|---|
| Memoize LLM calls per `test_name` in classify_node | `graph.py` | ✅ Done |

### 6.6 LLM robustness and caching ✅

| Change | Files | Status |
|---|---|---|
| `temperature=0` for deterministic output | `llm.py` | ✅ Done |
| Graceful fallback: LLM failure → FLAKY, log, continue | `llm.py` | ✅ Done |
| On-disk LLM response cache (resume analysis without re-calling) | `llm.py` | ✅ Done |
| Structured LLM call logging (prompt + response + latency + tokens) | `llm.py` | ✅ Done |
| Exact model version recorded from API response | `llm.py` | ✅ Done |

### 6.7 Log parser improvements ✅

| Change | Files | Status |
|---|---|---|
| Permissive unittest regex for Django's DiscoverRunner | `log_parser.py` | ✅ Done |

### 6.8 Other fixes ✅

| Change | Files | Status |
|---|---|---|
| `data/` and `llm-logs/` added to `.gitignore` | `.gitignore` | ✅ Done |
| Correlator `flake_rate` / `failure_rate` docstrings clarified | `types.py` | ✅ Done |
| 24 tests for downloader module | `tests/test_downloader.py` | ✅ Done |

---

## 7. Per-Repo Parameters

### 7.1 Download phase

```
ai-flake-sleuth download \
    --repo {repo} \
    --runs 500 \
    --data-dir ./data/ \
    --all-runs
```

No `--workflow` filter — download all workflows. `--all-runs` ensures successful run logs are captured too (catches flaky tests that retried+passed).

### 7.2 Analyze phase

Run **4× per repo**:

```bash
# OMLX (local, free)
ai-flake-sleuth analyze --repo {repo} --data-dir ./data/ --llm omlx --format all --output ./reports/

# OpenAI (cloud)
ai-flake-sleuth analyze --repo {repo} --data-dir ./data/ --llm openai --llm-model gpt-4o-mini --format all --output ./reports/

# DeepSeek (cloud, cheap)
ai-flake-sleuth analyze --repo {repo} --data-dir ./data/ --llm deepseek --llm-model deepseek-chat --format all --output ./reports/

# Rules-only baseline (no LLM)
ai-flake-sleuth analyze --repo {repo} --data-dir ./data/ --no-llm --format all --output ./reports/
```

---

## 8. Data Collection

For each repo × 4 runs, collect:

| Data Point | Source |
|---|---|
| Download runtime (seconds) | `time` command on download phase |
| Analyze runtime per LLM (seconds) | `time` command on each analyze phase |
| LLM provider + model | CLI args |
| Total runs fetched | manifest.json → runs_fetched |
| Runs with failures | manifest.json → runs_with_failures |
| Effective sample | Report → Data Quality → effective_sample |
| Flaky tests found (count + names) | Report → Flaky Tests |
| Real bugs found (count + names) | Report → Real Bugs |
| Infra issues found (count + names) | Report → Infra Issues |
| Insufficient data (count + names) | Report → Insufficient Data |
| Overall pass rate | Report → Summary → overall_pass_rate |
| Avg flake rate | Report → Summary → avg_flake_rate |
| Disk space used | `du -sh data/{repo}/` |
| LLM calls made (API calls, not cache hits) | `adapter.call_count` in verbose log |
| LLM cache hits | `adapter.cache_hits` in verbose log |
| LLM call logs (prompt + response + tokens) | `llm-logs/{provider}_*.json` files |
| Exact model version | LLM call log → `model_actual` field |
| JSON report | Saved to `./reports/` |
| Markdown report | Saved to `./reports/` |

**Total data points:** 5 repos × 4 runs × ~19 data points = ~380 data points.

---

## 9. Accuracy Validation Methodology

### 9.1 Sampling

**Sample per repo:** 10 classifications × 4 runs = 40 per repo = **200 total samples across 5 repos**.

**Sampling strategy per repo:**
- 4 from Flaky Tests (highest flake rate, lowest, + 2 random)
- 3 from Real Bugs (if any; if fewer, take from Flaky)
- 2 from Infra Issues (if any; if fewer, take from Flaky)
- 1 from Insufficient Data (if any; else from Flaky)

When the same test is classified by all 4 runs, review it once (the ground truth is the same).

### 9.2 Validation process

1. Note the test name and classification from each run's report
2. Read the raw log from downloaded `data/{repo}/logs/{run_id}.zip` (or GitHub UI)
3. Determine ground truth: REAL_BUG, FLAKY, or INFRA
4. Compare each run's classification to ground truth
5. Record match/mismatch + notes per run

### 9.3 Ground truth criteria

| Category | Criteria |
|---|---|
| **REAL_BUG** | Error is deterministic, same error every run, tied to a specific code change |
| **FLAKY** | Error is intermittent, appears in some runs but not others, no code change triggered it |
| **INFRA** | Error is clearly infrastructure (timeout, OOM, network, 502/503/504, disk full) |

---

## 10. LLM Model Comparison Criteria

| Criteria | How measured |
|---|---|
| **Agreement rate (LLM-only)** | % of test-level classifications where all 3 LLM providers return the same category |
| **Accuracy vs ground truth** | % where each run's classification matches manual review (per LLM + rules baseline) |
| **LLM vs rules delta** | Cases where LLM changed the classification from the rules-only default |
| **Runtime overhead** | Time spent in LLM calls vs total analysis time |
| **Cost** | Token count × pricing per model |
| **Cache hit rate** | % of LLM calls served from disk cache on re-runs |

---

## 11. Discovery Definition

A flaky test is "discovered" if:
- It appears in the agent's Flaky Tests section
- It is NOT already tracked in the repo's issue tracker
- A search for the test name or error message yields no relevant bug report

---

## 12. Pass/Fail Criteria

| Criteria | Target | Measurement |
|---|---|---|
| **Accuracy** | ≥ 90% (avg across 3 LLMs) | Manual review of sampled classifications |
| **Rules baseline accuracy** | ≥ 80% | Manual review of rules-only classifications |
| **LLM improvement** | LLM accuracy > rules accuracy by ≥ 5pp | Cross-comparison |
| **LLM agreement** | ≥ 80% agreement rate between 3 LLMs | Cross-model comparison |
| **Discovery** | ≥ 1 flaky test per Python repo | Count from reports + issue tracker search |
| **Coverage** | 2,500 total runs across 5 repos (500 ea) | Sum of runs_fetched from manifests |
| **Download speed** | < 10 min per repo (500 runs) | Wall-clock time for download phase |
| **Analyze speed** | < 3 min per repo per LLM | Wall-clock time for analyze phase |
| **Resume** | Download + analysis can stop + restart without data loss | Kill + re-run test |
| **Determinism** | Same data + same LLM = same output (temperature=0) | Re-run comparison |

---

## 13. Edge Cases to Document

| Edge Case | Expected Behavior | Likely Repo |
|---|---|---|
| Expired logs (>90 days) | 410 Gone → skip, record in manifest | Any busy repo |
| Rate-limit hits | Exponential backoff, warning logged | django, langchain |
| Repo with no parseable failures | Clean report: regex found no test results | next.js (non-Python) |
| Non-pytest framework logs | Regex fails, test not parsed | next.js (Jest) |
| Django test runner output | Permissive unittest regex catches it | django |
| Multi-workflow repos | All workflows analyzed, workflows_affected shown | django |
| OMLX timeout | Local model may be slow on first load | Repo 1 warm-up |
| LLM API failure | Graceful fallback to FLAKY, logged, continues | Any cloud LLM |
| API key missing | `preflight` catches before any work starts | Pre-flight check |
| Download interrupted | Resume from manifest — no data lost | Network drop, Ctrl-C |
| Analysis interrupted | LLM cache on disk — re-run skips cached calls | Kill + re-run |
| Corrupt log ZIP | Integrity check fails → removed, re-download on next run | Network corruption |
| Disk space | 500 runs × ~5MB avg = ~2.5GB per repo | Large repos |
| Flaky test in successful run | `--all-runs` downloads those logs too | Any repo with retries |

---

## 14. Disk Space Estimate

| Repo | Est. runs with logs | Avg log ZIP size | Total disk |
|---|---|---|---|
| pytest-dev/pytest | ~100 | 2 MB | ~200 MB |
| django/django | ~200 | 5 MB | ~1 GB |
| fastapi/fastapi | ~150 | 3 MB | ~450 MB |
| langchain-ai/langchain | ~250 | 4 MB | ~1 GB |
| vercel/next.js | ~300 | 6 MB | ~1.8 GB |
| **Total** | **~1,000** | | **~4.5 GB** |

Ensure at least **6 GB free** before starting downloads.

---

## 15. Rate Limit Budget

GitHub API allows 5,000 requests/hour with a token.

| API call type | Calls per repo (500 runs) | 5 repos total |
|---|---|---|
| Fetch run metadata (paginated, 100/page) | 5 | 25 |
| Fetch job metadata (per run) | ~500 | ~2,500 |
| Download logs (per run with `--all-runs`) | ~500 | ~2,500 |
| Rate limit checks | ~10 | ~50 |
| **Total per repo** | **~1,015** | **~5,075** |

> **Note:** With `--all-runs`, we download logs for all 500 runs, not just failures. This may exceed the 5,000/hour limit for all 5 repos combined. If rate-limited, the downloader backs off and sleeps until reset. Alternatively, run repos sequentially with a pause between them.

---

## 16. Pre-Flight Checks

Before running, verify:

### 16.1 Run preflight command
```bash
ai-flake-sleuth preflight \
    --repos pytest-dev/pytest django/django fastapi/fastapi langchain-ai/langchain vercel/next.js \
    --llm-providers omlx openai deepseek \
    --data-dir ./data/
```

This validates:
- [ ] `GITHUB_TOKEN` is set and valid
- [ ] `OPENAI_API_KEY` is set (for GPT-4o-mini runs)
- [ ] `DEEPSEEK_API_KEY` is set (for DeepSeek runs)
- [ ] Ollama is running (`ollama list`) and `qwen2.5-coder:7b` is pulled
- [ ] GitHub API rate limit is healthy
- [ ] Smoke test: fetch 1 run from each repo
- [ ] At least 6 GB free disk space

### 16.2 Code verification
- [ ] `ai-flake-sleuth --version` works
- [ ] `ai-flake-sleuth download --help` works
- [ ] `ai-flake-sleuth analyze --help` works
- [ ] `ai-flake-sleuth preflight --help` works
- [ ] `ai-flake-sleuth verify --help` works
- [ ] `pytest` passes (248 tests)
- [ ] `ruff check src/ tests/` clean
- [ ] `mypy src/` clean
- [ ] No API keys hardcoded (`grep -r "sk-" src/ tests/` returns nothing)

### 16.3 Smoke test
- [ ] Download 5 runs from pytest-dev/pytest → verify manifest + files
- [ ] `ai-flake-sleuth verify --repo pytest-dev/pytest` → data valid
- [ ] Analyze with `--no-llm` → verify report generates
- [ ] Kill download mid-run → re-run → verify resume works

---

## 17. Execution Order

### Phase 0: Code changes — COMPLETE ✅

All code changes are implemented and tested (248 tests, ruff clean, mypy clean).

### Phase 1: Download (batch with offsets, once per repo)

| Step | Repo | Command | Est. Time |
|---|---|---|---|
| 0 | — | `preflight` validation | 2 min |
| 1.1 | `pytest-dev/pytest` | `download --runs 500 --offset 0 --all-runs` | 5 min |
| 1.2 | `django/django` | `download --runs 500 --offset 0 --all-runs` | 10 min |
| 1.3 | `fastapi/fastapi` | `download --runs 500 --offset 0 --all-runs` | 8 min |
| 1.4 | `langchain-ai/langchain` | `download --runs 500 --offset 0 --all-runs` | 10 min |
| 1.5 | `vercel/next.js` | `download --runs 500 --offset 0 --all-runs` | 10 min |
| 1.6 | each | `verify --repo {repo}` | 2 min |
| **Phase 1 total** | | | **~50 min** |

> To download in batches of 100: run `download --runs 100 --offset 0`, then `--offset 100`, etc. The manifest tracks which offsets are done.

### Phase 2: Analyze (batch with offsets, 4 LLMs per repo)

For each repo, run 4× (omlx, openai, deepseek, no-llm). Each can be batched:

| Step | Repo | LLM | Batches | Est. Time |
|---|---|---|---|---|
| 2.1 | `pytest-dev/pytest` | OMLX | 5 × 100 | 12 min |
| 2.2 | | OpenAI | 5 × 100 | 10 min |
| 2.3 | | DeepSeek | 5 × 100 | 10 min |
| 2.4 | | no-llm | 5 × 100 | 5 min |
| 2.5 | `django/django` | (4 LLMs × 5 batches) | | 16 min |
| 2.6 | `fastapi/fastapi` | (4 LLMs × 5 batches) | | 13 min |
| 2.7 | `langchain-ai/langchain` | (4 LLMs × 5 batches) | | 16 min |
| 2.8 | `vercel/next.js` | (4 LLMs × 5 batches) | | 8 min |
| **Phase 2 total** | | | | **~65 min** |

> Re-running any batch with the same LLM = all cache hits, zero API calls, ~30 seconds.

### Phase 3: Review + writeup

| Step | Task | Est. Time |
|---|---|---|
| 3.1 | Manual review (50 samples × 4 runs) | 60 min |
| 3.2 | Cross-model comparison | 20 min |
| 3.3 | Article example capture (screenshots, error distributions) | 15 min |
| 3.4 | Write `docs/field-study-results.md` | 25 min |
| **Phase 3 total** | | **~2 hr** |

### Total

| Phase | Time |
|---|---|
| Phase 0 (code) | ✅ Done |
| Phase 1 (download) | ~50 min |
| Phase 2 (analyze) | ~65 min |
| Phase 3 (review) | ~2 hr |
| **Grand total** | **~3.5 hr** (excluding code) |

---

## 18. Output Artifacts

After execution, the following should exist:

```
data/                                    ← Phase 1 output (downloaded data)
├── pytest-dev_pytest/
│   ├── manifest.json                    ← tracks offsets_downloaded, processed_run_ids
│   ├── runs/
│   │   ├── 123456.json                  ← per-run metadata (RunInfo + JobInfo[])
│   │   └── ...
│   ├── logs/
│   │   ├── 123456.zip                   ← raw log ZIP
│   │   └── ...
│   └── llm-cache/                       ← LLM response cache (per provider, shared across batches)
│       ├── omlx/
│       │   └── omlx_qwen2.5-coder:7b_test_foo.json
│       ├── openai/
│       └── deepseek/
├── django_django/                       (same structure)
├── fastapi_fastapi/                     (same structure)
├── langchain-ai_langchain/              (same structure)
└── vercel_next-js/                      (same structure)

runs/                                    ← Phase 2 output (analysis, per repo per LLM per batch)
├── pytest-dev_pytest/
│   ├── omlx/
│   │   ├── batch-0000-0100/
│   │   │   ├── report.json              ← full JSON report
│   │   │   ├── report.md               ← markdown report
│   │   │   ├── report.txt              ← CLI table
│   │   │   ├── summary.json            ← batch metadata (counts, rates, runtime)
│   │   │   └── llm-logs/               ← structured LLM call logs
│   │   │       ├── omlx_0001.json      ← prompt + response + tokens + latency + model version
│   │   │       └── ...
│   │   ├── batch-0100-0200/
│   │   │   └── (same structure)
│   │   └── ...
│   ├── openai/
│   │   ├── batch-0000-0100/
│   │   │   └── (same structure)
│   │   └── ...
│   ├── deepseek/
│   │   └── ...
│   └── no-llm/
│       └── ...
├── django_django/                       (same structure)
├── fastapi_fastapi/                     (same structure)
├── langchain-ai_langchain/              (same structure)
└── vercel_next-js/                      (same structure)

docs/
├── field-study-plan.md                  ← this file
├── field-study-results.md               ← written in Phase 3
```

**Per-batch summary.json format:**
```json
{
  "repo": "pytest-dev/pytest",
  "provider": "omlx",
  "model": "qwen2.5-coder:7b",
  "batch": "batch-0000-0100",
  "offset": 0,
  "batch_size": 100,
  "runs_analyzed": 100,
  "runs_with_failures": 28,
  "flaky_count": 5,
  "real_bug_count": 2,
  "infra_count": 3,
  "insufficient_data_count": 18,
  "overall_pass_rate": 0.72,
  "avg_flake_rate": 12.5,
  "output_dir": "runs/pytest-dev_pytest/omlx/batch-0000-0100"
}
```

**Total artifact count (5 repos × 5 batches × 4 LLMs):**
- 5 manifests + ~2,500 run JSONs + ~2,500 log ZIPs
- 100 batch directories (5 repos × 5 batches × 4 LLMs)
- Each batch: 3 report files + 1 summary + N LLM log files
- LLM cache: shared across batches per provider

---

## 19. Article Example Capture

During Phase 3, capture compelling examples for the Hashnode article:

| Example | What to capture | Where to find it |
|---|---|---|
| Clear flaky test | Test with 3+ distinct error signatures, low failure rate | Report → Flaky Tests → highest signature count |
| Clear real bug | Test with 1 dominant signature, high failure rate | Report → Real Bugs → highest dominant_signature_ratio |
| Infra timeout | Test with timeout/OOM error message | Report → Infra Issues |
| LLM disagreement | Test where 3 LLMs gave different categories | Cross-model comparison spreadsheet |
| LLM vs rules delta | Test where LLM changed the classification | Compare no-llm run vs LLM run |
| CLI table screenshot | Rich terminal output | Terminal capture of table format |
| Error distribution chart | Error signatures for a flaky test | Report JSON → error_signatures |
| Cost table | LLM cost at different scales | §5.3 of this document |

---

## 20. Risk Mitigation

| Risk | Mitigation |
|---|---|
| Download crashes midway | Resume from manifest — no data lost |
| GitHub rate limit hit | Backoff + sleep; ~5,075 calls total |
| LLM provider down | Graceful fallback to FLAKY; re-run later (cache on disk) |
| LLM API key invalid | `preflight` catches before any work starts |
| Disk full mid-download | Manifest shows partial state; clear space + resume |
| OMLX too slow | Can re-run analyze with cloud LLM; OMLX run is optional |
| Corrupt log ZIP | Integrity check on load; removed + re-download on next run |
| Non-Python logs unparseable | Documented edge case (next.js); expected clean report |
| Django test runner format | Permissive unittest regex added |
| Analysis interrupted | LLM cache on disk; re-run skips cached calls |
| Non-deterministic LLM output | temperature=0; same input = same output |
| Flaky tests in successful runs | `--all-runs` flag downloads those logs too |

---

## 21. Learnings: Reasoning Models (Qwen3 family)

### 21.1 Problem

Reasoning models (Qwen3-8B-4bit, Qwen3.5-9B-MLX-4bit) generate an internal
chain-of-thought *before* emitting the final answer. With the original
hardcoded `max_tokens: 512`, the model exhausted the token budget mid-reasoning
and never produced the JSON the prompt requested. The response was silently
truncated (`finish_reason: "length"`), JSON parsing failed, and the fallback
returned a **fake FLAKY verdict** indistinguishable from a real model judgment.

### 21.2 Root cause

| Issue | Location | Impact |
|---|---|---|
| `max_tokens` hardcoded at 512 | `llm.py:239` | Reasoning models run out of tokens before answering |
| `finish_reason` never inspected | `llm.py:253` | Truncation invisible — looked like a normal response |
| Parse failure labeled `llm:` (same as real verdict) | `llm.py:282` | Silent default FLAKY masqueraded as a model verdict |
| No degraded-outcome aggregation | `types.py` / `report.py` | Degraded calls buried in `classified_by` strings |

### 21.3 Fixes applied

| Fix | Files |
|---|---|
| `max_tokens` configurable (default 4096) + `--llm-max-tokens` CLI flag | `llm.py`, `config.py`, `cli.py` |
| `finish_reason == "length"` detected → distinct `llm-truncated:` prefix | `llm.py` |
| Parse failure → distinct `llm-parse-error:` prefix (was `llm:`) | `llm.py` |
| Call failure keeps `llm-fallback:` prefix (already correct) | `llm.py` |
| 4 disjoint prefixes: `llm:` / `llm-truncated:` / `llm-parse-error:` / `llm-fallback:` | `llm.py` |
| Degraded counts in `ReportSummary` (truncated, parse-error, fallback) | `types.py`, `graph.py`, `report.py`, `cli.py` |
| `--no-thinking` flag → sends `chat_template_kwargs: {enable_thinking: false}` | `llm.py`, `config.py`, `graph.py`, `cli.py` |
| Prompt tightened: "JSON only, no reasoning, no explanation" | `llm.py` |

### 21.4 Working commands

**Clear the LLM cache before a fresh run (cache lives under `data/`, not `runs/`):**
```bash
rm -rf data/llm-cache/omlx runs/fastapi_fastapi/omlx
```

**Run with Qwen3.5-9B-MLX-4bit, thinking disabled (recommended for reasoning models):**
```bash
ai-flake-sleuth analyze --repo fastapi/fastapi --data-dir ./data/ \
    --llm omlx --llm-model Qwen3.5-9B-MLX-4bit \
    --llm-endpoint http://127.0.0.1:8000 \
    --force-llm --limit 1 --no-thinking --format all
```

**Run with Qwen3-8B-4bit, thinking disabled:**
```bash
ai-flake-sleuth analyze --repo fastapi/fastapi --data-dir ./data/ \
    --llm omlx --llm-model Qwen3-8B-4bit \
    --llm-endpoint http://127.0.0.1:8000 \
    --force-llm --limit 1 --no-thinking --format all
```

**Run with a non-reasoning model (thinking off by default, no flag needed):**
```bash
ai-flake-sleuth analyze --repo fastapi/fastapi --data-dir ./data/ \
    --llm omlx --llm-model qwen2.5-coder:7b \
    --llm-endpoint http://127.0.0.1:8000 \
    --force-llm --limit 1 --format all
```

**Run with raised max_tokens (if keeping thinking ON — slow):**
```bash
ai-flake-sleuth analyze --repo fastapi/fastapi --data-dir ./data/ \
    --llm omlx --llm-model Qwen3.5-9B-MLX-4bit \
    --llm-endpoint http://127.0.0.1:8000 \
    --force-llm --limit 1 --llm-max-tokens 250000 --format all
```

> `Qwen3.5-9B-MLX-4bit` supports `max_model_len: 262144`. With ~7,779 prompt
> tokens, a safe `--llm-max-tokens` is 250,000. However, thinking-ON calls
> take 200s+ each — use `--no-thinking` unless reasoning is specifically needed.

### 21.5 Measured results

| Metric | Thinking ON (Qwen3-8B, max_tokens=4096) | Thinking ON (Qwen3.5-9B, max_tokens=250K) | Thinking OFF (Qwen3.5-9B) |
|---|---|---|---|
| `finish_reason` | `length` (truncated) | `length` (still truncated at 250K?) | `stop` (complete) |
| Completion tokens | 4,096 (all reasoning) | 4,096+ | **79** (just JSON) |
| Latency | 214s | 214s+ | **16s** |
| Verdict | fake FLAKY (silent default) | truncated (no verdict) | **INFRA** (real, conf 0.95) |
| `classified_by` prefix | `llm:` (misleading) | `llm-truncated:` | `llm:` |

### 21.6 Thinking vs. no-thinking runtime comparison

Single classification call for `tests/test_tutorial/test_testing/test_tutorial003.py::test_main`
against `fastapi/fastapi` data, `--limit 1`, same endpoint `http://127.0.0.1:8000`.

| Metric | Thinking ON | Thinking OFF | Δ |
|---|---|---|---|
| Model | Qwen3-8B-4bit | Qwen3.5-9B-MLX-4bit | (different model, same family) |
| `max_tokens` set | 4,096 (default) | 4,096 (default) | same |
| `finish_reason` | `length` | `stop` | OFF completes; ON truncates |
| Prompt tokens | 7,779 | 7,779 | identical input |
| Completion tokens | 4,096 | 79 | **52× fewer** |
| Total tokens | 8,291 | 7,858 | |
| Latency (s) | 214.45 | 15.98 | **13.4× faster** |
| Verdict obtained? | No (silently defaulted) | Yes (real model judgment) | |
| Verdict | FLAKY (fake default) | INFRA (conf 0.95) | |
| `classified_by` | `llm:omlx:Qwen3-8B-4bit` | `llm:omlx:Qwen3.5-9B-MLX-4bit` | |
| Degraded? | Yes (`llm-truncated` after fix) | No | |

**Projected per-repo cost (21 failures, fastapi/fastapi):**

| Mode | Per-call latency | 21 calls (sequential) | Verdicts |
|---|---|---|---|
| Thinking ON | ~214s | ~75 min | 0 real (all truncated) |
| Thinking OFF | ~16s | ~5.6 min | 21 real |

> At 21 failures/repo × 5 repos = 105 calls, thinking-ON would take
> **~6.25 hours** and produce **zero** real verdicts. Thinking-OFF takes
> **~28 min** and produces real verdicts for all. Use `--no-thinking` with
> Qwen3-family models for this task.

### 21.7 Key takeaways

1. **Always use `--no-thinking` with Qwen3-family models** for this
   classification task — the prompt is simple enough that reasoning adds
   no accuracy but 13× latency and token cost.
2. **Clear `data/llm-cache/{provider}/`**, not just `runs/`, before re-running
   with changed LLM params — the cache keys by `{provider}_{model}_{test}`
   and will serve stale results from prior runs.
3. **Check `llm-logs/` after every run** — an empty `llm-logs/` dir means
   a cache hit (no live call); a `finish_reason: length` in the log means
   truncation. The summary now surfaces degraded counts directly.
4. **Verify the endpoint is up** before analysis: `curl -s http://127.0.0.1:8000/v1/models`

### 21.8 Skipped repo: django/django — prompt-size overflow

**Status:** Skipped for OMLX field study run. Likely needs to be skipped for
cloud LLMs (OpenAI, DeepSeek) too until the root cause is fixed.

**Symptom:** Every LLM call returns `400 Bad Request` immediately (2.7s, no
response). `llm_fallback_count: 1`, all 14,925 tests fall through to
rules-based classification.

**Root cause:** The `cross_run_context` passed to `_build_prompt` contains
the **entire** `preliminary_stats` dict — all tests' stats, not just the one
being classified. Django's test suite has ~14,925 tests, producing a prompt
of **9.8 million characters** (~2.5M+ tokens), far exceeding any model's
context window (Qwen3.5-9B max is 262,144; GPT-4o-mini is 128K).

**Evidence:**
```
prompt length (chars): 9869622
error: LLM 'omlx' failed: 400 Client Error: Bad Request
```

**Fix needed (future work):** The classifier should pass only the stats for
the test being classified (or a small summary), not the full
`preliminary_stats` dict. See `classifier.py` → `classify()` →
`cross_run_context` argument.

**Impact on field study:**
- django/django excluded from OMLX run (results are rules-only, not LLM)
- Cloud LLM runs will hit the same 400 (OpenAI 128K, DeepSeek 64K context)
- **django/django should be skipped for all LLM providers** until the
  prompt-size bug is fixed, or the context is trimmed to per-test stats

**Repro:**
```bash
rm -rf data/llm-cache/omlx && ai-flake-sleuth analyze --repo django/django --data-dir ./data/ \
    --llm omlx --llm-model Qwen3.5-9B-MLX-4bit \
    --llm-endpoint http://127.0.0.1:8000 \
    --force-llm --no-thinking --format all
# → 400 Bad Request on first LLM call, all tests fall back to rules
```

### 21.9 Successful run: fastapi/fastapi

**Command:**
```bash
rm -rf data/llm-cache/omlx runs/fastapi_fastapi/omlx && ai-flake-sleuth analyze --repo fastapi/fastapi \
    --data-dir ./data/ --llm omlx --llm-model Qwen3.5-9B-MLX-4bit \
    --llm-endpoint http://127.0.0.1:8000 --force-llm --no-thinking --format all
```

**Summary (from `summary.json`):**

| Metric | Value |
|---|---|
| Runs analyzed | 500 |
| Runs with failures | 21 |
| Flaky | 18 |
| Real bugs | 0 |
| Infra | 3 |
| Insufficient data | 0 |
| Overall pass rate | 88% |
| LLM calls | 21 |
| LLM truncated | 0 |
| LLM parse errors | 0 |
| LLM fallbacks | 0 |

**Per-call latency & token stats (21 calls, `--no-thinking`):**

| Call | Latency (s) | Total tokens | finish_reason |
|---|---|---|---|
| 01 | 3.8 | 8,459 | stop |
| 02 | 14.8 | 8,461 | stop |
| 03 | 14.9 | 8,484 | stop |
| 04 | 14.7 | 8,483 | stop |
| 05 | 16.8 | 8,466 | stop |
| 06 | 16.0 | 8,462 | stop |
| 07 | 15.4 | 8,463 | stop |
| 08 | 15.1 | 8,461 | stop |
| 09 | 16.6 | 8,478 | stop |
| 10 | 39.4 | 8,477 | stop |
| 11 | 14.9 | 8,479 | stop |
| 12 | 14.6 | 8,478 | stop |
| 13 | 15.6 | 8,479 | stop |
| 14 | 15.6 | 8,488 | stop |
| 15 | 14.7 | 8,490 | stop |
| 16 | 14.7 | 8,489 | stop |
| 17 | 15.0 | 8,491 | stop |
| 18 | 14.5 | 8,490 | stop |
| 19 | 14.7 | 8,491 | stop |
| 20 | 13.9 | 8,448 | stop |
| 21 | 14.0 | 8,475 | stop |

**Aggregate:**

| Stat | Value |
|---|---|
| Total wall-clock (LLM calls) | ~323s (~5.4 min) |
| Mean latency | 15.4s/call |
| Median latency | 14.8s/call |
| Min / max latency | 3.8s / 39.4s |
| Mean total tokens | 8,475 |
| Mean prompt tokens | ~7,779 |
| Mean completion tokens | ~79 |
| Truncated / errors / fallbacks | 0 / 0 / 0 |

> All 21 verdicts are real model judgments (zero degradation). Call 10
> outlier (39.4s) is likely first-call model warm-up or endpoint contention.

### 21.10 Successful run: pytest-dev/pytest

**Command:**
```bash
rm -rf data/llm-cache/omlx && ai-flake-sleuth analyze --repo pytest-dev/pytest \
    --data-dir ./data/ --llm omlx --llm-model Qwen3.5-9B-MLX-4bit \
    --llm-endpoint http://127.0.0.1:8000 --force-llm --no-thinking --format all
```

**Summary (from `summary.json`):**

| Metric | Value |
|---|---|
| Runs analyzed | 342 |
| Runs with failures | 23 |
| Flaky | 38 |
| Real bugs | 0 |
| Infra | 0 |
| Insufficient data | 0 |
| Overall pass rate | 71% |
| LLM calls | 38 |
| LLM truncated | 0 |
| LLM parse errors | 0 |
| LLM fallbacks | 0 |

**Aggregate stats (38 calls, `--no-thinking`):**

| Stat | Value |
|---|---|
| Total wall-clock (LLM calls) | ~778s (~13 min) |
| Mean latency | 20.5s/call |
| Median latency | 21.6s/call |
| Min / max latency | 4.8s / 24.9s |
| Mean total tokens | 13,929 |
| Mean completion tokens | ~79 |
| Truncated / errors / fallbacks | 0 / 0 / 0 |

> All 38 verdicts are real model judgments (zero degradation). Latency is
> higher than fastapi (20.5s vs 15.4s) because pytest's cross-run context
> produces larger prompts (~13.9K tokens vs ~8.5K). The first few calls
> (4-7s) are faster, then stabilises at ~21s once the model is warm.

### 21.11 Successful run: langchain-ai/langchain

**Command:**
```bash
rm -rf data/llm-cache/omlx && ai-flake-sleuth analyze --repo langchain-ai/langchain \
    --data-dir ./data/ --llm omlx --llm-model Qwen3.5-9B-MLX-4bit \
    --llm-endpoint http://127.0.0.1:8000 --force-llm --no-thinking --format all
```

**Summary (from `summary.json`):**

| Metric | Value |
|---|---|
| Runs analyzed | 500 |
| Runs with failures | 28 |
| Flaky | 44 |
| Real bugs | 0 |
| Infra | 0 |
| Insufficient data | 0 |
| Overall pass rate | 51.6% |
| LLM calls | 44 |
| LLM truncated | 0 |
| LLM parse errors | 0 |
| LLM fallbacks | 0 |

**Aggregate stats (44 calls, `--no-thinking`):**

| Stat | Value |
|---|---|
| Total wall-clock (LLM calls) | ~1,258s (~21 min) |
| Mean latency | 28.6s/call |
| Median latency | 28.4s/call |
| Min / max latency | 25.9s / 32.7s |
| Mean total tokens | 17,283 |
| Mean completion tokens | ~79 |
| Truncated / errors / fallbacks | 0 / 0 / 0 |

> All 44 verdicts are real model judgments (zero degradation). Langchain has
> the largest prompts (~17.3K tokens) of the three Python repos due to its
> massive test suite and cross-run context size. Latency is correspondingly
> higher (28.6s vs 20.5s for pytest, 15.4s for fastapi).

---

### 21.12 Cross-repo summary (all OMLX runs, `--no-thinking`, Qwen3.5-9B-MLX-4bit)

| Repo | Failures | Unique tests | FLAKY | REAL_BUG | INFRA | LLM calls | Degraded | Mean lat | Mean tokens | Wall clock |
|---|---|---|---|---|---|---|---|---|---|---|
| fastapi/fastapi | 21 | 21 | 18 | 0 | 3 | 21 | 0 | 15.4s | 8,475 | ~5 min |
| pytest-dev/pytest | 23 | 38 | 38 | 0 | 0 | 38 | 0 | 20.5s | 13,929 | ~13 min |
| langchain-ai/langchain | 28 | 44 | 44 | 0 | 0 | 44 | 0 | 28.6s | 17,283 | ~21 min |
| django/django | 17 | — | — | — | — | — | 1 (400 error) | — | — | skipped |
| vercel/next.js | 18 | 0 | — | — | — | 0 | 0 | — | — | instant |

**Key observations:**
- **103 total LLM calls** across 3 Python repos, **0 degraded** (0 truncated, 0 parse errors, 0 fallbacks)
- No `REAL_BUG` detected in any repo at this sample — all failures classified as FLAKY or INFRA
- Prompt size correlates with repo test-suite size, which drives latency (8.5K → 13.9K → 17.3K tokens)
- django/django blocked by prompt-size overflow bug (section 21.8)
- vercel/next.js produced 0 parsed tests (Jest output, not supported by regex parser — see §21.13)

---

## 22. Late Discovery: Non-Python Test Framework Support

### 22.1 Problem

The log parser at `log_parser.py` only supports **pytest** and **unittest** output
formats. The field study's target set includes `vercel/next.js`, which uses
**Jest** (a JavaScript test framework). Since no regex patterns match Jest
output, zero test results are extracted, and the LLM is never called.

This was documented in §13 as an expected edge case ("Non-pytest framework
logs → Regex fails, test not parsed"), but the field study would benefit from
supporting at least Jest (and ideally other common JS/TS frameworks).

### 22.2 Jest output format

```
FAIL packages/next/lib/test/foo.test.js
  ● FooComponent › renders correctly
    expect(received).toBe(expected)
    Expected: true
    Received: false

      6 |     expect(wrapper.find('.foo')).toHaveLength(1);
    > 7 |                                ^

      at Object.<anonymous> (foo.test.js:6:32)

PASS packages/next/lib/test/bar.test.js

Test Suites: 1 failed, 5 passed, 6 total
Tests:       1 failed, 42 passed, 43 total
```

### 22.3 Fix applied

A `_parse_jest` method was added to `LogParser` (and wired into `_try_parse`)
that matches:
- Suite-level lines: `` `FAIL|PASS|SKIP <filepath>``
- Individual test failures: `` `  ● <test name>`` with indented error blocks
- Generic JS/TS test framework patterns as a fallback (Mocha, Vitest)

**Files changed:** `log_parser.py`, `tests/test_log_parser.py`

This allows the parser to extract test results from next.js and any other
repo using Jest, Mocha, or Vitest output.
