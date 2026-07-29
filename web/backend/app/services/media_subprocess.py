from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from queue import Empty, Queue


class JobCancelled(Exception):
    pass


class MediaProcessError(RuntimeError):
    def __init__(self, message: str, stderr: str) -> None:
        super().__init__(message)
        self.stderr = stderr


def run_capture_process(
    command: Sequence[str],
    *,
    cancelled: Callable[[], bool],
    timeout_seconds: float,
    stderr_max_chars: int = 4000,
) -> tuple[str, str]:
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=os.name != "nt",
        creationflags=creationflags,
    )
    deadline = time.monotonic() + timeout_seconds
    while True:
        if cancelled():
            _terminate_process_group(process)
            raise JobCancelled()
        if time.monotonic() >= deadline:
            _terminate_process_group(process)
            raise MediaProcessError("Media process timed out", "")
        try:
            stdout, stderr = process.communicate(timeout=0.1)
            break
        except subprocess.TimeoutExpired:
            continue
    bounded_stderr = stderr[-stderr_max_chars:]
    if process.returncode != 0:
        raise MediaProcessError(
            f"Media process exited with status {process.returncode}",
            bounded_stderr,
        )
    return stdout, bounded_stderr


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def run_json_progress_process(
    command: Sequence[str],
    *,
    cancelled: Callable[[], bool],
    progress: Callable[[dict], None],
    stderr_max_chars: int = 4000,
    progress_line_max_chars: int = 4096,
) -> str:
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        list(command),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        start_new_session=os.name != "nt",
        creationflags=creationflags,
    )
    queue: Queue[tuple[str, str | None]] = Queue()
    stderr_lines: deque[str] = deque()

    def read_stream(name: str, stream) -> None:
        try:
            for line in iter(stream.readline, ""):
                queue.put((name, line))
        finally:
            queue.put((name, None))
            stream.close()

    assert process.stdout is not None
    assert process.stderr is not None
    threads = [
        threading.Thread(target=read_stream, args=("stdout", process.stdout), daemon=True),
        threading.Thread(target=read_stream, args=("stderr", process.stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()

    closed_streams = 0
    try:
        while closed_streams < 2 or process.poll() is None:
            if cancelled():
                _terminate_process_group(process)
                raise JobCancelled()
            try:
                stream_name, line = queue.get(timeout=0.1)
            except Empty:
                continue
            if line is None:
                closed_streams += 1
                continue
            bounded = line[-progress_line_max_chars:].rstrip()
            if stream_name == "stderr":
                stderr_lines.append(bounded)
                while len("\n".join(stderr_lines)) > stderr_max_chars:
                    stderr_lines.popleft()
                continue
            try:
                event = json.loads(bounded)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                progress(event)
        return_code = process.wait()
    finally:
        if process.poll() is None:
            _terminate_process_group(process)
        for thread in threads:
            thread.join(timeout=1)

    stderr = "\n".join(stderr_lines)[-stderr_max_chars:]
    if return_code != 0:
        raise MediaProcessError(
            f"Media process exited with status {return_code}", stderr
        )
    return stderr
