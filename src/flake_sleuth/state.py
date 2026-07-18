from __future__ import annotations

from pydantic import BaseModel, Field

from flake_sleuth.types import (
    Classification,
    DataQuality,
    FlakeSleuthReport,
    RunInfo,
    TestResult,
    TestStats,
)


class FlakeSleuthState(BaseModel):
    """LangGraph state for the flake-sleuth diagnostic pipeline.

    All list/dict fields have ``default_factory`` so the state can be
    instantiated with no arguments and populated incrementally by nodes.
    """

    repo: str = ""
    runs_requested: int = 100
    runs: list[RunInfo] = Field(default_factory=list)
    failed_runs: list[RunInfo] = Field(default_factory=list)
    test_results: list[TestResult] = Field(default_factory=list)
    preliminary_stats: dict[str, TestStats] = Field(default_factory=dict)
    classifications: list[Classification] = Field(default_factory=list)
    per_test_stats: dict[str, TestStats] = Field(default_factory=dict)
    data_quality: DataQuality | None = None
    report: FlakeSleuthReport | None = None
    error: str | None = None
