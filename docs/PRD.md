# PRD: Build Flakiness Triage & Quarantine Agent

**Status:** Approved  
**Date:** 2026-07-17  
**Author:** Debashish Ghosal  
**Repo:** [ai-flake-sleuth](https://github.com/deghosal-2026/ai-flake-sleuth)  
**Article angle:** "Before You Quarantine: Building the Diagnostic Layer for AI-Driven Flaky Test Triage"

---

## 1. Problem (WHY)

### 1.1 The Core Problem

**Flaky tests destroy CI trust.**

When the pipeline is red 30% of the time for random reasons, engineers ignore ALL failures — including real bugs. A red build stops meaning "something is broken" and starts meaning "maybe something is broken, who knows." Engineers merge around red builds. Real regressions slip into production.

### 1.2 Why This Is Hard Today

Diagnosing flaky tests requires:
1. Reading 50+ run logs manually to find patterns
2. Determining whether a failure is a real intermittent bug or just infra noise
3. Tracking which tests are flaky, how often, and with what error signatures
4. Remembering to revisit quarantined tests before they become permanent dead weight

Nobody has time to do this manually. So flaky tests persist for months.

### 1.3 Why This Is the Right Time

CI-Agent (#04) handled failure triage — classifying *what* failed. This project handles *flakiness* — classifying *whether the failure is reproducible or random*. It's the temporal pattern problem that CI-Agent doesn't solve: the same test failing intermittently across runs.

### 1.4 Consequences of Not Solving This

| Impact | Detail |
|--------|--------|
| False confidence | Engineers merge past red builds — real regressions slip through |
| Wasted cycles | Engineers investigate infra noise thinking it's a real bug |
| Technical debt | Flaky tests never get fixed; they accumulate until someone does a mass cleanup |
| Poor DORA metrics | Change Failure Rate stays high because "everything fails" |
| Team morale | Nobody trusts the CI system — "just rerun it" becomes the default response |

### 1.5 The Scale of the Problem (Public Data)

This isn't a niche issue. Data from peer-reviewed studies, large-scale surveys, and major engineering organizations confirms the systemic impact.

**Prevalence — flaky tests are everywhere**

| Data Point | Source |
|-----------|--------|
| 51% of developers experience flaky tests at least weekly; 66% rate it a moderate or serious problem | Gruber & Fraser, ICST 2022 — survey of 335 professional developers ([DOI](https://doi.org/10.1109/icst53961.2022.00020)) |
| 79% of developers consider flaky tests a moderate to serious problem; 40% deal with them at least weekly | Eck et al., FSE 2019 — survey of 121 developers ([paper](http://www.sback.it/publications/fse2019.pdf)) |
| 3.2% of builds are rerun; 67.7% of reruns are flaky; flakiness affects over half (51.28%) of projects | Ge & Zhang, 2025 — study of 4.8M builds across 1,960 GitHub Actions Java projects ([arXiv](https://arxiv.org/html/2602.02307v1)) |
| Google: 0.5% of small tests, 1.6% of medium tests, 14% of large tests are flaky — across 4.2M+ tests | Trunk blog (2024), citing Jeff Listfield at Google — analysis of 20.2M CI jobs ([source](https://trunk.io/blog/what-we-learned-from-analyzing-20-2-million-ci-jobs-in-trunk-flaky-tests-part-1)) |
| Uber: 1,000+ flaky tests in their Go monorepo. At 0.1% flake rate per test, ~63% of PRs need at least 1 rerun | Trunk blog (2024) ([source](https://trunk.io/blog/what-we-learned-from-analyzing-20-2-million-ci-jobs-in-trunk-flaky-tests-part-1)) |

**Cost — it drains real money and engineering time**

| Data Point | Source |
|-----------|--------|
| Developers spend at least 2.5% of productive time dealing with flaky tests (1.1% investigating + 1.3% repairing + 0.1% tooling). Manual investigation costs $5.67 per failure; auto-rerun costs $0.02 | Leinen et al., ICST 2024 — industrial case study, ~30 developers, ~1M SLoC, 5 years of data ([DOI](https://doi.org/10.1109/icst60714.2024.00037)) |
| Developers spend up to 1.28% of their time repairing flaky tests — $2,250/month | Leinen et al., ICST 2024 (cited in Parry et al., 2025 — [arXiv](https://arxiv.org/html/2504.16777v1)) |
| For every week of computing time spent on testing, up to one day is used for re-running flaky tests | Cited in SAP HANA study, ICSE 2024 — attributed to Google ([paper](https://assets.empirical-software.engineering/pdf/icse24-timeout-flakiness.pdf)) |
| Rerun builds accumulated ~339 years of waiting time and consumed 31.6 years of computational time | Ge & Zhang, 2025 — across 1,960 GitHub Actions projects ([arXiv](https://arxiv.org/html/2602.02307v1)) |

**Trust — the hidden cost is worse than the time**

| Data Point | Source |
|-----------|--------|
| 73% of developers report that once a test becomes flaky, it's no longer fully reliable — they start disregarding it, potentially ignoring actual failures | Eck et al., FSE 2019 — survey of 121 developers ([paper](http://www.sback.it/publications/fse2019.pdf)) |
| Losing trust and wasting developer time are perceived as the most severe impacts — more than computational resource waste | Gruber & Fraser, ICST 2022 — survey of 335 developers ([DOI](https://doi.org/10.1109/icst53961.2022.00020)) |
| Each flaky failure triggers a context switch — ~23 minutes of productivity lost per interruption | Trunk blog (2024), citing "Cost of Interrupted Work" research ([source](https://trunk.io/blog/what-we-learned-from-analyzing-20-2-million-ci-jobs-in-trunk-flaky-tests-part-1)) |

**The bottom line:** Flaky tests are not a "nice to fix" problem. They are a systemic drain on engineering productivity, CI compute budgets, and — most critically — the trust that makes CI worth running at all. The research consistently shows that trust erosion is worse than the measurable time waste: when engineers stop believing test results, the entire testing investment loses its value.

---

## 2. Solution (WHAT)

### 2.1 Product Vision

A LangGraph agent that fetches recent GitHub Actions run history from public repos, classifies failures (real bug vs. flaky vs. infra) by log pattern + cross-run correlation, and produces a diagnostic CI health report. The report is the foundation — agentic-ready JSON that a future v2 agent loop can pick up as state input for quarantine/fix/retry recommendations.

**v1 = the diagnostic layer.** Before you can quarantine a flaky test, you need to know: which tests are flaky, how often they fail, what errors they produce, and whether the failure is a real bug or just infra noise. v1 answers those questions.

### 2.2 Target Users

| Role | Need | v1 Served? |
|------|------|------------|
| CI owner | Restore CI signal reliability; stop ignoring red builds | Yes — full CI health report |
| Engineer | Investigate a specific flaky test with full evidence | Yes — per-test failure history + error distributions |
| Tech lead | Govern quarantined tests; ensure they're reviewed and re-enabled | v2 — quarantine governance |
| Platform lead | Track flake rate trends; decide where to invest engineering time | v2 — dashboard |

### 2.3 What v1 Does

1. **Fetches** N recent GitHub Actions runs from a public repo (configurable, default 100)
2. **Parses** job logs for each failed run — extracts test names, error messages, timing
3. **Classifies** each failure: real bug / flaky / infra
4. **Correlates** across runs — per-test flake rate, error distribution, temporal patterns
5. **Generates a report** in three formats:
   - **CLI table** — interactive terminal output for the demo
   - **JSON** — agentic-ready schema designed as v2's LangGraph state input
   - **Markdown** — human-readable for sharing in PRs, issues, articles

### 2.4 Customer User Journeys

| CUJ | Actor | Trigger | Agent Action | Human Decision | v1? |
|-----|-------|---------|-------------|----------------|-----|
| CUJ-1: Triage flaky tests | CI owner | "CI is flaky" | Pulls run history, classifies failures, identifies flaky tests with flake rate | Review report; decide what to investigate first | Yes (report only, no proposed actions) |
| CUJ-2: Investigate a flaky test | Engineer | Specific test flagged | Pulls all runs where the test failed, shows error distribution | Fix the test vs. fix the code vs. ignore | Yes |
| CUJ-3: Quarantine governance | Tech lead | Quarterly review | Lists all quarantined tests with review dates; flags overdue reviews | Re-enable vs. extend vs. delete | v2 |
| CUJ-4: CI health dashboard | Platform lead | Weekly review | Flake rate trend, quarantine count, real vs. flaky ratio | Invest in fixing vs. accept current rate | v2 |

### 2.5 v1 Capabilities

| Capability | What it does |
|------------|-------------|
| Multi-workflow analysis | Analyzes all workflows by default; filter to a specific workflow |
| Time window scoping | Optional date filter to scope analysis to recent runs |
| API response caching | Optional cache to avoid re-fetching on re-runs (useful for field study) |
| Data quality reporting | Shows total runs fetched, runs with parseable logs, skipped runs, effective sample |
| Clean report | When a repo has zero failures, confirms CI health with pass-rate breakdown |
| Expired log handling | Skips runs with expired logs (>90 days), warns, adjusts sample |
| Rate-limit aware | Handles GitHub API limits gracefully without crashing |

### 2.6 Non-Goals (v1)

- Not a generic CI monitoring platform — scoped to flaky test triage
- Not quarantine or PR generation — that's v2
- Not a full test runner — we consume CI results, we don't run tests
- Not a CI system — we read from GitHub Actions, we don't replace it
- Not auto-quarantine — the agent never auto-quarantines (even in v2)
- Not a web UI or dashboard — CLI only in v1
- Not non-Python frameworks — v1 targets pytest/unittest; jest/go test/rspec deferred to v2

---

## 3. Key Product Decisions

### 3.1 v1 = Diagnostic Layer, v2 = Action Layer

v1 produces the diagnostic report (what's flaky, what's real, what's infra). v2 adds the LangGraph interrupt loop, quarantine manager, and PR/issue generation. The v1 JSON output is designed as v2's state input — agentic-ready, not throwaway.

### 3.2 Three Output Formats

| Format | Audience | Purpose |
|--------|----------|---------|
| CLI table | Developer at terminal | Interactive use, demo, field study screenshot |
| JSON (agentic-ready) | v2 agent / machine | Structured schema designed as LangGraph state input for v2 |
| Markdown | Human sharing | Paste into PRs, issues, articles — the Hashnode article artifact |

### 3.3 All Three Classification Categories in the Report

The report covers flaky tests (with flake rates + error distributions), real bugs (with reproducibility evidence), and infra issues (with failure patterns). A complete CI health snapshot, not just flakiness.

### 3.4 Minimum Sample Size

Flaky detection needs a minimum sample size (50+ test executions). Small samples produce false positives. The agent enforces this threshold — below 50, a test is flagged as "insufficient data" instead of flaky.

### 3.5 Infra Flakes Are Separate

Infra failures (OOM, network, runner issues) are classified separately from test flakiness. The fix for an infra flake is infrastructure, not test quarantine.

---

## 4. Success Criteria

### 4.1 v1 Good (Ship)

- [ ] Fetches N recent GitHub Actions runs via API (configurable, default 100)
- [ ] Downloads + parses job logs for failed runs
- [ ] Extracts test names from logs
- [ ] Classifies failures: real bug / flaky / infra
- [ ] Cross-run correlation: per-test flake rate, error distribution, temporal pattern
- [ ] Multi-workflow analysis (all workflows by default, filterable)
- [ ] Generates report in three formats: CLI table, JSON (agentic-ready), markdown
- [ ] Data quality section in report (total runs, runs with logs, skipped, effective sample)
- [ ] Clean report for repos with zero failures
- [ ] Handles GitHub API rate limits and expired logs gracefully

### 4.2 v1 Success Metrics

| Metric | Target | How to Measure |
|--------|--------|----------------|
| **Accuracy** | 90%+ of classifications match manual review | Sample N classifications from field study, manually verify each |
| **Discovery** | Find previously-unknown flaky tests across 3-5 repos | Count flaky tests identified that weren't already documented/tracked |
| **Coverage + speed** | 500 runs across 5 repos in under 5 minutes | Time the full pipeline end-to-end |

### 4.3 v2 Roadmap (Post-v1)

| Milestone | Scope | Output |
|-----------|-------|--------|
| M5: Error signature embedder | Semantic clustering of similar failures | `embedder.py` |
| M6: LangGraph cyclic graph + interrupt | Cyclic map-reduce with `interrupt()` per flaky test | `graph.py` |
| M7: Quarantine manager | PR generator + SQLite review-date tracker | `quarantine.py` |
| M8: Dashboard | Flake rate trend, quarantine count, real vs. flaky ratio | `dashboard.py` |

---

## 5. Scope & Boundaries

| In Scope (v1) | Out of Scope (v1) |
|---------------|-------------------|
| GitHub Actions run history | Other CI systems (Jenkins, CircleCI, GitLab CI) |
| Public repo analysis | Private repo auth |
| Per-test flake rate calculation | Test execution or re-running |
| Failure classification (3 categories) | Quarantine PR generation (v2) |
| CLI + JSON + markdown output | Web UI or dashboard (v2) |
| Python test frameworks (pytest, unittest) | Non-Python frameworks (jest, go test, rspec) — v2 |
| Multi-workflow analysis | Cross-repo correlation (each repo analyzed independently) |
| Optional API response caching | Persistent state between runs (v2) |
| Multi-repo field testing (3-5 repos) | Continuous monitoring / scheduled runs |

---

## 6. User Stories

### Tier 1 (Core — Must Have)

As a CI owner, I want to point the agent at a repo and get a list of flaky tests with flake rates, so I know which tests to investigate first.

As an engineer, I want to investigate a specific flaky test and see all runs where it failed with error distributions, so I can diagnose the root cause.

As a CI owner, I want the report to distinguish flaky tests from real bugs and infra issues, so I don't waste time fixing the wrong thing.

### Tier 2 (Important — Should Have)

As a developer, I want the report in JSON format, so I can pipe it into other tools or a future agent loop.

As a developer, I want the report in markdown, so I can paste it into a PR or issue for team visibility.

### Tier 3 (Nice to Have — v2)

As a tech lead, I want to quarantine flaky tests with review dates, so I can govern the flaky-test debt.

As a platform lead, I want a dashboard showing flake rate trends, so I can decide where to invest engineering time.

---

## 7. Constraints

| Constraint | Impact |
|------------|--------|
| GitHub Actions only for v1 | Limits scope to one CI platform |
| Public repos only | Private repo auth adds complexity — deferred |
| CLI interface only | No web UI in v1 — terminal + file output |
| GitHub Actions logs expire after 90 days | Effective sample may be < requested runs; warning shown |
| Minimum 50 test executions for flaky classification | Small samples produce false positives — enforced threshold |
| Python test frameworks only (v1) | pytest/unittest; other frameworks deferred to v2 |

---

## 8. Field Study Plan

**Target repos (3-5):** Active open-source projects with frequent CI runs and public Actions history.

| Repo | Why |
|------|-----|
| `pytest-dev/pytest` | Large, active, frequent CI — the project note's suggestion |
| `ansible/ansible` | Massive test suite, known for CI volume |
| `pallets/flask` | Mature but active — likely has some flaky tests |
| `python/cpython` | High CI volume, well-maintained — good for real-bug detection |
| `langchain-ai/langgraph` | Aligns with the LangGraph ecosystem — meta appeal for the article |

**Field study output:** Run the agent against all 5 repos, produce reports, manually validate a sample of classifications for accuracy, count discovered flaky tests, measure end-to-end runtime. This becomes the Hashnode article data.

---

## 9. Article Plan

**Title:** "Before You Quarantine: Building the Diagnostic Layer for AI-Driven Flaky Test Triage"

**Angle:** v1 is the diagnostic foundation — before you can quarantine a flaky test, you need to know it's flaky. The article covers:
1. The problem (flaky tests destroy CI trust)
2. The diagnostic approach (fetch → classify → correlate)
3. LangGraph conditional edges (rate-limit retry, skip-if-no-failures)
4. Field study results (5 repos, 500 runs, accuracy, discovery, speed)
5. What comes next (v2: interrupt loop + quarantine governance)

**Data points for the article:**
- X flaky tests discovered across 5 repos
- 90%+ classification accuracy vs manual review
- 500 runs processed in under 5 minutes
- Error distribution examples from real flaky tests found

---

## 10. Related

- [Project note #46](https://github.com/deghosal-2026/my-2nd-brain/blob/main/vault/projects/46-Build-Flakiness-Triage.md) — full project context
- CI-Agent (#04) — extends from failure triage to flakiness detection
- CI/CD Bottleneck Optimizer (#33) — CI quality suite companion
