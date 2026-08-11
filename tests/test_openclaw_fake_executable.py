"""Real-process QA for current OpenClaw agent creation output."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

import traderbot.deploy.openclaw as openclaw


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable shim")
def test_current_agent_add_response_accepts_explicit_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: PATH contains a real executable emitting current string-array bindings
    fake = tmp_path / "openclaw"
    log = tmp_path / "argv.log"
    _ = fake.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import json
            import sys
            from pathlib import Path

            args = sys.argv[1:]
            with Path({str(log)!r}).open("a", encoding="utf-8") as stream:
                stream.write("\\0".join(args) + "\\n")
            if args[:2] == ["agents", "add"]:
                workspace = args[args.index("--workspace") + 1]
                print(json.dumps({{
                    "agentId": "weather", "workspace": workspace,
                    "agentDir": "/state/agents/weather/agent",
                    "bindings": {{"added": ["telegram"], "updated": [],
                                 "skipped": [], "conflicts": []}},
                }}))
            else:
                raise SystemExit(2)
            """
        ),
        encoding="utf-8",
    )
    fake.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    # When: production create_agent launches the executable
    workspace = tmp_path / "nested" / "weather"
    result = openclaw.create_agent("weather", workspace)

    # Then: the current add response is accepted without unrelated config writes
    calls = log.read_text(encoding="utf-8")
    assert result is True
    assert calls.count("agents\0add") == 1
    assert str(workspace) in calls
    assert "config\0set" not in calls
