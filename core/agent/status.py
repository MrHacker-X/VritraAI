"""Animated in-place status line for agent wait / work phases."""
from __future__ import annotations

import sys
import threading
import time
from typing import List, Optional


_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
_MUTED = "\033[38;5;245m"
_ACCENT = "\033[38;5;110m"
_RESET = "\033[0m"
_CLEAR = "\033[2K"  # clear entire line

# Model HTTP calls - surface the real wall-clock limit in the spinner.
try:
    from core.agent.provider_util import model_call_timeout_sec as _model_timeout

    _MODEL_TIMEOUT_HINT = _model_timeout()
except Exception:
    _MODEL_TIMEOUT_HINT = 120


class StatusSpinner:
    """
    Single-line live status: ⠋ Thinking · …
    Clears itself when stopped so streaming / tool events can follow cleanly.

    kind="model" escalates labels by elapsed time so long API waits read as
    "still waiting", not a frozen "Planning next steps".
    """

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._label = "Thinking"
        self._lock = threading.Lock()
        self._active = False
        self._phases: List[str] = []
        self._phase_i = 0
        self._started_at = 0.0
        self._kind = "work"

    @property
    def active(self) -> bool:
        return self._active

    def start(
        self,
        label: str = "Thinking",
        *,
        phases: Optional[List[str]] = None,
        kind: str = "work",
    ) -> None:
        self.stop(clear=True)
        with self._lock:
            self._label = label
            self._phases = list(phases) if phases else []
            self._phase_i = 0
            self._kind = kind or "work"
            self._stop.clear()
            self._active = True
            self._started_at = time.time()
            # Paint immediately so the line never blanks between stop and first tick
            try:
                sys.stdout.write(
                    f"\r{_CLEAR}{_ACCENT}{_FRAMES[0]}{_RESET} {_MUTED}{label}{_RESET}"
                )
                sys.stdout.flush()
            except Exception:
                pass
            self._thread = threading.Thread(target=self._run, name="vritra-status", daemon=True)
            self._thread.start()

    def set_label(self, label: str) -> None:
        with self._lock:
            self._label = label
            # Manual label overrides phase cycling until next start
            self._phases = []

    def stop(self, *, clear: bool = True) -> None:
        with self._lock:
            thread = self._thread
            was_active = self._active
            self._active = False
            self._stop.set()
            self._thread = None
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.6)
        if was_active and clear:
            try:
                sys.stdout.write(f"\r{_CLEAR}")
                sys.stdout.flush()
            except Exception:
                pass

    def _model_label(self, elapsed: int, phase_label: str) -> str:
        """Honest wait copy so long API stalls don't look like a hung planner."""
        provider = ""
        model = ""
        try:
            from core import runtime

            provider = str(getattr(runtime, "API_BASE", "") or "")
            model = str(getattr(runtime, "MODEL", "") or "")
        except Exception:
            pass
        short = model.split("/")[-1] if model else ""
        where = f"{provider}/{short}" if provider and short else (provider or short or "model")

        if elapsed >= 120:
            return (
                f"Still waiting on {where} · {elapsed}s "
                f"(timeout ~{_MODEL_TIMEOUT_HINT}s · Ctrl+C cancel)"
            )
        if elapsed >= 45:
            return f"Waiting for {where} · {elapsed}s - model is slow, not stuck"
        if elapsed >= 15:
            return f"Waiting for {where} · {elapsed}s"
        # Early: short rotating hints + time
        return f"{phase_label} · {where}"

    def _run(self) -> None:
        frame_i = 0
        last_phase_swap = time.time()
        while not self._stop.wait(0.08):
            now = time.time()
            with self._lock:
                if self._phases and (now - last_phase_swap) >= 2.2:
                    self._phase_i = (self._phase_i + 1) % len(self._phases)
                    self._label = self._phases[self._phase_i]
                    last_phase_swap = now
                label = self._label
                kind = self._kind
            elapsed = max(0, int(now - self._started_at))
            if kind == "model":
                label = self._model_label(elapsed, label)
                suffix = ""
            else:
                suffix = f"  {_MUTED}{elapsed}s{_RESET}" if elapsed >= 2 else ""
            frame = _FRAMES[frame_i % len(_FRAMES)]
            frame_i += 1
            line = f"\r{_CLEAR}{_ACCENT}{frame}{_RESET} {_MUTED}{label}{_RESET}{suffix}"
            try:
                sys.stdout.write(line)
                sys.stdout.flush()
            except Exception:
                break


# Process-wide spinner used by llm / tools / stream handoff
_GLOBAL = StatusSpinner()


def start_status(
    label: str = "Thinking",
    *,
    phases: Optional[List[str]] = None,
    kind: str = "work",
) -> None:
    _GLOBAL.start(label, phases=phases, kind=kind)


def set_status(label: str) -> None:
    _GLOBAL.set_label(label)


def stop_status(*, clear: bool = True) -> None:
    _GLOBAL.stop(clear=clear)


def status_active() -> bool:
    return _GLOBAL.active


# Sensible phase packs for the agent / normal assistant
PHASES_MODEL = [
    "Calling model",
    "Waiting for reply",
    "Model is thinking",
]
PHASES_WORKING = [
    "Working",
    "Applying changes",
    "Following the plan",
]
PHASES_ASSISTANT = [
    "Calling model",
    "Waiting for reply",
    "Drafting reply",
]
