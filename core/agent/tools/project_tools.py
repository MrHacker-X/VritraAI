"""Project inspection tools - reuse core.commands.project helpers."""
from __future__ import annotations

import json
from typing import Any, Dict

from core.agent.tools.base import ToolRegistry
from core.agent.types import ToolResult, ToolSpec
from core.agent.workspace import WorkspaceManager
from core.commands.project import (
    _analyze_project_structure,
    _find_dependency_files,
    _generate_health_report,
)
from core.context import detect_project_type


def register_project_tools(registry: ToolRegistry, workspace: WorkspaceManager) -> None:
    def inspect_project(args: Dict[str, Any]) -> ToolResult:
        path_s = args.get("path") or "."
        path, err = workspace.resolve(path_s)
        if err or path is None:
            return ToolResult("", "inspect_project", False, err or "bad path")
        if not path.is_dir():
            return ToolResult("", "inspect_project", False, "path must be a directory")
        info = _analyze_project_structure(str(path))
        # Trim large language maps
        payload = {
            "workspace": str(workspace.root),
            "path": workspace.rel(path),
            "detected_type_quick": detect_project_type(),
            "primary_type": info.get("primary_type"),
            "secondary_types": info.get("secondary_types"),
            "confidence": info.get("confidence"),
            "total_files": info.get("total_files"),
            "code_files": info.get("code_files"),
            "key_files": (info.get("key_files") or [])[:25],
            "technologies": info.get("technologies"),
            "frameworks": info.get("frameworks"),
            "languages": info.get("languages"),
        }
        return ToolResult("", "inspect_project", True, json.dumps(payload, indent=2, default=str))

    def list_dependencies(args: Dict[str, Any]) -> ToolResult:
        path_s = args.get("path") or "."
        path, err = workspace.resolve(path_s)
        if err or path is None:
            return ToolResult("", "list_dependencies", False, err or "bad path")
        files = _find_dependency_files(str(path))
        if not files:
            return ToolResult("", "list_dependencies", True, "No dependency files found")
        return ToolResult("", "list_dependencies", True, "\n".join(files))

    def project_health(args: Dict[str, Any]) -> ToolResult:
        path_s = args.get("path") or "."
        path, err = workspace.resolve(path_s)
        if err or path is None:
            return ToolResult("", "project_health", False, err or "bad path")
        report = _generate_health_report(str(path))
        return ToolResult("", "project_health", True, json.dumps(report, indent=2, default=str)[:12000])

    registry.register(
        ToolSpec(
            "inspect_project",
            "Inspect project type, key files, languages, frameworks, and structure.",
            {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
            "safe",
        ),
        inspect_project,
    )
    registry.register(
        ToolSpec(
            "list_dependencies",
            "Find dependency manifest files (package.json, requirements.txt, etc.).",
            {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
            "safe",
        ),
        list_dependencies,
    )
    registry.register(
        ToolSpec(
            "project_health",
            "Generate a structured project health report (docs/tests/structure/deps).",
            {
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
            "safe",
        ),
        project_health,
    )
