"""In-session todo list for agent planning (Cursor-style)."""
from __future__ import annotations

from typing import Any, Dict, List

from core.agent.tools.base import ToolRegistry
from core.agent.types import AgentState, ToolResult, ToolSpec


def register_todo_tools(registry: ToolRegistry, state: AgentState) -> None:
    def todo_write(args: Dict[str, Any]) -> ToolResult:
        items = args.get("items")
        if not isinstance(items, list) or not items:
            return ToolResult(
                "",
                "todo_write",
                False,
                'items must be a non-empty list of {id,content,status}. '
                'Example: {"items":[{"id":"1","content":"Create site files","status":"in_progress"}]}',
            )
        cleaned: List[Dict[str, str]] = []
        for it in items[:16]:
            if not isinstance(it, dict):
                continue
            content = str(it.get("content") or "").strip()
            if not content:
                continue
            status = str(it.get("status") or "pending").lower()
            if status not in {"pending", "in_progress", "done", "cancelled"}:
                status = "pending"
            tid = str(it.get("id") or len(cleaned) + 1)
            cleaned.append({"id": tid, "content": content, "status": status})
        if not cleaned:
            return ToolResult("", "todo_write", False, "no valid todo items")
        state.todos = cleaned
        lines = [f"{t['status']:11}  {t['id']}. {t['content']}" for t in cleaned]
        return ToolResult("", "todo_write", True, "Todos updated:\n" + "\n".join(lines))

    registry.register(
        ToolSpec(
            "todo_write",
            "Create/update the task checklist for this agent run. statuses: pending|in_progress|done|cancelled.",
            {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "content": {"type": "string"},
                                "status": {"type": "string"},
                            },
                            "required": ["content"],
                        },
                    }
                },
                "required": ["items"],
            },
            "safe",
        ),
        todo_write,
    )
