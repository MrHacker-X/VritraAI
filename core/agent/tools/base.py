"""Tool protocol + registry."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from core.agent.json_util import coerce_tool_arguments, repair_tool_call
from core.agent.types import ToolResult, ToolSpec


ToolHandler = Callable[[Dict[str, Any]], ToolResult]


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: Dict[str, ToolSpec] = {}
        self._handlers: Dict[str, ToolHandler] = {}

    def register(self, spec: ToolSpec, handler: ToolHandler) -> None:
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._specs.get(name)

    def known_names(self) -> set:
        return set(self._specs.keys())

    def list_specs(self) -> List[ToolSpec]:
        return list(self._specs.values())

    def openai_tools(self) -> List[Dict[str, Any]]:
        out = []
        for spec in self._specs.values():
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": spec.parameters,
                    },
                }
            )
        return out

    def gemini_declarations(self) -> List[Dict[str, Any]]:
        decls = []
        for spec in self._specs.values():
            decls.append(
                {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                }
            )
        return decls

    def execute(self, name: str, arguments: Dict[str, Any], call_id: str) -> ToolResult:
        name, arguments = repair_tool_call(
            name, arguments or {}, known_tools=self.known_names()
        )
        handler = self._handlers.get(name)
        if not handler:
            sample = ", ".join(sorted(self.known_names())[:12])
            return ToolResult(
                call_id=call_id,
                name=name,
                ok=False,
                output=(
                    f"Unknown tool: {name}. "
                    f"Use run_command with {{\"command\": \"…\"}} for shell "
                    f"(e.g. python3 -m py_compile path.py). Known tools include: {sample}…"
                ),
            )
        try:
            coerced = coerce_tool_arguments(name, arguments or {})
            result = handler(coerced)
            result.call_id = call_id
            result.name = name
            return result
        except Exception as e:
            return ToolResult(call_id=call_id, name=name, ok=False, output=f"Tool error: {e}")
