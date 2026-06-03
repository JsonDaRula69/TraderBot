"""Tests for AdapterStateStore persistence and BayesianAdapter state lifecycle."""

import json
from datetime import UTC, datetime
from pathlib import Path

from traderbot.simulation.adapter_state import AdapterStateStore, resolve_state_path
from traderbot.simulation.adaptation import BayesianAdapter, GuardrailConfig


class TestAdapterStateStoreSaveLoad:
    """Roundtrip save + load for AdapterStateStore."""

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        state_path = tmp_path / "state.json"
        now = datetime.now(UTC)
        timestamps = [now, now]
        drift_counts = {"edge_threshold": 2}
        dist_states = {"edge_threshold": {"alpha": 3.0, "beta": 9.0}}

        AdapterStateStore.save(timestamps, drift_counts, dist_states, state_path)

        loaded = AdapterStateStore.load(state_path)
        assert loaded is not None
        assert len(loaded.update_timestamps) == 2
        assert loaded.drift_counts == {"edge_threshold": 2}
        assert loaded.distribution_states["edge_threshold"]["alpha"] == 3.0

    def test_file_exists_after_save(self, tmp_path: Path) -> None:
        state_path = tmp_path / "state.json"
        AdapterStateStore.save([], {}, {}, state_path)
        assert state_path.exists()

    def test_load_missing_file_returns_none(self, tmp_path: Path) -> None:
        result = AdapterStateStore.load(tmp_path / "nonexistent.json")
        assert result is None

    def test_load_corrupt_json_returns_none(self, tmp_path: Path) -> None:
        state_path = tmp_path / "bad.json"
        state_path.write_text("{invalid json!!!")
        result = AdapterStateStore.load(state_path)
        assert result is None

    def test_load_invalid_schema_returns_none(self, tmp_path: Path) -> None:
        state_path = tmp_path / "bad_schema.json"
        state_path.write_text(json.dumps({"version": 999, "bogus": True}))
        result = AdapterStateStore.load(state_path)
        assert result is None


class TestTimestampConversion:
    """ISO 8601 string → datetime roundtrip."""

    def test_utc_timestamps_roundtrip(self) -> None:
        now = datetime.now(UTC)
        iso = now.isoformat()
        result = AdapterStateStore.timestamps_to_datetime([iso])
        assert len(result) == 1
        assert result[0].year == now.year

    def test_invalid_timestamps_skipped(self) -> None:
        result = AdapterStateStore.timestamps_to_datetime(["not-a-date"])
        assert result == []


class TestResolveStatePath:
    """resolve_state_path priority logic."""

    def test_explicit_path_takes_priority(self, tmp_path: Path) -> None:
        explicit = tmp_path / "custom.json"
        assert resolve_state_path(explicit) == explicit

    def test_profile_base_dir(self, tmp_path: Path) -> None:
        base = str(tmp_path)
        result = resolve_state_path(profile_base_dir=base)
        assert str(result).endswith("adaptation_state.json")
        assert base in str(result)

    def test_default_path(self) -> None:
        result = resolve_state_path()
        assert result.as_posix().endswith(".traderbot/adaptation_state.json")
        assert Path(result).is_absolute()


class TestBayesianAdapterPersistence:
    """BayesianAdapter loads and persists state via AdapterStateStore."""

    def test_adapter_loads_state_on_init(self, tmp_path: Path) -> None:
        state_path = tmp_path / "state.json"
        now = datetime.now(UTC)
        AdapterStateStore.save(
            [now],
            {"edge_threshold": 3},
            {"edge_threshold": {"alpha": 4.0, "beta": 8.0}},
            state_path,
        )
        adapter = BayesianAdapter(state_path=state_path)
        assert len(adapter._update_timestamps) == 1
        assert adapter._drift_counts.get("edge_threshold") == 3

    def test_adapter_no_state_path_does_not_load(self) -> None:
        adapter = BayesianAdapter()
        assert adapter._update_timestamps == []
        assert adapter._drift_counts == {}

    def test_adapter_no_state_path_does_not_persist(self, tmp_path: Path) -> None:
        state_path = tmp_path / "should_not_exist.json"
        adapter = BayesianAdapter()
        adapter._update_timestamps = [datetime.now(UTC)]
        adapter._persist_state()
        assert not state_path.exists()

    def test_state_survives_across_instances(self, tmp_path: Path) -> None:
        state_path = tmp_path / "persist.json"
        adapter1 = BayesianAdapter(
            config=GuardrailConfig(min_observations=10),
            state_path=state_path,
        )
        adapter1._update_timestamps = [datetime.now(UTC)]
        adapter1._drift_counts = {"edge_threshold": 1}
        adapter1._persist_state()

        adapter2 = BayesianAdapter(state_path=state_path)
        assert adapter2._drift_counts.get("edge_threshold") == 1
