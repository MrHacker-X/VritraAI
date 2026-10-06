"""High-autonomy iterative coding-agent loop."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple

from core.agent import ui
from core.agent.approval import ApprovalManager
from core.agent.context import (
    build_workspace_snapshot,
    compact_messages,
    load_project_rules,
)
from core.agent.failover import ModelFailover, SOFT_STREAK_LIMIT
from core.agent.status import PHASES_WORKING, start_status, stop_status
from core.agent.llm import chat_with_tools
from core.agent.memory import (
    format_memory_block,
    load_memory,
    progress_digest,
    save_run_memory,
)
from core.agent.json_util import repair_tool_call
from core.agent.prompts import (
    bootstrap_user_message,
    build_system_prompt,
    continue_nudge,
    multi_file_intent,
    verification_hint,
)
from core.agent.provider_util import (
    blocked_finish_hint,
    empty_response_fault,
)
from core.agent.tools import build_registry
from core.agent.tools.base import ToolRegistry
from core.agent.types import AgentMessage, AgentState, ToolCall, ToolResult
from core.agent.workspace import WorkspaceManager
from core.display import print_with_rich
from core.interrupt import Cancelled, check_cancelled, clear_cancel, is_cancelled

# Read-only / no-approval tools safe to run concurrently
_PARALLEL_SAFE = frozenset(
    {
        "read_file",
        "read_files",
        "list_directory",
        "file_info",
        "glob_files",
        "search_text",
        "code_search",
        "git_status",
        "git_diff",
        "git_log",
        "inspect_project",
        "list_dependencies",
        "project_health",
    }
)


class CodingAgent:
    def __init__(
        self,
        *,
        workspace: Optional[str] = None,
        approval_mode: str = "ask",
        max_iterations: int = 32,
    ) -> None:
        self.workspace = WorkspaceManager(workspace or os.getcwd())
        self.approval = ApprovalManager(approval_mode)
        self.max_iterations = max_iterations

    def run(self, objective: str) -> AgentState:
        state = AgentState(
            objective=objective.strip(),
            workspace=str(self.workspace.root),
            max_iterations=self.max_iterations,
        )
        if not state.objective:
            print_with_rich("Empty task.", "warning")
            return state

        if multi_file_intent(state.objective):
            state.max_iterations = max(state.max_iterations, 48)

        snapshot = build_workspace_snapshot(self.workspace)
        memory = load_memory(self.workspace)
        memory_block = format_memory_block(memory)
        project_rules = load_project_rules(self.workspace)
        registry = build_registry(self.workspace, self.approval, state)
        system = build_system_prompt(
            state.workspace,
            state.objective,
            snapshot=snapshot,
            memory_block=memory_block,
            project_rules=project_rules,
        )
        messages: list[AgentMessage] = [
            AgentMessage(
                role="user",
                content=bootstrap_user_message(
                    state.objective,
                    state.workspace,
                    snapshot,
                    memory_block=memory_block,
                ),
            )
        ]

        print()
        ui.event(f"{state.objective}")
        ui.event(f"workspace {state.workspace}", kind="think")
        if memory_block:
            ui.event("prior memory loaded", kind="think")
        if project_rules:
            ui.event("project rules loaded", kind="think")
        clear_cancel()
        failover = ModelFailover()

        try:
            while (
                state.iteration < state.max_iterations
                and not state.completed
                and not state.cancelled
            ):
                check_cancelled()
                state.iteration += 1

                if len(messages) > 18:
                    messages = compact_messages(
                        messages,
                        keep_recent=14,
                        progress_digest=progress_digest(state),
                    )

                if state.max_iterations < 48 and self._todos_suggest_multifile(state):
                    state.max_iterations = 48

                text, calls, fault, streamed_live = chat_with_tools(
                    messages, registry, system=system
                )
                check_cancelled()

                if fault is None and not calls and not (text and str(text).strip()):
                    fault = empty_response_fault()

                if fault is not None:
                    state.errors.append(fault.line())
                    switch = failover.note_failure(fault)
                    ui.provider_fault(
                        fault,
                        streak=switch.streak if switch else 0,
                        soft_limit=SOFT_STREAK_LIMIT,
                    )
                    if switch and switch.ok:
                        ui.model_failover(switch)
                        messages.append(
                            AgentMessage(
                                role="user",
                                content=continue_nudge(
                                    reason=(
                                        f"Provider switched to {switch.to_display} "
                                        f"({switch.to_provider}/{switch.to_model}) after "
                                        f"{fault.title.lower()}. Continue the task with tools."
                                    )
                                ),
                            )
                        )
                        # Don't burn the iteration - retry with the new model.
                        state.iteration = max(0, state.iteration - 1)
                        continue
                    if switch and switch.reason in {"exhausted", "limit"}:
                        ui.model_failover(switch)
                        state.final_summary = blocked_finish_hint(fault)
                        break
                    # Soft failure #1 - retry same model once more (never soft-retry hard)
                    if fault.hard:
                        state.final_summary = blocked_finish_hint(fault)
                        break
                    messages.append(
                        AgentMessage(
                            role="user",
                            content=continue_nudge(
                                reason=(
                                    f"Provider error ({fault.code}): {fault.detail}. "
                                    "Retry with a tool call, or finish_task as blocked."
                                )
                            ),
                        )
                    )
                    continue

                failover.note_success()

                # Avoid double-printing narration already streamed live
                if text and calls and not streamed_live:
                    snippet = text.strip().splitlines()[0][:120]
                    if snippet and not snippet.lstrip().startswith("{"):
                        ui.event(snippet, kind="think")

                if not calls:
                    handled = self._handle_text_only(state, messages, text)
                    if handled == "done":
                        break
                    continue

                messages.append(
                    AgentMessage(role="assistant", content=text or "", tool_calls=calls)
                )

                # Execute tool calls - parallelize independent safe batches
                for batch in self._partition_calls(calls):
                    check_cancelled()
                    if len(batch) > 1 and all(c.name in _PARALLEL_SAFE for c in batch):
                        results = self._execute_parallel(
                            registry, batch, state, messages
                        )
                    else:
                        results = []
                        stop = False
                        for call in batch:
                            item, should_break = self._execute_one(
                                registry, call, state, messages
                            )
                            if item is not None:
                                results.append(item)
                            if should_break:
                                stop = True
                                break
                        if stop:
                            break

                    for call, result in results:
                        if call.name == "write_files" and result.ok and not state.verify_hint_sent:
                            paths = (result.meta or {}).get("paths") or []
                            if paths:
                                state.verify_hint_sent = True
                                messages.append(
                                    AgentMessage(
                                        role="user",
                                        content=continue_nudge(
                                            reason=verification_hint([str(p) for p in paths])
                                        ),
                                    )
                                )
                        if call.name == "finish_task" and result.ok:
                            state.completed = True

                    if state.completed:
                        break

                if state.completed:
                    break

            if not state.completed and state.iteration >= state.max_iterations:
                state.final_summary = (
                    state.final_summary
                    or self._timeout_summary(state)
                )
                state.errors.append("max_iterations reached")

        except (KeyboardInterrupt, Cancelled):
            state.cancelled = True
            state.final_summary = "Cancelled by user (Ctrl+C)."
            ui.event("Cancelled - back to prompt", kind="err")

        # Persist cross-turn memory
        try:
            save_run_memory(self.workspace, state)
        except Exception:
            pass

        summary = state.final_summary or "No summary."
        if state.cancelled and not state.files_changed:
            print()
        else:
            ui.show_summary(
                summary,
                files_changed=state.files_changed,
                commands=state.commands_run,
                files_read=state.files_read,
                todos=state.todos,
            )
        return state

    def _partition_calls(self, calls: List[ToolCall]) -> List[List[ToolCall]]:
        """Group consecutive parallel-safe calls; keep mutating calls alone."""
        batches: List[List[ToolCall]] = []
        buf: List[ToolCall] = []
        for call in calls:
            if call.name in _PARALLEL_SAFE:
                buf.append(call)
            else:
                if buf:
                    batches.append(buf)
                    buf = []
                batches.append([call])
        if buf:
            batches.append(buf)
        return batches

    def _execute_parallel(
        self,
        registry: ToolRegistry,
        batch: List[ToolCall],
        state: AgentState,
        messages: list[AgentMessage],
    ) -> List[Tuple[ToolCall, ToolResult]]:
        ui.event(f"Parallel {len(batch)} reads/searches", kind="think")
        out: List[Tuple[ToolCall, ToolResult]] = []

        def _run(call: ToolCall) -> Tuple[ToolCall, ToolResult]:
            fixed_name, fixed_args = repair_tool_call(
                call.name, call.arguments or {}, known_tools=registry.known_names()
            )
            if fixed_name != call.name or fixed_args != (call.arguments or {}):
                call = ToolCall(id=call.id, name=fixed_name, arguments=fixed_args)
            if (call.arguments or {}).get("arguments_invalid"):
                err_msg = (call.arguments or {}).get("error") or "json_parse_failed"
                hint = (call.arguments or {}).get("hint") or ""
                return call, ToolResult(
                    call.id,
                    call.name,
                    False,
                    f"arguments_invalid: {err_msg}. {hint}",
                )
            return call, registry.execute(call.name, call.arguments or {}, call.id)

        start_status("Working", phases=PHASES_WORKING)
        try:
            with ThreadPoolExecutor(max_workers=min(6, len(batch))) as pool:
                futs = [pool.submit(_run, c) for c in batch]
                by_id = {}
                for fut in as_completed(futs):
                    call, result = fut.result()
                    by_id[call.id] = (call, result)
        finally:
            stop_status(clear=True)

        for call in batch:
            call, result = by_id[call.id]
            tool_limit = 10000
            ui.show_result(call, result)
            messages.append(
                AgentMessage(
                    role="tool",
                    content=result.as_text(limit=tool_limit),
                    tool_call_id=call.id,
                    name=call.name,
                )
            )
            out.append((call, result))
        return out

    def _execute_one(
        self,
        registry: ToolRegistry,
        call: ToolCall,
        state: AgentState,
        messages: list[AgentMessage],
    ) -> Tuple[Optional[Tuple[ToolCall, ToolResult]], bool]:
        """Returns ((call, result)|None, should_break_outer)."""
        check_cancelled()
        # Recover JSON-as-name / invented shell tools before fingerprint + UI.
        fixed_name, fixed_args = repair_tool_call(
            call.name, call.arguments or {}, known_tools=registry.known_names()
        )
        if fixed_name != call.name or fixed_args != (call.arguments or {}):
            call = ToolCall(id=call.id, name=fixed_name, arguments=fixed_args)

        sig = f"{call.name}:{sorted((call.arguments or {}).items())}"
        if sig == state.last_tool_signature:
            state.repeat_count += 1
        else:
            state.last_tool_signature = sig
            state.repeat_count = 0

        if state.repeat_count >= 3:
            ui.event("Identical tool call repeated - forcing progress", kind="err")
            messages.append(
                AgentMessage(
                    role="user",
                    content=continue_nudge(
                        reason=(
                            "You repeated the same tool call 3 times with the same arguments. "
                            "Change strategy, broaden search, or finish_task as blocked."
                        )
                    ),
                )
            )
            state.repeat_count = 0
            return None, True

        if (call.arguments or {}).get("arguments_invalid"):
            state.json_repairs += 1
            hint = (call.arguments or {}).get("hint") or (
                "Resend tool call with valid JSON; "
                "prefer write_file one file at a time or write_files with 1–2 files"
            )
            err_msg = (call.arguments or {}).get("error") or "json_parse_failed"
            result = ToolResult(
                call.id,
                call.name,
                False,
                f"arguments_invalid: {err_msg}. {hint}",
            )
            ui.show_result(call, result)
            messages.append(
                AgentMessage(
                    role="tool",
                    content=result.as_text(limit=2000),
                    tool_call_id=call.id,
                    name=call.name,
                )
            )
            if state.json_arg_nudges < 1:
                state.json_arg_nudges += 1
                messages.append(
                    AgentMessage(
                        role="user",
                        content=continue_nudge(
                            reason=(
                                "Your last tool call had invalid JSON arguments. "
                                "Resend with valid JSON. If a file is large, write a complete "
                                "usable section first, then expand via replace_in_file / write_files."
                            )
                        ),
                    )
                )
            return (call, result), False

        if call.name == "finish_task" and self._open_todos(state):
            if state.finish_todo_nudges < 1:
                status = str((call.arguments or {}).get("status") or "completed").lower()
                if status not in {"blocked", "failed"}:
                    state.finish_todo_nudges += 1
                    open_ids = ", ".join(t["id"] for t in self._open_todos(state))
                    result = ToolResult(
                        call.id,
                        call.name,
                        False,
                        (
                            f"Refusing finish_task: todos still open ({open_ids}). "
                            "Mark them done/cancelled, finish remaining work, then finish_task. "
                            "Use status=blocked if truly stuck."
                        ),
                    )
                    ui.show_result(call, result)
                    messages.append(
                        AgentMessage(
                            role="tool",
                            content=result.as_text(limit=2000),
                            tool_call_id=call.id,
                            name=call.name,
                        )
                    )
                    messages.append(
                        AgentMessage(
                            role="user",
                            content=continue_nudge(
                                reason=(
                                    "finish_task rejected - complete or cancel open todos first, "
                                    "or finish_task with status=blocked."
                                )
                            ),
                        )
                    )
                    return (call, result), False

        # Don't spin here for ask/approve tools - spinner would fight the approval card.
        # Shell/verify spin inside their handlers after approval; model wait spins in llm.py.
        if call.name in {"todo_write", "analyze_code", "finish_task"}:
            start_status(
                {
                    "todo_write": "Planning",
                    "analyze_code": "Analyzing",
                    "finish_task": "Wrapping up",
                }[call.name]
            )
        try:
            result = registry.execute(call.name, call.arguments or {}, call.id)
        finally:
            stop_status(clear=True)
        if is_cancelled():
            raise Cancelled("Operation cancelled by user (Ctrl+C)")

        tool_limit = 2500 if call.name == "write_files" and result.ok else 10000
        ui.show_result(call, result)
        messages.append(
            AgentMessage(
                role="tool",
                content=result.as_text(limit=tool_limit),
                tool_call_id=call.id,
                name=call.name,
            )
        )
        return (call, result), False

    @staticmethod
    def _open_todos(state: AgentState) -> list:
        return [
            t
            for t in state.todos
            if str(t.get("status") or "").lower() in {"pending", "in_progress"}
        ]

    @staticmethod
    def _todos_suggest_multifile(state: AgentState) -> bool:
        createish = 0
        for t in state.todos:
            c = str(t.get("content") or "").lower()
            if any(k in c for k in ("write", "create", "scaffold", ".html", ".css", ".js", "file")):
                createish += 1
        return createish >= 3

    def _handle_text_only(
        self,
        state: AgentState,
        messages: list[AgentMessage],
        text: Optional[str],
    ) -> str:
        """Return 'done' or 'continue'. Prevents childish early exits."""
        if not text or not text.strip():
            messages.append(
                AgentMessage(
                    role="user",
                    content=continue_nudge(
                        reason="Empty response. Call a tool or finish_task."
                    ),
                )
            )
            return "continue"

        stripped = text.strip()
        if stripped.startswith("{") and (
            '"type"' in stripped or '"name"' in stripped or "finish_task" in stripped
        ):
            messages.append(
                AgentMessage(
                    role="user",
                    content=continue_nudge(
                        reason=(
                            "Do not print tool/protocol JSON. Use native tool calls "
                            "(or finish_task). If arguments failed, resend valid JSON."
                        )
                    ),
                )
            )
            state.empty_final_nudges += 1
            return "continue"

        did_work = bool(
            state.files_changed
            or state.commands_run
            or len(state.files_read) >= 2
            or state.batch_ops
        )

        codingish = multi_file_intent(state.objective) or bool(state.files_changed) or bool(state.todos)
        if codingish:
            messages.append(AgentMessage(role="assistant", content=text))
            messages.append(
                AgentMessage(
                    role="user",
                    content=continue_nudge(
                        reason=(
                            "Coding tasks must end with finish_task, not bare text. "
                            "Continue with tools or call finish_task with evidence."
                        )
                    ),
                )
            )
            state.empty_final_nudges += 1
            if state.empty_final_nudges >= 4 and did_work:
                state.final_summary = text.strip()
                state.completed = True
                return "done"
            return "continue"

        if not did_work and state.iteration <= 2:
            messages.append(AgentMessage(role="assistant", content=text))
            messages.append(
                AgentMessage(
                    role="user",
                    content=continue_nudge(
                        reason=(
                            "You answered without inspecting the workspace. "
                            "For coding/project tasks: use tools first. "
                            "For pure Q&A after a quick inspect, call finish_task."
                        )
                    ),
                )
            )
            state.empty_final_nudges += 1
            return "continue"

        if state.empty_final_nudges < 1:
            messages.append(AgentMessage(role="assistant", content=text))
            messages.append(
                AgentMessage(
                    role="user",
                    content=continue_nudge(
                        reason=(
                            "Do not end with bare text. Call finish_task with your final summary "
                            "(status completed|partial|blocked), or continue with tools."
                        )
                    ),
                )
            )
            state.empty_final_nudges += 1
            return "continue"

        state.final_summary = text.strip()
        state.completed = True
        return "done"

    @staticmethod
    def _timeout_summary(state: AgentState) -> str:
        return (
            f"Stopped after {state.max_iterations} steps without finish_task.\n"
            f"Inspected: {', '.join(state.files_read[:8]) or 'none'}\n"
            f"Changed: {', '.join(state.files_changed) or 'none'}\n"
            f"Created: {', '.join(state.files_created) or 'none'}\n"
            f"Batch ops: {state.batch_ops}\n"
            "Re-run with a narrower objective if needed."
        )


def run_agent(
    objective: str,
    *,
    approval_mode: str = "ask",
    max_iterations: int = 32,
) -> AgentState:
    return CodingAgent(approval_mode=approval_mode, max_iterations=max_iterations).run(objective)
