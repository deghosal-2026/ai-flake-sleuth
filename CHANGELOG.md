# Changelog

All notable changes to ai-flake-sleuth will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-07-18

### Added
- Initial release
- CI run history fetcher from GitHub Actions API
- Failure classification engine (real bug vs flaky vs infra)
- Cross-run correlation for flaky test detection
- Per-test action proposals: quarantine, fix-now, re-run-threshold
- LangGraph agent loop with human-in-the-loop interrupt
- CLI interface with rich output
- 12 test framework parsers (pytest, Jest, RSpec, etc.)
- OMLX local LLM integration for enhanced classification

[0.1.0]: https://github.com/deghosal-2026/ai-flake-sleuth/releases/tag/v0.1.0