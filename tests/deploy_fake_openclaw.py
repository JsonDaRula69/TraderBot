from __future__ import annotations

import textwrap
from pathlib import Path


def write_fake_openclaw(path: Path) -> None:
    script = textwrap.dedent(
        """\
        #!/usr/bin/env python3
        from __future__ import annotations
        import json
        import os
        import sys
        from pathlib import Path

        state_path = Path(os.environ["FAKE_OC_STATE"])
        state = json.loads(state_path.read_text(encoding="utf-8"))
        args = sys.argv[1:]
        state["events"].append(" ".join(args))
        state_path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")

        def save() -> None:
            state_path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")

        def missing(key: str) -> None:
            print(json.dumps({"error": f"Config path not found: {key}"}))
            save()
            raise SystemExit(1)

        if args == ["agents", "list", "--json"]:
            print(json.dumps([
                {"id": agent_id, "workspace": record["workspace"],
                 "agentDir": f"/state/{agent_id}", "bindings": 0,
                 "isDefault": agent_id == "main"}
                for agent_id, record in state["agents"].items()
            ]))
            save()
        elif args[:3] == ["gateway", "status", "--json"]:
            print(json.dumps({"running": True, "pid": 21,
                              "rpc": {"ok": True, "latencyMs": 1},
                              "configPath": "/state/openclaw.json"}))
            save()
        elif args[:2] == ["config", "get"]:
            key = args[2]
            if key.startswith("agents.entries."):
                agent_id = key.split(".")[2]
                if agent_id not in state["agents"]:
                    missing(key)
                print(json.dumps(state["agents"][agent_id]["config"]))
            else:
                agent_id = key.rsplit(".", 1)[-1]
                if agent_id not in state["refs"]:
                    missing(key)
                print(json.dumps(state["refs"][agent_id]))
            save()
        elif args[:2] == ["config", "set"]:
            if "--dry-run" in args:
                print(json.dumps({"ok": True, "operations": 1,
                                  "configPath": "/state/openclaw.json",
                                  "inputModes": ["json"],
                                  "checks": {"schema": True,
                                             "resolvability": True,
                                             "resolvabilityComplete": True},
                                  "refsChecked": 0, "skippedExecRefs": 1}))
                save()
            else:
                key = args[2]
                value = json.loads(args[3])
                if ".agentTokenMap." in key:
                    state["refs"][key.rsplit(".", 1)[-1]] = value
                    state["mutations"].append(f"secret:{key.rsplit('.', 1)[-1]}")
                else:
                    agent_id = key.split(".")[2]
                    if key.endswith("heartbeat.every"):
                        heartbeat = state["agents"][agent_id]["config"].setdefault(
                            "heartbeat", {}
                        )
                        heartbeat["every"] = value
                        state["mutations"].append(f"heartbeat:{agent_id}")
                    elif key.endswith("sandbox.mode"):
                        sandbox = state["agents"][agent_id]["config"].setdefault(
                            "sandbox", {}
                        )
                        sandbox["mode"] = value
                        state["mutations"].append(f"sandbox:{agent_id}")
                save()
        elif args[:2] == ["agents", "add"]:
            agent_id = args[2]
            workspace = args[args.index("--workspace") + 1]
            state["agents"][agent_id] = {
                "workspace": workspace,
                "config": {"heartbeat": {}, "sandbox": {}},
            }
            state["mutations"].append(f"add:{agent_id}")
            save()
            if state["mode"] == "partial":
                print("malformed")
                raise SystemExit(1)
            print(json.dumps({"agentId": agent_id, "workspace": workspace,
                              "agentDir": f"/state/{agent_id}",
                              "bindings": {"added": [], "updated": [],
                                           "skipped": [], "conflicts": []}}))
        elif args[:2] == ["cron", "list"]:
            print(json.dumps({"jobs": state["crons"]}))
            save()
        elif args[:2] == ["cron", "add"]:
            job = {"id": "bootstrap-1", "name": "traderbot-main-at-5m",
                   "agentId": "main", "enabled": True,
                   "createdAtMs": 1700000000000, "updatedAtMs": 1700000000000,
                   "schedule": {"kind": "at", "at": "2023-11-14T22:18:20+00:00"},
                   "sessionTarget": "isolated", "wakeMode": "now",
                   "payload": {"kind": "agentTurn", "message": args[args.index("--message") + 1]},
                   "state": {}, "deleteAfterRun": True}
            state["crons"] = [job]
            state["mutations"].append("cron:add")
            save()
            print(json.dumps(job))
        elif args and args[0] in {"doctor", "setup"}:
            state["mutations"].append(f"forbidden:{args[0]}")
            save()
            raise SystemExit(9)
        else:
            save()
            raise SystemExit(2)
        """
    )
    _ = path.write_text(script, encoding="utf-8")
    path.chmod(0o755)
