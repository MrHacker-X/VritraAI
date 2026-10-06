"""Focused analysis helpers - lean LLM (no giant project dump)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from core.agent.lean import lean_complete
from core.agent.tools.base import ToolRegistry
from core.agent.types import AgentState, ToolResult, ToolSpec
from core.agent.workspace import WorkspaceManager
from core.display import clean_ai_response


def register_analysis_tools(
    registry: ToolRegistry,
    workspace: WorkspaceManager,
    state: AgentState,
) -> None:
    def _read(path_s: str, limit: int = 10000) -> tuple[Optional[str], Optional[str], Optional[str]]:
        path, err = workspace.resolve(path_s)
        if err or path is None:
            return None, None, err
        if not path.is_file():
            return None, None, f"Not a file: {path_s}"
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return None, None, str(e)
        rel = workspace.rel(path)
        if rel not in state.files_read:
            state.files_read.append(rel)
        return rel, text[:limit], None

    def analyze_code(args: Dict[str, Any]) -> ToolResult:
        mode = (args.get("mode") or "review").lower()
        path_s = args.get("path") or ""
        rel, content, err = _read(path_s)
        if err or content is None:
            return ToolResult("", "analyze_code", False, err or "read failed")
        prompts = {
            "review": "Review for bugs, edge cases, and maintainability. Bullet findings with severity.",
            "security": "Security review: injection, authz, secrets, unsafe shell, path traversal. Bullet CVEs-style findings.",
            "summarize": "Summarize purpose, public API, and key flows in under 20 lines.",
            "explain": "Explain how this code works for a competent engineer. Be concrete.",
            "optimize": "Suggest concrete high-ROI optimizations with rationale. No drive-by rewrites.",
        }
        instruction = prompts.get(mode, prompts["review"])
        system = (
            "You are a precise code analyst inside VritraAI Agent. "
            "Use only the provided file content. No markdown fences unless showing a tiny patch."
        )
        user = f"Mode: {mode}\nFile: {rel}\n\n{instruction}\n\n----- FILE -----\n{content}"
        result = lean_complete(system, user)
        if not result:
            return ToolResult("", "analyze_code", False, "Analysis model returned empty / AI disabled")
        return ToolResult("", "analyze_code", True, clean_ai_response(result))

    def finish_task(args: Dict[str, Any]) -> ToolResult:
        summary = (args.get("summary") or "").strip()
        status = (args.get("status") or "completed").lower()
        state.completed = True
        state.final_summary = summary or f"Task {status}."
        if status in {"blocked", "failed", "partial"}:
            state.errors.append(state.final_summary)
        return ToolResult("", "finish_task", True, f"Marked task as {status}")

    registry.register(
        ToolSpec(
            "analyze_code",
            "Deep analysis of one file. mode=review|security|summarize|explain|optimize. Prefer after read_file.",
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "mode": {"type": "string"},
                },
                "required": ["path"],
            },
            "safe",
        ),
        analyze_code,
    )
    registry.register(
        ToolSpec(
            "finish_task",
            "End the agent run. Always call this when done/blocked. status=completed|partial|blocked|failed.",
            {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "status": {"type": "string"},
                },
                "required": ["summary"],
            },
            "safe",
        ),
        finish_task,
    )
