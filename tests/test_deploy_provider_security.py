from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from tests.deploy_cli_support import build_fake_environment
from tests.test_deploy_cli_fake_e2e import write_config, write_happy_state
from traderbot.deploy.wizard import DeployResult, StepStatus

_PROJECT_ROOT = Path(__file__).parents[1]
_PROVIDER_REFERENCE = "traderbot.deploy.installed_test_provider:provider"
_PROVIDER_ENV_NAMES = ("TRADERBOT_DEPLOY_PROVIDER", "TRADERBOT_TEST_PROVIDER_ALLOWED")


def _provider_attempt(tmp_path: Path, clean_workspace_root: Path) -> tuple[Path, dict[str, str]]:
    state_path, environment = build_fake_environment(tmp_path)
    write_happy_state(state_path, clean_workspace_root)
    _ = environment.pop("TRADERBOT_TEST_KALSHI_KEY")
    _ = environment.pop("TRADERBOT_TEST_KALSHI_PEM")
    environment["TRADERBOT_DEPLOY_PROVIDER"] = _PROVIDER_REFERENCE
    environment["TRADERBOT_TEST_PROVIDER_ALLOWED"] = "1"
    config_path = tmp_path / "deploy.json"
    write_config(config_path, clean_workspace_root / "approved" / "crypto")
    return config_path, environment


def _run_production_deploy(
    python: Path,
    config_path: Path,
    environment: dict[str, str],
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(python), "-m", "traderbot.cli", "deploy", "--config", str(config_path), "--json"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60.0,
        env=environment,
        cwd=cwd,
    )


def _assert_real_ports_rejected_missing_secrets(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 1, (
        "production deploy accepted environment-selected fake ports\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    report = DeployResult.model_validate_json(result.stdout)
    assert report.steps[3].status is StepStatus.FAILED
    assert "TRADERBOT_TEST_KALSHI_KEY" in report.steps[3].message
    assert "TRADERBOT_TEST_KALSHI_PEM" in report.steps[3].message


def _run_checked(
    arguments: list[str],
    *,
    cwd: Path,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        timeout=180.0,
        cwd=cwd,
        env=environment,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def _build_and_install_wheel(tmp_path: Path) -> tuple[Path, tuple[str, ...], str]:
    uv = shutil.which("uv")
    assert uv is not None
    wheel_root = tmp_path / "wheel"
    wheel_root.mkdir()
    _ = _run_checked(
        [uv, "build", "--wheel", "--out-dir", str(wheel_root)],
        cwd=_PROJECT_ROOT,
    )
    wheels = tuple(wheel_root.glob("*.whl"))
    assert len(wheels) == 1
    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as archive:
        names = tuple(archive.namelist())
        production_sources = "\n".join(
            archive.read(name).decode("utf-8")
            for name in names
            if name.startswith("traderbot/") and name.endswith(".py")
        )

    install_root = tmp_path / "installed"
    _ = _run_checked(
        [
            uv,
            "pip",
            "install",
            "--target",
            str(install_root),
            "--no-deps",
            "--no-index",
            str(wheel),
        ],
        cwd=tmp_path,
    )
    return install_root, names, production_sources


def test_source_cli_rejects_environment_selected_fake_provider(
    tmp_path: Path,
    clean_workspace_root: Path,
) -> None:
    config_path, environment = _provider_attempt(tmp_path, clean_workspace_root)

    result = _run_production_deploy(Path(sys.executable), config_path, environment, tmp_path)

    _assert_real_ports_rejected_missing_secrets(result)


def test_installed_wheel_rejects_provider_environment_and_contains_no_fake(
    tmp_path: Path,
    clean_workspace_root: Path,
) -> None:
    install_root, wheel_names, production_sources = _build_and_install_wheel(tmp_path)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    config_path, environment = _provider_attempt(runtime_root, clean_workspace_root)
    environment["PYTHONPATH"] = str(install_root)
    origin = _run_checked(
        [
            sys.executable,
            "-c",
            "import traderbot; print(traderbot.__file__)",
        ],
        cwd=tmp_path,
        environment=environment,
    )
    installed_origin = Path(origin.stdout.strip()).resolve()
    assert installed_origin.is_relative_to(install_root.resolve())
    forbidden_modules = tuple(
        name
        for name in wheel_names
        if Path(name).name in {"installed_test_provider.py", "test_provider.py"}
    )
    forbidden_markers = tuple(
        marker
        for marker in (*_PROVIDER_ENV_NAMES, "installed_test_provider", "deploy.test_provider")
        if marker in production_sources
    )

    result = _run_production_deploy(Path(sys.executable), config_path, environment, tmp_path)

    _assert_real_ports_rejected_missing_secrets(result)
    assert forbidden_modules == ()
    assert forbidden_markers == ()
    assert set(_PROVIDER_ENV_NAMES).issubset(environment)
