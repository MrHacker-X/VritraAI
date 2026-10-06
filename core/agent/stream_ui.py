"""Live token streaming UI for agent model turns."""
from __future__ import annotations

import os
import re
import sys
from typing import Optional


def streaming_enabled() -> bool:
    raw = os.environ.get("VRITRA_AGENT_STREAM", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


_MONOLOGUE = re.compile(
    r"(?is)\b("
    r"first[, ]+i need|looking at the|the user wants|let'?s (?:look|check|start)|"
    r"i (?:will|need to|should|can) (?:address|confirm|update|refine)|"
    r"wait, the objective|actually, i'?ll"
    r")\b"
)


class LiveNarration:
    """
    Prints short assistant narration as tokens arrive (muted · line).
    Suppresses tool/protocol JSON and long internal monologues.
    Stops the wait spinner on first visible token.
    """

    def __init__(self) -> None:
        self._started = False
        self._suppressed = False
        self._buf: list[str] = []
        self._printed_any = False
        self._printed_chars = 0
        self._prefix = "\033[38;5;245m·\033[0m \033[38;5;245m"
        self._reset = "\033[0m"
        self._cleared_status = False
        self._max_print = 280  # keep the terminal usable

    @property
    def printed(self) -> bool:
        return self._printed_any

    def _ensure_status_cleared(self) -> None:
        if self._cleared_status:
            return
        self._cleared_status = True
        try:
            from core.agent.status import stop_status

            stop_status(clear=True)
        except Exception:
            pass

    def feed(self, chunk: Optional[str]) -> None:
        if not chunk:
            return
        self._buf.append(chunk)
        if self._suppressed:
            return

        peek = "".join(self._buf).lstrip()
        if not self._started and peek.startswith("{"):
            self._suppressed = True
            self._ensure_status_cleared()
            return

        # Hide long planning monologues (common on Gemma / thinking models)
        if len(peek) > 160 and _MONOLOGUE.search(peek[:500]):
            self._suppressed = True
            self._ensure_status_cleared()
            return

        self._ensure_status_cleared()
        if self._printed_chars >= self._max_print:
            return
        if not self._started:
            sys.stdout.write(self._prefix)
            self._started = True
            self._printed_any = True
        room = self._max_print - self._printed_chars
        piece = chunk[:room]
        sys.stdout.write(piece)
        self._printed_chars += len(piece)
        if self._printed_chars >= self._max_print:
            sys.stdout.write("…")
        sys.stdout.flush()

    def close(self) -> str:
        text = "".join(self._buf)
        self._ensure_status_cleared()
        if self._started and not self._suppressed:
            sys.stdout.write(self._reset + "\n")
            sys.stdout.flush()
        return text

    def text(self) -> str:
        return "".join(self._buf)
