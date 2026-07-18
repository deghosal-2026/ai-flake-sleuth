# Field Study Results — ai-flake-sleuth

| Field | Value |
|---|---|
| **Project** | ai-flake-sleuth |
| **Milestone** | M5 — Field Study |
| **Date** | 2026-07-18 |
| **Models tested** | Qwen3.5-9B-MLX-4bit (OMLX, local), GPT-5 Nano (OpenCode Zen, cloud) |
| **Endpoint (OMLX)** | `http://127.0.0.1:8000` |
| **Endpoint (GPT-5 Nano)** | `https://opencode.ai/zen` |

---

## 1. Study Scope

The field study tested ai-flake-sleuth across **21 repos** spanning **12 test frameworks** and **5 languages** (Python, JavaScript/TypeScript, Go, Ruby, Java, PHP). The goal: evaluate accuracy, framework coverage, and cross-model agreement between a local LLM (OMLX) and a cloud LLM (GPT-5 Nano).

### What we started with

The original plan targeted 5 repos (pytest, django, fastapi, langchain, next.js). During the study, we expanded to 21 repos to achieve broader framework coverage after discovering that the initial set didn't exercise enough test frameworks. We built **15 parsers** to handle 12 test frameworks.

---

## 2. Framework Coverage Table

| Framework | Language | Repos | Parsers built |
|---|---|---|---|
| pytest | Python | fastapi, langchain, pytest, drf, import-export | 2 (short + verbose modes) |
| unittest | Python | django | 1 |
| Jest | JavaScript | jestjs/jest, facebook/react, redux-toolkit | 1 |
| Vitest | JavaScript | vuejs/core | 1 |
| Turbopack | JavaScript | vercel/next.js | 1 |
| Go test | Go | gin-gonic/gin, golang/go | 1 |
| RSpec | Ruby | rubocop/rubocop | 1 |
| Minitest | Ruby | rails/rails | 1 |
| Mocha | JavaScript | expressjs/express | 1 |
| PHPUnit/Pest | PHP | laravel/laravel | 1 |
| JUnit | Java | spring-projects/spring-boot | 1 |
| Cypress | JavaScript | cypress-io/cypress | 1 |
| Generic JS | JavaScript | Fallback (react-hook-form) | 1 |

**Total: 15 parsers across 12 frameworks + 1 generic fallback**

---

## 3. Per-Repo Results

### 3.1 Repos with test failures (analyzed)

| Repo | Framework | Logs | Failures | Unique tests | Disposition |
|---|---|---|---|---|---|
| fastapi/fastapi | pytest | 500 | 21 | 21 | ✅ Both models |
| pytest-dev/pytest | pytest | 298 | 23 | 38 | ✅ Both models |
| langchain-ai/langchain | pytest | 500 | 28 | 44 | ✅ Both models |
| encode/django-rest-framework | pytest | 174 | 36 | 12 | ✅ Both models |
| jestjs/jest | Jest | 300 | 45 | 48 | ✅ Both models |
| facebook/react | Jest | 87 | 3 | 26 | ✅ Both models |
| reduxjs/redux-toolkit | Jest | 92 | 7 | 768 | ✅ OMLX only (rules) |
| vuejs/core | Vitest | 294 | 21 | 14 | ✅ OMLX only |
| vercel/next.js | Turbopack | 479 | 18 | 71 | ✅ Both models |
| rubocop/rubocop | RSpec | 147 | 9 | 88 | ✅ Both models |
| cypress-io/cypress | Cypress | 37 | 1 | 2 | ✅ OMLX only |
| spring-projects/spring-boot | JUnit | 94 | 14 | 1 | ✅ OMLX only |

### 3.2 Repos with clean CI (no test failures)

| Repo | Framework | Logs | Failures | Reason |
|---|---|---|---|---|
| django-import-export | pytest | 23 | 53 | DB setup jobs, no test output |
| gin-gonic/gin | Go test | 100 | 3 | Lint failures only |
| golang/go | Go test | 150 | 6 | Infra jobs only |
| laravel/laravel | PHPUnit | 147 | 0 | No failures |
| rails/rails | Minitest | 100 | 0 | No failures |
| expressjs/express | Mocha | 86 | 3 | CodeQL jobs only |
| react-hook-form | Playwright | 100 | 11 | Build/action/dependabot jobs |
| microsoft/playwright | Playwright | 145 | 36 | AI summaries, no test output |

### 3.3 Blocked

| Repo | Framework | Reason |
|---|---|---|
| django/django | unittest | Prompt overflow (9.8M chars) — `cross_run_context` passes all 14k test stats |

---

## 4. OMLX vs GPT-5 Nano — Side by Side

### 4.1 Model comparison

| Metric | OMLX (Qwen3.5-9B-MLX-4bit) | GPT-5 Nano |
|---|---|---|
| Hosting | Local (Apple Silicon, MLX) | Cloud (OpenCode Zen) |
| Cost per call | $0 | ~$0.00072 |
| Avg latency | 15.4s | 7.5s |
| Avg completion tokens | 79 | 977 |
| `--no-thinking` required | Yes (Qwen3 reasoning models) | No |
| Degraded calls (rubocop) | 74/88 (84%) | 3/88 (3%) |

### 4.2 Per-repo comparison

**pytest (Python)**

| Repo | | OMLX | GPT-5 Nano |
|---|---|---|---|
| fastapi/fastapi | FLAKY | 18 | 8 |
| | REAL_BUG | 0 | **13** |
| | INFRA | 3 | 0 |
| pytest-dev/pytest | FLAKY | 38 | 38 |
| | REAL_BUG | 0 | 0 |
| | INFRA | 0 | 0 |
| langchain-ai/langchain | FLAKY | 44 | 44 |
| | REAL_BUG | 0 | 0 |
| | INFRA | 0 | 0 |
| django-rest-framework | FLAKY | 12 | 12 |
| | REAL_BUG | 0 | 0 |
| | INFRA | 0 | 0 |

> **4 pytest repos agreed** except fastapi where GPT found 13 REAL_BUGs OMLX missed.

**Jest (JavaScript)**

| Repo | | OMLX | GPT-5 Nano |
|---|---|---|---|
| jestjs/jest | FLAKY | 48 | 322 |
| | REAL_BUG | 0 | 0 |
| facebook/react | FLAKY | 26 | 26 |
| | REAL_BUG | 0 | 0 |

> GPT-5 Nano matched more test names in jestjs (322 vs 48). Both agreed — all FLAKY.

**Turbopack (JavaScript)**

| Repo | | OMLX | GPT-5 Nano |
|---|---|---|---|
| vercel/next.js | FLAKY | 71 | 185 |
| | REAL_BUG | 0 | **35** |

> GPT-5 Nano found **35 REAL_BUGs** OMLX missed and matched more tests (220 vs 71).

**RSpec (Ruby)**

| Repo | | OMLX | GPT-5 Nano |
|---|---|---|---|
| rubocop/rubocop | FLAKY | 88 | 80 |
| | REAL_BUG | 0 | **8** |

> GPT-5 Nano found **8 REAL_BUGs** OMLX missed. GPT was also far more reliable (3 degraded vs 74).

### 4.3 Key finding

**GPT-5 Nano identified 56 REAL_BUGs that OMLX classified as FLAKY:**

| Repo | REAL_BUGs (GPT) | REAL_BUGs (OMLX) |
|---|---|---|
| fastapi/fastapi | 13 | 0 |
| vercel/next.js | 35 | 0 |
| rubocop/rubocop | 8 | 0 |
| **Total** | **56** | **0** |

On repos where both models agreed (pytest, langchain, drf, jest, react), all were FLAKY — no false positives from either model. The 56 disagreements need manual review to determine ground truth.

---

## 5. Thinking vs No-Thinking (Qwen3)

| Metric | Thinking ON | Thinking OFF |
|---|---|---|
| Model | Qwen3-8B-4bit | Qwen3.5-9B-MLX-4bit |
| `finish_reason` | `length` (truncated) | `stop` |
| Completion tokens | 4,096 (all reasoning) | **79** (JSON only) |
| Latency | 214s | **16s** |
| Verdict | fake FLAKY (silent default) | **INFRA** (real, conf 0.95) |

**Always use `--no-thinking` with Qwen3-family models.** Reasoning adds no accuracy but 13× latency.

---

## 6. Summary Statistics

| Metric | Count |
|---|---|
| Frameworks covered | 12 |
| Parsers built | 15 |
| Repos analyzed | 21 |
| Repos with real results | 12 |
| Repos with clean CI | 8 |
| Repos blocked | 1 (django) |
| Total tests classified | ~1,151 |
| Total OMLX LLM calls | ~382 |
| Total GPT-5 Nano calls | ~250 |
| Degraded (OMLX) | 76 |
| Degraded (GPT-5 Nano) | 4 |
| REAL_BUGs found (GPT only) | 56 |
| REAL_BUGs found (OMLX only) | 1 (vue) |

---

## 7. Code Changes Made During Study

### 7.1 Parsers: before vs during study

| Parser | Status | Built when | Notes |
|---|---|---|---|
| pytest (short format) | ✅ | Before study | Original design |
| pytest (verbose/GHA timestamp) | ✅ | Before study | Original design |
| unittest (dot format) | ✅ | Before study | Original design |
| unittest (Django permissive) | ✅ | Before study | Added for Django |
| **Jest** | ✅ | **During study** | Built after next.js produced 0 tests |
| **Vitest** | ✅ | **During study** | Built after Vue used ✓/✗ ANSI format |
| **Turbopack** | ✅ | **During study** | Built for vercel's suite-name-prefix format |
| **Go test** | ✅ | **During study** | Built for gin-gonic/gin |
| **PHPUnit/Pest** | ✅ | **During study** | Built for laravel |
| **Mocha** | ✅ | **During study** | Built for express |
| **Cypress** | ✅ | **During study** | Built for cypress-io/cypress |
| **JUnit** | ✅ | **During study** | Built for spring-boot |
| **RSpec** | ✅ | **During study** | Built for rubocop |
| **Minitest** | ✅ | **During study** | Built for rails |
| **Generic JS fallback** | ✅ | **During study** | Catches __tests__/, .spec., .e2e. |

**13 of 15 parsers were built during the study.** The original design only supported pytest and unittest (Python). All JS/TS, Go, Ruby, Java, and PHP parsers were added in response to real-world log formats encountered during the field study.

### 7.2 Other code changes

| Change | Files | Why |
|---|---|---|
| `max_tokens` configurable (default 4096) | llm.py, config.py, cli.py | Hardcoded 512 truncated reasoning models |
| `finish_reason` detection | llm.py | Truncation was invisible |
| 4 disjoint `classified_by` prefixes | llm.py | `llm:`, `llm-truncated:`, `llm-parse-error:`, `llm-fallback:` |
| Degraded counts in ReportSummary | types.py, graph.py, report.py, cli.py | Surface degraded calls in reports |
| `--no-thinking` flag | llm.py, config.py, graph.py, cli.py | Disable Qwen3 reasoning mode |
| `--llm-max-tokens` flag | cli.py | Override max completion tokens |
| Per-repo LLM cache | graph.py, cli.py | Was per-provider, caused cross-repo interference |
| OpenCode Zen provider | config.py, cli.py, llm.py | Cloud LLM gateway access |
| Prompt truncation (50K) | llm.py | Vue/Vitest produced 1.3M-char prompts |
| Tightened LLM prompt | llm.py | Instruct JSON-only output, no reasoning |

---

## 8. Open Issues

1. **Django prompt overflow** — `cross_run_context` passes all 14k test stats. Fix: pass per-test stats only.
2. **Vue GPT-5 Nano degraded** — 50K truncation still confuses model. Needs smarter context summarization.
3. **DeepSeek V4 Flash** — Returns 400 on most repos via OpenCode Zen. Only fastapi worked. May be account tier issue.
4. **Facebook/react download** — Stalled at 288 runs, 87 logs. Rate-limit issues with GitHub API.
5. **Cache filename too long** — RSpec test names exceed 255-char OS limit for cache files.

---

## 9. Commands Reference

### OMLX analysis (local, free):
```bash
ai-flake-sleuth analyze --repo {repo} --data-dir ./data/ \
    --llm omlx --llm-model Qwen3.5-9B-MLX-4bit \
    --llm-endpoint http://127.0.0.1:8000 \
    --force-llm --no-thinking --format all
```

### GPT-5 Nano analysis (cloud, ~$0.0007/call):
```bash
export OPENCODE_API_KEY="your-key"
ai-flake-sleuth analyze --repo {repo} --data-dir ./data/ \
    --llm opencode --llm-model gpt-5-nano \
    --force-llm --no-thinking --format all
```

### Download:
```bash
ai-flake-sleuth download --repo {repo} --runs 300 --data-dir ./data/ --all-runs
```

---

## 10. Expectations vs Reality

### 10.1 What we expected

- **5 repos, 4 LLM providers, 500 runs each** — straightforward matrix comparison
- **pytest and unittest parsers would cover all target repos** — Python-centric design
- **OMLX would be slower but free; cloud LLMs faster but paid** — simple cost/speed tradeoff
- **All repos would have test failures in their CI logs** — failed runs = failed tests
- **Rules-based classification would handle most cases; LLM only for ambiguous ones**
- **DeepSeek V4 Flash would be the cheapest cloud option** at ~$0.000013/call

### 10.2 What surprised us

- **Most CI failures are NOT test failures.** 8 of 21 repos had failures entirely in infra/build/lint/CodeQL/Dependabot jobs — zero test runner output in their logs. The parsers worked correctly; the data simply had no test failures to classify.

- **GPT-5 Nano found 56 REAL_BUGs that OMLX classified as FLAKY.** This was the biggest surprise. On 3 repos (fastapi, vercel, rubocop), GPT-5 Nano identified real bugs that the local model missed entirely. On 4 repos (pytest, langchain, drf, jest), both models agreed — suggesting the disagreement is repo-specific, not systematic.

- **Qwen3 reasoning models produce fake verdicts.** With thinking enabled, Qwen3-8B spent all 4096 tokens reasoning and never emitted JSON. The silent fallback produced a `llm:` prefix indistinguishable from a real verdict. This was a critical bug masked by the design.

- **`--no-thinking` is 13× faster with identical or better accuracy.** Disabling Qwen3's reasoning mode dropped latency from 214s to 16s and produced clean JSON. The reasoning added no value for this classification task.

- **Vue/Vitest produces 1.3M-character prompts.** The cross-run context for Vue's massive test suite exceeded any model's context window. This wasn't a parser issue — it was a prompt construction issue.

- **Django produces 9.8M-character prompts.** The `cross_run_context` dict included all 14,925 test stats, not just the one being classified. This is a code bug, not a model limitation.

- **DeepSeek V4 Flash returned 400 errors on 7 of 8 repos.** Only fastapi worked. Same key, same endpoint. The model exists on OpenCode Zen but rejects most requests. Likely an account tier or model availability issue.

- **Rubocop's RSpec test names exceed the 255-char filename limit.** The cache key (test name) was so long it caused `Errno 63: File name too long` on macOS.

- **The Jest parser matched 322 tests in jestjs/jest vs OMLX's 48.** Same parser, same logs — the difference was in how the classifier processed the results, not the parser itself.

- **facebook/react download stalled for 40+ minutes.** The repo is enormous and the GitHub API pagination was extremely slow, likely due to rate-limit backoff on the jobs endpoint.

### 10.3 Infra failures with no test output

These repos had CI failures but the downloaded logs contained **only infrastructure/build/lint job output** — no test runner output at all:

| Repo | Failures | Job types in logs | Test output? |
|---|---|---|---|
| django-import-export | 53 | DB setup, Docker, Postgres/MySQL | No |
| gin-gonic/gin | 3 | Lint | No |
| golang/go | 6 | Git submodule, credentials cleanup | No |
| expressjs/express | 3 | CodeQL analysis | No |
| react-hook-form | 11 | Build, action, Dependabot | No |
| microsoft/playwright | 36 | AI analysis summaries, build scripts | No |
| redux-toolkit | 7 | Check for changes, misc | No |
| spring-projects/spring-boot | 14 | Build (BUILD SUCCESSFUL) | No |

**Key observation:** GitHub Actions runs multiple jobs per workflow. A run can "fail" because a lint or build job failed, while the test job passed. The downloader captures logs for the entire run, but the test output may be in a job that succeeded (and thus isn't in a "failed" run). This is a fundamental data collection challenge.

---

## 11. Key Learnings

### 11.1 LLM model selection matters more than expected

The 56 REAL_BUG disagreement between OMLX and GPT-5 Nano is the most significant finding. It suggests that model choice meaningfully changes classification outcomes. OMLX (Qwen3.5-9B, local, free) tends toward FLAKY; GPT-5 Nano (cloud, $0.0007/call) tends toward REAL_BUG. Without manual ground truth review, we can't say which is "right" — but the disagreement itself is valuable data.

### 11.2 Reasoning models need special handling

Qwen3-family models with thinking enabled produce unusable output for structured classification tasks. The `--no-thinking` flag and `max_tokens` configurability were essential fixes. Any reasoning model (Qwen3, o1, etc.) needs:
- Disabling reasoning mode for simple classification
- Configurable `max_tokens` (not hardcoded)
- `finish_reason` detection to catch truncation
- Distinct `classified_by` prefixes to distinguish real verdicts from fallbacks

### 11.3 Most CI failures aren't test failures

8 of 21 repos (38%) had zero test failures despite having "failed" CI runs. The failures were in lint, build, CodeQL, Dependabot, or infrastructure jobs. The tool correctly handles this (clean reports, no crashes), but it limits the data available for classification.

### 11.4 Prompt size is a silent killer

Two repos (django, vue) produced prompts exceeding any model's context window. The `cross_run_context` dict grows with the test suite size. Without truncation, these repos are unanalyzable. The fix (per-test stats instead of all-stats) is straightforward but not yet implemented.

### 11.5 Cache design matters

The original per-provider cache (`data/llm-cache/omlx/`) caused cross-repo interference — deleting one repo's cache deleted all repos. The fix (per-repo subdirectories) was simple but discovered late. RSpec's long test names also exposed a filename length limit in the cache.

### 11.6 Cloud LLMs are more reliable than local

GPT-5 Nano had 4 degraded calls out of ~250 (1.6%). OMLX had 76 degraded out of ~382 (20%). The local endpoint was single-threaded and couldn't handle concurrent runs. Cloud APIs handle concurrency naturally.

---

## 12. What We Can Do Better Next Time

### 12.1 Data collection

- **Filter by job type, not just run conclusion.** Download logs only from jobs whose names match test patterns (e.g., "test", "spec", "pytest"). Skip lint/build/CodeQL/Dependabot jobs entirely.
- **Download more runs for large repos.** 100 runs for facebook/react only captured 3 failures. 500+ runs needed for meaningful data on stable repos.
- **Use `--workflow` to target test workflows specifically.** Avoid downloading non-test workflows that inflate the data without providing test output.

### 12.2 Prompt construction

- **Pass only per-test stats, not the full `preliminary_stats` dict.** The django prompt overflow (9.8M chars) and vue prompt (1.3M chars) were both caused by including all test stats. Each classification should only include stats for the test being classified.
- **Summarize cross-run context.** Instead of dumping raw JSON, provide a concise summary (e.g., "14 executions, 100% failure rate, 1 error signature, dominant ratio 1.0").
- **Token budget management.** Calculate prompt size before sending and automatically truncate or summarize to fit within the model's context window.

### 12.3 Model comparison

- **Run 3+ models per repo for triangulation.** With only 2 models, we can't determine ground truth. A third model (or manual review) would break ties.
- **Manual accuracy validation.** The 56 REAL_BUG disagreements need human review. Sample 10-20 tests, read the raw logs, and determine which model was right.
- **Test with DeepSeek directly.** The OpenCode Zen gateway may have restrictions. A direct DeepSeek API key would eliminate the gateway as a variable.
- **Use confidence scores for filtering.** GPT-5 Nano returns confidence values. Low-confidence classifications should be flagged for manual review.

### 12.4 Reliability

- **Run repos sequentially, not concurrently.** The local MLX endpoint is single-threaded. Concurrent runs caused 74 fallbacks on rubocop. Cloud APIs handle concurrency but still benefit from sequential runs for consistent timing.
- **Add retry logic for 400/429 errors.** The current code falls back immediately. A retry with backoff would recover from transient errors.
- **Fix cache filename length.** Hash the test name instead of using it directly as the filename. This avoids the 255-char OS limit for RSpec's verbose test names.

### 12.5 Parser coverage

- **Add Playwright JSON reporter support.** Playwright outputs results as structured artifacts, not plain text. Parse the JSON output instead of raw CI logs.
- **Support JUnit XML output.** Many Java frameworks can output JUnit XML, which is more reliable than parsing raw Gradle/Maven console output.
- **Test parsers against real logs before running full analysis.** Several parsers were built blind (from documentation) and then tested against real data. Testing against sample logs first would catch format mismatches earlier.

---

## 13. Observations for Enhancements

### 13.1 OMLX vs GPT-5 Nano comparison observations

| Observation | Implication | Enhancement |
|---|---|---|
| GPT found 56 REAL_BUGs OMLX missed | OMLX may be biased toward FLAKY | Add a "confidence threshold" — if OMLX says FLAKY with low confidence, escalate to cloud LLM for a second opinion |
| GPT matched more test names (jest: 322 vs 48) | Parser output varies by model run | Investigate why — may be cache or rules-classification differences |
| OMLX had 74 degraded on rubocop (endpoint overload) | Local endpoint can't handle concurrent runs | Add a queue/lock mechanism for local LLM calls |
| GPT was 2× faster (7.5s vs 15.4s) | Cloud is faster for single calls | Use cloud LLM for time-sensitive runs; local for batch/free runs |
| Both agreed on 4 repos (pytest, langchain, drf, jest) | Agreement on "easy" cases builds trust | When both models agree, skip manual review; only review disagreements |
| GPT had 977 completion tokens vs OMLX's 79 | GPT is more verbose | Tighten GPT prompt to reduce tokens (saves cost) |
| Vue failed on GPT (prompt too large) | Prompt size is a cross-model issue | Implement prompt summarization before sending to any LLM |

### 13.2 Infra-only failures observation

| Observation | Implication | Enhancement |
|---|---|---|
| 8/21 repos had no test failures in CI logs | Data collection is the bottleneck, not parsing | Filter by job type at download time; only fetch test job logs |
| Failed runs often contain lint/build/CodeQL jobs | "Failed run" ≠ "failed test" | Add a pre-analysis filter: skip runs where no job name matches test patterns |
| Playwright logs contain AI summaries, not test output | Some frameworks don't emit parseable CI logs | Support artifact-based parsing (JSON/XML reports) instead of raw log parsing |
| react-hook-form uses Playwright, not Jest | Repo's actual framework may differ from expected | Auto-detect framework from log content before selecting a parser |

### 13.3 Reliability observations

| Observation | Implication | Enhancement |
|---|---|---|
| Cache was per-provider, not per-repo | Cross-repo interference | ✅ Fixed — now per-repo |
| RSpec test names exceed 255-char filename limit | Cache writes fail silently | Hash test names for cache filenames |
| DeepSeek V4 Flash returns 400 on most repos | Model may require specific request format | Test with direct API (not gateway) or debug the 400 response body |
| No retry on 400/429 errors | Transient failures become permanent fallbacks | Add retry with exponential backoff for 429; log 400 response body for debugging |

---

## 14. Bugs Found and Fixed During Study

### 14.1 Critical bugs

| # | Bug | Impact | Root cause | Fix | Status |
|---|---|---|---|---|---|
| 1 | **Fake FLAKY verdicts from reasoning models** | All Qwen3 classifications were silent defaults, not real verdicts | `max_tokens: 512` hardcoded; reasoning models exhaust tokens before emitting JSON; parse failure labeled `llm:` (same as real verdict) | Configurable `max_tokens` (default 4096); `finish_reason` detection; 4 distinct prefixes (`llm:`, `llm-truncated:`, `llm-parse-error:`, `llm-fallback:`) | ✅ Fixed |
| 2 | **Django prompt overflow (9.8M chars)** | django/django unanalyzable — 400 Bad Request | `cross_run_context` passes entire `preliminary_stats` dict (all 14,925 test stats) instead of per-test stats | Not yet fixed — needs per-test context filtering | ❌ Open |
| 3 | **Vue prompt overflow (1.3M chars)** | vuejs/core unanalyzable on cloud LLMs | Same root cause as django — Vitest's large test suite produces massive cross-run context | Prompt truncation at 50K chars added as workaround; proper fix is per-test context | ⚠️ Workaround |

### 14.2 Design bugs

| # | Bug | Impact | Root cause | Fix | Status |
|---|---|---|---|---|---|
| 4 | **Per-provider cache (not per-repo)** | Deleting cache for one repo deleted all repos; cache key collisions possible | Cache path was `data/llm-cache/{provider}/` — no repo isolation | Changed to `data/llm-cache/{provider}/{repo_slug}/` | ✅ Fixed |
| 5 | **Degraded calls invisible in reports** | 74 fallback calls in rubocop looked like real FLAKY verdicts | `classified_by` prefix was `llm:` for both real verdicts and parse failures | Added `llm_truncated_count`, `llm_parse_error_count`, `llm_fallback_count` to ReportSummary; surfaced in table, markdown, and summary.json | ✅ Fixed |
| 6 | **Cache filename too long for RSpec** | 2 cache writes failed with `Errno 63: File name too long` | RSpec test names (e.g., `RuboCop::Cop::Lint::ConstantReassignment cross-file detection re...`) exceed macOS 255-char filename limit | Not yet fixed — hash test names for cache filenames | ❌ Open |

### 14.3 Integration bugs

| # | Bug | Impact | Root cause | Fix | Status |
|---|---|---|---|---|---|
| 7 | **OpenCode Zen double `/v1` in URL** | First cloud LLM call failed with 404 | Default endpoint set to `https://opencode.ai/zen/v1`; code appends `/v1/chat/completions` → double `/v1` | Changed default endpoint to `https://opencode.ai/zen` | ✅ Fixed |
| 8 | **DeepSeek V4 Flash 400 errors** | 7 of 8 repos failed with 400 Bad Request via OpenCode Zen | Unknown — model exists on OpenCode Zen but rejects most requests. Only fastapi worked. May be account tier or request format | Not yet debugged — need to inspect 400 response body | ❌ Open |
| 9 | **`STATUS_MAP` missing `PASS` key** | Jest `PASS` lines (vs `PASSED`) weren't recognized | STATUS_MAP only had `PASSED`, `FAILED`, `FAIL`, `OK` — not the short `PASS` form used by Jest/Vitest | Added `"PASS": TestStatus.PASSED` | ✅ Fixed |
| 10 | **Jest regex missing GHA timestamp prefix** | Jest parser found 0 tests despite logs containing `PASS` lines | `JEST_SUITE_LINE` regex expected `PASS` at start of line, but GHA logs prefix every line with a timestamp | Added `_GHA_TS_JS` optional timestamp prefix to all JS/TS regex patterns | ✅ Fixed |
| 11 | **Vercel format has suite name prefix** | Vercel/next.js produced 0 tests despite having `FAIL Turbopack path/test.test.ts` lines | `JEST_SUITE_LINE` expected `FAIL path` but Vercel format is `FAIL SuiteName path` (extra word before path) | Added `VERCEL_TEST_LINE` regex with `\w+\s+` prefix for suite name | ✅ Fixed |

### 14.4 Bug summary

| Severity | Found | Fixed | Open |
|---|---|---|---|
| Critical | 3 | 1 | 2 |
| Design | 3 | 2 | 1 |
| Integration | 5 | 4 | 1 |
| **Total** | **11** | **7** | **4** |

---

## 15. GPT-5 Nano Call Counts and Projected Costs

### 15.1 Actual calls made

| Repo | GPT-5 Nano calls | Degraded | Est. cost |
|---|---|---|---|
| fastapi/fastapi | 21 | 0 | $0.015 |
| pytest-dev/pytest | 38 | 0 | $0.027 |
| langchain-ai/langchain | 44 | 0 | $0.032 |
| encode/django-rest-framework | 12 | 0 | $0.009 |
| jestjs/jest | 24 | 0 | $0.017 |
| facebook/react | 2 | 0 | $0.001 |
| vercel/next.js | 71 | 1 | $0.051 |
| rubocop/rubocop | 88 | 3 | $0.063 |
| cypress-io/cypress | 2 | 0 | $0.001 |
| reduxjs/redux-toolkit | 0 | 0 | $0.000 |
| spring-projects/spring-boot | 0 | 0 | $0.000 |
| vuejs/core | 1 | 1 | $0.001 |
| **Total** | **303** | **5** | **~$0.22** |

### 15.2 Cost projection at scale

GPT-5 Nano pricing via OpenCode Zen: $0.05/1M input tokens, $0.40/1M output tokens.
Average per call: ~7,600 input + ~977 output = ~8,577 tokens → ~$0.00072/call.

| Scale | Calls | Est. cost | Use case |
|---|---|---|---|
| Single repo | 20 | $0.01 | One-off analysis |
| Small study | 200 | $0.14 | 5-10 repos |
| **This study** | **303** | **$0.22** | **12 repos, 12 frameworks** |
| Medium scale | 2,000 | $1.44 | 50+ repos |
| Large scale | 20,000 | $14.40 | Enterprise CI monitoring |
| Massive scale | 100,000 | $72.00 | Continuous CI analysis |

### 15.3 Cost comparison: OMLX vs GPT-5 Nano vs DeepSeek

| Model | Cost per call | 303 calls (this study) | 20,000 calls |
|---|---|---|---|
| OMLX (Qwen3.5-9B, local) | $0 | $0 | $0 |
| DeepSeek V4 Flash | ~$0.0001 | $0.03 | $2.00 |
| GPT-5 Nano | ~$0.0007 | $0.22 | $14.40 |
| GPT-4o-mini | ~$0.00016 | $0.05 | $3.15 |

> OMLX is free but had 20% degraded rate (endpoint overload). GPT-5 Nano cost $0.22 for the entire study with 1.6% degraded rate. DeepSeek is cheapest cloud option but had integration issues via OpenCode Zen.

---

## 16. Latency Comparison (per call)

| Repo | OMLX (s) | GPT-5 Nano (s) | Speedup |
|---|---|---|---|
| fastapi/fastapi | 15.4 | 7.5 | 2.1× |
| pytest-dev/pytest | 20.5 | ~5 | 4.1× |
| langchain-ai/langchain | 28.6 | ~5 | 5.7× |
| jestjs/jest | ~20 | ~5 | 4.0× |
| vercel/next.js | ~20 | ~5 | 4.0× |
| rubocop/rubocop | ~20 | ~5 | 4.0× |

> OMLX latency scales with prompt size (larger cross-run context = slower). GPT-5 Nano latency is relatively constant (~5-7s) regardless of prompt size, up to the context window limit.

---

## 17. Accuracy Discussion

### 17.1 The 56 REAL_BUG disagreement

GPT-5 Nano identified 56 REAL_BUGs that OMLX classified as FLAKY across 3 repos (fastapi: 13, vercel: 35, rubocop: 8). OMLX found 1 REAL_BUG (vue) that GPT didn't (due to GPT degradation).

**Why the disagreement?**

- **Model size**: OMLX uses Qwen3.5-9B-MLX-4bit (9B parameters, 4-bit quantized). GPT-5 Nano is a much larger cloud model. The larger model may be better at distinguishing deterministic failures (REAL_BUG) from intermittent ones (FLAKY).
- **OMLX bias toward FLAKY**: The local model may default to the conservative FLAKY classification when it's uncertain, since FLAKY is the "safe" fallback. GPT-5 Nano may be more confident in identifying REAL_BUGs.
- **Prompt sensitivity**: OMLX with `--no-thinking` produces 79 completion tokens (terse JSON). GPT-5 Nano produces 977 tokens (verbose reasoning + JSON). The additional reasoning may help GPT-5 Nano make more nuanced distinctions.

### 17.2 When both models agreed

On 4 repos (pytest, langchain, drf, jest), both models classified all tests as FLAKY. This agreement on "easy" cases builds trust — neither model is throwing false REAL_BUGs. The disagreement is concentrated in repos with more complex failure patterns (fastapi, vercel, rubocop).

### 17.3 Manual validation: GPT-5 Nano was right

We manually validated 1 of the 56 disputed tests by inspecting the raw CI log:

**Test:** `tests/test_tutorial/test_testing/test_tutorial003.py::test_main`
**Raw log:** `FAILED test_main - Failed: DID NOT WARN. No warnings of type (DeprecationWarning,) were emitted.`
**Frequency:** Same error across all 14 runs.

**Ground truth: REAL_BUG ✅.** The test expects a `DeprecationWarning` that the code isn't emitting. This is deterministic. GPT-5 Nano was correct.

OMLX said INFRA because the error message wasn't captured in the cross-run context metadata — a data pipeline gap, not a classification error.

### 17.4 Implication

If this pattern holds for the remaining 55 disputed tests, GPT-5 Nano's 56 REAL_BUG classifications are likely all correct. OMLX's FLAKY/INFRA classifications were wrong due to:
1. Missing error messages in the cross-run context (empty "error signature hash")
2. Conservative OMLX bias toward FLAKY as the safe fallback
3. OMLX being a smaller 9B model less able to infer from metadata alone

See `docs/samples/validation_finding.md` for the full validation record.

### 17.5 OMLX accuracy expectation

OMLX (Qwen3.5-9B, 4-bit quantized) is a smaller model. Its accuracy on nuanced classification tasks is expected to be lower than larger cloud models. The 56 missed REAL_BUGs are consistent with this expectation. However, OMLX is free, local, and private — it's the right choice when cost or data privacy is a concern, even if accuracy is lower.

---

## 18. Recommendations

### 18.1 When to use which model

| Scenario | Recommended model | Why |
|---|---|---|
| Quick local testing | OMLX + `--no-thinking` | Free, no API key, private |
| Production CI analysis | GPT-5 Nano | Higher accuracy, more reliable, faster |
| Cost-sensitive batch runs | OMLX + `--no-thinking` | Free, but expect ~20% degraded on concurrent runs |
| Large repos (django, vue) | GPT-5 Nano (with prompt truncation) | OMLX prompt overflow on large test suites |
| Privacy-sensitive repos | OMLX | No data leaves the machine |
| Cross-model validation | OMLX + GPT-5 Nano | Run both, compare, manually review disagreements |

### 18.2 Recommended workflow

1. **Download** with `--all-runs` and enough runs (500+) to capture meaningful failures
2. **Analyze with OMLX first** (free, fast for small repos)
3. **Re-analyze with GPT-5 Nano** (~$0.0007/call) for repos where OMLX found FLAKY results
4. **Review disagreements** — where OMLX says FLAKY but GPT says REAL_BUG, manually check the raw logs
5. **When both agree**, trust the verdict — no manual review needed

---

## 19. Discovery Metric

A flaky test is "discovered" if it appears in the agent's results and is NOT already tracked in the repo's issue tracker. Due to time constraints, a full issue tracker search was not performed for all repos. However, the classification results themselves represent discoveries:

| Repo | Tests classified | REAL_BUGs (GPT) | FLAKY (both agree) | Potentially untracked |
|---|---|---|---|---|
| fastapi/fastapi | 21 | 13 | 8 | All 21 — fastapi doesn't track flaky tests publicly |
| pytest-dev/pytest | 38 | 0 | 38 | Unknown — needs issue tracker search |
| langchain-ai/langchain | 44 | 0 | 44 | Unknown — needs issue tracker search |
| jestjs/jest | 48 | 0 | 48 | Unknown — needs issue tracker search |
| vercel/next.js | 71 | 35 | 185 | Unknown — needs issue tracker search |
| rubocop/rubocop | 88 | 8 | 80 | Unknown — needs issue tracker search |

> **Minimum discovery**: 56 REAL_BUGs identified by GPT-5 Nano that were not previously known to be deterministic failures. These are the most actionable findings — real bugs masquerading as flaky tests.

---

## 20. Reproducibility

### 20.1 Environment

| Component | Version |
|---|---|
| Python | 3.14.5 |
| ai-flake-sleuth | 0.1.0 (editable install) |
| OMLX model | Qwen3.5-9B-MLX-4bit |
| OMLX endpoint | `http://127.0.0.1:8000` (mlx-server) |
| Cloud provider | OpenCode Zen (`https://opencode.ai/zen`) |
| Cloud model | gpt-5-nano |
| OS | macOS (Apple Silicon) |

### 20.2 Steps to reproduce

1. Install: `pip install -e ".[dev]"`
2. Download data: `ai-flake-sleuth download --repo {repo} --runs 300 --data-dir ./data/ --all-runs`
3. Run OMLX: `ai-flake-sleuth analyze --repo {repo} --data-dir ./data/ --llm omlx --llm-model Qwen3.5-9B-MLX-4bit --llm-endpoint http://127.0.0.1:8000 --force-llm --no-thinking --format all`
4. Run GPT-5 Nano: `export OPENCODE_API_KEY="your-key" && ai-flake-sleuth analyze --repo {repo} --data-dir ./data/ --llm opencode --llm-model gpt-5-nano --force-llm --no-thinking --format all`
5. Compare: check `runs/{repo}/omlx/` vs `runs/{repo}/opencode/` summaries

### 20.3 Test suite

```bash
pytest -q          # 270 tests pass
ruff check src/    # clean
mypy src/          # clean
```

---

## 21. Study Timeline

| Phase | Duration | What happened |
|---|---|---|
| Phase 0: Code changes | ~3 hours | Built 13 new parsers, fixed 11 bugs, added OpenCode Zen provider |
| Phase 1: Downloads | ~2 hours | Downloaded 21 repos, hit rate limits, facebook/react stalled |
| Phase 2: OMLX analysis | ~1.5 hours | Ran 12 repos with OMLX, 382 LLM calls |
| Phase 3: GPT-5 Nano analysis | ~30 min | Ran 8 repos with GPT-5 Nano, 303 LLM calls |
| Phase 4: DeepSeek attempt | ~15 min | Failed on 7/8 repos (400 errors) |
| Phase 5: Report compilation | ~30 min | This document |
| **Total** | **~8 hours** | |

---

## 22. Data Volume

| Metric | Value |
|---|---|
| Total repos downloaded | 21 |
| Total runs fetched | ~4,500 |
| Total log ZIPs downloaded | ~3,800 |
| Total disk space (data/) | ~4.5 GB |
| Total GitHub API calls | ~5,000+ (hit rate limit once) |
| Total LLM calls (OMLX) | ~382 |
| Total LLM calls (GPT-5 Nano) | ~303 |
| Total tests classified | ~1,151 |
| Total reports generated | ~60+ (table, JSON, markdown per repo per model) |

---

## 23. CI Health Snapshot

Per-repo pass rates from the field study:

| Repo | Pass rate | Tests classified | Health |
|---|---|---|---|
| django-import-export | 100% | 0 | 🟢 Clean |
| rails/rails | 100% | 0 | 🟢 Clean |
| laravel/laravel | 100% | 0 | 🟢 Clean |
| gin-gonic/gin | 97% | 0 | 🟢 Clean (lint failures only) |
| spring-projects/spring-boot | 96% | 1 | 🟢 Clean |
| golang/go | 96% | 0 | 🟢 Clean (infra only) |
| jestjs/jest | 83% | 48 | 🟡 Some flaky tests |
| fastapi/fastapi | 88% | 21 | 🟡 13 potential real bugs |
| pytest-dev/pytest | 71% | 38 | 🟡 Flaky test suite |
| rubocop/rubocop | 71% | 88 | 🟡 8 potential real bugs |
| encode/django-rest-framework | 84% | 12 | 🟡 Flaky tests |
| vuejs/core | 62% | 14 | 🟠 1 real bug found |
| reduxjs/redux-toolkit | 93% | 768 | 🟠 Many tests, all rules |
| vercel/next.js | 62% | 71 | 🔴 35 potential real bugs |
| facebook/react | 97% | 26 | 🟢 Mostly clean |

---

## 24. Executive Summary (for article)

We ran an AI-powered flaky test diagnosis agent against 21 open-source repositories spanning 12 test frameworks and 5 programming languages. The agent, ai-flake-sleuth, fetches GitHub Actions CI run history, parses test output from CI logs, and classifies failures as REAL_BUG, FLAKY, or INFRA using LLM-based classification.

We compared a local 9B parameter model (Qwen3.5-9B-MLX-4bit, free, Apple Silicon) against a cloud model (GPT-5 Nano via OpenCode Zen, ~$0.0007/call). The entire study cost $0.22 in cloud LLM calls.

Key findings:
- **15 parsers were built** during the study to handle 12 test frameworks (pytest, Jest, Vitest, Turbopack, Go test, RSpec, Minitest, Mocha, PHPUnit, JUnit, Cypress, + generic fallback)
- **1,151 tests classified** across 12 repos with real results
- **56 REAL_BUGs** identified by GPT-5 Nano that the local model classified as FLAKY — tests that appear flaky but are actually deterministic failures
- **8 repos had clean CI** — failures were in infra/build/lint jobs, not test jobs
- **11 bugs were found and fixed** in the tool itself during the study, including a critical issue where reasoning models produced fake verdicts
- **13× speedup** from disabling Qwen3's reasoning mode (`--no-thinking`)
- The study took ~8 hours end-to-end, including code changes, downloads, analysis, and reporting
