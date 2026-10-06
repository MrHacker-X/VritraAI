"""Detect and run project verification commands."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.agent.approval import ApprovalManager
from core.agent.tools.base import ToolRegistry
from core.agent.types import AgentState, ToolResult, ToolSpec
from core.agent.workspace import WorkspaceManager
from core.interrupt import Cancelled, run_cancellable


def detect_verify_commands(root: Path) -> List[Tuple[str, str]]:
    """Return ordered (label, command) candidates for verification."""
    candidates: List[Tuple[str, str]] = []

    pkg = root / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
            scripts = data.get("scripts") or {}
            for key in ("test", "lint", "typecheck", "build"):
                if key in scripts:
                    candidates.append((f"npm run {key}", f"npm run {key}"))
        except Exception:
            pass

    if (root / "pytest.ini").is_file() or (root / "tests").is_dir() or (root / "test").is_dir():
        candidates.append(("pytest", "python3 -m pytest -q"))

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        text = ""
        try:
            text = pyproject.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass
        if "[tool.pytest" in text or "pytest" in text:
            if not any(c[1].startswith("python3 -m pytest") for c in candidates):
                candidates.append(("pytest", "python3 -m pytest -q"))
        # compile check for python packages
        candidates.append(("py_compile core", "python3 -m compileall -q -f core"))

    if any(root.glob("*.py")) and not any("compileall" in c[1] for c in candidates):
        # lightweight: compile top-level / common dirs
        for sub in ("core", "src", "app"):
            if (root / sub).is_dir():
                candidates.append((f"py_compile {sub}", f"python3 -m compileall -q -f {sub}"))
                break

    if (root / "Cargo.toml").is_file():
        candidates.append(("cargo test", "cargo test --quiet"))
        candidates.append(("cargo build", "cargo build --quiet"))

    if (root / "go.mod").is_file():
        candidates.append(("go test", "go test ./..."))

    makefile = root / "Makefile"
    if makefile.is_file():
        try:
            mk = makefile.read_text(encoding="utf-8", errors="replace")
            for target in ("test", "check", "lint"):
                if f"\n{target}:" in mk or mk.startswith(f"{target}:"):
                    candidates.append((f"make {target}", f"make {target}"))
        except Exception:
            pass

    # de-dupe by command
    seen = set()
    out: List[Tuple[str, str]] = []
    for label, cmd in candidates:
        if cmd in seen:
            continue
        seen.add(cmd)
        out.append((label, cmd))
    return out[:6]


def register_verify_tools(
    registry: ToolRegistry,
    workspace: WorkspaceManager,
    approval: ApprovalManager,
    state: AgentState,
) -> None:
    def verify_project(args: Dict[str, Any]) -> ToolResult:
        prefer = (args.get("prefer") or "").strip().lower()
        dry = bool(args.get("list_only"))
        cands = detect_verify_commands(workspace.root)
        if not cands:
            return ToolResult(
                "",
                "verify_project",
                False,
                "No verification command detected (no package.json/pytest/cargo/go/Makefile cues).",
            )

        listing = "\n".join(f"- {label}: `{cmd}`" for label, cmd in cands)
        if dry:
            return ToolResult("", "verify_project", True, "Detected verify commands:\n" + listing)

        chosen: Optional[Tuple[str, str]] = None
        if prefer:
            for label, cmd in cands:
                if prefer in label.lower() or prefer in cmd.lower():
                    chosen = (label, cmd)
                    break
        if chosen is None:
            chosen = cands[0]
        label, cmd = chosen

        if not approval.approve(
            action="verify project",
            risk="ask",
            detail=cmd,
            kind="shell",
        ):
            return ToolResult("", "verify_project", False, f"User denied verify: {cmd}")

        try:
            from core.agent.status import start_status, stop_status

            start_status(f"Verifying · {label}")
            try:
                proc = run_cancellable(cmd, cwd=str(workspace.root), timeout=180)
            finally:
                stop_status(clear=True)
        except Cancelled as e:
            return ToolResult("", "verify_project", False, str(e))
        except Exception as e:
            return ToolResult("", "verify_project", False, str(e))

        if cmd not in state.commands_run:
            state.commands_run.append(cmd)

        out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        if len(out) > 12000:
            out = out[:12000] + "\n…[truncated]"
        ok = proc.returncode == 0
        header = f"Ran: {cmd}\nexit={proc.returncode}\nDetected options:\n{listing}\n\n"
        return ToolResult(
            "",
            "verify_project",
            ok,
            header + (out.strip() or "(no output)"),
            {"exit_code": proc.returncode, "command": cmd},
        )

    registry.register(
        ToolSpec(
            "verify_project",
            "Detect and run the best project test/lint/build check. Set list_only=true to only list. prefer=test|lint|build optional.",
            {
                "type": "object",
                "properties": {
                    "prefer": {"type": "string"},
                    "list_only": {"type": "boolean"},
                },
            },
            "ask",
        ),
        verify_project,
    )
