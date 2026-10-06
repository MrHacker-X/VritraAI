"""Git inspection + approved mutation tools."""
from __future__ import annotations

import shlex
from typing import Any, Dict, List, Optional

from core.agent.approval import ApprovalManager
from core.agent.tools.base import ToolRegistry
from core.agent.types import ToolResult, ToolSpec
from core.agent.workspace import WorkspaceManager
from core.interrupt import Cancelled, run_cancellable


def register_git_tools(
    registry: ToolRegistry,
    workspace: WorkspaceManager,
    approval: Optional[ApprovalManager] = None,
) -> None:
    def _git(args: str) -> ToolResult:
        try:
            proc = run_cancellable(
                f"git {args}",
                cwd=str(workspace.root),
                timeout=60,
            )
        except Cancelled as e:
            return ToolResult("", "git", False, str(e))
        except Exception as e:
            return ToolResult("", "git", False, str(e))
        body = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        return ToolResult(
            "",
            "git",
            proc.returncode == 0,
            body.strip() or "(empty)",
            {"exit_code": proc.returncode},
        )

    def git_status(args: Dict[str, Any]) -> ToolResult:
        r = _git("status --short --branch")
        r.name = "git_status"
        return r

    def git_diff(args: Dict[str, Any]) -> ToolResult:
        path = (args.get("path") or "").strip()
        staged = bool(args.get("staged"))
        cmd = "diff --stat" if args.get("stat") else "diff"
        if staged:
            cmd += " --staged"
        if path:
            p, err = workspace.resolve(path)
            if err or p is None:
                return ToolResult("", "git_diff", False, err or "bad path")
            cmd += f" -- {workspace.rel(p)}"
        r = _git(cmd)
        r.name = "git_diff"
        if len(r.output) > 14000:
            r.output = r.output[:14000] + "\n…[truncated]"
        return r

    def git_log(args: Dict[str, Any]) -> ToolResult:
        n = int(args.get("limit") or 8)
        n = max(1, min(n, 30))
        r = _git(f"log -n {n} --oneline --decorate")
        r.name = "git_log"
        return r

    def git_add(args: Dict[str, Any]) -> ToolResult:
        paths = args.get("paths") or []
        if isinstance(paths, str):
            paths = [paths]
        if not isinstance(paths, list) or not paths:
            return ToolResult("", "git_add", False, "paths must be a non-empty list (or ['.'])")
        resolved: List[str] = []
        for raw in paths[:40]:
            raw_s = str(raw).strip()
            if raw_s in {".", "all", "--all"}:
                resolved = ["."]
                break
            p, err = workspace.resolve(raw_s)
            if err or p is None:
                return ToolResult("", "git_add", False, err or f"bad path: {raw_s}")
            resolved.append(workspace.rel(p))

        detail = ", ".join(resolved)
        if approval and not approval.approve(
            action="git add",
            risk="ask",
            detail=detail,
            kind="shell",
        ):
            return ToolResult("", "git_add", False, "User denied git add")

        if resolved == ["."]:
            cmd = "add -A"
        else:
            cmd = "add -- " + " ".join(shlex.quote(p) for p in resolved)
        r = _git(cmd)
        r.name = "git_add"
        if r.ok:
            r.output = f"Staged: {detail}\n" + (r.output or "")
        return r

    def git_commit(args: Dict[str, Any]) -> ToolResult:
        message = (args.get("message") or "").strip()
        if not message:
            return ToolResult("", "git_commit", False, "message required")
        if "\n\n\n" in message or len(message) > 4000:
            return ToolResult("", "git_commit", False, "message too long / malformed")

        # Preview staged diff for approval context
        preview = _git("diff --staged --stat")
        detail = f"{message[:120]}\n{preview.output[:400]}"
        if approval and not approval.approve(
            action="git commit",
            risk="ask",
            detail=detail,
            kind="shell",
        ):
            return ToolResult("", "git_commit", False, "User denied git commit")

        # Allow empty? No - require staged changes
        status = _git("diff --staged --name-only")
        if not (status.output or "").strip():
            return ToolResult(
                "",
                "git_commit",
                False,
                "Nothing staged. Use git_add first.",
            )

        r = _git(f"commit -m {shlex.quote(message)}")
        r.name = "git_commit"
        return r

    registry.register(
        ToolSpec(
            "git_status",
            "Show git branch and short status of the workspace repo.",
            {"type": "object", "properties": {}},
            "safe",
        ),
        git_status,
    )
    registry.register(
        ToolSpec(
            "git_diff",
            "Show git diff (optionally staged, path, or --stat).",
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "staged": {"type": "boolean"},
                    "stat": {"type": "boolean"},
                },
            },
            "safe",
        ),
        git_diff,
    )
    registry.register(
        ToolSpec(
            "git_log",
            "Show recent commit history (oneline).",
            {
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
            },
            "safe",
        ),
        git_log,
    )
    registry.register(
        ToolSpec(
            "git_add",
            "Stage files for commit (paths list, or ['.'] for all). Requires approval.",
            {
                "type": "object",
                "properties": {
                    "paths": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["paths"],
            },
            "ask",
        ),
        git_add,
    )
    registry.register(
        ToolSpec(
            "git_commit",
            "Create a git commit from staged changes with a message. Requires approval. Never push.",
            {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
            "ask",
        ),
        git_commit,
    )
