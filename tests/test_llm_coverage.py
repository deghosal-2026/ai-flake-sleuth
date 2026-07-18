from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from flake_sleuth.exceptions import LLMError
from flake_sleuth.llm import LLMAdapter
from flake_sleuth.types import FailureCategory, TestResult, TestStatus

SAMPLE_TEST = TestResult(
    test_name="tests/test_auth.py::test_login",
    status=TestStatus.FAILED,
    error_message="AssertionError: assert 200 == 302",
    stack_trace="tests/test_auth.py:42: AssertionError",
    timing_seconds=0.32,
    run_id=1001,
    workflow_name="CI",
    job_name="test (3.11)",
    timestamp=datetime(2026, 7, 16, tzinfo=UTC),
)


def test_invalid_provider_raises() -> None:
    with pytest.raises(LLMError, match="unknown provider"):
        LLMAdapter(provider="nonexistent")


def test_parse_response_invalid_category_falls_back() -> None:
    adapter = LLMAdapter()
    response = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"category": "INVALID", "evidence": "x",'
                        ' "confidence": 0.7}'
                    )
                }
            }
        ]
    }
    result = adapter._parse_response(response, SAMPLE_TEST)
    assert result.category == FailureCategory.FLAKY


@patch("requests.post")
def test_non_request_exception_falls_back_to_flaky(mock_post: MagicMock) -> None:
    """A non-RequestException (e.g. AttributeError from .json()) falls back to FLAKY."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.side_effect = AttributeError("weird attr error")
    mock_post.return_value = mock_resp

    adapter = LLMAdapter(provider="omlx")
    result = adapter.classify_ambiguous(SAMPLE_TEST)
    assert result.category == FailureCategory.FLAKY
    assert "llm-fallback" in result.classified_by
