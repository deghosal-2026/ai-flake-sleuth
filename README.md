# ai-flake-sleuth

[![MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![PyPI](https://img.shields.io/pypi/v/ai-flake-sleuth)](https://pypi.org/project/ai-flake-sleuth/)
[![CI](https://github.com/deghosal-2026/ai-flake-sleuth/actions/workflows/ci.yml/badge.svg)](https://github.com/deghosal-2026/ai-flake-sleuth/actions)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/13797/badge)](https://www.bestpractices.dev/projects/13797)

**LangGraph agent that diagnoses flaky CI tests across 12 test frameworks and 5 languages.** Fetches GitHub Actions run history, parses test output from CI logs, classifies failures (real bug vs. flaky vs. infra) using rules + LLM, and produces a CI health report.

> Flaky tests destroy CI trust. When the pipeline is red 30% of the time for random reasons, engineers ignore ALL failures — including real bugs. This agent tells you which tests you can't trust.

---

## Why This Exists

Flaky tests are not a "nice to fix" problem. They are a systemic drain on engineering productivity, CI compute budgets, and — most critically — the trust that makes CI worth running at all.

| Data Point | Source |
|-----------|--------|
| 51% of developers experience flaky tests weekly | Gruber & Fraser, ICST 2022 |
| 73% of developers lose trust in test results once flakiness appears | Eck et al., FSE 2019 |
| 3.2% of builds are rerun; 67.7% of reruns are flaky | Ge & Zhang, 2025 |
| Google: 14% of large tests are flaky across 4.2M+ tests | Trunk, 2024 |
| Rerun builds accumulated ~339 years of waiting time | Ge & Zhang, 2025 |

**The bottom line:** Trust erosion is worse than the measurable time waste. Before you can quarantine a flaky test, you need to know it's flaky. That's what this tool does.

---

## Features

- **15 log parsers** supporting **12 test frameworks** across **5 languages**
- **Two-phase design**: download once (network), analyze offline (no network needed)
- **LLM classification** for ambiguous failures — supports local (OMLX) and cloud (OpenCode Zen, OpenAI, DeepSeek) models
- **Cross-run correlation**: per-test flake rates, error signature distribution, dominant error analysis
- **Resumable downloads** with manifest tracking, parallel log fetching, and rate-limit aware backoff
- **Three output formats**: CLI table (rich), JSON (agentic-ready), markdown (human-readable)
- **LLM response caching** per-repo for fast re-runs
- **Degraded call tracking** — distinguishes real verdicts from fallbacks

---

## Supported Test Frameworks

| Framework | Language | Parser |
|-----------|----------|--------|
| pytest | Python | ✅ Short + verbose modes |
| unittest | Python | ✅ Dot + Django permissive |
| Jest | JavaScript | ✅ Suite-level + individual failures |
| Vitest | JavaScript | ✅ ✓/✗ ANSI output |
| Turbopack | JavaScript | ✅ Suite-name prefix format |
| Go test | Go | ✅ `--- PASS/FAIL` format |
| RSpec | Ruby | ✅ Summary + individual failures |
| Minitest | Ruby | ✅ Summary line |
| Mocha | JavaScript | ✅ ✓/✗ individual tests |
| PHPUnit/Pest | PHP | ✅ PASS/FAIL format |
| JUnit | Java | ✅ Gradle/Maven output |
| Cypress | JavaScript | ✅ ✓/✗ with timing |
| Generic JS | JavaScript | ✅ Fallback for `__tests__/`, `.spec.`, `.e2e.` |

---

## Quick Start

### Install

```bash
# From PyPI (recommended)
pip install ai-flake-sleuth

# From source (for development)
git clone https://github.com/deghosal-2026/ai-flake-sleuth.git
cd ai-flake-sleuth
pip install -e ".[dev]"
```

### Set up

```bash
# GitHub token (required for downloads)
export GITHUB_TOKEN="your_token"

# Optional: cloud LLM for classification
export OPENCODE_API_KEY="your-opencode-key"   # for GPT-5 Nano, DeepSeek, GLM
```

### Download CI data (Phase 1 — network required)

```bash
# Download 500 runs with all logs (including successful runs)
ai-flake-sleuth download --repo fastapi/fastapi --runs 500 --data-dir ./data/ --all-runs
```

### Analyze (Phase 2 — offline, no network needed)

```bash
# Local LLM (free, Apple Silicon MLX)
ai-flake-sleuth analyze --repo fastapi/fastapi --data-dir ./data/ \
    --llm omlx --llm-model Qwen3.5-9B-MLX-4bit \
    --llm-endpoint http://127.0.0.1:8000 \
    --force-llm --no-thinking --format all

# Cloud LLM (GPT-5 Nano via OpenCode Zen, ~$0.0007/call)
ai-flake-sleuth analyze --repo fastapi/fastapi --data-dir ./data/ \
    --llm opencode --llm-model gpt-5-nano \
    --force-llm --no-thinking --format all

# Rules-only baseline (no LLM)
ai-flake-sleuth analyze --repo fastapi/fastapi --data-dir ./data/ \
    --no-llm --format all
```

### Legacy mode (download + analyze in one command)

```bash
ai-flake-sleuth --repo fastapi/fastapi --runs 100 --format all --output ./reports/
```

---

## CLI Reference

### `download` — Fetch CI data from GitHub

```
ai-flake-sleuth download --repo owner/repo [options]

Options:
  --repo          Target repository (owner/repo)
  --runs N        Number of runs to fetch (default: 100)
  --data-dir DIR  Data directory (default: ./data/)
  --all-runs      Download logs for successful runs too (catches flaky tests that retried+passed)
  --workflow NAME Filter to a specific workflow
  --offset N      Start from run N (for batch analysis)
  --force         Re-download even if data exists
  --github-token  GitHub token (default: $GITHUB_TOKEN env)
```

### `analyze` — Classify failures from downloaded data

```
ai-flake-sleuth analyze --repo owner/repo [options]

Options:
  --repo            Target repository (owner/repo)
  --data-dir DIR    Directory containing downloaded data
  --llm PROVIDER    LLM provider: omlx | openai | deepseek | opencode (default: omlx)
  --llm-model NAME  Model name (default: provider-specific)
  --llm-endpoint URL  LLM API endpoint (default: provider-specific)
  --no-llm          Disable LLM (rules-only classification)
  --force-llm       Classify ALL failures via LLM (skip rules)
  --no-thinking     Disable reasoning mode (Qwen3 models)
  --llm-max-tokens  Max completion tokens (default: 4096)
  --limit N         Max LLM calls (0 = no limit)
  --format          table | json | markdown | all (default: table)
  --output DIR      Output directory (default: ./runs/{repo}/{llm}/batch-{offset}-{end}/)
  --offset N        Start analyzing from run N
  --batch-size N    Analyze N runs from offset
```

### `preflight` — Validate environment

```bash
ai-flake-sleuth preflight --repos pytest-dev/pytest --llm-providers omlx openai
```

### `verify` — Validate downloaded data

```bash
ai-flake-sleuth verify --repo pytest-dev/pytest --data-dir ./data/
```

---

## How It Works

```
ai-flake-sleuth download --repo owner/repo --runs 500 --all-runs

  Fetch run metadata from GitHub API (paginated, rate-limit aware)
      ↓
  For each run: fetch job metadata + download log ZIP
      ↓
  Save to disk: data/{repo}/runs/{run_id}.json + logs/{run_id}.zip
      ↓
  Write manifest.json tracking progress (resumable)

ai-flake-sleuth analyze --repo owner/repo --data-dir ./data/ --llm omlx --force-llm

  Load runs + logs from disk (no network needed)
      ↓
  Parse log content with 15 regex parsers (12 frameworks)
      ↓
  Preliminary correlation: per-test stats across runs
      ↓
  Classify each failure: rules → LLM for ambiguous cases
      ↓
  Correlate: per-test flake rate, error signatures, final category
      ↓
  Generate report: table + JSON + markdown + summary.json
```

### Classification

| Category | Meaning | Detection |
|----------|---------|-----------|
| **REAL_BUG** | Reproducible — same error every time | Dominant error signature (90%+), failure rate > 50% |
| **FLAKY** | Intermittent — multiple distinct errors | Multiple error signatures, failure rate < 50% |
| **INFRA** | Environment failure — timeout, OOM, network | Infra pattern regex (timeout, OOM, network, 502/503/504) |
| **INSUFFICIENT_DATA** | Fewer than 50 executions | Cannot classify reliably |

### LLM Classification Quality

Each LLM call produces one of 4 distinct `classified_by` prefixes for auditability:

| Prefix | Meaning |
|--------|---------|
| `llm:provider:model` | Real model verdict (JSON parsed successfully) |
| `llm-truncated:provider:model` | Response cut off (`finish_reason=length`) |
| `llm-parse-error:provider:model` | Response arrived but couldn't parse as JSON |
| `llm-fallback:provider:model` | Call failed (network, auth, timeout) |

---

## Output

Reports are written to `runs/{repo}/{provider}/batch-{offset}-{end}/`:

```
runs/fastapi_fastapi/omlx/batch-0000-all/
├── report.txt          ← CLI table format
├── report.json         ← Full JSON report
├── report.md           ← Markdown format
├── summary.json        ← Batch metadata (counts, rates, runtime)
└── llm-logs/           ← Structured LLM call logs (prompt + response + tokens + latency)
    ├── omlx_0001.json
    └── ...
```

---

## LLM Providers

| Provider | Endpoint | Models | Cost |
|----------|----------|--------|------|
| **OMLX** (local) | `http://127.0.0.1:8000` | Qwen3.5-9B-MLX-4bit, Qwen3-8B-4bit | Free |
| **OpenCode Zen** (cloud) | `https://opencode.ai/zen` | gpt-5-nano, deepseek-v4-flash, glm-5.2 | ~$0.0007/call (gpt-5-nano) |
| **OpenAI** (cloud) | `https://api.openai.com` | gpt-4o-mini | ~$0.00016/call |
| **DeepSeek** (cloud) | `https://api.deepseek.com` | deepseek-chat | ~$0.00001/call |

> **Tip:** Use `--no-thinking` with Qwen3-family models for 13× speedup. Reasoning mode produces no accuracy benefit for this classification task.

---

## Field Study Results

Tested across 21 repos, 12 frameworks, 5 languages. Full results in [`docs/field-study-results.md`](docs/field-study-results.md).

| Metric | Value |
|--------|-------|
| Repos analyzed | 21 |
| Frameworks covered | 12 |
| Parsers built | 15 |
| Tests classified | ~1,151 |
| LLM calls (OMLX) | ~382 |
| LLM calls (GPT-5 Nano) | ~303 |
| Total cloud cost | $0.22 |
| REAL_BUGs found (GPT) | 56 |

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Agent framework | LangGraph (StateGraph with conditional edges) |
| LLM integration | OpenAI-compatible API (requests) |
| Data source | GitHub Actions REST API (PyGithub) |
| Report rendering | rich (CLI tables) |
| Test coverage | 81.95% (280 tests) |

---

## Development

```bash
# Run tests
pytest -q

# Lint
ruff check src/ tests/

# Type check
mypy src/

# Coverage
pytest --cov=flake_sleuth --cov-report=term-missing
```

---

## Roadmap

### v1 — Diagnostic Layer (current) ✅

- [x] PRD, SPEC, WBS
- [x] M1: Scaffold + GitHub client
- [x] M2: Log parser + error signature (15 parsers, 12 frameworks)
- [x] M3: Classifier (rules + LLM)
- [x] M4: Correlator + graph + report
- [x] M5: Field study (21 repos, OMLX vs GPT-5 Nano)
- [ ] M6: Hashnode article + dev.to cross-post

### v2 — Action Layer (planned)

- [ ] Error signature embedder — Qdrant semantic clustering
- [ ] LangGraph cyclic graph — interrupt() per flaky test, human-in-the-loop
- [ ] Quarantine manager — PR generator + review-date tracker
- [ ] Dashboard — flake rate trends, quarantine metrics

---

## Documentation

- [PRD](docs/PRD.md) — Problem definition, scope, success criteria
- [SPEC](docs/SPEC.md) — Technical architecture, schemas, interfaces
- [WBS](docs/WBS.md) — Work breakdown structure
- [Field Study Plan](docs/field-study-plan.md) — Study methodology
- [Field Study Results](docs/field-study-results.md) — Full results, comparison, learnings

---

## License

MIT
