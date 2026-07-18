"""Optional file-based cache for GitHub API responses.

Reduces redundant network calls during field study and development
by caching run metadata and log downloads on disk.
"""

from __future__ import annotations

from pathlib import Path


class FileCache:
    """Simple file-based key-value cache for API responses.

    Cache files are stored as raw bytes under ``cache_dir / repo /``.
    """

    def __init__(self, cache_dir: str | Path) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _repo_dir(self, repo: str) -> Path:
        """Return the subdirectory for a given repo, creating it if needed."""
        repo_path = self.cache_dir / repo.replace("/", "_")
        repo_path.mkdir(parents=True, exist_ok=True)
        return repo_path

    def _path(self, repo: str, identifier: str) -> Path:
        """Return the full cache file path for *repo* / *identifier*."""
        return self._repo_dir(repo) / f"{identifier}.bin"

    def get(self, repo: str, identifier: str) -> bytes | None:
        """Read cached data for *identifier* under *repo*.

        Returns ``None`` on cache miss.
        """
        path = self._path(repo, identifier)
        if not path.exists():
            return None
        return path.read_bytes()

    def set(self, repo: str, identifier: str, data: bytes) -> None:
        """Write *data* to the cache under *repo* / *identifier*."""
        self._path(repo, identifier).write_bytes(data)

    def has(self, repo: str, identifier: str) -> bool:
        """Return ``True`` if the cache entry exists."""
        return self._path(repo, identifier).exists()

    def clear(self, repo: str | None = None) -> None:
        """Remove cached entries.

        If *repo* is ``None`` the entire cache is wiped.
        """
        if repo is None:
            for child in self.cache_dir.iterdir():
                if child.is_dir():
                    for f in child.iterdir():
                        f.unlink()
                    child.rmdir()
        else:
            repo_path = self._repo_dir(repo)
            for f in repo_path.iterdir():
                f.unlink()
            repo_path.rmdir()
