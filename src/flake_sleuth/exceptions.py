"""Custom exceptions for ai-flake-sleuth.

All pipeline-specific errors inherit from FlakeSleuthError so callers
can catch them selectively without catching built-in exceptions.

Hierarchy::

    FlakeSleuthError
    ├── GitHubAPIError           — non-429 HTTP errors
    ├── RateLimitExhaustedError  — 429 after exhausting retries
    ├── LogExpiredError          — 410 Gone on log download
    ├── LogParseError            — regex / LLM failed to parse a log
    ├── LLMError                 — LLM call failed
    └── GraphError               — LangGraph node raised an error
"""


class FlakeSleuthError(Exception):
    """Base exception for all ai-flake-sleuth errors.

    Catch this in top-level handlers to report any pipeline failure.
    """


class GitHubAPIError(FlakeSleuthError):
    """GitHub API request failed with a non-429 HTTP error.

    Raised when the API returns 4xx (except 429) or 5xx and retries
    are exhausted.
    """

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"GitHub API error {status_code}: {message}")


class RateLimitExhaustedError(FlakeSleuthError):
    """GitHub API rate limit exhausted after all retries.

    Raised when remaining requests hit zero or 429 responses persist
    past ``max_retries``.
    """

    def __init__(self, reset_at: int) -> None:
        self.reset_at = reset_at  # Unix timestamp when the bucket refills
        super().__init__(f"rate limit exhausted, resets at {reset_at}")


class LogExpiredError(FlakeSleuthError):
    """GitHub Actions log has expired (>90 days old).

    The API returns 410 Gone. This is permanent — retrying won't help.
    """

    def __init__(self, run_id: int) -> None:
        self.run_id = run_id
        super().__init__(f"logs for run {run_id} expired (410 Gone)")


class LogParseError(FlakeSleuthError):
    """Failed to parse test results from a CI job log.

    Neither regex patterns nor the LLM fallback could extract test results.
    """

    def __init__(self, run_id: int, reason: str) -> None:
        self.run_id = run_id
        self.reason = reason
        super().__init__(f"log parse failed for run {run_id}: {reason}")


class LLMError(FlakeSleuthError):
    """LLM call failed for ambiguous classification.

    Covers timeouts, connection errors, and unexpected response formats
    from any supported provider (OMLX, OpenAI, DeepSeek).
    """

    def __init__(self, provider: str, error: str) -> None:
        self.provider = provider
        self.error = error
        super().__init__(f"LLM '{provider}' failed: {error}")


class GraphError(FlakeSleuthError):
    """LangGraph pipeline execution failed in a specific node.

    Wraps exceptions raised inside graph nodes so the graph can route
    to an error handler instead of crashing.
    """

    def __init__(self, node: str, error: str) -> None:
        self.node = node
        self.error = error
        super().__init__(f"graph error in node '{node}': {error}")
