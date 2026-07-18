"""Shared fixtures for ai-flake-sleuth tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from flake_sleuth.config import FlakeSleuthConfig
from tests.fixtures.mock_github_api import MockGitHubClient


@pytest.fixture
def mock_github_client() -> MockGitHubClient:
    """Return a MockGitHubClient pre-configured with fixture data."""
    return MockGitHubClient()


@pytest.fixture
def default_config() -> FlakeSleuthConfig:
    """Return a default FlakeSleuthConfig for testing."""
    return FlakeSleuthConfig()


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the test fixtures directory."""
    return Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def sample_logs_dir(fixtures_dir: Path) -> Path:
    """Return the path to the sample log fixtures."""
    return fixtures_dir / "sample_logs"
