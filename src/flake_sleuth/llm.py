"""LLM adapter for ambiguous classification fallback.

Supports OMLX (default, no auth), OpenAI, and DeepSeek providers via the
OpenAI-compatible /v1/chat/completions endpoint. Builds a structured prompt
with test context and optional cross-run statistics, then parses the JSON
response into a Classification.

All providers use the same code path — endpoint and optional api_key are
config, not hardcoded provider checks. API keys are read from env vars
by the caller (config.py), never stored in this module.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import requests

from flake_sleuth.exceptions import LLMError
from flake_sleuth.types import Classification, FailureCategory, TestResult

logger = logging.getLogger(__name__)


def _make_serializable(obj: Any) -> Any:
    """Convert non-serializable objects to plain dicts/strings for JSON.

    Handles dataclasses, datetimes, and enums recursively.
    """
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _make_serializable(v) for k, v in obj.__dict__.items()}
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_serializable(v) for v in obj]
    if isinstance(obj, Enum):
        return obj.name
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


class LLMAdapter:
    """Adapter for LLM classification (OMLX default, OpenAI-compatible cloud).

    All providers are treated uniformly: each has an endpoint and an optional
    api_key. No provider-specific branching in the request path.
    """

    VALID_PROVIDERS = frozenset({"omlx", "openai", "deepseek", "opencode"})

    def __init__(
        self,
        provider: str = "omlx",
        model: str = "qwen2.5-coder:7b",
        endpoint: str = "http://localhost:11434",
        api_key: str | None = None,
        timeout: int = 60,
        max_tokens: int = 4096,
        disable_thinking: bool = False,
        llm_log_dir: str | None = None,
        cache_dir: str | None = None,
    ) -> None:
        if provider not in self.VALID_PROVIDERS:
            raise LLMError(provider, f"unknown provider '{provider}'")
        self.provider = provider
        self.model = model
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.disable_thinking = disable_thinking
        self.llm_log_dir = Path(llm_log_dir) if llm_log_dir else None
        if self.llm_log_dir:
            self.llm_log_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._call_count = 0
        self._cache_hits = 0

    def classify_ambiguous(
        self,
        test_result: TestResult,
        cross_run_context: dict[str, Any] | None = None,
    ) -> Classification:
        """Classify an ambiguous test failure via LLM, with graceful fallback.

        Checks the on-disk response cache first. If cached, returns the
        stored Classification without making an API call. This enables
        analysis-phase resume: if analysis crashes after N LLM calls,
        re-running skips those N calls entirely.

        If the LLM call or parsing fails, falls back to a conservative
        FLAKY classification (safe default) instead of raising.
        """
        cache_key = self._cache_key(test_result.test_name)
        cached = self._load_cache(cache_key)
        if cached is not None:
            self._cache_hits += 1
            logger.debug("LLM cache hit for test %s", test_result.test_name)
            return cached

        prompt = self._build_prompt(test_result, cross_run_context)
        self._call_count += 1
        call_start = time.time()

        try:
            response_data = self._call_llm(prompt)
            latency = time.time() - call_start
            self._log_call(prompt, response_data, latency, test_result.test_name)
            result = self._parse_response(response_data, test_result)
            self._save_cache(cache_key, result)
            return result
        except LLMError as exc:
            latency = time.time() - call_start
            logger.warning(
                "LLM call failed for test %s (provider=%s, model=%s): %s — "
                "falling back to conservative FLAKY",
                test_result.test_name,
                self.provider,
                self.model,
                exc,
            )
            self._log_call(prompt, None, latency, test_result.test_name, error=str(exc))
            return Classification(
                test_name=test_result.test_name,
                run_id=test_result.run_id,
                category=FailureCategory.FLAKY,
                evidence=f"LLM call failed ({self.provider}): {exc}; defaulted to flaky",
                confidence=0.5,
                classified_by=f"llm-fallback:{self.provider}:{self.model}",
            )
        except Exception as exc:
            latency = time.time() - call_start
            logger.warning(
                "Unexpected error in LLM classification for test %s: %s — "
                "falling back to conservative FLAKY",
                test_result.test_name,
                exc,
            )
            self._log_call(prompt, None, latency, test_result.test_name, error=str(exc))
            return Classification(
                test_name=test_result.test_name,
                run_id=test_result.run_id,
                category=FailureCategory.FLAKY,
                evidence=f"LLM error ({self.provider}): {exc}; defaulted to flaky",
                confidence=0.5,
                classified_by=f"llm-fallback:{self.provider}:{self.model}",
            )

    def _cache_key(self, test_name: str) -> str:
        """Build a filesystem-safe cache key for a test name."""
        safe = test_name.replace("/", "_").replace("::", "_").replace(" ", "_")
        return f"{self.provider}_{self.model}_{safe}.json"

    def _load_cache(self, cache_key: str) -> Classification | None:
        """Load a cached Classification from disk, or None on miss."""
        if not self.cache_dir:
            return None
        path = self.cache_dir / cache_key
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return Classification(
                test_name=data["test_name"],
                run_id=data["run_id"],
                category=FailureCategory[data["category"]],
                evidence=data["evidence"],
                confidence=data["confidence"],
                classified_by=data["classified_by"],
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    def _save_cache(self, cache_key: str, cls: Classification) -> None:
        """Persist a Classification to the on-disk cache."""
        if not self.cache_dir:
            return
        path = self.cache_dir / cache_key
        data = {
            "test_name": cls.test_name,
            "run_id": cls.run_id,
            "category": cls.category.name,
            "evidence": cls.evidence,
            "confidence": cls.confidence,
            "classified_by": cls.classified_by,
        }
        path.write_text(json.dumps(data, indent=2))

    def _build_prompt(
        self,
        test_result: TestResult,
        cross_run_context: dict[str, Any] | None = None,
    ) -> str:
        """Build the prompt sent to the LLM for ambiguous classification.

        Includes the test name, error message, stack trace, and optionally
        cross-run statistics (e.g. total executions, failure rate) to help
        the LLM distinguish real bugs from flaky tests.
        """
        parts = [
            "You are a CI log classifier. Classify this test failure as one of:",
            "  REAL_BUG (reproducible, deterministic failure)",
            "  FLAKY (intermittent, non-deterministic)",
            "  INFRA (environment issue: timeout, OOM, network)",
            "",
            f"Test name: {test_result.test_name}",
            f"Error message: {test_result.error_message}",
            f"Stack trace: {test_result.stack_trace}",
        ]
        serializable = None
        if cross_run_context:
            serializable = _make_serializable(cross_run_context)
            parts.append(
                f"Cross-run context: {json.dumps(serializable, indent=2)}"
            )
        parts.append("")
        json_instruction = (
            'Respond with ONLY the JSON object below — no reasoning, no '
            'explanation, no markdown fences:\n'
            '{"category": "REAL_BUG|FLAKY|INFRA", "evidence": "one-sentence'
            ' justification", "confidence": 0.0-1.0}'
        )
        parts.append(json_instruction)
        prompt = "\n".join(parts)
        # Truncate cross-run context if total prompt exceeds 50K chars
        # (Vue/Vitest produces massive context). Keep it compact so the
        # instruction and JSON format stay visible at the end.
        if len(prompt) > 50_000 and serializable is not None:
            serialized = json.dumps(serializable, indent=2)
            max_data = 50_000 - len(json_instruction) - 200
            parts[7] = f"Cross-run context: {serialized[:max_data]}"
            prompt = "\n".join(parts)
        return prompt

    def _call_llm(self, prompt: str) -> dict[str, Any]:
        """POST to /v1/chat/completions with optional Bearer auth.

        All providers use the same code path. If api_key is set, a Bearer
        token is included. OMLX (local) simply has api_key=None.
        """
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": self.max_tokens,
        }
        if self.disable_thinking:
            body["chat_template_kwargs"] = {"enable_thinking": False}
        try:
            resp = requests.post(
                f"{self.endpoint}/v1/chat/completions",
                headers=headers,
                json=body,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return dict(resp.json())
        except requests.RequestException as exc:
            raise LLMError(self.provider, str(exc)) from exc

    def _parse_response(
        self,
        response_data: dict[str, Any],
        test_result: TestResult,
    ) -> Classification:
        """Parse the LLM JSON response into a Classification.

        Handles malformed JSON, missing keys, and out-of-range confidence
        values gracefully by falling back to FLAKY / 0.5. Records the
        exact model version returned by the API for reproducibility.

        Three distinct ``classified_by`` prefixes make the outcome
        auditable:

        * ``llm:<provider>:<model>``           — a real model verdict
        * ``llm-truncated:<provider>:<model>``  — response cut off
          (``finish_reason == "length"``) before JSON was emitted; no
          verdict was obtained, so we default to FLAKY
        * ``llm-parse-error:<provider>:<model>``— a response arrived but
          could not be parsed as the expected JSON; defaulted to FLAKY

        Call-level failures (network, timeout) are handled by the caller
        and tagged ``llm-fallback:`` so the four outcomes are disjoint.
        """
        actual_model = response_data.get("model", self.model)

        try:
            choice = response_data["choices"][0]
            finish_reason = choice.get("finish_reason")
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return Classification(
                test_name=test_result.test_name,
                run_id=test_result.run_id,
                category=FailureCategory.FLAKY,
                evidence="LLM response had no parseable choice; defaulted to flaky",
                confidence=0.5,
                classified_by=f"llm-parse-error:{self.provider}:{actual_model}",
            )

        if finish_reason == "length":
            return Classification(
                test_name=test_result.test_name,
                run_id=test_result.run_id,
                category=FailureCategory.FLAKY,
                evidence=(
                    f"LLM response truncated (finish_reason=length, "
                    f"max_tokens={self.max_tokens}); no verdict extracted, "
                    f"defaulted to flaky"
                ),
                confidence=0.5,
                classified_by=f"llm-truncated:{self.provider}:{actual_model}",
            )

        try:
            parsed = json.loads(content)
            category_str = parsed.get("category", "FLAKY").upper()
            try:
                category = FailureCategory[category_str]
            except KeyError:
                category = FailureCategory.FLAKY
            evidence = parsed.get("evidence", "LLM classification")
            confidence = float(parsed.get("confidence", 0.5))
        except (json.JSONDecodeError, TypeError, ValueError):
            return Classification(
                test_name=test_result.test_name,
                run_id=test_result.run_id,
                category=FailureCategory.FLAKY,
                evidence="LLM response could not be parsed as JSON; defaulted to flaky",
                confidence=0.5,
                classified_by=f"llm-parse-error:{self.provider}:{actual_model}",
            )
        return Classification(
            test_name=test_result.test_name,
            run_id=test_result.run_id,
            category=category,
            evidence=evidence,
            confidence=max(0.0, min(1.0, confidence)),
            classified_by=f"llm:{self.provider}:{actual_model}",
        )

    def _log_call(
        self,
        prompt: str,
        response: dict[str, Any] | None,
        latency: float,
        test_name: str,
        error: str | None = None,
    ) -> None:
        """Write a structured JSON log entry for each LLM call.

        Captures prompt, response, latency, token counts, and model version
        for reproducibility and the field study article.
        """
        if not self.llm_log_dir:
            return

        usage = {}
        actual_model = self.model
        finish_reason: str | None = None
        if response:
            usage = response.get("usage", {})
            actual_model = response.get("model", self.model)
            try:
                finish_reason = response["choices"][0].get("finish_reason")
            except (KeyError, IndexError, TypeError):
                finish_reason = None

        entry = {
            "call_number": self._call_count,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "provider": self.provider,
            "model_requested": self.model,
            "model_actual": actual_model,
            "test_name": test_name,
            "latency_seconds": round(latency, 3),
            "prompt": prompt,
            "response": response,
            "error": error,
            "finish_reason": finish_reason,
            "max_tokens": self.max_tokens,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }

        log_file = self.llm_log_dir / f"{self.provider}_{self._call_count:04d}.json"
        log_file.write_text(json.dumps(entry, indent=2, default=str))

    @property
    def call_count(self) -> int:
        """Number of LLM API calls made (excludes cache hits)."""
        return self._call_count

    @property
    def cache_hits(self) -> int:
        """Number of cache hits (calls avoided)."""
        return self._cache_hits
