"""Tests for FileCache in cache.py."""

from __future__ import annotations

import tempfile
from pathlib import Path

from flake_sleuth.cache import FileCache


def test_cache_write_read() -> None:
    """Cache write followed by read returns the same data."""
    with tempfile.TemporaryDirectory() as tmp:
        cache = FileCache(tmp)
        cache.set("pytest-dev/pytest", "runs", b"test data")
        result = cache.get("pytest-dev/pytest", "runs")
        assert result == b"test data"


def test_cache_miss() -> None:
    """Cache miss returns None."""
    with tempfile.TemporaryDirectory() as tmp:
        cache = FileCache(tmp)
        result = cache.get("pytest-dev/pytest", "nonexistent")
        assert result is None


def test_cache_has() -> None:
    """has returns True for existing keys, False otherwise."""
    with tempfile.TemporaryDirectory() as tmp:
        cache = FileCache(tmp)
        cache.set("owner/repo", "key1", b"data")
        assert cache.has("owner/repo", "key1") is True
        assert cache.has("owner/repo", "key2") is False


def test_cache_clear_all() -> None:
    """clear() without args wipes the entire cache."""
    with tempfile.TemporaryDirectory() as tmp:
        cache = FileCache(tmp)
        cache.set("repo1", "a", b"data")
        cache.set("repo2", "b", b"data")
        cache.clear()
        assert cache.get("repo1", "a") is None
        assert cache.get("repo2", "b") is None


def test_cache_clear_single_repo() -> None:
    """clear(repo) only removes entries for the given repo."""
    with tempfile.TemporaryDirectory() as tmp:
        cache = FileCache(tmp)
        cache.set("repo1", "a", b"data")
        cache.set("repo2", "b", b"data")
        cache.clear("repo1")
        assert cache.get("repo1", "a") is None
        assert cache.get("repo2", "b") is not None


def test_cache_directory_created() -> None:
    """Cache directory is created on init if it doesn't exist."""
    with tempfile.TemporaryDirectory() as tmp:
        cache_dir = Path(tmp) / "nonexistent" / "subdir"
        cache = FileCache(cache_dir)
        assert cache_dir.exists()
        cache.set("repo", "k", b"v")
        assert cache.get("repo", "k") == b"v"
