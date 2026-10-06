"""Workspace snapshot + conversation compaction for the agent."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

from core.agent.types import AgentMessage
from core.agent.workspace import WorkspaceManager
from core.context import detect_project_type

_SKIP = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", "VritraAI-og"}

_RULE_CANDIDATES = (
    "AGENTS.md",
    "AGENT.md",
    ".vritraai/rules.md",
    ".vritraai/rules",
    # Legacy names (still read if present)
    ".vritra/rules.md",
    ".vritra/rules",
    ".vritrarules",
)


def _discover_entry_scripts(root: Path) -> List[str]:
    """Root-level launch scripts (current process + __main__ files) - no hardcoded names."""
    found: List[str] = []
    seen = set()

    def _add(name: str) -> None:
        if name and name not in seen and (root / name).is_file():
            seen.add(name)
            found.append(name)

    # Prefer whatever is currently running, if it lives in this workspace
    try:
        argv0 = Path(sys.argv[0]).resolve() if sys.argv else None
        if argv0 and argv0.parent == root.resolve() and argv0.suffix == ".py":
            _add(argv0.name)
    except Exception:
        pass

    try:
        for p in sorted(root.glob("*.py")):
            if p.name.startswith("_") or p.name in {"setup.py", "conftest.py"}:
                continue
            try:
                head = p.read_text(encoding="utf-8", errors="ignore")[:5000]
            except Exception:
                continue
            if '__name__' in head and "__main__" in head:
                _add(p.name)
            if len(found) >= 4:
                break
    except Exception:
        pass
    return found


def build_workspace_snapshot(workspace: WorkspaceManager, *, max_entries: int = 60) -> str:
    """Cheap, high-signal project overview - not a full dump."""
    root = workspace.root
    lines = [
        f"cwd: {root}",
        f"project_type_hint: {detect_project_type() or 'unknown'}",
        "top_level:",
    ]
    try:
        entries = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except Exception as e:
        return f"cwd: {root}\n(error listing: {e})"

    shown = 0
    for p in entries:
        if p.name in _SKIP or (p.name.startswith(".") and p.name not in {".env.example", ".gitignore"}):
            continue
        mark = "/" if p.is_dir() else ""
        lines.append(f"  {p.name}{mark}")
        shown += 1
        if shown >= 40:
            lines.append("  …")
            break

    # Key manifests + discovered entry scripts (no hardcoded launcher name)
    keys = [
        "README.md",
        "pyproject.toml",
        "package.json",
        "requirements.txt",
        "Cargo.toml",
        "go.mod",
        "Makefile",
    ] + _discover_entry_scripts(root)
    found = [k for k in keys if (root / k).exists()]
    if found:
        lines.append("key_files: " + ", ".join(found))

    # Shallow tree of core/ or src/ if exists
    for sub in ("core", "src", "app", "lib"):
        d = root / sub
        if d.is_dir():
            lines.append(f"{sub}/:")
            try:
                kids = sorted(d.iterdir(), key=lambda p: p.name.lower())[:20]
                for k in kids:
                    if k.name in _SKIP:
                        continue
                    lines.append(f"  {k.name}{'/' if k.is_dir() else ''}")
            except Exception:
                pass
            break

    return "\n".join(lines)


def load_project_rules(workspace: WorkspaceManager, *, max_chars: int = 6000) -> str:
    """Load user/project agent rules if present (AGENTS.md, .vritraai/rules, …)."""
    root = workspace.root
    for rel in _RULE_CANDIDATES:
        path = root / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            continue
        if not text:
            continue
        if len(text) > max_chars:
            text = text[:max_chars] + "\n…[rules truncated]"
        return f"## Project rules ({rel})\n{text}"
    return ""


def compact_messages(
    messages: List[AgentMessage],
    *,
    keep_recent: int = 14,
    progress_digest: Optional[str] = None,
) -> List[AgentMessage]:
    """Keep first user turn + recent window; compress older tool payloads.

    When progress_digest is provided, inject it after the head so the model
    retains structured state instead of only truncated tool noise.
    """
    if len(messages) <= keep_recent + 1:
        return messages

    head = messages[:1]
    tail = messages[-keep_recent:]
    middle = messages[1:-keep_recent]
    compressed: List[AgentMessage] = []
    for m in middle:
        if m.role == "tool":
            # Keep path/status lines; drop bulky bodies harder
            compressed.append(
                AgentMessage(
                    role="tool",
                    content=_shrink_tool(m.content, 280),
                    tool_call_id=m.tool_call_id,
                    name=m.name,
                )
            )
        elif m.role == "assistant" and m.tool_calls:
            compressed.append(
                AgentMessage(
                    role="assistant",
                    content=_shrink(m.content, 160),
                    tool_calls=m.tool_calls,
                )
            )
        else:
            compressed.append(
                AgentMessage(role=m.role, content=_shrink(m.content, 400))
            )

    out = head + compressed
    if progress_digest and progress_digest.strip():
        out.append(
            AgentMessage(
                role="user",
                content=(
                    "Context was compacted. Use this digest as ground truth for "
                    "what already happened:\n\n" + progress_digest.strip()
                ),
            )
        )
    return out + tail


def _shrink(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…[compacted]"


def _shrink_tool(text: str, limit: int) -> str:
    text = text or ""
    lines = text.splitlines()
    if not lines:
        return _shrink(text, limit)
    # Prefer first status line + any path-looking lines
    keep = [lines[0]]
    for ln in lines[1:]:
        if any(tok in ln for tok in ("OK ", "FAIL ", "path=", "/", ".py", ".js", ".ts", ".html")):
            keep.append(ln)
        if len("\n".join(keep)) >= limit:
            break
    body = "\n".join(keep)
    return _shrink(body, limit)
