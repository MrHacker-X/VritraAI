"""Shell execution tool - non-interactive, timed, workspace-cwd."""
from __future__ import annotations

import subprocess
import time
from typing import Any, Dict, List

from core.agent.json_util import rewrite_shell_command
from core.agent.approval import ApprovalManager
from core.agent.tools.base import ToolRegistry
from core.agent.types import ToolResult, ToolSpec
from core.agent.workspace import WorkspaceManager


def register_shell_tools(
    registry: ToolRegistry,
    workspace: WorkspaceManager,
    approval: ApprovalManager,
    state_commands: List[str],
) -> None:
    def run_command(args: Dict[str, Any]) -> ToolResult:
        command = rewrite_shell_command((args.get("command") or "").strip())
        if not command:
            return ToolResult("", "run_command", False, "command required")
        timeout = int(args.get("timeout_seconds") or 120)
        timeout = max(5, min(timeout, 300))

        cwd = workspace.root
        if args.get("cwd"):
            resolved, err = workspace.resolve(args["cwd"])
            if err or resolved is None:
                return ToolResult("", "run_command", False, err or "bad cwd")
            if not resolved.is_dir():
                return ToolResult("", "run_command", False, "cwd is not a directory")
            cwd = resolved

        risk = approval.classify_shell(command)
        if approval.needs_approval(risk, detail=command):
            # Compact command preview card is handled inside approve()
            if not approval.approve(
                action="run shell command",
                risk=risk,
                detail=command if len(command) < 80 else command[:77] + "…",
                kind="shell",
            ):
                return ToolResult("", "run_command", False, "User denied command")

        state_commands.append(command)
        started = time.time()
        try:
            import os

            from core.agent.status import start_status, stop_status
            from core.interrupt import Cancelled, run_cancellable

            env = os.environ.copy()
            env["TERM"] = "dumb"
            preview = command if len(command) < 48 else command[:45] + "…"
            start_status(f"Running {preview}")
            try:
                proc = run_cancellable(
                    command,
                    cwd=str(cwd),
                    env=env,
                    timeout=timeout,
                )
            finally:
                stop_status(clear=True)
            duration = time.time() - started
            out = (proc.stdout or "")[-8000:]
            err = (proc.stderr or "")[-4000:]
            body = (
                f"$ {command}\n"
                f"cwd: {cwd}\n"
                f"exit: {proc.returncode}\n"
                f"duration: {duration:.2f}s\n"
                f"--- stdout ---\n{out or '(empty)'}\n"
                f"--- stderr ---\n{err or '(empty)'}"
            )
            return ToolResult(
                "",
                "run_command",
                proc.returncode == 0,
                body,
                {"exit_code": proc.returncode, "duration": duration},
            )
        except Cancelled as e:
            return ToolResult("", "run_command", False, str(e))
        except subprocess.TimeoutExpired:
            return ToolResult("", "run_command", False, f"Timed out after {timeout}s: {command}")
        except Exception as e:
            return ToolResult("", "run_command", False, f"Failed: {e}")

    registry.register(
        ToolSpec(
            "run_command",
            "Run a non-interactive shell command in the workspace. Capture stdout/stderr/exit code. Use for tests, builds, git status, etc.",
            {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "cwd": {"type": "string", "description": "Optional subdirectory of workspace"},
                    "timeout_seconds": {"type": "integer"},
                },
                "required": ["command"],
            },
            "ask",
        ),
        run_command,
    )
