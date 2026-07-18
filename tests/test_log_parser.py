from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from flake_sleuth.log_parser import LogParser
from flake_sleuth.types import JobInfo, RunInfo, TestStatus


@pytest.fixture
def sample_logs_dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "sample_logs"


@pytest.fixture
def run_info() -> RunInfo:
    return RunInfo(
        run_id=1001,
        workflow_name="CI",
        status="completed",
        conclusion="failure",
        timestamp=datetime(2026, 7, 16, tzinfo=UTC),
        html_url="https://github.com/owner/repo/actions/runs/1001",
        jobs=[JobInfo(job_id=10010, name="test (3.11)", conclusion="failure", logs_url="")],
    )


def _load_log(sample_logs_dir: Path, name: str) -> dict[str, str]:
    return {"job_log.txt": (sample_logs_dir / name).read_text()}


class TestPytestParsing:

    def test_parses_failed_pytest_log(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "pytest_failed.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        assert len(results) == 3
        names = {r.test_name for r in results}
        assert "tests/test_auth.py::test_login_redirect" in names
        assert "tests/test_auth.py::test_logout" in names
        assert "tests/test_parser.py::test_edge_case" in names

    def test_extracts_failed_status(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "pytest_failed.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        for r in results:
            if r.test_name == "tests/test_auth.py::test_login_redirect":
                assert r.status == TestStatus.FAILED
                break
        else:
            pytest.fail("test not found")

    def test_extracts_passed_status(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "pytest_failed.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        for r in results:
            if r.test_name == "tests/test_auth.py::test_logout":
                assert r.status == TestStatus.PASSED
                break
        else:
            pytest.fail("test not found")

    def test_extracts_error_message(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "pytest_failed.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        for r in results:
            if r.test_name == "tests/test_auth.py::test_login_redirect":
                assert "AssertionError" in r.error_message
                assert r.error_message  # non-empty
                break
        else:
            pytest.fail("test not found")

    def test_extracts_stack_trace_for_failed(
        self, sample_logs_dir: Path, run_info: RunInfo
    ) -> None:
        logs = _load_log(sample_logs_dir, "pytest_failed.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        for r in results:
            if r.test_name == "tests/test_auth.py::test_login_redirect":
                assert "assert response.status_code == 302" in r.stack_trace
                break
        else:
            pytest.fail("test not found")

    def test_extracts_timing(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "pytest_failed.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        for r in results:
            assert r.timing_seconds == 0.32
            break

    def test_passed_test_has_no_error(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "pytest_failed.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        for r in results:
            if r.status == TestStatus.PASSED:
                assert r.error_message == ""
                assert r.stack_trace == ""
                break
        else:
            pytest.fail("no passed test found")


class TestUnittestParsing:

    def test_parses_failed_unittest_log(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "unittest_failed.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        assert len(results) == 3

    def test_extracts_test_names(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "unittest_failed.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        names = {r.test_name for r in results}
        assert "test_auth.TestAuth.test_login_redirect" in names
        assert "test_auth.TestAuth.test_logout" in names
        assert "test_parser.TestParser.test_edge_case" in names

    def test_maps_status_correctly(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "unittest_failed.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        status_map = {r.test_name: r.status for r in results}
        assert status_map["test_auth.TestAuth.test_login_redirect"] == TestStatus.FAILED
        assert status_map["test_auth.TestAuth.test_logout"] == TestStatus.PASSED
        assert status_map["test_parser.TestParser.test_edge_case"] == TestStatus.ERROR

    def test_extracts_error_message(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "unittest_failed.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        for r in results:
            if r.test_name == "test_auth.TestAuth.test_login_redirect":
                assert "AssertionError" in r.error_message or "200 != 302" in r.error_message
                break
        else:
            pytest.fail("test not found")

    def test_extracts_stack_trace(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "unittest_failed.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        for r in results:
            if r.test_name == "test_auth.TestAuth.test_login_redirect":
                assert "Traceback" in r.stack_trace
                assert "self.assertEqual" in r.stack_trace
                break
        else:
            pytest.fail("test not found")

    def test_extracts_timing(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "unittest_failed.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        for r in results:
            assert r.timing_seconds == 0.25
            break


class TestCleanRun:

    def test_parses_clean_log(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "clean_run.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        assert len(results) == 3

    def test_all_passed(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "clean_run.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        assert all(r.status == TestStatus.PASSED for r in results)

    def test_no_error_messages(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "clean_run.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        assert all(r.error_message == "" for r in results)

    def test_timing_extracted(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "clean_run.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        for r in results:
            assert r.timing_seconds == 0.12
            break

    def test_no_stack_traces(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "clean_run.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        assert all(r.stack_trace == "" for r in results)


class TestInfraLog:

    def test_parses_infra_log(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "infra_timeout.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        assert len(results) == 2

    def test_extracts_connection_errors(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "infra_timeout.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        for r in results:
            assert r.status == TestStatus.FAILED
            assert r.error_message  # non-empty

    def test_error_message_mentions_timeout(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "infra_timeout.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        for r in results:
            if "test_external_api" in r.test_name:
                assert "ConnectionError" in r.error_message or "timed out" in r.error_message
                break
        else:
            pytest.fail("test_external_api not found")


class TestRunInfoMetadata:

    def test_run_id_carried_to_results(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "pytest_failed.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        for r in results:
            assert r.run_id == run_info.run_id

    def test_workflow_name_carried(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "pytest_failed.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        for r in results:
            assert r.workflow_name == run_info.workflow_name

    def test_job_name_mapped(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "pytest_failed.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        for r in results:
            assert r.job_name == "test (3.11)"

    def test_timestamp_carried(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = _load_log(sample_logs_dir, "pytest_failed.txt")
        parser = LogParser()
        results = parser.parse(run_info, logs)
        for r in results:
            assert r.timestamp == run_info.timestamp


class TestEdgeCases:

    def test_empty_log_returns_empty(self, run_info: RunInfo) -> None:
        parser = LogParser()
        results = parser.parse(run_info, {})
        assert results == []

    def test_no_matching_pattern_logs_warning(
        self, run_info: RunInfo, caplog: pytest.LogCaptureFixture
    ) -> None:
        logs = {"unknown.txt": "some random output that doesn't match any pattern"}
        parser = LogParser()
        results = parser.parse(run_info, logs)
        assert results == []
        assert "No parser matched" in caplog.text

    def test_log_without_timing_defaults_to_zero(self, run_info: RunInfo) -> None:
        logs = {"job.txt": "tests/test_foo.py::test_bar PASSED"}
        parser = LogParser()
        results = parser.parse(run_info, logs)
        for r in results:
            assert r.timing_seconds == 0.0

    def test_multiple_log_files_all_parsed(self, sample_logs_dir: Path, run_info: RunInfo) -> None:
        logs = {
            "job1.txt": (sample_logs_dir / "pytest_failed.txt").read_text(),
            "job2.txt": (sample_logs_dir / "clean_run.txt").read_text(),
        }
        parser = LogParser()
        results = parser.parse(run_info, logs)
        assert len(results) == 6
