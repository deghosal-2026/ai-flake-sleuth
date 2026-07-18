"""CI job log parser for pytest and unittest output.

Extracts structured TestResult objects from raw log text using regex
patterns for both short-format pytest and dot-format unittest output.
Includes failure-block extraction for error messages and stack traces.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from flake_sleuth.types import JobInfo, RunInfo, TestResult, TestStatus

# ANSI escape sequences used by pytest for colored output in CI logs.
# These appear as e.g. [31mFAILED[0m or [1mtest_name[0m.
_ANSI = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

logger = logging.getLogger(__name__)

# ─── Pytest Patterns ───

# Short format: "tests/test_foo.py::test_bar FAILED"
# Also handles GHA-timestamp-prefixed lines where FAILED comes before the
# test name: "2026-07-17T14:05:21Z FAILED tests/test_foo.py::test_bar - msg"
_GHA_TS_PYTEST = r"(?:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\s+)?"

# Status before test name: "TIMESTAMP FAILED test_name - error_message"
PYTEST_FAILED_BEFORE = re.compile(
    rf"^{_GHA_TS_PYTEST}(FAILED|ERROR)\s+(\S+::\S+)\s*-?\s*",
    re.MULTILINE,
)

# Status after test name: "TIMESTAMP test_name FAILED"
PYTEST_SHORT = re.compile(
    rf"^{_GHA_TS_PYTEST}(\S+::\S+)\s+(FAILED|ERROR|PASSED|SKIPPED)\s*$",
    re.MULTILINE,
)

# ─── Unittest Patterns ───

# GitHub Actions timestamps prefix (e.g. "2026-07-16T08:36:32.1785327Z ")
_GHA_TS = r"(?:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\s+)?"

# Dot-format per-test line: "test_bar (test_foo.TestClass) ... FAIL"
UNITTEST_DOT = re.compile(
    rf"^{_GHA_TS}(\S+)\s+\((\S+)\)\s+\.\.\.\s+(FAIL|ERROR|ok|skip)$",
    re.MULTILINE,
)

# Django/verbose-unittest format with optional GHA timestamp prefix.
# Django's DiscoverRunner wraps unittest with --verbosity=2 producing:
# "2026-07-16T08:36:32Z test_bar (test_foo.TestClass) ... ok"
UNITTEST_DOT_PERMISSIVE = re.compile(
    rf"^{_GHA_TS}(\S+)\s+\(([^)]+)\)\s+\.{{2,}}\s*(FAIL|ERROR|ok|skip)\s*$",
    re.MULTILINE,
)

# Plain unittest verbose: "FAIL: test_bar (test_foo.TestClass)"
UNITTEST_VERBOSE_LINE = re.compile(
    rf"^{_GHA_TS}(FAIL|ERROR):\s+(\S+)\s*(?:\((\S+)\))?\s*$",
    re.MULTILINE,
)

# ─── Failure Section Headers ───

# Pytest uses a line of underscores as a visual separator:
# "_____________________________ test_bar ______________________________"
PYTEST_FAILURE_HEADER = re.compile(
    r"^_{3,}\s*(.+?)\s*_{3,}\s*$",
    re.MULTILINE,
)

# Unittest uses "FAIL: test_bar (test_foo.TestClass)" as section header.
UNITTEST_FAILURE_HEADER = re.compile(
    r"^(FAIL|ERROR):\s+(\S+)\s*\((\S+)\)",
    re.MULTILINE,
)

# ─── Jest / JS Test Framework Patterns ───

# Shared GHA timestamp prefix for JS/TS patterns
_GHA_TS_JS = r"(?:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\s+)?"

# Suite-level result: "FAIL|PASS|SKIP path/to/test.test.ext"
JEST_SUITE_LINE = re.compile(
    rf"^{_GHA_TS_JS}(FAIL|PASS|SKIP)\s+(\S+\.(?:test|spec|e2e|unit)\.(?:[jt]sx?|mjs|cjs))",
    re.MULTILINE,
)

# Individual test failure: "  ● FooComponent › renders correctly"
JEST_INDIVIDUAL_FAILURE = re.compile(r"^\s{2}●\s+(.+)$", re.MULTILINE)

# Generic JS/TS framework fallback: "FAIL|PASS|ERROR <path>" with common
# test file conventions (__tests__/, .test., .spec., etc.)
GENERIC_JS_TEST_LINE = re.compile(
    rf"^{_GHA_TS_JS}(FAIL|PASS|ERROR|SKIP)\s+"
    r"((?:__tests__/\S+|\S+__tests__\S+|"
    r"\S+\.(?:test|spec|e2e|unit|integ)\.(?:[jt]sx?|mjs|cjs)))",
    re.MULTILINE,
)

# ─── Vitest Patterns ───

# After ANSI stripping: " ✓ unit path/__tests__/file.spec.ts (N tests) Xms"
VITEST_LINE = re.compile(
    rf"^{_GHA_TS_JS}[✓✗]\s+\S+\s+(\S+__tests__\S+\.spec\.\S+)",
    re.MULTILINE,
)

# ─── Vercel/Turbopack Patterns ───

# "FAIL SuiteName path/to/test.test.ts (duration s)"
# SuiteName is a single word prefix before the file path
VERCEL_TEST_LINE = re.compile(
    rf"^{_GHA_TS_JS}(FAIL|PASS)\s+\w+\s+(\S+\.(?:test|spec)\.(?:[jt]sx?))",
    re.MULTILINE,
)

# ─── PHPUnit/Pest Patterns ───

# "PASS  Tests\Path\TestName" or "FAIL  Tests\Path\TestName"
# Uses [A-Z] instead of backslash-escape to avoid regex escaping issues
PHPUNIT_LINE = re.compile(
    rf"^{_GHA_TS_JS}(PASS|FAIL)\s+(Tests[A-Za-z0-9_\\\.]+)",
    re.MULTILINE,
)

# ─── Go test Patterns ───

# Individual test result: "--- PASS: TestName (0.00s)" or "--- FAIL: TestName"
GO_TEST_LINE = re.compile(
    rf"^{_GHA_TS_JS}--- (PASS|FAIL):\s+(\S+)",
    re.MULTILINE,
)

# ─── RSpec Patterns ───

# Summary: "N examples, N failures, N pending"
RSPEC_SUMMARY = re.compile(
    rf"^{_GHA_TS_JS}(\d+) examples,\s+(\d+) failures",
    re.MULTILINE,
)

# Individual failure: "1) TestName should do something"
RSPEC_FAILURE = re.compile(
    rf"^{_GHA_TS_JS}(\d+)\)\s+(.+?)(?:\s+FAILED)?$",
    re.MULTILINE,
)

# ─── Minitest Patterns ───

# Summary: "N runs, N assertions, N failures, N errors, N skips"
MINITEST_SUMMARY = re.compile(
    rf"^{_GHA_TS_JS}(\d+) runs,\s+(\d+) assertions,\s+(\d+) failures",
    re.MULTILINE,
)

# ─── Mocha Patterns ───

# Mocha outputs like Vitest: ✓ test name, ✗ test name, N passing, N failing
MOCHA_LINE = re.compile(
    rf"^{_GHA_TS_JS}\s*([✓✗])\s+(.+)$",
    re.MULTILINE,
)

# ─── JUnit Patterns (from Gradle/Maven output) ───

# "Tests run: N, Failures: M, Errors: E, Skipped: S"
JUNIT_SUMMARY = re.compile(
    rf"^{_GHA_TS_JS}Tests run:\s+(\d+),\s+Failures:\s+(\d+)",
    re.MULTILINE,
)

# "testMethod(TestClass)  Time elapsed: Ns  <<< FAILURE!"
JUNIT_FAILURE = re.compile(
    rf"^{_GHA_TS_JS}(\S+)\((\S+)\)\s+Time elapsed:\s+[\d.]+\s*s\s+<<<\s+(FAILURE|ERROR)!",
    re.MULTILINE,
)

# ─── Cypress Patterns ───

# "  ✓ TestName (Nms)" or "  ✗ TestName (Nms)"
# "  N passing" or "  N failing"
CYPRESS_LINE = re.compile(
    rf"^{_GHA_TS_JS}\s*([✓✗])\s+(.+?)\s+\(\d+ms\)$",
    re.MULTILINE,
)

# Timing line at end of both pytest and unittest output: "in 0.32s"
TIMING_PATTERN = re.compile(r"in\s+([\d.]+)s")

STATUS_MAP: dict[str, TestStatus] = {
    "FAILED": TestStatus.FAILED,
    "ERROR": TestStatus.ERROR,
    "PASSED": TestStatus.PASSED,
    "SKIPPED": TestStatus.SKIPPED,
    "PASS": TestStatus.PASSED,
    "FAIL": TestStatus.FAILED,
    "SKIP": TestStatus.SKIPPED,
    "OK": TestStatus.PASSED,
    "ok": TestStatus.PASSED,
    "skip": TestStatus.SKIPPED,
    "✓": TestStatus.PASSED,
    "✗": TestStatus.FAILED,
}


class LogParser:
    """Parse CI job logs to extract structured TestResult objects.

    Supports pytest (short/verbose) and unittest (dot-format) output.
    Falls back to LLM when configured and no regex matches.
    """

    def __init__(
        self,
        llm_adapter: Any | None = None,
    ) -> None:
        self.llm_adapter = llm_adapter

    def parse(
        self,
        run_info: RunInfo,
        logs: dict[str, str],
    ) -> list[TestResult]:
        """Parse all log files for a run and return extracted test results.

        Iterates over each log entry (filename → content), identifies the
        associated job, and delegates to the correct parser backend.
        """
        results: list[TestResult] = []
        for filename, content in logs.items():
            job_name = self._identify_job(filename, run_info.jobs)
            parsed = self._try_parse(content, run_info, job_name)
            results.extend(parsed)
        return results

    def _identify_job(self, filename: str, jobs: list[JobInfo]) -> str:
        """Map a log filename to a job name from run_info.jobs.

        If only one job exists, use it directly. Otherwise try substring
        matching before falling back to the bare filename.
        """
        if len(jobs) == 1:
            return jobs[0].name
        for job in jobs:
            if job.name in filename or filename in job.name:
                return job.name
        return filename

    @staticmethod
    def _strip_ansi(text: str) -> str:
        """Remove ANSI escape codes from CI log text."""
        return _ANSI.sub("", text)

    def _try_parse(
        self,
        content: str,
        run_info: RunInfo,
        job_name: str,
    ) -> list[TestResult]:
        """Try each parser backend in order; fall back to LLM if configured.

        Strips ANSI color codes first (common in GitHub Actions logs with
        pytest) then tries pytest first, then unittest.
        """
        content = self._strip_ansi(content)
        results = self._parse_pytest(content, run_info, job_name)
        if results:
            return results
        results = self._parse_unittest(content, run_info, job_name)
        if results:
            return results
        results = self._parse_jest(content, run_info, job_name)
        if results:
            return results
        results = self._parse_vitest(content, run_info, job_name)
        if results:
            return results
        results = self._parse_vercel(content, run_info, job_name)
        if results:
            return results
        results = self._parse_go_test(content, run_info, job_name)
        if results:
            return results
        results = self._parse_phpunit(content, run_info, job_name)
        if results:
            return results
        results = self._parse_rspec(content, run_info, job_name)
        if results:
            return results
        results = self._parse_minitest(content, run_info, job_name)
        if results:
            return results
        results = self._parse_mocha(content, run_info, job_name)
        if results:
            return results
        results = self._parse_junit(content, run_info, job_name)
        if results:
            return results
        results = self._parse_cypress(content, run_info, job_name)
        if results:
            return results
        if self.llm_adapter:
            logger.warning(
                "LLM fallback not yet implemented for run %d", run_info.run_id
            )
        else:
            logger.warning(
                "No parser matched log for run %d, job %s", run_info.run_id, job_name
            )
        return []

    def _parse_pytest(
        self,
        content: str,
        run_info: RunInfo,
        job_name: str,
    ) -> list[TestResult]:
        """Parse pytest-format log content with short-format regex.

        For each matched test line, looks up the corresponding failure
        block (by function name) to extract error_message and stack_trace.
        Tries standard pattern (status after name) first, then falls back
        to GHA-timestamp pattern (status before name, e.g. "FAILED test_name - ...").
        """
        timing = self._extract_timing(content)
        failure_blocks = self._extract_pytest_failure_blocks(content)

        results: list[TestResult] = []
        for match in PYTEST_SHORT.finditer(content):
            test_name = match.group(1)
            status_str = match.group(2)
            self._append_test_result(results, match, test_name, status_str,
                                      failure_blocks, timing, run_info, job_name)

        if not results:
            for match in PYTEST_FAILED_BEFORE.finditer(content):
                status_str = match.group(1)
                test_name = match.group(2)
                self._append_test_result(results, match, test_name, status_str,
                                          failure_blocks, timing, run_info, job_name)

        return results

    @staticmethod
    def _append_test_result(
        results: list[TestResult],
        match: re.Match[str],
        test_name: str,
        status_str: str,
        failure_blocks: dict[str, dict[str, str]],
        timing: float,
        run_info: RunInfo,
        job_name: str,
    ) -> None:
        """Extract test result from a regex match and append to results list."""
        status = STATUS_MAP[status_str]
        error_message = ""
        stack_trace = ""
        if status in (TestStatus.FAILED, TestStatus.ERROR):
            func_name = test_name.split("::")[-1]
            block = failure_blocks.get(func_name)
            if block:
                error_message = block.get("error_message", "")
                stack_trace = block.get("stack_trace", "")
        results.append(
            TestResult(
                test_name=test_name,
                status=status,
                error_message=error_message,
                stack_trace=stack_trace,
                timing_seconds=timing,
                run_id=run_info.run_id,
                workflow_name=run_info.workflow_name,
                job_name=job_name,
                timestamp=run_info.timestamp,
            )
        )

    def _parse_unittest(
        self,
        content: str,
        run_info: RunInfo,
        job_name: str,
    ) -> list[TestResult]:
        """Parse unittest-format log content with dot-format regex.

        Uses UNITTEST_DOT to match per-test lines (e.g. "test_bar
        (test_foo.TestClass) ... FAIL"), then resolves the fully qualified
        test name as "module.Class.test_name". Falls back to a more
        permissive pattern for Django's DiscoverRunner output.
        """
        timing = self._extract_timing(content)
        failure_blocks = self._extract_unittest_failure_blocks(content)

        results: list[TestResult] = []
        matches = list(UNITTEST_DOT.finditer(content))
        if not matches:
            # Fallback: try permissive pattern for Django/variant output
            matches = list(UNITTEST_DOT_PERMISSIVE.finditer(content))

        for match in matches:
            test_name_short = match.group(1)
            module_class = match.group(2)
            status_str = match.group(3)
            test_name = f"{module_class}.{test_name_short}"
            status = STATUS_MAP[status_str]
            error_message = ""
            stack_trace = ""
            if status in (TestStatus.FAILED, TestStatus.ERROR):
                block = failure_blocks.get(test_name_short)
                if block:
                    error_message = block.get("error_message", "")
                    stack_trace = block.get("stack_trace", "")
            results.append(
                TestResult(
                    test_name=test_name,
                    status=status,
                    error_message=error_message,
                    stack_trace=stack_trace,
                    timing_seconds=timing,
                    run_id=run_info.run_id,
                    workflow_name=run_info.workflow_name,
                    job_name=job_name,
                    timestamp=run_info.timestamp,
                )
            )
        return results

    def _parse_jest(
        self,
        content: str,
        run_info: RunInfo,
        job_name: str,
    ) -> list[TestResult]:
        """Parse Jest-format log content.

        Matches suite-level PASS/FAIL/SKIP lines, then looks up individual
        test failures (``  ● TestName › sub›...)`` for context. Falls back
        to a generic JS/TS framework pattern for Vitest, Mocha, etc.
        """
        timing = self._extract_timing(content)
        results: list[TestResult] = []

        # Extract individual test failures with their error blocks
        failure_tests: dict[str, str] = {}
        lines = content.splitlines()
        i = 0
        while i < len(lines):
            m = JEST_INDIVIDUAL_FAILURE.match(lines[i])
            if m:
                test_name = m.group(1).strip()
                i += 1
                block_lines: list[str] = []
                while i < len(lines):
                    if JEST_INDIVIDUAL_FAILURE.match(lines[i]):
                        break
                    if GENERIC_JS_TEST_LINE.match(lines[i]):
                        break
                    if JEST_SUITE_LINE.match(lines[i]):
                        break
                    if re.match(r"^(Tests:|Test Suites:)", lines[i]):
                        break
                    block_lines.append(lines[i])
                    i += 1
                block_text = "\n".join(block_lines).strip()
                # Extract error message as first non-empty line after "●"
                error_message = ""
                for line in block_lines:
                    stripped = line.strip()
                    if stripped and stripped.startswith("expect"):
                        error_message = stripped
                        break
                if not error_message and block_text:
                    for line in block_lines:
                        stripped = line.strip()
                        if stripped and not stripped.startswith("at ") \
                           and not stripped.startswith("> ") \
                           and not stripped.startswith("File ") \
                           and not stripped.startswith("|"):
                            error_message = stripped
                            break
                failure_tests[test_name] = error_message
                continue
            i += 1

        # Match suite-level lines (FAIL/PASS/SKIP/ERROR <filepath>)
        # Use JEST_SUITE_LINE first, then supplement with GENERIC_JS_TEST_LINE
        # matches that JEST_SUITE_LINE missed (e.g. ERROR status).
        seen_positions: set[int] = set()
        suite_matches: list[re.Match[str]] = []
        for m in JEST_SUITE_LINE.finditer(content):
            seen_positions.add(m.start())
            suite_matches.append(m)
        for m in GENERIC_JS_TEST_LINE.finditer(content):
            if m.start() not in seen_positions:
                suite_matches.append(m)

        for match in suite_matches:
            status_str = match.group(1)
            filepath = match.group(2)
            status = STATUS_MAP.get(status_str)
            if status is None:
                continue
            # Normalize filepath to look like a test name
            test_name = filepath.replace("/", ".").replace("\\", ".")
            error_message = ""
            if status in (TestStatus.FAILED, TestStatus.ERROR):
                # Find matching individual test failures for this file
                file_errors = []
                for name, err in failure_tests.items():
                    file_errors.append(f"{name}: {err}" if err else name)
                error_message = "; ".join(file_errors) if file_errors else ""
            results.append(
                TestResult(
                    test_name=test_name,
                    status=status,
                    error_message=error_message,
                    stack_trace="",
                    timing_seconds=timing,
                    run_id=run_info.run_id,
                    workflow_name=run_info.workflow_name,
                    job_name=job_name,
                    timestamp=run_info.timestamp,
                )
            )
        return results

    def _parse_vitest(
        self,
        content: str,
        run_info: RunInfo,
        job_name: str,
    ) -> list[TestResult]:
        """Parse Vitest-format log content (✓/✗ with ANSI codes).

        Vitest in CI outputs lines like:
          TIMESTAMP ✓ unit path/__tests__/file.spec.ts (N tests) Xms
          TIMESTAMP ✗ unit path/__tests__/file.spec.ts (N tests) Xms

        ANSI escape codes are stripped before matching.
        """
        clean = self._strip_ansi(content)
        timing = self._extract_timing(clean)
        results: list[TestResult] = []
        for match in VITEST_LINE.finditer(clean):
            symbol = match.group(0)[0]
            filepath = match.group(1)
            status = STATUS_MAP.get(symbol)
            if status is None:
                continue
            test_name = filepath.replace("/", ".").replace("\\", ".")
            results.append(
                TestResult(
                    test_name=test_name,
                    status=status,
                    error_message="",
                    stack_trace="",
                    timing_seconds=timing,
                    run_id=run_info.run_id,
                    workflow_name=run_info.workflow_name,
                    job_name=job_name,
                    timestamp=run_info.timestamp,
                )
            )
        return results

    def _parse_vercel(
        self,
        content: str,
        run_info: RunInfo,
        job_name: str,
    ) -> list[TestResult]:
        """Parse Vercel/Turbopack test output.

        Format:
          TIMESTAMP FAIL SuiteName path/to/test.test.ts (duration s)
          TIMESTAMP PASS SuiteName path/to/test.test.ts (duration s)
        """
        timing = self._extract_timing(content)
        results: list[TestResult] = []
        for match in VERCEL_TEST_LINE.finditer(content):
            status_str = match.group(1)
            filepath = match.group(2)
            status = STATUS_MAP.get(status_str)
            if status is None:
                continue
            test_name = filepath.replace("/", ".").replace("\\", ".")
            results.append(
                TestResult(
                    test_name=test_name,
                    status=status,
                    error_message="",
                    stack_trace="",
                    timing_seconds=timing,
                    run_id=run_info.run_id,
                    workflow_name=run_info.workflow_name,
                    job_name=job_name,
                    timestamp=run_info.timestamp,
                )
            )
        return results

    def _parse_go_test(
        self,
        content: str,
        run_info: RunInfo,
        job_name: str,
    ) -> list[TestResult]:
        """Parse Go test output (go test -v).

        Format:
          --- PASS: TestName (0.00s)
          --- FAIL: TestName (0.00s)
              file_test.go:42: Error message
          ok  	package/path	0.225s
          FAIL 	package/path	0.225s
        """
        results: list[TestResult] = []
        for match in GO_TEST_LINE.finditer(content):
            status_str = match.group(1)
            test_name = match.group(2)
            status = STATUS_MAP.get(status_str)
            if status is None:
                continue
            results.append(
                TestResult(
                    test_name=test_name,
                    status=status,
                    error_message="",
                    stack_trace="",
                    timing_seconds=0.0,
                    run_id=run_info.run_id,
                    workflow_name=run_info.workflow_name,
                    job_name=job_name,
                    timestamp=run_info.timestamp,
                )
            )
        return results

    def _parse_phpunit(
        self,
        content: str,
        run_info: RunInfo,
        job_name: str,
    ) -> list[TestResult]:
        r"""Parse PHPUnit/Pest test output.

        Format:
          PASS  Tests\Path\TestName
          FAIL  Tests\Path\TestName
          Tests: N passed (M assertions)
        """
        clean = self._strip_ansi(content)
        results: list[TestResult] = []
        for match in PHPUNIT_LINE.finditer(clean):
            status_str = match.group(1)
            test_name = match.group(2).replace("\\", ".")
            status = STATUS_MAP.get(status_str)
            if status is None:
                continue
            results.append(
                TestResult(
                    test_name=test_name,
                    status=status,
                    error_message="",
                    stack_trace="",
                    timing_seconds=0.0,
                    run_id=run_info.run_id,
                    workflow_name=run_info.workflow_name,
                    job_name=job_name,
                    timestamp=run_info.timestamp,
                )
            )
        return results

    def _parse_rspec(
        self,
        content: str,
        run_info: RunInfo,
        job_name: str,
    ) -> list[TestResult]:
        """Parse RSpec output.

        Matches summary line and individual failure blocks:
          N examples, M failures, K pending
          N) TestName should do something (FAILED)
        """
        results: list[TestResult] = []
        for match in RSPEC_FAILURE.finditer(content):
            test_name = match.group(2).strip()
            results.append(
                TestResult(
                    test_name=test_name, status=TestStatus.FAILED,
                    error_message="", stack_trace="",
                    timing_seconds=0.0, run_id=run_info.run_id,
                    workflow_name=run_info.workflow_name,
                    job_name=job_name, timestamp=run_info.timestamp,
                )
            )
        return results

    def _parse_minitest(
        self,
        content: str,
        run_info: RunInfo,
        job_name: str,
    ) -> list[TestResult]:
        """Parse Minitest output.

        Summary: N runs, M assertions, K failures, E errors, S skips
        """
        results: list[TestResult] = []
        for match in MINITEST_SUMMARY.finditer(content):
            failures = int(match.group(3))
            if failures > 0:
                results.append(
                    TestResult(
                        test_name="minitest_summary", status=TestStatus.FAILED,
                        error_message=f"{failures} failures",
                        stack_trace="", timing_seconds=0.0,
                        run_id=run_info.run_id,
                        workflow_name=run_info.workflow_name,
                        job_name=job_name, timestamp=run_info.timestamp,
                    )
                )
        return results

    def _parse_mocha(
        self,
        content: str,
        run_info: RunInfo,
        job_name: str,
    ) -> list[TestResult]:
        """Parse Mocha output.

        ✓ test name
        ✗ test name
        N passing, N failing
        """
        clean = self._strip_ansi(content)
        results: list[TestResult] = []
        for match in MOCHA_LINE.finditer(clean):
            symbol = match.group(1)
            test_name = match.group(2).strip()
            status = STATUS_MAP.get(symbol)
            if status is None:
                continue
            results.append(
                TestResult(
                    test_name=test_name, status=status,
                    error_message="", stack_trace="",
                    timing_seconds=0.0, run_id=run_info.run_id,
                    workflow_name=run_info.workflow_name,
                    job_name=job_name, timestamp=run_info.timestamp,
                )
            )
        return results

    def _parse_junit(
        self,
        content: str,
        run_info: RunInfo,
        job_name: str,
    ) -> list[TestResult]:
        """Parse JUnit/Gradle test output.

        Tests run: N, Failures: M, Errors: E, Skipped: S
        testMethod(TestClass)  Time elapsed: Ns  <<< FAILURE!
        """
        results: list[TestResult] = []
        for match in JUNIT_FAILURE.finditer(content):
            test_name = f"{match.group(2)}.{match.group(1)}"
            results.append(
                TestResult(
                    test_name=test_name, status=TestStatus.FAILED,
                    error_message="", stack_trace="",
                    timing_seconds=0.0, run_id=run_info.run_id,
                    workflow_name=run_info.workflow_name,
                    job_name=job_name, timestamp=run_info.timestamp,
                )
            )
        return results

    def _parse_cypress(
        self,
        content: str,
        run_info: RunInfo,
        job_name: str,
    ) -> list[TestResult]:
        """Parse Cypress test output.

        ✓ TestName (Nms)
        ✗ TestName (Nms)
        """
        clean = self._strip_ansi(content)
        results: list[TestResult] = []
        for match in CYPRESS_LINE.finditer(clean):
            symbol = match.group(1)
            test_name = match.group(2).strip()
            status = STATUS_MAP.get(symbol)
            if status is None:
                continue
            results.append(
                TestResult(
                    test_name=test_name, status=status,
                    error_message="", stack_trace="",
                    timing_seconds=0.0, run_id=run_info.run_id,
                    workflow_name=run_info.workflow_name,
                    job_name=job_name, timestamp=run_info.timestamp,
                )
            )
        return results

    def _extract_timing(self, content: str) -> float:
        match = TIMING_PATTERN.search(content)
        if match:
            return float(match.group(1))
        return 0.0

    def _extract_pytest_failure_blocks(
        self,
        content: str,
    ) -> dict[str, dict[str, str]]:
        blocks: dict[str, dict[str, str]] = {}
        lines = content.splitlines()
        i = 0
        while i < len(lines):
            m = PYTEST_FAILURE_HEADER.match(lines[i])
            if m and m.group(1).strip():
                func_name = m.group(1).strip()
                i += 1
                block_lines: list[str] = []
                while i < len(lines):
                    if PYTEST_FAILURE_HEADER.match(lines[i]):
                        break
                    block_lines.append(lines[i])
                    i += 1
                block_text = "\n".join(block_lines)
                error_e_lines = [
                    line[2:].strip()
                    for line in block_lines
                    if line.startswith("E ")
                ]
                error_message = "\n".join(error_e_lines) if error_e_lines else ""
                # Also check for the summary error line: file:line: ErrorType
                summary_error_match = re.search(
                    r"^[\w./]+:\d+:\s+(.+)$", block_text, re.MULTILINE
                )
                if summary_error_match and not error_message:
                    error_message = summary_error_match.group(1)
                blocks[func_name] = {
                    "stack_trace": block_text.strip(),
                    "error_message": error_message.strip(),
                }
                continue
            i += 1
        return blocks

    def _extract_unittest_failure_blocks(
        self,
        content: str,
    ) -> dict[str, dict[str, str]]:
        blocks: dict[str, dict[str, str]] = {}
        lines = content.splitlines()
        i = 0
        while i < len(lines):
            m = UNITTEST_FAILURE_HEADER.match(lines[i])
            if m:
                test_name_short = m.group(2)
                i += 1
                block_lines: list[str] = []
                while i < len(lines):
                    if UNITTEST_FAILURE_HEADER.match(lines[i]):
                        break
                    if lines[i].startswith("---"):
                        i += 1
                        continue
                    if re.match(r"^={60,}", lines[i]):
                        break
                    if lines[i].startswith("Ran "):
                        break
                    block_lines.append(lines[i])
                    i += 1
                block_text = "\n".join(block_lines)
                error_line = ""
                for line in reversed(block_lines):
                    line_stripped = line.strip()
                    if line_stripped and not line_stripped.startswith(
                        "Traceback"
                    ) and not line_stripped.startswith("File "):
                        error_line = line_stripped
                        break
                blocks[test_name_short] = {
                    "stack_trace": block_text.strip(),
                    "error_message": error_line,
                }
                continue
            i += 1
        return blocks
