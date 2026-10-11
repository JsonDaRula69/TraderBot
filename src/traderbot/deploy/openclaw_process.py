"""Cross-platform bounded process collection for OpenClaw commands."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from contextlib import suppress
from typing import BinaryIO, Final

_MAX_OUTPUT_BYTES: Final = 1_048_576
_READ_CHUNK_BYTES: Final = 65_536
_WAIT_SLICE_SECONDS: Final = 0.02
_CLEANUP_SECONDS: Final = 0.4
_WINDOWS_NEW_PROCESS_GROUP: Final = 0x00000200
_WINDOWS_CTRL_BREAK_EVENT: Final = 1


def _read_pipe(
    stream: BinaryIO,
    output: bytearray,
    failed: threading.Event,
) -> None:
    try:
        while not failed.is_set():
            chunk = stream.read(_READ_CHUNK_BYTES)
            if not chunk:
                return
            remaining = _MAX_OUTPUT_BYTES - len(output)
            output.extend(chunk[:remaining])
            if len(chunk) > remaining:
                failed.set()
                return
    except OSError:
        failed.set()
    finally:
        stream.close()


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=_CLEANUP_SECONDS,
            )
            if result.returncode != 0:
                os.kill(process.pid, _WINDOWS_CTRL_BREAK_EVENT)
        except (OSError, subprocess.TimeoutExpired):
            with suppress(OSError):
                os.kill(process.pid, _WINDOWS_CTRL_BREAK_EVENT)
    else:
        with suppress(PermissionError, ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
    if process.poll() is None:
        process.kill()


def run_bounded(
    argv: list[str],
    *,
    timeout: float,
) -> subprocess.CompletedProcess[str] | None:
    """Run one argv command with per-stream limits and guaranteed process reaping."""
    try:
        process = subprocess.Popen(
            argv,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            bufsize=0,
            start_new_session=os.name != "nt",
            creationflags=_WINDOWS_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
    except OSError:
        return None

    stdout = process.stdout
    stderr = process.stderr
    if stdout is None or stderr is None:
        process.kill()
        _ = process.wait()
        return None

    output = bytearray()
    errors = bytearray()
    failed = threading.Event()
    readers = (
        threading.Thread(
            target=_read_pipe,
            args=(stdout, output, failed),
            name=f"openclaw-stdout-{process.pid}",
            daemon=False,
        ),
        threading.Thread(
            target=_read_pipe,
            args=(stderr, errors, failed),
            name=f"openclaw-stderr-{process.pid}",
            daemon=False,
        ),
    )
    deadline = time.monotonic() + timeout
    timed_out = False
    reader_launch_failed = False
    started: list[threading.Thread] = []
    returncode: int | None = None
    try:
        for reader in readers:
            try:
                reader.start()
            except (OSError, RuntimeError):
                reader_launch_failed = True
                break
            started.append(reader)
        while not reader_launch_failed and not failed.is_set():
            returncode = process.poll()
            if returncode is not None and all(not reader.is_alive() for reader in started):
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            if returncode is None:
                try:
                    _ = process.wait(timeout=min(remaining, _WAIT_SLICE_SECONDS))
                except subprocess.TimeoutExpired:
                    continue
            else:
                time.sleep(min(remaining, _WAIT_SLICE_SECONDS))
    finally:
        failed_execution = timed_out or reader_launch_failed or failed.is_set()
        if failed_execution or any(reader.is_alive() for reader in started):
            _terminate_process_tree(process)
        for stream, reader in zip((stdout, stderr), readers, strict=True):
            if reader not in started:
                stream.close()
        cleanup_deadline = time.monotonic() + _CLEANUP_SECONDS
        if process.poll() is None:
            try:
                returncode = process.wait(timeout=_CLEANUP_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                returncode = process.wait()
        else:
            returncode = process.wait()
        for reader in started:
            reader.join(timeout=max(0.0, cleanup_deadline - time.monotonic()))

    if (
        timed_out
        or reader_launch_failed
        or failed.is_set()
        or any(reader.is_alive() for reader in started)
    ):
        return None
    try:
        stdout_text = bytes(output).decode("utf-8")
        stderr_text = bytes(errors).decode("utf-8")
    except UnicodeDecodeError:
        return None
    return subprocess.CompletedProcess(argv, returncode, stdout_text, stderr_text)
