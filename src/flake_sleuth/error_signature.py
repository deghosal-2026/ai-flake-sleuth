"""Error-message normalizer for grouping failures by root cause.

Strips variable parts (file paths, line numbers, timestamps, PIDs, ports)
so that two failures with the same root cause but different local paths
produce the same stable hash signature.
"""

import hashlib
import re


class ErrorSignatureNormalizer:
    """Normalize error text and produce stable hash signatures for grouping.

    Two tests that fail with the same root cause but different local paths
    or line numbers will produce the same signature. Different root causes
    produce different signatures.
    """

    # (regex, replacement) pairs applied in order. Order matters: timestamps
    # must be stripped BEFORE line numbers so ':42:' inside an ISO timestamp
    # like '10:00:00' is not falsely replaced.
    NORMALIZE_PATTERNS: list[tuple[str, str]] = [
        # File paths — common CI runner locations
        (r"/Users/[^/\s]+/", "<PATH>/"),
        (r"/home/[^/\s]+/", "<PATH>/"),
        (r"/tmp/[^/\s]+/", "<PATH>/"),
        (r"/runner/[^/\s]+/", "<PATH>/"),
        # Timestamps — ISO 8601 and epoch (must come before line-number pattern)
        (r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", "<TIMESTAMP>"),
        (r"\d{10,13}", "<TIMESTAMP>"),
        # Line numbers — e.g. "foo.py:42:" -> "foo.py:<LINE>:"
        (r":\d+:", ":<LINE>:"),
        # Memory addresses from segfaults / tracebacks
        (r"0x[0-9a-fA-F]+", "<ADDR>"),
        # Process IDs and port numbers
        (r"pid\s*\d+", "pid <PID>"),
        (r"port\s*\d+", "port <PORT>"),
    ]

    @staticmethod
    def normalize(error_text: str) -> str:
        """Strip variable parts (paths, line numbers, etc.) from error text."""
        normalized = error_text
        for pattern, replacement in ErrorSignatureNormalizer.NORMALIZE_PATTERNS:
            normalized = re.sub(pattern, replacement, normalized)
        return normalized.strip()

    @staticmethod
    def signature(normalized_text: str) -> str:
        """Return a stable 16-char hex hash for a normalized error string."""
        return hashlib.sha256(normalized_text.encode()).hexdigest()[:16]
