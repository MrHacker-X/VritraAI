"""Codex-style agent progress UI."""
from __future__ import annotations

from typing import TYPE_CHECKING, List

from core.agent.types import ToolCall, ToolResult

if TYPE_CHECKING:
    from core.agent.failover import SwitchResult
    from core.agent.provider_util import ProviderFault


def _short_path(path: object) -> str:
    """Prefer a short relative-looking path for status lines."""
    s = str(path or "?")
    if "/site/" in s:
        return "site/" + s.split("/site/", 1)[1]
    if s.startswith("/") and s.count("/") >= 2:
        return "/".join(s.strip("/").split("/")[-2:])
    return s


def event(message: str, *, kind: str = "work") -> None:
    if kind == "ok":
        print(f"\033[38;5;114m✓\033[0m {message}")
    elif kind == "err":
        print(f"\033[38;5;203m✗\033[0m {message}")
    elif kind == "ask":
        print(f"\033[38;5;214m?\033[0m {message}")
    elif kind == "think":
        print(f"\033[38;5;245m·\033[0m \033[38;5;245m{message}\033[0m")
    else:
        print(f"\033[38;5;110m●\033[0m {message}")


def provider_fault(fault: "ProviderFault", *, streak: int = 0, soft_limit: int = 2) -> None:
    """Compact professional provider error - never dumps raw HTTP bodies."""
    print()
    print(f"\033[38;5;203m✗\033[0m \033[1;97m{fault.title}\033[0m")
    meta = " · ".join(
        p for p in (fault.provider, fault.model, fault.code.replace("_", " ")) if p
    )
    if meta:
        print(f"  \033[38;5;245m{meta}\033[0m")
    if fault.detail:
        print(f"  {fault.detail}")
    if streak and streak < soft_limit and not fault.hard:
        left = soft_limit - streak
        print(
            f"  \033[38;5;245mRetrying - auto-switch after {left} more failure"
            f"{'s' if left != 1 else ''} on this model\033[0m"
        )
    print()


def model_failover(switch: "SwitchResult") -> None:
    """Announce automatic model switch."""
    if switch.reason == "switched" and switch.ok:
        print(
            f"\033[38;5;214m↻\033[0m \033[1;97mSwitched model\033[0m  "
            f"\033[38;5;245m{switch.from_display}\033[0m → "
            f"\033[38;5;114m{switch.to_display}\033[0m"
        )
        print(
            f"  \033[38;5;245m{switch.from_provider}/{switch.from_model}  →  "
            f"{switch.to_provider}/{switch.to_model}\033[0m"
        )
        print()
        return
    if switch.reason == "exhausted":
        event("All configured models failed - run /model or check API keys", kind="err")
        return
    if switch.reason == "limit":
        event("Auto-switch limit reached - pick a model with /model", kind="err")


def describe_call(call: ToolCall) -> str:
    args = call.arguments or {}
    name = call.name
    if name == "read_file":
        return f"Read {args.get('path', '?')}"
    if name == "read_files":
        paths = args.get("paths") or []
        return f"Read {len(paths)} files"
    if name == "list_directory":
        return f"List {args.get('path', '.')}"
    if name == "ensure_dir":
        return f"Ensure dir {args.get('path', '?')}"
    if name == "write_file":
        return f"Write {args.get('path', '?')}"
    if name == "write_files":
        if (args or {}).get("arguments_invalid"):
            return "Write files"
        files = args.get("files") or []
        n = len(files) if isinstance(files, list) else 0
        return f"Write {n} files" if n else "Write files"
    if name == "replace_in_file":
        return f"Edit {_short_path(args.get('path', '?'))}"
    if name == "apply_edits":
        edits = args.get("edits") or []
        n = len(edits) if isinstance(edits, list) else 0
        return f"Edit {n} files" if n else "Apply edits"
    if name == "delete_file":
        return f"Delete {args.get('path', '?')}"
    if name == "search_text":
        q = str(args.get("query", "?"))
        return f"Search {q!r}" if len(q) < 48 else f"Search {q[:45]!r}…"
    if name == "code_search":
        q = str(args.get("query", "?"))
        return f"Code search {q!r}" if len(q) < 40 else f"Code search {q[:37]!r}…"
    if name == "glob_files":
        return f"Glob {args.get('pattern', '?')}"
    if name == "run_command":
        cmd = str(args.get("command", ""))
        return f"$ {cmd}" if len(cmd) < 88 else f"$ {cmd[:85]}…"
    if name == "verify_project":
        if args.get("list_only"):
            return "List verify commands"
        prefer = args.get("prefer") or ""
        return f"Verify project{f' ({prefer})' if prefer else ''}"
    if name == "inspect_project":
        return "Inspect project"
    if name == "list_dependencies":
        return "List dependencies"
    if name == "project_health":
        return "Project health"
    if name == "analyze_code":
        return f"Analyze {args.get('path', '?')} · {args.get('mode', 'review')}"
    if name == "git_status":
        return "git status"
    if name == "git_diff":
        return "git diff"
    if name == "git_log":
        return "git log"
    if name == "git_add":
        paths = args.get("paths") or []
        n = len(paths) if isinstance(paths, list) else 0
        return f"git add ({n} paths)" if n else "git add"
    if name == "git_commit":
        msg = str(args.get("message") or "")
        return f"git commit {msg!r}" if len(msg) < 40 else f"git commit {msg[:37]!r}…"
    if name == "todo_write":
        return "Update plan"
    if name == "finish_task":
        return "Complete"
    return name


def show_result(call: ToolCall, result: ToolResult) -> None:
    label = describe_call(call)
    if result.ok:
        if call.name == "run_command":
            code = result.meta.get("exit_code")
            event(f"{label}  \033[38;5;245m(exit {code})\033[0m", kind="ok" if code == 0 else "err")
        elif call.name == "finish_task":
            event(label, kind="ok")
        elif call.name == "todo_write":
            event(label, kind="think")
        elif call.name in {"write_files", "apply_edits"}:
            event(label, kind="ok")
        else:
            event(label, kind="work")
    else:
        first = (result.output or "").splitlines()[0][:140] if result.output else "failed"
        event(f"{label} - {first}", kind="err")


def show_summary(
    summary: str,
    *,
    files_changed: List[str],
    commands: List[str],
    files_read: List[str] | None = None,
    todos: List[dict] | None = None,
) -> None:
    print()
    print("\033[1;97mDone\033[0m")
    print("\033[38;5;240m" + "─" * 44 + "\033[0m")
    print(summary.strip() or "(no summary)")
    if files_changed:
        print()
        print("\033[38;5;245mChanged\033[0m")
        for f in files_changed:
            print(f"  \033[38;5;114m•\033[0m {f}")
    elif files_read:
        print()
        print("\033[38;5;245mInspected\033[0m")
        for f in files_read[:12]:
            print(f"  \033[38;5;245m•\033[0m {f}")
        if len(files_read) > 12:
            print(f"  \033[38;5;245m• … +{len(files_read) - 12} more\033[0m")
    if commands:
        print()
        print("\033[38;5;245mCommands\033[0m")
        for c in commands[-10:]:
            print(f"  \033[38;5;245m$\033[0m {c}")
    print()
