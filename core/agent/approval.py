"""Professional approval UI for agent mutations."""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import List, Optional, Sequence, Set

from core import runtime

DEFAULT_MODE = "ask"
TRUST_MODES = frozenset({"ask", "auto", "safe"})

_DANGEROUS_SHELL = re.compile(
    r"""(?ix)
    \b(rm\s+-rf|rm\s+-r\b|sudo\b|mkfs\b|dd\s+if=|
       git\s+reset\s+--hard|git\s+clean\s+-f|
       shutdown\b|reboot\b|chmod\s+-R\s+777|
       curl\s+[^\n]*\|\s*(ba)?sh|
       wget\s+[^\n]*\|\s*(ba)?sh|
       >\s*/dev/sd|:\(\)\s*\{)
    """
)

_SAFE_SHELL = re.compile(
    r"""(?ix)^\s*(
        (git\s+(status|diff|log|show|branch|rev-parse|remote\s+-v|ls-tree|ls-files))|
        (python3?\s+-m\s+pytest|pytest|python3?\s+-m\s+unittest|
         npm\s+test|npm\s+run\s+test|npx\s+.*test|
         cargo\s+test|go\s+test|make\s+test|
         npm\s+run\s+build|cargo\s+build|go\s+build|
         python3?\s+-m\s+py_compile|python3?\s+-m\s+compileall|
         python3?\s+-c\s+|
         ls|pwd|rg\b|grep\b|find\b|wc\b|head\b|tail\b|cat\b|
         echo\b|which\b|type\b|node\s+-v|python3?\s+--version)
    )""",
)


class ApprovalManager:
    """
    Modes:
      ask  - prompt for edits/shell (professional card)
      auto - trust this workspace (no prompts)
      safe - block dangerous; ask for other mutations
    """

    def __init__(self, mode: str = DEFAULT_MODE) -> None:
        self.mode = mode if mode in TRUST_MODES else DEFAULT_MODE
        self._write_trusted = False
        self._shell_trusted = False
        self._denied: Set[str] = set()

    def classify_shell(self, command: str) -> str:
        cmd = (command or "").strip()
        if not cmd:
            return "ask"
        if _DANGEROUS_SHELL.search(cmd):
            return "dangerous"
        if re.search(
            r"\b(pip|npm|yarn|pnpm|apt|yum|brew|cargo)\s+(install|add|remove|uninstall)\b",
            cmd,
            re.I,
        ):
            return "ask"
        if _SAFE_SHELL.search(cmd):
            return "safe"
        return "ask"

    def needs_approval(self, risk: str, *, detail: str = "") -> bool:
        if self.mode == "auto":
            return False
        if risk == "safe":
            return False
        if self.mode == "safe":
            return True
        return risk in {"ask", "dangerous"}

    def approve(
        self,
        *,
        action: str,
        risk: str,
        detail: str = "",
        kind: str = "generic",
    ) -> bool:
        """
        kind: edit | write | delete | shell | generic
        Diff/preview should already be printed by the caller before this.
        """
        if self.mode == "auto" or risk == "safe":
            return True

        if kind in {"edit", "write"} and self._write_trusted and risk != "dangerous":
            return True
        if kind == "shell" and self._shell_trusted and risk != "dangerous":
            return True

        if self.mode == "safe" and risk == "dangerous":
            self._print_card(
                title="Blocked",
                subtitle=action,
                detail=detail or "Dangerous operation blocked in safe mode.",
                options=[],
            )
            return False

        if self.mode == "safe" and risk != "dangerous":
            # still ask in safe for mutations
            pass

        key = f"{action}:{detail}:{kind}"
        if key in self._denied:
            return False

        choice = self._prompt_card(action=action, risk=risk, detail=detail, kind=kind)
        if choice == "always":
            if kind in {"edit", "write"}:
                self._write_trusted = True
            if kind == "shell":
                self._shell_trusted = True
            return True
        if choice == "once":
            if kind in {"edit", "write"}:
                # optional soft-trust after first allow - keep explicit always for clarity
                pass
            return True
        self._denied.add(key)
        return False

    def approve_batch(
        self,
        *,
        action: str,
        paths: Sequence[str],
        risk: str = "ask",
        kind: str = "write",
    ) -> bool:
        """One approval card for multiple file changes. [y] [a] [n]."""
        path_list = [str(p) for p in paths if str(p).strip()]
        if not path_list:
            return False
        detail = "\n".join(f"• {p}" for p in path_list[:20])
        if len(path_list) > 20:
            detail += f"\n• … +{len(path_list) - 20} more"
        title_action = action or f"Apply {len(path_list)} file changes"
        # Reuse trust flags via approve with multi-line detail
        if self.mode == "auto" or risk == "safe":
            return True
        if kind in {"edit", "write"} and self._write_trusted and risk != "dangerous":
            return True
        if self.mode == "safe" and risk == "dangerous":
            self._print_card(
                title="Blocked",
                subtitle=title_action,
                detail=detail,
                options=[],
            )
            return False

        key = f"batch:{title_action}:{','.join(path_list)}:{kind}"
        if key in self._denied:
            return False

        risk_label = {
            "safe": "safe",
            "ask": "needs approval",
            "dangerous": "destructive",
        }.get(risk, risk)
        options = [
            ("y", "Allow once"),
            ("a", "Always allow this session"),
            ("n", "Deny"),
        ]
        try:
            from core.agent.status import stop_status

            stop_status(clear=True)
        except Exception:
            pass
        self._print_card(
            title=f"Apply {len(path_list)} file changes",
            subtitle=f"{title_action}  ·  {risk_label}",
            detail=detail,
            options=options,
            multiline_detail=True,
        )
        try:
            raw = input("  › ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False

        if raw in {"", "y", "yes"}:
            return True
        if raw in {"a", "always", "trust"}:
            if kind in {"edit", "write"}:
                self._write_trusted = True
            if kind == "shell":
                self._shell_trusted = True
            return True
        self._denied.add(key)
        return False

    def _prompt_card(
        self,
        *,
        action: str,
        risk: str,
        detail: str,
        kind: str,
    ) -> str:
        risk_label = {
            "safe": "safe",
            "ask": "needs approval",
            "dangerous": "destructive",
        }.get(risk, risk)

        options = [
            ("y", "Allow once"),
            ("a", "Always allow this session"),
            ("n", "Deny"),
        ]
        try:
            from core.agent.status import stop_status

            stop_status(clear=True)
        except Exception:
            pass
        self._print_card(
            title="Approval required",
            subtitle=f"{action}  ·  {risk_label}",
            detail=detail,
            options=options,
        )
        try:
            raw = input("  › ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return "deny"

        if raw in {"", "y", "yes"}:
            return "once"
        if raw in {"a", "always", "trust"}:
            return "always"
        return "deny"

    @staticmethod
    def _print_card(
        *,
        title: str,
        subtitle: str,
        detail: str,
        options: list,
        multiline_detail: bool = False,
    ) -> None:
        muted = "\033[90m"
        white = "\033[1;97m"
        amber = "\033[38;5;214m"
        reset = "\033[0m"
        width = 56
        print()
        print(f"{muted}╭{'─' * (width + 2)}╮{reset}")
        print(f"{muted}│{reset} {amber}{title}{' ' * max(0, width - len(title))}{reset} {muted}│{reset}")
        if subtitle:
            print(f"{muted}│{reset} {white}{subtitle[:width]}{' ' * max(0, width - len(subtitle[:width]))}{reset} {muted}│{reset}")
        if detail:
            lines: List[str] = detail.splitlines() if multiline_detail else [detail]
            for line in lines[:24]:
                chunk = line[:width]
                print(f"{muted}│{reset} {muted}{chunk}{' ' * max(0, width - len(chunk))}{reset} {muted}│{reset}")
        if options:
            print(f"{muted}│{' ' * (width + 2)}│{reset}")
            for key, label in options:
                line = f"[{key}]  {label}"
                print(f"{muted}│{reset} {line}{' ' * max(0, width - len(line))} {muted}│{reset}")
        print(f"{muted}╰{'─' * (width + 2)}╯{reset}")


def prompt_session_trust() -> Optional[str]:
    """
    Startup trust gate. Returns approval mode: ask | auto | safe.

    Returns None if the user cancels (q / Esc / Ctrl+C) - caller should abort launch.
    """
    from core.tui import Choice, arrow_select

    try:
        selected = arrow_select(
            "Trust this workspace",
            [
                Choice("ask", "Ask before changes"),
                Choice("auto", "Trust this workspace"),
                Choice("safe", "Strict mode for this workspace"),
            ],
            subtitle="Remembered for this folder - won't ask again here",
            initial=0,
            footer="↑/↓ · Enter confirm · Ctrl+C / q quit",
        )
    except KeyboardInterrupt:
        return None
    if selected not in TRUST_MODES:
        return None
    return selected


def _workspace_root(workspace: str | Path) -> Path:
    return Path(workspace).expanduser().resolve()


def _trust_store_path(workspace: str | Path) -> Path:
    """Per-workspace store: <project>/.vritraai/trust.json"""
    return _workspace_root(workspace) / ".vritraai" / "trust.json"


def _legacy_central_trust_path() -> Path:
    return Path(runtime.CONFIG_DIR) / "workspace_trust.json"


def _read_mode_from_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(data, dict):
        mode = data.get("mode")
        if isinstance(mode, str) and mode in TRUST_MODES:
            return mode
    return None


def _migrate_legacy_trust(workspace: str | Path) -> Optional[str]:
    """One-time: copy central path-keyed trust into .vritraai/, then drop that key."""
    key = str(_workspace_root(workspace))
    central = _legacy_central_trust_path()
    if not central.exists():
        return None
    try:
        data = json.loads(central.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    mode = data.get(key)
    if not (isinstance(mode, str) and mode in TRUST_MODES):
        return None
    if set_workspace_trust(workspace, mode):
        try:
            del data[key]
            if data:
                central.write_text(
                    json.dumps(data, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            else:
                central.unlink(missing_ok=True)
        except Exception:
            pass
        return mode
    return None


def get_workspace_trust(workspace: str | Path) -> Optional[str]:
    """Return trust mode from <workspace>/.vritraai/trust.json, or None."""
    mode = _read_mode_from_file(_trust_store_path(workspace))
    if mode:
        return mode
    return _migrate_legacy_trust(workspace)


def set_workspace_trust(workspace: str | Path, mode: str) -> bool:
    """Persist trust under the project: .vritraai/trust.json."""
    if mode not in TRUST_MODES:
        return False
    path = _trust_store_path(workspace)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Keep local-only files out of git; rules.md may still be committed if forced
        ignore = path.parent / ".gitignore"
        if not ignore.exists():
            try:
                ignore.write_text(
                    "trust.json\nagent_memory.json\n",
                    encoding="utf-8",
                )
            except Exception:
                pass
        payload = {"mode": mode}
        fd, tmp = tempfile.mkstemp(prefix="vritra-trust-", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
                f.write("\n")
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        return True
    except Exception:
        return False


def clear_workspace_trust(workspace: str | Path) -> bool:
    """Remove .vritraai/trust.json for this workspace."""
    path = _trust_store_path(workspace)
    try:
        if path.exists():
            path.unlink()
        return True
    except Exception:
        return False


def resolve_workspace_trust(workspace: str | Path) -> tuple[Optional[str], str]:
    """
    Resolve trust mode for a workspace.

    Returns (mode, source) where source is env | cache | prompt.
    mode is None if the user cancelled the prompt.
    """
    env_mode = os.environ.get("VRITRA_APPROVAL", "").strip().lower()
    if env_mode in TRUST_MODES:
        return env_mode, "env"

    if os.environ.get("VRITRA_RESET_TRUST", "").strip() in {"1", "true", "yes"}:
        clear_workspace_trust(workspace)
    else:
        cached = get_workspace_trust(workspace)
        if cached:
            return cached, "cache"

    mode = prompt_session_trust()
    if mode is None:
        return None, "prompt"
    set_workspace_trust(workspace, mode)
    return mode, "prompt"


TRUST_MODE_LABELS = {
    "ask": "ask before changes",
    "auto": "trust this workspace",
    "safe": "strict mode for this workspace",
}
