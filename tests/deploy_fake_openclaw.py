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
        import re
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
            # Deployed OpenClaw 2026.7.1-2 prints missing-path errors to STDERR
            # as plain text and leaves STDOUT empty.
            print(f"Config path not found: {key}", file=sys.stderr)
            save()
            raise SystemExit(1)

        def reject(message: str) -> None:
            print(message, file=sys.stderr)
            save()
            raise SystemExit(1)

        def dry_run(input_mode: str) -> None:
            print(json.dumps({"ok": True, "operations": 1,
                              "configPath": "/state/openclaw.json",
                              "inputModes": [input_mode],
                              "checks": {"schema": True,
                                         "resolvability": True,
                                         "resolvabilityComplete": True},
                              "refsChecked": 0, "skippedExecRefs": 1}))
            save()

        # Deployed 2026.7.1-2 config shape: agents live ONLY under
        # agents.list[] (pinned zod AgentsSchema = {defaults, list}; no
        # agents.entries config key exists in dist). This fake is therefore
        # LIST-FIRST: entries-namespace reads answer missing and entries
        # writes are rejected, so no test can pass in entries-world while
        # the deployed target is list-world. Agent order is canonicalized to
        # sorted ids, matching the state file's sort_keys serialization, so
        # a list index resolves identically before and after every save.
        agent_ids = sorted(state["agents"])

        _LIST_PATH = re.compile(r"^agents\\.list\\[(\\d+)\\](?:\\.([A-Za-z0-9_.-]+))?$")

        def resolve_list(key: str):
            match = _LIST_PATH.fullmatch(key)
            if match is None:
                reject(f"Invalid path (expected agents.list[<index>].<path>): {key}")
            index = int(match.group(1))
            if index >= len(agent_ids):
                missing(key)
            segments = match.group(2).split(".") if match.group(2) else []
            return agent_ids[index], segments

        def agent_config(agent_id: str):
            return state["agents"][agent_id]["config"]

        def walk(config, segments):
            current = config
            for segment in segments:
                if not isinstance(current, dict) or segment not in current:
                    return False, None
                current = current[segment]
            return True, current

        def read_path(key: str):
            if key == "agents.list":
                return [{"id": agent_id, **agent_config(agent_id)}
                        for agent_id in agent_ids]
            if key.startswith("agents.entries."):
                # The entries namespace does not exist on the deployed shape.
                missing(key)
            agent_id, segments = resolve_list(key)
            config = agent_config(agent_id)
            if not segments:
                return {**config, "id": agent_id}
            found, value = walk(config, segments)
            if not found:
                missing(key)
            return value

        def write_path(key: str, value):
            if key == "agents.list":
                reject(f"Refusing to replace the whole agents.list array: {key}")
            if key.startswith("agents.entries."):
                reject("agents.entries writes are invalid on the deployed "
                       f"2026.7.1-2 agents.list[]-shaped config: {key}")
            agent_id, segments = resolve_list(key)
            if not segments:
                reject(f"Refusing to replace a whole agents.list entry: {key}")
            current = agent_config(agent_id)
            for segment in segments[:-1]:
                child = current.get(segment)
                if not isinstance(child, dict):
                    child = {}
                    current[segment] = child
                current = child
            current[segments[-1]] = value
            return agent_id, segments

        def unset_path(key: str) -> None:
            if key == "agents.list":
                reject(f"Refusing to remove the whole agents.list array: {key}")
            if key.startswith("agents.entries."):
                reject("agents.entries unsets are invalid on the deployed "
                       f"2026.7.1-2 agents.list[]-shaped config: {key}")
            agent_id, segments = resolve_list(key)
            if not segments:
                reject(f"Refusing to remove a whole agents.list entry: {key}")
            config = agent_config(agent_id)
            found, parent = walk(config, segments[:-1])
            if not found or not isinstance(parent, dict) or segments[-1] not in parent:
                missing(key)
            # Object-leaf unset DELETES the key (absent on re-read, never null),
            # mirroring the pinned CLI's unsetAtPath leafContainer=object write.
            del parent[segments[-1]]
            state["mutations"].append(f"unset:{key}")

        if args == ["agents", "list", "--json"]:
            print(json.dumps([
                {"id": agent_id, "workspace": state["agents"][agent_id]["workspace"],
                 "agentDir": f"/state/{agent_id}", "bindings": 0,
                 "isDefault": agent_id == "main"}
                for agent_id in agent_ids
            ]))
            save()
        elif args[:3] == ["gateway", "status", "--json"]:
            print(json.dumps({"running": True, "pid": 21,
                              "rpc": {"ok": True, "latencyMs": 1},
                              "configPath": "/state/openclaw.json"}))
            save()
        elif args[:2] == ["config", "get"]:
            key = args[2]
            if key.startswith("agents."):
                print(json.dumps(read_path(key)))
            else:
                agent_id = key.rsplit(".", 1)[-1]
                if agent_id not in state["refs"]:
                    missing(key)
                print(json.dumps(state["refs"][agent_id]))
            save()
        elif args[:2] == ["config", "set"]:
            if "--dry-run" in args:
                dry_run("json")
            else:
                key = args[2]
                raw = args[3]
                try:
                    value = json.loads(raw)
                except json.JSONDecodeError:
                    reject(f"Invalid JSON value for --strict-json write of {key}: {raw}")
                if ".agentTokenMap." in key:
                    state["refs"][key.rsplit(".", 1)[-1]] = value
                    state["mutations"].append(f"secret:{key.rsplit('.', 1)[-1]}")
                else:
                    agent_id, segments = write_path(key, value)
                    if segments[-2:] == ["heartbeat", "every"]:
                        state["mutations"].append(f"heartbeat:{agent_id}")
                    elif segments[0] == "sandbox":
                        state["mutations"].append(f"sandbox:{agent_id}")
                save()
        elif args[:2] == ["config", "unset"]:
            key = args[2]
            if "--dry-run" in args:
                # The pinned CLI validates existence before reporting ok:true;
                # a missing path fails the dry-run (ok:false -> exit 1).
                if key.startswith("agents.entries.") or key == "agents.list":
                    missing(key)
                probe_id, probe_segments = resolve_list(key)
                found, _ = walk(agent_config(probe_id), probe_segments)
                if not found:
                    missing(key)
                dry_run("unset")
            else:
                unset_path(key)
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
            # Deployed OpenClaw 2026.7.1-2 populates the pending one-shot
            # envelope the moment the job is scheduled: state nextRunAtMs plus
            # top-level nextRunAtMs and status "idle"
            # (.omo/evidence/f3-a104-r5-receipts/recorded-cron-job.json).
            next_run_at_ms = 1700000300000
            job = {"id": "bootstrap-1", "name": "traderbot-main-at-5m",
                   "agentId": "main", "enabled": True,
                   "createdAtMs": 1700000000000, "updatedAtMs": 1700000000000,
                   "schedule": {"kind": "at", "at": "2023-11-14T22:18:20+00:00"},
                   "sessionTarget": "isolated", "wakeMode": "now",
                   "payload": {"kind": "agentTurn",
                               "message": args[args.index("--message") + 1]},
                   "state": {"nextRunAtMs": next_run_at_ms},
                   "nextRunAtMs": next_run_at_ms, "status": "idle",
                   "deleteAfterRun": True}
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
