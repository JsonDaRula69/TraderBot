from __future__ import annotations

from pathlib import Path

from traderbot.kalshi import __doc__ as kalshi_documentation
from traderbot.profiles.weather import create_weather_profile


def test_profile_serialization_omits_retired_environment_path() -> None:
    profile = create_weather_profile()

    payload = profile.model_dump()

    assert set(payload) >= {"name", "mode", "base_dir"}
    assert "env" + "_file" not in payload


def test_kalshi_documentation_omits_retired_credential_backend() -> None:
    assert kalshi_documentation is not None
    assert "key" + "ring" not in kalshi_documentation


def test_source_tree_contains_no_retired_legacy_names() -> None:
    source_root = Path(__file__).parents[1] / "src"
    forbidden = ("env" + "_file", "key" + "ring")

    matches = {
        path: name
        for path in source_root.rglob("*.py")
        for name in forbidden
        if name in path.read_text(encoding="utf-8")
    }

    assert matches == {}
