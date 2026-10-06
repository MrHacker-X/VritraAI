"""Ctrl+C safety: cancel the active operation, never quit VritraAI."""
from __future__ import annotations

import os
import signal
import subprocess
import threading
from contextlib import contextmanager
from typing import Generator, Optional

_lock = threading.Lock()
_busy = False
_cancel = False
_active_proc: Optional[subprocess.Popen] = None
_installed = False


class Cancelled(Exception):
    """Raised when the user cancels the current operation with Ctrl+C."""


def install_sigint_handler() -> None:
    """Install SIGINT handler once. Safe to call repeatedly."""
    global _installed
    if _installed:
        return
    try:
        signal.signal(signal.SIGINT, _on_sigint)
        _installed = True
    except Exception:
        # Environments that forbid signal handlers (some threads/tests)
        pass


def _on_sigint(signum, frame) -> None:  # noqa: ANN001
    request_cancel()
    kill_active_process()
    # Always raise KeyboardInterrupt so Python unwinds the current call stack.
    # The main REPL catches it and returns to the prompt (does not exit).
    raise KeyboardInterrupt


def request_cancel() -> None:
    with _lock:
        global _cancel
        _cancel = True


def clear_cancel() -> None:
    with _lock:
        global _cancel
        _cancel = False


def is_cancelled() -> bool:
    with _lock:
        return _cancel


def check_cancelled() -> None:
    if is_cancelled():
        raise Cancelled("Operation cancelled by user (Ctrl+C)")


def set_busy(busy: bool) -> None:
    with _lock:
        global _busy
        _busy = busy


def is_busy() -> bool:
    with _lock:
        return _busy


@contextmanager
def operation(label: str = "work") -> Generator[None, None, None]:
    """Mark a cancellable block (agent / slash command / AI call)."""
    clear_cancel()
    set_busy(True)
    try:
        yield
    finally:
        kill_active_process()
        set_busy(False)


def register_process(proc: subprocess.Popen) -> None:
    with _lock:
        global _active_proc
        _active_proc = proc


def clear_process(proc: Optional[subprocess.Popen] = None) -> None:
    with _lock:
        global _active_proc
        if proc is None or _active_proc is proc:
            _active_proc = None


def kill_active_process() -> bool:
    """Terminate the tracked subprocess (and its group) if running."""
    with _lock:
        proc = _active_proc
    if proc is None or proc.poll() is not None:
        clear_process(proc)
        return False
    try:
        if os.name != "nt":
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGINT)
            except (ProcessLookupError, PermissionError, OSError):
                proc.send_signal(signal.SIGINT)
        else:
            proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    clear_process(proc)
    return True


def run_cancellable(
    command: str,
    *,
    cwd: str,
    env: Optional[dict] = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess:
    """
    Like subprocess.run, but registers the process so Ctrl+C can kill it.
    Raises Cancelled if interrupted.
    """
    check_cancelled()
    popen_kwargs = {
        "shell": True,
        "cwd": cwd,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "env": env,
    }
    if os.name != "nt":
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen(command, **popen_kwargs)
    register_process(proc)
    try:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_active_process()
            raise
        if is_cancelled():
            raise Cancelled("Command cancelled by user (Ctrl+C)")
        return subprocess.CompletedProcess(command, proc.returncode or 0, stdout, stderr)
    except KeyboardInterrupt:
        kill_active_process()
        request_cancel()
        raise Cancelled("Command cancelled by user (Ctrl+C)")
    finally:
        clear_process(proc)
