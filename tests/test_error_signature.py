from __future__ import annotations

from flake_sleuth.error_signature import ErrorSignatureNormalizer


def test_normalize_strips_paths() -> None:
    text = "Error in /Users/bob/project/tests/test_foo.py:42: AssertionError"
    result = ErrorSignatureNormalizer.normalize(text)
    assert "<PATH>" in result
    assert "/Users/bob/" not in result


def test_normalize_strips_home() -> None:
    text = "File \"/home/runner/work/app/test_auth.py\", line 42"
    result = ErrorSignatureNormalizer.normalize(text)
    assert "<PATH>" in result
    assert "/home/runner/" not in result


def test_normalize_strips_tmp() -> None:
    text = "Error in /tmp/build/foo.py"
    result = ErrorSignatureNormalizer.normalize(text)
    assert "<PATH>" in result


def test_normalize_strips_runner() -> None:
    text = "/runner/_work/app/test.py"
    result = ErrorSignatureNormalizer.normalize(text)
    assert "<PATH>" in result


def test_normalize_strips_line_numbers() -> None:
    text = "File \"foo.py\":42: in test_bar"
    result = ErrorSignatureNormalizer.normalize(text)
    assert ":<LINE>:" in result


def test_normalize_strips_addresses() -> None:
    text = "Segfault at 0x7ffeea3b2c50"
    result = ErrorSignatureNormalizer.normalize(text)
    assert "<ADDR>" in result


def test_normalize_strips_timestamps() -> None:
    text = "2026-07-16T10:00:00 ERROR"
    result = ErrorSignatureNormalizer.normalize(text)
    assert "<TIMESTAMP>" in result


def test_normalize_strips_pid() -> None:
    text = "pid 12345 exited"
    result = ErrorSignatureNormalizer.normalize(text)
    assert "pid <PID>" in result


def test_normalize_strips_port() -> None:
    text = "port 8080 refused"
    result = ErrorSignatureNormalizer.normalize(text)
    assert "port <PORT>" in result


def test_same_error_same_signature() -> None:
    e1 = "AssertionError in /Users/bob/foo.py:42: assert 1 == 2"
    e2 = "AssertionError in /Users/alice/foo.py:99: assert 1 == 2"
    sig1 = ErrorSignatureNormalizer.signature(
        ErrorSignatureNormalizer.normalize(e1)
    )
    sig2 = ErrorSignatureNormalizer.signature(
        ErrorSignatureNormalizer.normalize(e2)
    )
    assert sig1 == sig2


def test_different_errors_different_signatures() -> None:
    e1 = "KeyError: 'missing'"
    e2 = "AssertionError: assert 1 == 2"
    sig1 = ErrorSignatureNormalizer.signature(
        ErrorSignatureNormalizer.normalize(e1)
    )
    sig2 = ErrorSignatureNormalizer.signature(
        ErrorSignatureNormalizer.normalize(e2)
    )
    assert sig1 != sig2


def test_signature_length() -> None:
    sig = ErrorSignatureNormalizer.signature(
        ErrorSignatureNormalizer.normalize("some error text")
    )
    assert len(sig) == 16
    assert isinstance(sig, str)


def test_normalize_returns_stripped() -> None:
    text = "   some error   "
    result = ErrorSignatureNormalizer.normalize(text)
    assert result == "some error"
