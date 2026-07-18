from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

from flake_sleuth.llm import LLMAdapter, _make_serializable
from flake_sleuth.types import Classification, FailureCategory, TestResult, TestStatus

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


def test_init_defaults() -> None:
    adapter = LLMAdapter()
    assert adapter.provider == "omlx"
    assert adapter.model == "qwen2.5-coder:7b"
    assert adapter.endpoint == "http://localhost:11434"
    assert adapter.api_key is None
    assert adapter.timeout == 60
    assert adapter.max_tokens == 4096


def test_init_custom() -> None:
    adapter = LLMAdapter(
        provider="openai",
        model="gpt-4o-mini",
        endpoint="https://api.openai.com/v1",
        api_key="sk-test",
        timeout=30,
    )
    assert adapter.provider == "openai"
    assert adapter.model == "gpt-4o-mini"
    assert adapter.api_key == "sk-test"


def test_build_prompt_includes_test_info() -> None:
    adapter = LLMAdapter()
    prompt = adapter._build_prompt(SAMPLE_TEST)
    assert SAMPLE_TEST.test_name in prompt
    assert SAMPLE_TEST.error_message in prompt
    assert "REAL_BUG" in prompt
    assert "FLAKY" in prompt
    assert "INFRA" in prompt
    assert "JSON" in prompt
    assert "no reasoning" in prompt or "no explanation" in prompt


def test_build_prompt_includes_cross_run_context() -> None:
    adapter = LLMAdapter()
    ctx = {"total_executions": 95, "failure_rate": 0.15}
    prompt = adapter._build_prompt(SAMPLE_TEST, ctx)
    assert "total_executions" in prompt
    assert "failure_rate" in prompt


def test_parse_response_valid_json() -> None:
    adapter = LLMAdapter()
    response = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"category": "FLAKY", "evidence": "intermittent", "confidence": 0.8}'
                    )
                }
            }
        ]
    }
    result = adapter._parse_response(response, SAMPLE_TEST)
    assert result.category == FailureCategory.FLAKY
    assert result.confidence == 0.8
    assert "llm:omlx:qwen2.5-coder:7b" in result.classified_by


def test_parse_response_real_bug() -> None:
    adapter = LLMAdapter()
    response = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"category": "REAL_BUG", "evidence": "dominant 90%",'
                        ' "confidence": 0.95}'
                    )
                }
            }
        ]
    }
    result = adapter._parse_response(response, SAMPLE_TEST)
    assert result.category == FailureCategory.REAL_BUG
    assert result.confidence == 0.95


def test_parse_response_infra() -> None:
    adapter = LLMAdapter()
    response = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"category": "INFRA", "evidence": "timeout", "confidence": 0.9}'
                    )
                }
            }
        ]
    }
    result = adapter._parse_response(response, SAMPLE_TEST)
    assert result.category == FailureCategory.INFRA


def test_parse_response_malformed_json_falls_back() -> None:
    adapter = LLMAdapter()
    response = {"choices": [{"message": {"content": "not json"}}]}
    result = adapter._parse_response(response, SAMPLE_TEST)
    assert result.category == FailureCategory.FLAKY
    assert result.confidence == 0.5
    assert "llm-parse-error" in result.classified_by


def test_parse_response_missing_choices_falls_back() -> None:
    adapter = LLMAdapter()
    response: dict = {}
    result = adapter._parse_response(response, SAMPLE_TEST)
    assert result.category == FailureCategory.FLAKY
    assert result.confidence == 0.5
    assert "llm-parse-error" in result.classified_by


def test_parse_response_truncated_marked_distinctly() -> None:
    """A response cut off (finish_reason=length) is tagged llm-truncated, not llm."""
    adapter = LLMAdapter()
    response = {
        "choices": [
            {
                "finish_reason": "length",
                "message": {"content": "Okay, let's think about this..."},
            }
        ]
    }
    result = adapter._parse_response(response, SAMPLE_TEST)
    assert result.category == FailureCategory.FLAKY
    assert result.confidence == 0.5
    assert "llm-truncated" in result.classified_by
    assert "truncated" in result.evidence


def test_parse_response_real_verdict_keeps_llm_prefix() -> None:
    """A successfully-parsed verdict keeps the honest llm: prefix."""
    adapter = LLMAdapter()
    response = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": (
                        '{"category": "REAL_BUG", "evidence": "det",'
                        ' "confidence": 0.9}'
                    )
                },
            }
        ]
    }
    result = adapter._parse_response(response, SAMPLE_TEST)
    assert result.category == FailureCategory.REAL_BUG
    assert result.classified_by.startswith("llm:")
    assert "llm-truncated" not in result.classified_by
    assert "llm-parse-error" not in result.classified_by


def test_parse_response_clamps_confidence() -> None:
    adapter = LLMAdapter()
    response = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"category": "FLAKY", "evidence": "x", "confidence": 1.5}'
                    )
                }
            }
        ]
    }
    result = adapter._parse_response(response, SAMPLE_TEST)
    assert result.confidence == 1.0
    response["choices"][0]["message"]["content"] = (
        '{"category": "FLAKY", "evidence": "x", "confidence": -0.5}'
    )
    result = adapter._parse_response(response, SAMPLE_TEST)
    assert result.confidence == 0.0


@patch("requests.post")
def test_omlx_call_success(mock_post) -> None:
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "choices": [
            {"message": {"content": '{"category": "FLAKY", "evidence": "x", "confidence": 0.7}'}}
        ]
    }
    adapter = LLMAdapter(provider="omlx")
    result = adapter.classify_ambiguous(SAMPLE_TEST)
    assert result.category == FailureCategory.FLAKY
    mock_post.assert_called_once()


@patch("requests.post")
def test_omlx_call_failure_falls_back_to_flaky(mock_post) -> None:
    import requests
    mock_post.side_effect = requests.RequestException("connection refused")
    adapter = LLMAdapter(provider="omlx")
    result = adapter.classify_ambiguous(SAMPLE_TEST)
    assert result.category == FailureCategory.FLAKY
    assert "LLM call failed" in result.evidence
    assert "llm-fallback" in result.classified_by


@patch("requests.post")
def test_openai_adapter_adds_bearer(mock_post) -> None:
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "choices": [
            {"message": {"content": '{"category": "FLAKY", "evidence": "x", "confidence": 0.7}'}}
        ]
    }
    adapter = LLMAdapter(
        provider="openai",
        model="gpt-4o-mini",
        endpoint="https://api.openai.com/v1",
        api_key="sk-test",
    )
    adapter.classify_ambiguous(SAMPLE_TEST)
    call_kwargs = mock_post.call_args[1]
    assert call_kwargs["headers"]["Authorization"] == "Bearer sk-test"


@patch("requests.post")
def test_disable_thinking_sends_template_kwargs(mock_post) -> None:
    """disable_thinking injects chat_template_kwargs.enable_thinking=False."""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "choices": [
            {"message": {"content": '{"category": "FLAKY", "evidence": "x", "confidence": 0.7}'}}
        ]
    }
    adapter = LLMAdapter(provider="omlx", disable_thinking=True)
    adapter.classify_ambiguous(SAMPLE_TEST)
    call_body = mock_post.call_args[1]["json"]
    assert call_body["chat_template_kwargs"] == {"enable_thinking": False}


@patch("requests.post")
def test_thinking_enabled_by_default_omits_template_kwargs(mock_post) -> None:
    """Without disable_thinking, no chat_template_kwargs are sent."""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "choices": [
            {"message": {"content": '{"category": "FLAKY", "evidence": "x", "confidence": 0.7}'}}
        ]
    }
    adapter = LLMAdapter(provider="omlx")
    adapter.classify_ambiguous(SAMPLE_TEST)
    call_body = mock_post.call_args[1]["json"]
    assert "chat_template_kwargs" not in call_body


class TestMakeSerializable:
    """Coverage for _make_serializable branches (dataclass, dict, list, enum, datetime)."""

    def test_dataclass(self) -> None:
        from dataclasses import dataclass
        @dataclass
        class D:
            x: int = 1
            y: str = "a"
        result = _make_serializable(D())
        assert result == {"x": 1, "y": "a"}

    def test_dict(self) -> None:
        result = _make_serializable({"a": [1, 2], "b": {"c": 3}})
        assert result == {"a": [1, 2], "b": {"c": 3}}

    def test_list(self) -> None:
        result = _make_serializable([1, "two", 3.0])
        assert result == [1, "two", 3.0]

    def test_enum(self) -> None:
        from flake_sleuth.types import TestStatus
        result = _make_serializable(TestStatus.FAILED)
        assert result == "FAILED"

    def test_datetime(self) -> None:
        from datetime import datetime
        dt = datetime(2026, 7, 18, tzinfo=UTC)
        result = _make_serializable(dt)
        assert "2026-07-18" in result

    def test_plain_value(self) -> None:
        result = _make_serializable(42)
        assert result == 42


class TestAdapterCache:
    """Coverage for LLM cache methods."""

    def test_cache_hit_returns_cached(self, tmp_path: Any) -> None:
        cache_dir = str(tmp_path / "cache")
        adapter = LLMAdapter(cache_dir=cache_dir)
        key = adapter._cache_key("tests/test_a.py::test_b")
        cls = Classification(
            test_name="tests/test_a.py::test_b", run_id=1,
            category=FailureCategory.FLAKY, evidence="cached",
            confidence=0.5, classified_by="rules",
        )
        adapter._save_cache(key, cls)
        loaded = adapter._load_cache(key)
        assert loaded is not None
        assert loaded.test_name == "tests/test_a.py::test_b"
        assert loaded.category == FailureCategory.FLAKY

    def test_cache_miss_returns_none(self) -> None:
        adapter = LLMAdapter()
        result = adapter._load_cache("nonexistent_key.json")
        assert result is None

    def test_classify_ambiguous_uses_cache(self, tmp_path: Any) -> None:
        cache_dir = str(tmp_path / "cache2")
        adapter = LLMAdapter(cache_dir=cache_dir)
        key = adapter._cache_key(SAMPLE_TEST.test_name)
        cls = Classification(
            test_name=SAMPLE_TEST.test_name, run_id=SAMPLE_TEST.run_id,
            category=FailureCategory.INFRA, evidence="cached",
            confidence=0.9, classified_by="rules",
        )
        adapter._save_cache(key, cls)
        result = adapter.classify_ambiguous(SAMPLE_TEST)
        assert result.category == FailureCategory.INFRA
        assert result.confidence == 0.9


class TestMaxTokens:
    """Coverage for max_tokens param."""

    @patch("requests.post")
    def test_max_tokens_sent_in_request(self, mock_post: Any) -> None:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "choices": [
                {"message": {
                    "content": '{"category": "FLAKY", "evidence": "x", "confidence": 0.7}'
                }}
            ]
        }
        adapter = LLMAdapter(max_tokens=8192)
        adapter.classify_ambiguous(SAMPLE_TEST)
        call_body = mock_post.call_args[1]["json"]
        assert call_body["max_tokens"] == 8192
