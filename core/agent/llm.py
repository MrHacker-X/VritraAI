"""Provider-agnostic chat-with-tools for the agent loop (with streaming)."""
from __future__ import annotations

import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Dict, List, Optional, Tuple

import requests

from core import runtime
from core.agent.json_util import (
    looks_like_protocol_or_tool_json,
    parse_tool_arguments,
    sanitize_text_to_tool_calls,
)
from core.agent.provider_util import (
    ProviderFault,
    agent_max_tokens,
    as_provider_fault,
    classify_provider_error,
    empty_response_fault,
    format_provider_error,
    model_call_timeout_sec,
    timeout_fault,
)
from core.agent.status import PHASES_MODEL, start_status, stop_status
from core.agent.stream_ui import LiveNarration, streaming_enabled
from core.agent.tools.base import ToolRegistry
from core.agent.types import AgentMessage, ToolCall
from core.interrupt import Cancelled, check_cancelled

# Re-export for callers/tests that import from llm
__all__ = [
    "chat_with_tools",
    "format_provider_error",
    "agent_max_tokens",
]


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _httpx_timeout(limit: Optional[int] = None) -> Any:
    """Per-attempt HTTP timeout for the requests-based OpenAI-compat client."""
    limit = int(limit or model_call_timeout_sec())
    return (15.0, float(limit))


def chat_with_tools(
    messages: List[AgentMessage],
    registry: ToolRegistry,
    *,
    system: str,
) -> Tuple[Optional[str], List[ToolCall], Optional[ProviderFault], bool]:
    """
    Returns (assistant_text, tool_calls, fault, streamed_live).
    fault is a ProviderFault (never a re-classified string).
    streamed_live=True means narration was already printed to the terminal.
    """
    if not runtime.AI_ENABLED:
        return (
            None,
            [],
            ProviderFault(
                code="denied",
                title="AI disabled",
                detail="Run /setup to enable a provider",
                hard=True,
            ),
            False,
        )

    check_cancelled()
    start_status("Calling model", phases=PHASES_MODEL, kind="model")
    try:
        if runtime.API_BASE == "gemini":
            text, calls, err, live = _gemini_tools(messages, registry, system=system)
        else:
            text, calls, err, live = _openai_tools(messages, registry, system=system)
        if err:
            return text, calls, as_provider_fault(err), live
        text2, calls2, err2 = _sanitize_response(text, calls)
        return text2, calls2, as_provider_fault(err2), live
    except KeyboardInterrupt as e:
        raise Cancelled("AI request cancelled by user (Ctrl+C)") from e
    finally:
        stop_status(clear=True)


def _sanitize_response(
    text: Optional[str],
    calls: List[ToolCall],
) -> Tuple[Optional[str], List[ToolCall], Optional[str]]:
    """Never leak protocol/tool JSON as user-facing assistant text."""
    if calls:
        if text and looks_like_protocol_or_tool_json(text):
            return None, calls, None
        return (text.strip() if text else None), calls, None

    if not text:
        return None, [], None

    if looks_like_protocol_or_tool_json(text):
        clean, parsed = sanitize_text_to_tool_calls(text)
        if parsed:
            tool_calls = [
                ToolCall(id=_new_id(), name=p["name"], arguments=p.get("arguments") or {})
                for p in parsed
                if p.get("name")
            ]
            return clean, tool_calls, None
        if clean is not None and clean != text.strip():
            return clean, [], None
        return None, [], None

    return text.strip() or None, [], None


def _parse_args(args_raw: Any, *, tool_name: str = "") -> Dict[str, Any]:
    arguments, err = parse_tool_arguments(args_raw, tool_name=tool_name)
    if err:
        return arguments
    return arguments


def _build_openai_messages(messages: List[AgentMessage], system: str) -> List[Dict[str, Any]]:
    oai_messages: List[Dict[str, Any]] = [{"role": "system", "content": system}]
    for m in messages:
        if m.role == "tool":
            oai_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": m.tool_call_id or _new_id(),
                    "content": m.content,
                }
            )
        elif m.role == "assistant" and m.tool_calls:
            oai_messages.append(
                {
                    "role": "assistant",
                    "content": m.content or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in m.tool_calls
                    ],
                }
            )
        else:
            oai_messages.append({"role": m.role, "content": m.content})
    return oai_messages


def _openai_tools(
    messages: List[AgentMessage],
    registry: ToolRegistry,
    *,
    system: str,
) -> Tuple[Optional[str], List[ToolCall], Optional[ProviderFault], bool]:
    if runtime.get_openai_client() is None:
        return (
            None,
            [],
            ProviderFault(
                code="denied",
                title="Client unavailable",
                detail="OpenAI-compatible client is not configured",
                hard=True,
            ),
            False,
        )
    oai_messages = _build_openai_messages(messages, system)

    if streaming_enabled():
        try:
            return _openai_tools_stream(oai_messages, registry)
        except Cancelled:
            raise
        except Exception:
            # Silent fallback to non-stream - final failure is surfaced by the loop.
            pass

    return _openai_tools_blocking(oai_messages, registry)


def _openai_chat_create(**kwargs: Any) -> Any:
    """OpenAI SDK >=1.x chat.completions.create via configured client."""
    client = runtime.get_openai_client()
    if client is None:
        raise RuntimeError("OpenAI client unavailable")
    return client.chat.completions.create(**kwargs)


def _delta_text(delta: Any) -> Optional[str]:
    """Extract user-visible narration from a stream delta (never dump reasoning)."""
    if delta is None:
        return None
    if isinstance(delta, dict):
        return delta.get("content") or None
    return getattr(delta, "content", None) or None


def _openai_tools_blocking(
    oai_messages: List[Dict[str, Any]],
    registry: ToolRegistry,
) -> Tuple[Optional[str], List[ToolCall], Optional[ProviderFault], bool]:
    limit = model_call_timeout_sec()
    started = time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(
                _openai_chat_create,
                model=runtime.MODEL,
                messages=oai_messages,
                tools=registry.openai_tools(),
                tool_choice="auto",
                temperature=0.15,
                max_tokens=agent_max_tokens(),
                timeout=_httpx_timeout(limit),
            )
            try:
                response = fut.result(timeout=limit)
            except FuturesTimeout:
                return None, [], timeout_fault(time.monotonic() - started, limit=limit), False
        stop_status(clear=True)
        msg = response.choices[0].message
        text = (getattr(msg, "content", None) or "") or ""
        raw_calls = getattr(msg, "tool_calls", None) or []
        calls = _normalize_openai_tool_calls(raw_calls)
        return text.strip() or None, calls, None, False
    except Exception as e:
        return None, [], classify_provider_error(e, provider=""), False


def _openai_tools_stream(
    oai_messages: List[Dict[str, Any]],
    registry: ToolRegistry,
) -> Tuple[Optional[str], List[ToolCall], Optional[ProviderFault], bool]:
    """Stream OpenAI-compatible chat.completions (openai>=1.x)."""
    live = LiveNarration()
    # index -> {id, name, arguments}
    tc_acc: Dict[int, Dict[str, str]] = {}
    limit = model_call_timeout_sec()
    started = time.monotonic()

    try:
        stream = _openai_chat_create(
            model=runtime.MODEL,
            messages=oai_messages,
            tools=registry.openai_tools(),
            tool_choice="auto",
            temperature=0.15,
            max_tokens=agent_max_tokens(),
            stream=True,
            timeout=_httpx_timeout(limit),
        )
        for chunk in stream:
            check_cancelled()
            elapsed = time.monotonic() - started
            if elapsed >= limit:
                try:
                    stream.close()
                except Exception:
                    pass
                live.close()
                return None, [], timeout_fault(elapsed, limit=limit), False
            if not chunk or not getattr(chunk, "choices", None):
                continue
            choice = chunk.choices[0]
            delta = choice.get("delta") if isinstance(choice, dict) else getattr(choice, "delta", None)
            if delta is None:
                continue
            if isinstance(delta, dict):
                content = _delta_text(delta)
                tool_calls = delta.get("tool_calls") or []
            else:
                content = _delta_text(delta)
                tool_calls = getattr(delta, "tool_calls", None) or []

            if content:
                live.feed(content)
            elif tool_calls:
                # Tool-only deltas: clear wait spinner so UI doesn't look frozen
                stop_status(clear=True)

            for tc in tool_calls:
                if isinstance(tc, dict):
                    idx = int(tc.get("index") or 0)
                    cid = tc.get("id")
                    fn = tc.get("function") or {}
                    name = fn.get("name")
                    args_piece = fn.get("arguments") or ""
                else:
                    idx = int(getattr(tc, "index", 0) or 0)
                    cid = getattr(tc, "id", None)
                    fn = getattr(tc, "function", None)
                    name = getattr(fn, "name", None) if fn else None
                    args_piece = getattr(fn, "arguments", "") if fn else ""
                    args_piece = args_piece or ""

                slot = tc_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                if cid:
                    slot["id"] = str(cid)
                if name:
                    slot["name"] = str(name)
                if args_piece:
                    slot["arguments"] += str(args_piece)

        text = live.close()
        calls: List[ToolCall] = []
        for idx in sorted(tc_acc.keys()):
            slot = tc_acc[idx]
            name = slot.get("name") or ""
            if not name:
                continue
            arguments = _parse_args(slot.get("arguments") or "{}", tool_name=name)
            calls.append(
                ToolCall(
                    id=slot.get("id") or _new_id(),
                    name=name,
                    arguments=arguments,
                )
            )
        return text.strip() or None, calls, None, live.printed
    except Cancelled:
        live.close()
        raise
    except KeyboardInterrupt:
        live.close()
        raise


def _normalize_openai_tool_calls(raw_calls: Any) -> List[ToolCall]:
    calls: List[ToolCall] = []
    for tc in raw_calls or []:
        fn = tc.get("function") if isinstance(tc, dict) else getattr(tc, "function", None)
        if isinstance(tc, dict):
            cid = tc.get("id") or _new_id()
            name = (fn or {}).get("name", "")
            args_raw = (fn or {}).get("arguments") or "{}"
        else:
            cid = getattr(tc, "id", None) or _new_id()
            name = getattr(fn, "name", "") if fn else ""
            args_raw = getattr(fn, "arguments", "{}") if fn else "{}"
        arguments = _parse_args(args_raw, tool_name=str(name or ""))
        calls.append(ToolCall(id=cid, name=name, arguments=arguments))
    return calls


def _build_gemini_contents(messages: List[AgentMessage]) -> List[Dict[str, Any]]:
    contents: List[Dict[str, Any]] = []
    tool_parts_buf: List[Dict[str, Any]] = []

    def _flush_tools() -> None:
        nonlocal tool_parts_buf
        if tool_parts_buf:
            contents.append({"role": "user", "parts": tool_parts_buf})
            tool_parts_buf = []

    for m in messages:
        if m.role == "tool":
            tool_parts_buf.append(
                {
                    "functionResponse": {
                        "name": m.name or "tool",
                        "response": {"result": m.content},
                    }
                }
            )
            continue
        _flush_tools()
        if m.role == "user":
            contents.append({"role": "user", "parts": [{"text": m.content}]})
        elif m.role == "assistant":
            parts: List[Dict[str, Any]] = []
            if m.content:
                parts.append({"text": m.content})
            for tc in m.tool_calls:
                parts.append(
                    {
                        "functionCall": {
                            "name": tc.name,
                            "args": tc.arguments or {},
                        }
                    }
                )
            if parts:
                contents.append({"role": "model", "parts": parts})
    _flush_tools()
    return contents


def _gemini_tools(
    messages: List[AgentMessage],
    registry: ToolRegistry,
    *,
    system: str,
) -> Tuple[Optional[str], List[ToolCall], Optional[ProviderFault], bool]:
    contents = _build_gemini_contents(messages)
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": contents,
        "tools": [{"function_declarations": registry.gemini_declarations()}],
        "tool_config": {"function_calling_config": {"mode": "AUTO"}},
        "generationConfig": {
            "temperature": 0.15,
            "maxOutputTokens": agent_max_tokens(),
        },
    }

    if streaming_enabled():
        try:
            return _gemini_tools_stream(payload)
        except Cancelled:
            raise
        except Exception:
            # Silent fallback to non-stream / JSON protocol.
            pass

    return _gemini_tools_blocking(payload, messages, registry, system)


def _gemini_tools_blocking(
    payload: Dict[str, Any],
    messages: List[AgentMessage],
    registry: ToolRegistry,
    system: str,
) -> Tuple[Optional[str], List[ToolCall], Optional[ProviderFault], bool]:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{runtime.MODEL}:generateContent?key={runtime.GEMINI_API_KEY}"
    )
    limit = model_call_timeout_sec()
    started = time.monotonic()
    try:
        response = requests.post(
            url,
            headers={"Content-Type": "application/json", "Connection": "close"},
            data=json.dumps(payload),
            timeout=(15, limit),
        )
        response.raise_for_status()
        data = response.json()
        stop_status(clear=True)
        text, calls = _parse_gemini_parts(
            data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        )
        return text, calls, None, False
    except requests.exceptions.Timeout:
        return None, [], timeout_fault(time.monotonic() - started, limit=limit), False
    except Exception as e:
        # Prefer JSON protocol quietly; only bubble the fault if that also fails.
        text, calls, err = _json_protocol(messages, registry, system=system)
        if err:
            return text, calls, classify_provider_error(e, provider="Gemini"), False
        return text, calls, as_provider_fault(err), False


def _gemini_tools_stream(
    payload: Dict[str, Any],
) -> Tuple[Optional[str], List[ToolCall], Optional[ProviderFault], bool]:
    """Stream via streamGenerateContent (SSE)."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{runtime.MODEL}:streamGenerateContent?alt=sse&key={runtime.GEMINI_API_KEY}"
    )
    live = LiveNarration()
    text_bits: List[str] = []
    calls: List[ToolCall] = []
    seen_fc: set = set()
    limit = model_call_timeout_sec()
    started = time.monotonic()

    try:
        with requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "Connection": "keep-alive",
            },
            data=json.dumps(payload),
            stream=True,
            timeout=(15, limit),
        ) as response:
            response.raise_for_status()
            for raw_line in response.iter_lines(decode_unicode=True):
                check_cancelled()
                elapsed = time.monotonic() - started
                if elapsed >= limit:
                    live.close()
                    return None, [], timeout_fault(elapsed, limit=limit), False
                if not raw_line:
                    continue
                line = raw_line.strip() if isinstance(raw_line, str) else raw_line.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data_s = line[5:].strip()
                if not data_s or data_s == "[DONE]":
                    continue
                try:
                    data = json.loads(data_s)
                except Exception:
                    continue
                parts = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [])
                )
                for part in parts:
                    if "text" in part and part["text"]:
                        piece = part["text"]
                        text_bits.append(piece)
                        live.feed(piece)
                    fc = part.get("functionCall") or part.get("function_call")
                    if fc:
                        name = fc.get("name", "")
                        args = fc.get("args") or fc.get("arguments") or {}
                        key = name + ":" + json.dumps(args, sort_keys=True, default=str)[:200]
                        if key in seen_fc:
                            continue
                        seen_fc.add(key)
                        if isinstance(args, str):
                            args = _parse_args(args)
                        elif not isinstance(args, dict):
                            args = _parse_args(args)
                        else:
                            args = dict(args)
                        calls.append(ToolCall(id=_new_id(), name=name, arguments=args))

        live.close()
        text = "".join(text_bits).strip() or None
        return text, calls, None, live.printed
    except Cancelled:
        live.close()
        raise
    except KeyboardInterrupt:
        live.close()
        raise
    except requests.exceptions.Timeout:
        live.close()
        return None, [], timeout_fault(time.monotonic() - started, limit=limit), False


def _parse_gemini_parts(parts: List[Dict[str, Any]]) -> Tuple[Optional[str], List[ToolCall]]:
    text_bits: List[str] = []
    calls: List[ToolCall] = []
    for part in parts:
        if "text" in part:
            text_bits.append(part["text"])
        fc = part.get("functionCall") or part.get("function_call")
        if fc:
            name = fc.get("name", "")
            args = fc.get("args") or fc.get("arguments") or {}
            if isinstance(args, str):
                args = _parse_args(args)
            elif not isinstance(args, dict):
                args = _parse_args(args)
            else:
                args = dict(args)
            calls.append(ToolCall(id=_new_id(), name=name, arguments=args))
    text = "\n".join(text_bits).strip() or None
    return text, calls


def _json_protocol(
    messages: List[AgentMessage],
    registry: ToolRegistry,
    *,
    system: str,
) -> Tuple[Optional[str], List[ToolCall], Optional[ProviderFault]]:
    """Fallback: ask model to emit a single JSON tool call or final answer."""
    from core.agent.lean import lean_complete

    tool_lines = []
    for spec in registry.list_specs():
        tool_lines.append(f"- {spec.name}: {spec.description}")
    transcript = []
    for m in messages[-12:]:
        if m.role == "tool":
            transcript.append(f"TOOL[{m.name}] => {m.content[:3000]}")
        else:
            transcript.append(f"{m.role.upper()}: {m.content[:3000]}")
    user = f"""Available tools:
{chr(10).join(tool_lines)}

Conversation:
{chr(10).join(transcript)}

Respond with ONLY one JSON object, either:
{{"type":"tool","name":"TOOL_NAME","arguments":{{...}}}}
or
{{"type":"final","content":"your answer to the user"}}
"""
    raw = lean_complete(system + "\nReturn JSON only.", user)
    if not raw:
        return None, [], empty_response_fault()

    clean, parsed = sanitize_text_to_tool_calls(raw)
    if parsed:
        calls = [
            ToolCall(id=_new_id(), name=p["name"], arguments=p.get("arguments") or {})
            for p in parsed
            if p.get("name")
        ]
        return None, calls, None
    if clean:
        return clean, [], None
    return (
        None,
        [],
        ProviderFault(
            code="bad_request",
            title="Invalid request",
            detail="JSON protocol parse failed - model must resend valid tool/final JSON",
            hard=True,
        ),
    )
