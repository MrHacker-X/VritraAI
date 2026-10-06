"""Shared types for the coding-agent loop."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema object
    risk: str = "safe"  # safe | ask | dangerous


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class ToolResult:
    call_id: str
    name: str
    ok: bool
    output: str
    meta: Dict[str, Any] = field(default_factory=dict)

    def as_text(self, *, limit: int = 12000) -> str:
        status = "ok" if self.ok else "error"
        body = self.output if len(self.output) <= limit else self.output[:limit] + "\n…[truncated]"
        return f"[{status}] {self.name}\n{body}"


@dataclass
class AgentMessage:
    role: str  # system | user | assistant | tool
    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    tool_call_id: str = ""
    name: str = ""


@dataclass
class AgentState:
    objective: str
    workspace: str
    iteration: int = 0
    max_iterations: int = 32
    files_read: List[str] = field(default_factory=list)
    files_changed: List[str] = field(default_factory=list)
    files_created: List[str] = field(default_factory=list)
    commands_run: List[str] = field(default_factory=list)
    todos: List[Dict[str, str]] = field(default_factory=list)
    last_tool_signature: str = ""
    repeat_count: int = 0
    empty_final_nudges: int = 0
    finish_todo_nudges: int = 0
    json_arg_nudges: int = 0
    json_repairs: int = 0
    batch_ops: int = 0
    verify_hint_sent: bool = False
    cancelled: bool = False
    completed: bool = False
    final_summary: str = ""
    errors: List[str] = field(default_factory=list)
