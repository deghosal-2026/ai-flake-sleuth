# Contributing to ai-flake-sleuth

## Development Setup

```bash
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest                     # All tests
pytest -q                  # Quiet mode
pytest tests/test_llm.py   # Single file
pytest --cov=flake_sleuth  # With coverage
```

## Linting and Type Checking

```bash
ruff check src/ tests/     # Lint
mypy src/                  # Type check
```

## Commit Message Convention

We use conventional commits:

- `feat:` — new feature (parser, subcommand, flag)
- `fix:` — bug fix
- `docs:` — documentation
- `test:` — test additions
- `refactor:` — code restructuring

## PR Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Make your changes
4. Run tests + lint + type check
5. Commit with conventional commit message
6. Push and open a PR against `main`

## Adding a New Test Framework Parser

1. Add regex patterns at the top of `src/flake_sleuth/log_parser.py`
2. Add a `_parse_<framework>` method to the `LogParser` class
3. Wire it into `_try_parse`
4. Add tests in `tests/test_log_parser_coverage.py`
5. Add a sample log to `tests/fixtures/sample_logs/`
6. Run `pytest` to confirm coverage
