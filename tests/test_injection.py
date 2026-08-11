import hashlib
import os
import stat
from pathlib import Path

import pytest

from traderbot.profiles.injection import (
    END_MARKER,
    START_MARKER,
    InjectionAction,
    WorkspaceTemplate,
    inject_workspace,
)


def _write_template(root: Path, template: WorkspaceTemplate, name: str, content: bytes) -> None:
    directory = root / template.value
    directory.mkdir(parents=True, exist_ok=True)
    _ = (directory / name).write_bytes(content)


def _write_weather_templates(root: Path, content: bytes = b"managed\n") -> None:
    for name in (
        "AGENTS.md",
        "SOUL.md",
        "IDENTITY.md",
        "TOOLS.md",
        "HEARTBEAT.md",
        "USER.md",
        "SESSION-STATE.md",
    ):
        _write_template(root, WorkspaceTemplate.WEATHER, name, content)


def test_fenced_merge_copies_templates(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    workspace = tmp_path / "workspace"
    _write_weather_templates(templates)

    report = inject_workspace(
        workspace,
        WorkspaceTemplate.WEATHER,
        templates_root=templates,
    )

    assert (workspace / "AGENTS.md").read_bytes() == (
        START_MARKER + b"\nmanaged\n" + END_MARKER + b"\n"
    )
    assert next(record for record in report.records if record.path == "AGENTS.md").action is (
        InjectionAction.CREATED
    )


def test_fenced_merge_preserves_user_bytes_and_replaces_only_block(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    workspace = tmp_path / "workspace"
    _write_weather_templates(templates, b"new policy\n")
    workspace.mkdir()
    target = workspace / "SOUL.md"
    _ = target.write_bytes(
        b"user-prefix\x80\n" + START_MARKER + b"\nstale\n" + END_MARKER + b"\nuser-suffix"
    )

    _ = inject_workspace(
        workspace,
        WorkspaceTemplate.WEATHER,
        templates_root=templates,
    )

    assert target.read_bytes() == (
        b"user-prefix\x80\n"
        + START_MARKER
        + b"\nnew policy\n"
        + END_MARKER
        + b"\nuser-suffix"
    )


def test_fenced_merge_appends_once_and_is_idempotent(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    workspace = tmp_path / "workspace"
    _write_weather_templates(templates, b"identity\n")
    workspace.mkdir()
    target = workspace / "IDENTITY.md"
    _ = target.write_bytes(b"owner text")

    first = inject_workspace(
        workspace,
        WorkspaceTemplate.WEATHER,
        templates_root=templates,
    )
    first_bytes = target.read_bytes()
    second = inject_workspace(
        workspace,
        WorkspaceTemplate.WEATHER,
        templates_root=templates,
    )

    assert first_bytes.startswith(b"owner text\n" + START_MARKER)
    assert target.read_bytes() == first_bytes
    assert first.manifest_hash == second.manifest_hash
    assert next(record for record in second.records if record.path == "IDENTITY.md").action is (
        InjectionAction.UNCHANGED
    )


def test_init_if_missing_preserves_existing_user_files(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    workspace = tmp_path / "workspace"
    _write_weather_templates(templates, b"template user\n")
    workspace.mkdir()
    target = workspace / "USER.md"
    _ = target.write_bytes(b"owner bytes\x80")

    report = inject_workspace(
        workspace,
        WorkspaceTemplate.WEATHER,
        templates_root=templates,
    )

    assert target.read_bytes() == b"owner bytes\x80"
    assert next(record for record in report.records if record.path == "USER.md").action is (
        InjectionAction.PRESERVED
    )


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not portable to Windows")
def test_injection_preserves_legacy_openclaw_files_byte_and_mode_exactly(tmp_path: Path) -> None:
    # Given
    templates = tmp_path / "templates"
    workspace = tmp_path / "workspace"
    _write_weather_templates(templates, b"managed replacement\n")
    workspace.mkdir()
    legacy = {
        "TOOLS.md": (b"operator tools\x80\n", 0o640),
        "HEARTBEAT.md": (b"operator heartbeat\xff\n", 0o604),
    }
    for name, (content, mode) in legacy.items():
        target = workspace / name
        _ = target.write_bytes(content)
        target.chmod(mode)

    # When
    report = inject_workspace(
        workspace,
        WorkspaceTemplate.WEATHER,
        templates_root=templates,
    )

    # Then
    for name, (content, mode) in legacy.items():
        target = workspace / name
        assert target.read_bytes() == content
        assert stat.S_IMODE(target.stat().st_mode) == mode
    assert {record.path for record in report.records}.isdisjoint(legacy)


@pytest.mark.parametrize(
    "content",
    [
        START_MARKER + b"\nincomplete",
        END_MARKER + b"\n" + START_MARKER,
        START_MARKER + b"\na\n" + START_MARKER + b"\nb\n" + END_MARKER,
        START_MARKER + b"\na\n" + END_MARKER + b"\n" + END_MARKER,
        b"<!-- BEGIN TRADERBOT -->\nlegacy\n<!-- END TRADERBOT -->",
        b"<!-- BEGIN TRADERBOT MANAGED\nmalformed",
    ],
)
def test_incompatible_markers_rejected(tmp_path: Path, content: bytes) -> None:
    templates = tmp_path / "templates"
    workspace = tmp_path / "workspace"
    _write_weather_templates(templates)
    workspace.mkdir()
    target = workspace / "AGENTS.md"
    _ = target.write_bytes(content)

    with pytest.raises(ValueError):
        _ = inject_workspace(
            workspace,
            WorkspaceTemplate.WEATHER,
            templates_root=templates,
        )

    assert target.read_bytes() == content


def test_symlink_file_and_directory_targets_are_rejected(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    _write_weather_templates(templates)
    outside = tmp_path / "outside"
    outside.mkdir()
    _ = (outside / "AGENTS.md").write_bytes(b"outside")
    file_workspace = tmp_path / "file-workspace"
    file_workspace.mkdir()
    (file_workspace / "AGENTS.md").symlink_to(outside / "AGENTS.md")
    directory_workspace = tmp_path / "directory-workspace"
    directory_workspace.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError):
        _ = inject_workspace(
            file_workspace,
            WorkspaceTemplate.WEATHER,
            templates_root=templates,
        )
    with pytest.raises(ValueError):
        _ = inject_workspace(
            directory_workspace,
            WorkspaceTemplate.WEATHER,
            templates_root=templates,
        )

    assert (outside / "AGENTS.md").read_bytes() == b"outside"


def test_invalid_category_name_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _ = inject_workspace(tmp_path / "workspace", "../escape")


def test_init_if_missing_rejects_wrong_file_type(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    workspace = tmp_path / "workspace"
    _write_weather_templates(templates)
    (workspace / "USER.md").mkdir(parents=True)

    with pytest.raises(ValueError):
        _ = inject_workspace(
            workspace,
            WorkspaceTemplate.WEATHER,
            templates_root=templates,
        )

    assert (workspace / "USER.md").is_dir()


def test_symlink_template_directory_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "templates"
    outside = tmp_path / "outside"
    _write_weather_templates(outside)
    source.mkdir()
    (source / "weather").symlink_to(outside / "weather", target_is_directory=True)

    with pytest.raises(ValueError):
        _ = inject_workspace(
            tmp_path / "workspace",
            WorkspaceTemplate.WEATHER,
            templates_root=source,
        )

    assert not (tmp_path / "workspace").exists()


def test_partial_replace_failure_rolls_back_and_removes_temps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    templates = tmp_path / "templates"
    workspace = tmp_path / "workspace"
    _write_weather_templates(templates, b"new policy\n")
    workspace.mkdir()
    originals = {name: f"owner {name}\n".encode() for name in ("AGENTS.md", "SOUL.md")}
    for name, content in originals.items():
        _ = (workspace / name).write_bytes(content)
    real_replace = os.replace
    failed = False

    def fail_second_replace(source: str | Path, target: str | Path) -> None:
        nonlocal failed
        if Path(target).name == "SOUL.md" and not failed:
            failed = True
            raise OSError("interrupted replace")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", fail_second_replace)

    with pytest.raises(OSError, match="interrupted replace"):
        _ = inject_workspace(
            workspace,
            WorkspaceTemplate.WEATHER,
            templates_root=templates,
        )

    actual = {(path.name, path.read_bytes()) for path in workspace.iterdir()}
    assert actual == set(originals.items())
    assert not tuple(workspace.glob(".*.tmp"))


def test_manifest_hash_matches_result_bytes(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    workspace = tmp_path / "workspace"
    _write_weather_templates(templates, b"heartbeat\n")

    report = inject_workspace(
        workspace,
        WorkspaceTemplate.WEATHER,
        templates_root=templates,
    )

    record = next(record for record in report.records if record.path == "AGENTS.md")
    assert record.sha256 == hashlib.sha256((workspace / record.path).read_bytes()).hexdigest()


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not portable to Windows")
def test_created_workspace_permissions_are_owner_only(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    _ = inject_workspace(workspace, WorkspaceTemplate.WEATHER)

    assert stat.S_IMODE(workspace.stat().st_mode) == 0o700
    assert stat.S_IMODE((workspace / "AGENTS.md").stat().st_mode) == 0o600


@pytest.mark.parametrize("template", tuple(WorkspaceTemplate))
def test_all_allowlisted_templates_inject_from_repository(
    tmp_path: Path, template: WorkspaceTemplate
) -> None:
    workspace = tmp_path / template.value

    report = inject_workspace(workspace, template)

    assert {record.path for record in report.records} == {path.name for path in workspace.iterdir()}
