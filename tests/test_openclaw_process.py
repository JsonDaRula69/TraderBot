"""Adversarial process-lifecycle tests for the OpenClaw command boundary."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal, TypedDict, Unpack

import pytest

import traderbot.deploy.openclaw_process as openclaw_process
from traderbot.deploy.openclaw_process import run_bounded


class _PopenOptions(TypedDict):
    shell: Literal[False]
    stdin: int
    stdout: int
    stderr: int
    text: Literal[False]
    bufsize: int
    start_new_session: bool
    creationflags: int


class _ControlledMonotonicClock:
    _frozen: float
    _released_at: float
    _released: threading.Event

    def __init__(self) -> None:
        self._frozen = time.monotonic()
        self._released_at = 0.0
        self._released = threading.Event()

    def release(self) -> None:
        self._released_at = time.monotonic()
        self._released.set()

    def monotonic(self) -> float:
        if not self._released.is_set():
            return self._frozen
        return self._frozen + time.monotonic() - self._released_at

    @staticmethod
    def sleep(seconds: float) -> None:
        time.sleep(seconds)


def _capture_processes(monkeypatch: pytest.MonkeyPatch) -> list[subprocess.Popen[bytes]]:
    launched: list[subprocess.Popen[bytes]] = []
    original_popen = subprocess.Popen

    def capture(
        argv: list[str],
        **options: Unpack[_PopenOptions],
    ) -> subprocess.Popen[bytes]:
        process = original_popen(argv, **options)
        launched.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", capture)
    return launched


def _wait_for_path(path: Path, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while not path.exists():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        _ = threading.Event().wait(min(remaining, 0.01))
    return True


def _wait_until(predicate: Callable[[], bool], timeout: float, interval: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        if predicate():
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        _ = threading.Event().wait(min(remaining, interval))


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _assert_reaped(pid: int, *, within: float = 2.0) -> None:
    # Reaping is asynchronous: a killed descendant is reparented to init and only
    # then reaped, so it can linger as a zombie for a scheduling interval after the
    # kill. Assert the outcome within a bounded window instead of at one instant;
    # the strictness is that the process MUST be gone, not that it is gone at the
    # first observation.
    if _wait_until(lambda: not _pid_exists(pid), timeout=within):
        return
    raise AssertionError(f"child process {pid} remains alive after {within}s")


def _leaked_reader_threads() -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if thread.name.startswith("openclaw-")]


def _assert_no_readers(*, within: float = 2.0) -> None:
    # Reader threads finish asynchronously with respect to the caller, so give them
    # a bounded window to exit; leaking one beyond it is still a failure.
    if _wait_until(lambda: not _leaked_reader_threads(), timeout=within):
        return
    names = [thread.name for thread in _leaked_reader_threads()]
    raise AssertionError(f"openclaw reader threads survived: {names}")


def test_run_bounded_terminates_and_reaps_output_overflow_child(tmp_path: Path) -> None:
    # Given: a child records its pid, emits without bound, then would leave a marker
    pid_path = tmp_path / "overflow.pid"
    marker = tmp_path / "overflow-finished"
    script = (
        "import os; from pathlib import Path; "
        f"Path({str(pid_path)!r}).write_text(str(os.getpid())); "
        "[(os.write(1, b'x' * 65536)) for _ in range(64)]; "
        f"Path({str(marker)!r}).touch()"
    )

    # When: collection exceeds the one-MiB stream cap
    result = run_bounded([sys.executable, "-c", script], timeout=5.0)

    # Then: collection fails closed and no process or pipe reader survives
    assert result is None
    _assert_reaped(int(pid_path.read_text()))
    assert not marker.exists()
    _assert_no_readers()


def test_run_bounded_terminates_and_reaps_timeout_child(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: the parent fixture captures the child pid before its deadline begins
    launched = _capture_processes(monkeypatch)
    marker = tmp_path / "timeout-finished"
    script = f"import time; from pathlib import Path; time.sleep(10); Path({str(marker)!r}).touch()"

    # When: execution exceeds its deadline
    started = time.monotonic()
    result = run_bounded([sys.executable, "-c", script], timeout=0.2)
    elapsed = time.monotonic() - started

    # Then: the sleeping child is terminated and reaped without reader leaks
    assert result is None
    assert elapsed < 0.8
    _assert_reaped(launched[0].pid)
    assert not marker.exists()
    _assert_no_readers()


def test_run_bounded_terminates_and_reaps_stderr_overflow_child(tmp_path: Path) -> None:
    # Given: a child records its pid and emits more than one MiB on stderr
    pid_path = tmp_path / "stderr.pid"
    marker = tmp_path / "stderr-finished"
    script = (
        "import os; from pathlib import Path; "
        f"Path({str(pid_path)!r}).write_text(str(os.getpid())); "
        "[(os.write(2, b'x' * 65536)) for _ in range(64)]; "
        f"Path({str(marker)!r}).touch()"
    )

    # When: stderr collection crosses its independent stream cap
    result = run_bounded([sys.executable, "-c", script], timeout=5.0)

    # Then: the child is terminated and reaped without a completion marker
    assert result is None
    _assert_reaped(int(pid_path.read_text()))
    assert not marker.exists()
    _assert_no_readers()


def test_run_bounded_returns_decoded_output_within_limits() -> None:
    # Given: a child emits bounded UTF-8 on both streams
    script = "import sys; print('ok'); print('warning', file=sys.stderr)"

    # When: the child exits normally
    result = run_bounded([sys.executable, "-c", script], timeout=2.0)

    # Then: output and return status are preserved
    assert result is not None
    assert result.returncode == 0
    assert result.stdout == "ok\n"
    assert result.stderr == "warning\n"


def test_run_bounded_fails_closed_for_missing_executable() -> None:
    # Given: argv names an executable that cannot exist on PATH
    argv = ["traderbot-openclaw-definitely-missing"]

    # When/Then: launch failure returns no process result
    assert run_bounded(argv, timeout=0.2) is None


def test_run_bounded_fails_closed_for_invalid_utf8() -> None:
    # Given: a child emits bytes that strict text decoding rejects
    script = "import os; os.write(1, bytes([255]))"

    # When/Then: decoding failure returns no result after child reaping
    assert run_bounded([sys.executable, "-c", script], timeout=2.0) is None
    _assert_no_readers()


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group lifecycle")
def test_run_bounded_kills_pipe_inheriting_descendant_by_deadline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: the fixture parent signals that it started, then blocks on a gate the
    # test opens explicitly - setup ordering is synchronised, never timed
    launched = _capture_processes(monkeypatch)
    descendant_pid = tmp_path / "descendant.pid"
    startup_started = tmp_path / "descendant.starting"
    spawn_gate = tmp_path / "spawn.go"
    ready = tmp_path / "descendant.ready"
    marker = tmp_path / "descendant-finished"
    descendant = (
        f"import time; from pathlib import Path; time.sleep(2); Path({str(marker)!r}).touch()"
    )
    parent = (
        "import subprocess, sys, time\n"
        "from pathlib import Path\n"
        f"Path({str(startup_started)!r}).touch()\n"
        f"gate = Path({str(spawn_gate)!r})\n"
        "gate_deadline = time.monotonic() + 10.0\n"
        "while not gate.exists() and time.monotonic() < gate_deadline:\n"
        "    time.sleep(0.005)\n"
        "assert gate.exists(), 'spawn gate never opened'\n"
        f"child = subprocess.Popen([sys.executable, '-c', {descendant!r}],\n"
        "                          stdout=sys.stdout, stderr=sys.stderr)\n"
        f"Path({str(descendant_pid)!r}).write_text(str(child.pid))\n"
        f"Path({str(ready)!r}).touch()\n"
    )
    clock = _ControlledMonotonicClock()
    monkeypatch.setattr(openclaw_process, "time", clock)
    results: list[subprocess.CompletedProcess[str] | None] = []

    def run() -> None:
        results.append(run_bounded([sys.executable, "-c", parent], timeout=0.2))

    runner = threading.Thread(target=run, name="openclaw-fixture-runner")
    runner.start()

    try:
        # When: the child is still gated while the frozen deadline cannot expire
        assert _wait_for_path(startup_started, timeout=2.0)
        assert len(launched) == 1
        # Deterministic: the parent cannot reach the descendant without the gate,
        # so `ready` cannot exist yet, regardless of scheduler load.
        assert not ready.exists()
        assert runner.is_alive()
        assert results == []

        # And: the pipe-inheriting descendant exists before the deadline is released
        spawn_gate.touch()
        fixture_ready = _wait_for_path(ready, timeout=2.0)
        started = time.monotonic()
        clock.release()
        runner.join(timeout=1.0)
        elapsed = time.monotonic() - started

        # Then: the whole process group is gone within a strict bounded tolerance
        assert fixture_ready
        assert not runner.is_alive()
        assert results == [None]
        assert elapsed < 0.8
        _assert_reaped(launched[0].pid)
        _assert_reaped(int(descendant_pid.read_text()))
        assert not marker.exists()
        _assert_no_readers()
    finally:
        # A failed assertion above must not poison later tests with a live gated
        # child and its pipe readers: open the gate, expire the deadline, join.
        spawn_gate.touch()
        clock.release()
        _ = runner.join(timeout=5.0)


def test_run_bounded_cleans_up_when_second_reader_fails_to_start(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: the child is live and the second reader start raises an OS launch error
    pid_path = tmp_path / "reader-start.pid"
    script = (
        "import os,time; from pathlib import Path; "
        f"Path({str(pid_path)!r}).write_text(str(os.getpid())); time.sleep(10)"
    )
    original_start = threading.Thread.start
    starts = 0

    def fail_second_start(reader: threading.Thread) -> None:
        nonlocal starts
        starts += 1
        if starts == 2:
            deadline = time.monotonic() + 1.0
            while not pid_path.exists() and time.monotonic() < deadline:
                _ = threading.Event().wait(0.005)
            assert pid_path.exists()
            raise OSError("reader start failed")
        original_start(reader)

    monkeypatch.setattr(threading.Thread, "start", fail_second_start)

    # When: bounded execution launches its readers
    result = run_bounded([sys.executable, "-c", script], timeout=2.0)

    # Then: failure is returned without escaping or leaking the process/first reader
    assert result is None
    _assert_reaped(int(pid_path.read_text()))
    _assert_no_readers()


def test_run_bounded_passes_json_value_atom_byte_exact() -> None:
    # Given: a JSON-array config value carrying whitespace and shell metacharacters
    payload = '["/srv/a ws:/workspace:ro", "/srv/$(touch pwned):/data:rw"]'
    script = "import sys; sys.stdout.write(sys.argv[1])"

    # When: the value crosses the bounded argv boundary
    result = run_bounded([sys.executable, "-c", script, payload], timeout=5.0)

    # Then: the atom arrives byte-exactly — argv is never shelled or reformatted
    assert result is not None
    assert result.returncode == 0
    assert result.stdout == payload
