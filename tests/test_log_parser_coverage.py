from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from flake_sleuth.log_parser import LogParser
from flake_sleuth.types import JobInfo, RunInfo, TestStatus


def _run_info(jobs: list[JobInfo] | None = None) -> RunInfo:
    return RunInfo(
        run_id=1001,
        workflow_name="CI",
        status="completed",
        conclusion="failure",
        timestamp=datetime(2026, 7, 16, tzinfo=UTC),
        html_url="",
        jobs=jobs or [],
    )


def test_identify_job_multiple_jobs_matches_name() -> None:
    jobs = [
        JobInfo(job_id=1, name="test (3.11)", conclusion="failure", logs_url=""),
        JobInfo(job_id=2, name="test (3.14)", conclusion="success", logs_url=""),
    ]
    parser = LogParser()
    result = parser._identify_job("test (3.14)", jobs)
    assert result == "test (3.14)"


def test_identify_job_multiple_jobs_uses_filename() -> None:
    jobs = [
        JobInfo(job_id=1, name="lint", conclusion="failure", logs_url=""),
        JobInfo(job_id=2, name="deploy", conclusion="success", logs_url=""),
    ]
    parser = LogParser()
    result = parser._identify_job("build", jobs)
    assert result == "build"


def test_llm_fallback_warning() -> None:
    """When llm_adapter is set and no parser matches, a warning is logged."""
    ri = _run_info()
    logs = {"job_log.txt": "unparsable garbage"}
    mock_llm = MagicMock()
    parser = LogParser(llm_adapter=mock_llm)
    results = parser.parse(ri, logs)
    assert results == []


def test_pytest_unknown_status_skipped() -> None:
    content = "tests/test_a.py::test_foo NOT_A_STATUS\n"
    ri = _run_info()
    parser = LogParser()
    results = parser.parse(ri, {"job_log.txt": content})
    assert results == []


def test_unittest_unknown_status_skipped() -> None:
    content = "test_foo (tests.test_a.FooTest) ... NOT_A_STATUS\n"
    ri = _run_info()
    parser = LogParser()
    results = parser.parse(ri, {"job_log.txt": content})
    assert results == []


def test_pytest_summary_error_line() -> None:
    """When there's no '  File' in traceback, the summary error line is used."""
    content = (
        "tests/test_b.py::test_bar FAILED\n"
        "======= FAILURES =======\n"
        "_______ test_bar ________\n"
        "tests/test_b.py:5: AssertionError\n"
        "assert False\n"
    )
    ri = _run_info()
    parser = LogParser()
    results = parser.parse(ri, {"job_log.txt": content})
    assert len(results) == 1
    assert results[0].test_name == "tests/test_b.py::test_bar"
    assert results[0].status == TestStatus.FAILED
    assert "AssertionError" in results[0].error_message


def test_unittest_multiple_failure_blocks() -> None:
    """Blocks are parsed independently; covers break on next FAIL header."""
    textblock = (
        "test_one (tests.test_demo.DemoTest) ... FAIL\n"
        "test_two (tests.test_demo.DemoTest) ... FAIL\n"
        "FAIL: test_one (tests.test_demo.DemoTest)\n"
        "----------------------------------------------------------------------\n"
        "Traceback (most recent call last):\n"
        "  File \"/path/demo.py\", line 10, in test_one\n"
        "    self.assertTrue(False)\n"
        "AssertionError: False is not true\n"
        "FAIL: test_two (tests.test_demo.DemoTest)\n"
        "----------------------------------------------------------------------\n"
        "Traceback (most recent call last):\n"
        "  File \"/path/demo.py\", line 20, in test_two\n"
        "    self.assertTrue(False)\n"
        "AssertionError: False is not true\n"
    )
    ri = _run_info()
    parser = LogParser()
    results = parser.parse(ri, {"job_log.txt": textblock})
    assert len(results) == 2
    assert results[0].test_name == "tests.test_demo.DemoTest.test_one"
    assert results[0].status == TestStatus.FAILED
    assert results[1].test_name == "tests.test_demo.DemoTest.test_two"
    assert results[1].status == TestStatus.FAILED


JEST_LOG = (
    "PASS packages/foo/bar.test.js\n"
    "FAIL packages/baz/qux.test.js\n"
    "  ● FooComponent › renders correctly\n"
    "    expect(received).toBe(expected)\n"
    "    Expected: true\n"
    "    Received: false\n"
    "\n"
    "      5 |   it('renders correctly', () => {\n"
    "    > 6 |     expect(wrapper.find('.foo')).toHaveLength(1);\n"
    "        |                                ^\n"
    "      7 |   });\n"
    "\n"
    "      at Object.<anonymous> (qux.test.js:6:32)\n"
    "\n"
    "  ● BarComponent › handles empty state\n"
    "    TypeError: Cannot read property 'length' of undefined\n"
    "\n"
    "      at BarComponent (bar.js:42)\n"
    "\n"
    "Test Suites: 1 failed, 5 passed, 6 total\n"
    "Tests:       2 failed, 42 passed, 44 total\n"
)

GENERIC_JS_LOG = (
    "FAIL __tests__/integration/api.test.ts\n"
    "PASS src/components/header.spec.jsx\n"
    "ERROR tests/e2e/login.e2e.ts\n"
)


class TestJestParsing:
    def test_parses_jest_suite_failures(self) -> None:
        parser = LogParser()
        results = parser.parse(_run_info(), {"job_log.txt": JEST_LOG})
        assert len(results) == 2
        names = {r.test_name for r in results}
        assert any("packages.foo.bar.test.js" in n for n in names)
        assert any("packages.baz.qux.test.js" in n for n in names)

    def test_parses_jest_failed_status(self) -> None:
        parser = LogParser()
        results = parser.parse(_run_info(), {"job_log.txt": JEST_LOG})
        for r in results:
            if "qux" in r.test_name:
                assert r.status == TestStatus.FAILED
                break
        else:
            pytest.fail("No FAILED test found")

    def test_jest_extracts_error_message(self) -> None:
        parser = LogParser()
        results = parser.parse(_run_info(), {"job_log.txt": JEST_LOG})
        for r in results:
            if "qux" in r.test_name:
                assert "FooComponent" in r.error_message
                assert "expect" in r.error_message or "toBe" in r.error_message
                break
        else:
            pytest.fail("No FAILED test found")

    def test_jest_skips_passed_suites(self) -> None:
        parser = LogParser()
        results = parser.parse(_run_info(), {"job_log.txt": JEST_LOG})
        for r in results:
            if "bar.test.js" in r.test_name:
                assert r.status == TestStatus.PASSED
                break
        else:
            pytest.fail("No PASSED test found")

    def test_generic_js_framework_fallback(self) -> None:
        parser = LogParser()
        results = parser.parse(_run_info(), {"job_log.txt": GENERIC_JS_LOG})
        assert len(results) == 3
        names = {r.test_name for r in results}
        assert any("__tests__.integration.api.test.ts" in n for n in names)
        assert any("src.components.header.spec.jsx" in n for n in names)
        assert any("tests.e2e.login.e2e.ts" in n for n in names)


RSPEC_LOG = (
    "1) RuboCop::Cop::Lint::ConstantReassignment should detect nested assignment\n"
    "   Failure/Error: expect(x).to eq(y)\n"
    "     expected: true\n"
    "          got: false\n"
    "   # ./spec/rubocop/cop/lint/constant_reassignment_spec.rb:42\n"
)

MINITEST_LOG = (
    "2026-07-16T12:21:56Z 100 runs, 200 assertions, 3 failures, 1 errors, 0 skips\n"
)

MOCHA_LOG = (
    "2026-07-16T12:21:56Z   ✓ should render component\n"
    "2026-07-16T12:21:56Z   ✗ should handle error\n"
    "2026-07-16T12:21:56Z   1 passing (10ms)\n"
    "2026-07-16T12:21:56Z   1 failing\n"
)

JUNIT_LOG = (
    "2026-07-16T12:21:56Z testMethod(TestClass)  Time elapsed: 1.234s  <<< FAILURE!\n"
    "2026-07-16T12:21:56Z Tests run: 5, Failures: 1, Errors: 0, Skipped: 0\n"
)

CYPRESS_LOG = (
    "2026-07-16T12:21:56Z   ✓ renders correctly (234ms)\n"
    "2026-07-16T12:21:56Z   ✗ handles empty state (567ms)\n"
)


class TestNewParsers:
    def test_rspec_extracts_failures(self) -> None:
        parser = LogParser()
        results = parser.parse(_run_info(), {"job_log.txt": RSPEC_LOG})
        assert len(results) >= 1
        assert any("ConstantReassignment" in r.test_name for r in results)

    def test_minitest_extracts_failures(self) -> None:
        parser = LogParser()
        results = parser.parse(_run_info(), {"job_log.txt": MINITEST_LOG})
        assert len(results) >= 1
        for r in results:
            assert r.status == TestStatus.FAILED
            assert "3 failures" in r.error_message

    def test_mocha_extracts_results(self) -> None:
        parser = LogParser()
        results = parser.parse(_run_info(), {"job_log.txt": MOCHA_LOG})
        assert len(results) == 2
        names = {r.test_name for r in results}
        assert any("render component" in n for n in names)
        assert any("handle error" in n for n in names)

    def test_junit_extracts_failures(self) -> None:
        parser = LogParser()
        results = parser.parse(_run_info(), {"job_log.txt": JUNIT_LOG})
        assert len(results) >= 1
        assert any("TestClass.testMethod" in r.test_name for r in results)

    def test_cypress_extracts_results(self) -> None:
        parser = LogParser()
        results = parser.parse(_run_info(), {"job_log.txt": CYPRESS_LOG})
        assert len(results) == 2
        names = {r.test_name for r in results}
        assert any("renders correctly" in n for n in names)
        assert any("handles empty state" in n for n in names)
