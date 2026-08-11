import os
import stat
from pathlib import Path
from typing import Never

import pytest

import traderbot.profiles.injection as injection
from traderbot.profiles.injection import END_MARKER, START_MARKER, WorkspaceTemplate


def _write_weather_templates(root: Path, content: bytes = b"managed\n") -> None:
    directory = root / WorkspaceTemplate.WEATHER.value
    directory.mkdir(parents=True)
    for name in (
        "AGENTS.md",
        "SOUL.md",
        "IDENTITY.md",
        "TOOLS.md",
        "HEARTBEAT.md",
        "USER.md",
        "SESSION-STATE.md",
    ):
        _ = (directory / name).write_bytes(content)


@pytest.mark.skipif(os.name == "nt", reason="Windows symlink creation requires privileges")
def test_parent_symlink_component_rejected_before_write(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    _write_weather_templates(templates)
    base = tmp_path / "base"
    destination = tmp_path / "real"
    base.mkdir()
    destination.mkdir()
    (base / "linked").symlink_to(destination, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        _ = injection.inject_workspace(
            base / "linked" / "workspace",
            WorkspaceTemplate.WEATHER,
            templates_root=templates,
        )

    assert not (destination / "workspace").exists()
    assert not tuple(destination.iterdir())


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not portable to Windows")
def test_fenced_update_preserves_existing_mode(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    workspace = tmp_path / "workspace"
    _write_weather_templates(templates, b"new policy\n")
    workspace.mkdir()
    target = workspace / "AGENTS.md"
    original = b"owner\n" + START_MARKER + b"\nstale\n" + END_MARKER + b"\n"
    _ = target.write_bytes(original)
    target.chmod(0o640)

    _ = injection.inject_workspace(
        workspace,
        WorkspaceTemplate.WEATHER,
        templates_root=templates,
    )

    assert b"new policy" in target.read_bytes()
    assert stat.S_IMODE(target.stat().st_mode) == 0o640


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not portable to Windows")
def test_rollback_preserves_original_bytes_and_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    templates = tmp_path / "templates"
    workspace = tmp_path / "workspace"
    _write_weather_templates(templates, b"new policy\n")
    workspace.mkdir()
    originals = {name: f"owner {name}\n".encode() for name in ("AGENTS.md", "SOUL.md")}
    for name, content in originals.items():
        target = workspace / name
        _ = target.write_bytes(content)
        target.chmod(0o640)
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
        _ = injection.inject_workspace(
            workspace,
            WorkspaceTemplate.WEATHER,
            templates_root=templates,
        )

    for name, content in originals.items():
        target = workspace / name
        assert target.read_bytes() == content
        assert stat.S_IMODE(target.stat().st_mode) == 0o640


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not portable to Windows")
def test_rollback_preserves_fenced_non_utf8_bytes_and_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    templates = tmp_path / "templates"
    workspace = tmp_path / "workspace"
    _write_weather_templates(templates, b"replacement\n")
    workspace.mkdir()
    originals = {
        "AGENTS.md": b"owner-prefix\x80\n" + START_MARKER + b"\nstale\n" + END_MARKER + b"\n",
        "SOUL.md": b"owner-soul\xff\n",
    }
    for name, content in originals.items():
        target = workspace / name
        _ = target.write_bytes(content)
        target.chmod(0o640)
    real_replace = os.replace
    failed = False

    def fail_second_replace(source: str | Path, target: str | Path) -> None:
        nonlocal failed
        if Path(target).name == "SOUL.md" and not failed:
            failed = True
            raise OSError("characterization interrupted replace")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", fail_second_replace)

    # When
    with pytest.raises(OSError, match="characterization interrupted replace"):
        _ = injection.inject_workspace(
            workspace,
            WorkspaceTemplate.WEATHER,
            templates_root=templates,
        )

    # Then
    for name, content in originals.items():
        target = workspace / name
        assert target.read_bytes() == content
        assert stat.S_IMODE(target.stat().st_mode) == 0o640


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not portable to Windows")
def test_fsync_failure_preserves_targets_and_removes_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    templates = tmp_path / "templates"
    workspace = tmp_path / "workspace"
    _write_weather_templates(templates, b"replacement\n")
    workspace.mkdir()
    target = workspace / "AGENTS.md"
    original = b"owner-prefix\x80\n" + START_MARKER + b"\nstale\n" + END_MARKER + b"\n"
    _ = target.write_bytes(original)
    target.chmod(0o640)
    failure = OSError("fsync failed")

    def fail_fsync(_descriptor: int) -> Never:
        raise failure

    monkeypatch.setattr(os, "fsync", fail_fsync)

    # When
    with pytest.raises(OSError) as caught:
        _ = injection.inject_workspace(
            workspace,
            WorkspaceTemplate.WEATHER,
            templates_root=templates,
        )

    # Then
    assert caught.value is failure
    assert target.read_bytes() == original
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert not tuple(workspace.glob(".*.tmp"))


def test_fdopen_failure_closes_descriptor_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    templates = tmp_path / "templates"
    workspace = tmp_path / "workspace"
    _write_weather_templates(templates)
    failure = OSError("fdopen failed")
    captured: list[int] = []
    closed: list[int] = []
    real_close = os.close

    def fail_fdopen(descriptor: int, _mode: str) -> Never:
        captured.append(descriptor)
        raise failure

    def record_close(descriptor: int) -> None:
        closed.append(descriptor)
        real_close(descriptor)

    monkeypatch.setattr(os, "fdopen", fail_fdopen)
    monkeypatch.setattr(os, "close", record_close)

    try:
        with pytest.raises(OSError) as caught:
            _ = injection.inject_workspace(
                workspace,
                WorkspaceTemplate.WEATHER,
                templates_root=templates,
            )
        assert caught.value is failure
        assert closed == captured
        assert len(closed) == 1
        with pytest.raises(OSError):
            _ = os.fstat(closed[0])
        assert not tuple(tmp_path.glob(".*.tmp"))
        assert not workspace.exists()
    finally:
        for descriptor in captured:
            try:
                real_close(descriptor)
            except OSError:
                continue
