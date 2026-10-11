from __future__ import annotations

from pathlib import Path

import pytest

from traderbot.profiles.injection import (
    START_MARKER,
    WorkspaceInjectionError,
    WorkspaceTemplate,
    inject_workspace,
    preflight_workspace,
)


def test_preflight_plans_identical_manifest_without_creating_workspace(tmp_path: Path) -> None:
    # Given: a nonexistent selected workspace
    workspace = tmp_path / "weather"

    # When: the complete template injection is planned and later applied
    preview = preflight_workspace(workspace, WorkspaceTemplate.WEATHER)
    assert workspace.exists() is False
    applied = inject_workspace(workspace, WorkspaceTemplate.WEATHER)

    # Then: preflight predicted the exact deterministic manifest without writing
    assert preview.manifest_hash == applied.manifest_hash


def test_preflight_rejects_malformed_marker_without_mutation(tmp_path: Path) -> None:
    # Given: an existing workspace with an incomplete managed marker
    workspace = tmp_path / "weather"
    workspace.mkdir()
    agents = workspace / "AGENTS.md"
    original = START_MARKER + b"\nincomplete"
    _ = agents.write_bytes(original)

    # When/Then: read-only planning rejects it and preserves all bytes
    with pytest.raises(WorkspaceInjectionError):
        _ = preflight_workspace(workspace, WorkspaceTemplate.WEATHER)
    assert agents.read_bytes() == original
