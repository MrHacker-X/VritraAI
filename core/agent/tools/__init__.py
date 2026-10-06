"""Build the default agent tool registry."""
from __future__ import annotations

from core.agent.approval import ApprovalManager
from core.agent.tools.analysis_tools import register_analysis_tools
from core.agent.tools.base import ToolRegistry
from core.agent.tools.fs_tools import register_fs_tools
from core.agent.tools.git_tools import register_git_tools
from core.agent.tools.project_tools import register_project_tools
from core.agent.tools.search_tools import register_search_tools
from core.agent.tools.shell_tools import register_shell_tools
from core.agent.tools.todo_tools import register_todo_tools
from core.agent.tools.verify_tools import register_verify_tools
from core.agent.types import AgentState
from core.agent.workspace import WorkspaceManager


def build_registry(
    workspace: WorkspaceManager,
    approval: ApprovalManager,
    state: AgentState,
) -> ToolRegistry:
    registry = ToolRegistry()
    register_fs_tools(
        registry,
        workspace,
        approval,
        state.files_read,
        state.files_changed,
        state,
    )
    register_search_tools(registry, workspace)
    register_shell_tools(registry, workspace, approval, state.commands_run)
    register_git_tools(registry, workspace, approval)
    register_project_tools(registry, workspace)
    register_verify_tools(registry, workspace, approval, state)
    register_analysis_tools(registry, workspace, state)
    register_todo_tools(registry, state)
    return registry
