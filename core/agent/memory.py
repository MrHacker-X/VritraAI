"""Cross-turn agent memory persisted under the workspace."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.agent.types import AgentState
from core.agent.workspace import WorkspaceManager

_MEMORY_REL = Path(".vritraai") / "agent_memory.json"
_LEGACY_MEMORY_REL = Path(".vritra") / "agent_memory.json"
_MAX_HISTORY = 5


def memory_path(workspace: WorkspaceManager) -> Path:
    return workspace.root / _MEMORY_REL


def _legacy_memory_path(workspace: WorkspaceManager) -> Path:
    return workspace.root / _LEGACY_MEMORY_REL


def load_memory(workspace: WorkspaceManager) -> Dict[str, Any]:
    path = memory_path(workspace)
    if not path.is_file():
        legacy = _legacy_memory_path(workspace)
        if legacy.is_file():
            try:
                data = json.loads(legacy.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    # Prefer new location going forward
                    try:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                    except Exception:
                        pass
                    return data
            except Exception:
                return {}
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_run_memory(workspace: WorkspaceManager, state: AgentState) -> None:
    """Persist a compact summary of the finished run for the next agent turn."""
    if state.cancelled and not state.files_changed and not state.final_summary:
        return

    prev = load_memory(workspace)
    history: List[Dict[str, Any]] = list(prev.get("history") or [])
    entry = {
        "ts": int(time.time()),
        "objective": (state.objective or "")[:400],
        "summary": (state.final_summary or "")[:1200],
        "completed": bool(state.completed),
        "cancelled": bool(state.cancelled),
        "files_changed": list(state.files_changed)[:40],
        "files_created": list(state.files_created)[:40],
        "files_read": list(state.files_read)[:40],
        "commands_run": list(state.commands_run)[-12:],
        "todos": list(state.todos)[:12],
        "batch_ops": state.batch_ops,
        "errors": list(state.errors)[:6],
    }
    history.append(entry)
    history = history[-_MAX_HISTORY:]

    payload = {
        "version": 1,
        "workspace": str(workspace.root),
        "updated_at": entry["ts"],
        "last": entry,
        "history": history,
    }
    path = memory_path(workspace)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass


def format_memory_block(memory: Optional[Dict[str, Any]]) -> str:
    """Short block for system/bootstrap context."""
    if not memory:
        return ""
    last = memory.get("last") if isinstance(memory.get("last"), dict) else None
    if not last:
        return ""
    lines = ["## Prior agent memory (this workspace)"]
    obj = last.get("objective") or "(none)"
    lines.append(f"Last objective: {obj}")
    if last.get("summary"):
        lines.append(f"Last summary: {str(last['summary'])[:500]}")
    changed = last.get("files_changed") or []
    if changed:
        lines.append("Last files changed: " + ", ".join(changed[:12]))
    created = last.get("files_created") or []
    if created:
        lines.append("Last files created: " + ", ".join(created[:12]))
    read = last.get("files_read") or []
    if read:
        lines.append("Last files read: " + ", ".join(read[:12]))
    todos = last.get("todos") or []
    open_todos = [
        t
        for t in todos
        if isinstance(t, dict)
        and str(t.get("status") or "").lower() in {"pending", "in_progress"}
    ]
    if open_todos:
        bits = [f"{t.get('id')}:{t.get('content')}" for t in open_todos[:6]]
        lines.append("Open todos from last run: " + "; ".join(bits))
    lines.append(
        "Use this as continuity context only - re-verify with tools before editing."
    )
    return "\n".join(lines)


def progress_digest(state: AgentState) -> str:
    """Structured mid-run digest for compaction / context refresh."""
    lines = [
        "## Agent progress digest",
        f"Objective: {state.objective[:300]}",
        f"Iteration: {state.iteration}/{state.max_iterations}",
        f"Files read: {', '.join(state.files_read[-12:]) or 'none'}",
        f"Files changed: {', '.join(state.files_changed[-12:]) or 'none'}",
        f"Created: {', '.join(state.files_created[-12:]) or 'none'}",
        f"Commands: {', '.join(state.commands_run[-8:]) or 'none'}",
        f"Batch ops: {state.batch_ops}; json_repairs: {state.json_repairs}",
    ]
    if state.todos:
        for t in state.todos[:10]:
            lines.append(
                f"  todo[{t.get('status', '?')}] {t.get('id', '?')}: {t.get('content', '')}"
            )
    if state.errors:
        lines.append("Recent errors: " + " | ".join(state.errors[-3:]))
    lines.append("Continue from this state; do not re-discover blindly.")
    return "\n".join(lines)
