from __future__ import annotations

from flake_sleuth.state import FlakeSleuthState


class TestInitialState:
    def test_defaults(self) -> None:
        state = FlakeSleuthState()
        assert state.repo == ""
        assert state.runs_requested == 100
        assert state.runs == []
        assert state.failed_runs == []
        assert state.test_results == []
        assert state.preliminary_stats == {}
        assert state.classifications == []
        assert state.per_test_stats == {}
        assert state.data_quality is None
        assert state.report is None
        assert state.error is None

    def test_repo_field(self) -> None:
        state = FlakeSleuthState(repo="pytest-dev/pytest")
        assert state.repo == "pytest-dev/pytest"

    def test_runs_requested(self) -> None:
        state = FlakeSleuthState(runs_requested=50)
        assert state.runs_requested == 50

    def test_error_setting(self) -> None:
        state = FlakeSleuthState(error="something went wrong")
        assert state.error == "something went wrong"

    def test_pydantic_validates_types(self) -> None:
        state = FlakeSleuthState(runs_requested=50)
        assert isinstance(state.runs_requested, int)
