"""AI calling layer (provider credentials from runtime; no setup UI)."""
from __future__ import annotations

import json
import os
from typing import Optional

import requests

from core import runtime
from core.context import build_comprehensive_context
from core.display import print_with_rich, show_ai_thinking, stop_ai_thinking
from core.session_log import log_session


def network_check() -> bool:
    """Check if network/internet connection is available."""
    import socket

    test_servers = [
        ("8.8.8.8", 53),
        ("1.1.1.1", 53),
        ("8.8.4.4", 53),
    ]

    for server, port in test_servers:
        try:
            socket.create_connection((server, port), timeout=2)
            return True
        except OSError:
            continue

    return False


def check_internet_for_ai() -> tuple[bool, str]:
    """Check internet connectivity specifically for AI operations."""
    if not network_check():
        return False, "No internet connection detected. AI features require internet access."

    import socket

    host = (
        "generativelanguage.googleapis.com"
        if runtime.API_BASE == "gemini"
        else "api.groq.com"
        if runtime.API_BASE == "groq"
        else "openrouter.ai"
        if runtime.API_BASE == "openrouter"
        else "api.mistral.ai"
        if runtime.API_BASE == "mistral"
        else "integrate.api.nvidia.com"
        if runtime.API_BASE == "nvidia"
        else "openrouter.ai"
    )
    try:
        socket.create_connection((host, 443), timeout=5)
        label = runtime.API_BASE or "provider"
        return True, f"Internet and AI service ({label}) connectivity confirmed"
    except OSError:
        return False, f"Internet available but AI service ({runtime.API_BASE}) unreachable."


def handle_network_error(operation_name: str) -> bool:
    """Handle network errors with user-friendly messages and options."""
    print_with_rich("\nNETWORK ERROR", "error")
    print_with_rich(f"Operation: {operation_name}", "warning")
    print_with_rich("Internet connection is required but not available", "error")

    print_with_rich("\nTroubleshooting:", "info")
    print_with_rich("  1. Check your internet connection", "default")
    print_with_rich("  2. Retry the operation", "default")
    print_with_rich("  3. Use offline mode (limited functionality)", "default")
    print_with_rich("  4. Cancel operation", "default")

    try:
        choice = input("\nChoose option (1-4): ").strip()

        if choice == "1":
            print_with_rich("\nTesting connectivity...", "info")
            if network_check():
                print_with_rich("Internet connection restored!", "success")
                return True
            print_with_rich("Still no internet connection", "error")
            return False
        if choice == "2":
            print_with_rich("Retrying operation...", "info")
            return True
        if choice == "3":
            print_with_rich("Switching to offline mode", "warning")
            runtime.set_provider_state(ai_enabled=False)
            return False
        print_with_rich("Operation cancelled", "error")
        return False

    except (EOFError, KeyboardInterrupt):
        print_with_rich("\nOperation aborted by user", "error")
        return False
    except Exception as recovery_error:
        print_with_rich(f"\nError in recovery handler: {recovery_error}", "warning")
        return False


def _out_cap(max_tokens: Optional[int]) -> int:
    from core.agent.provider_util import GEMINI_MAX_OUTPUT_TOKENS, OPENROUTER_MAX_TOKENS

    out_cap = max_tokens
    if out_cap is None:
        out_cap = (
            GEMINI_MAX_OUTPUT_TOKENS
            if runtime.API_BASE == "gemini"
            else OPENROUTER_MAX_TOKENS
        )
    # Groq free/on_demand tiers often enforce ~1000 completion tokens.
    hard_cap = 1000 if runtime.API_BASE == "groq" else 4096
    return min(int(out_cap), hard_cap)


def _complete_once(enhanced_prompt: str, out_cap: int) -> str:
    """Single provider call. Raises on failure; returns non-empty text."""
    if runtime.API_BASE == "gemini":
        gemini_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{runtime.MODEL}:generateContent?key={runtime.GEMINI_API_KEY}"
        )
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                "You are VritraAI, an intelligent terminal assistant. "
                                "Provide helpful, accurate responses. Prefer clean Markdown "
                                "with proper fenced code blocks (language tag on its own line). "
                                "Prefer sections/bullets over dense pipe tables. "
                                "Do not wrap the entire answer in an outer markdown fence.\n\n"
                                f"{enhanced_prompt}"
                            )
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": out_cap,
            },
        }
        response = requests.post(
            gemini_url,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Connection": "close",
            },
            data=json.dumps(payload),
            stream=False,
            timeout=(15, 180),
            verify=True,
        )
        response.raise_for_status()
        data = response.json()
        result = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    else:
        client = runtime.get_openai_client()
        if client is None:
            raise RuntimeError("OpenAI client unavailable - run /setup")
        response = client.chat.completions.create(
            model=runtime.MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VritraAI, an intelligent terminal assistant. "
                        "Be concise. When showing code, use proper Markdown fenced "
                        "code blocks with a language tag on their own line "
                        "(```python then newline, then code, then ```). "
                        "Prefer numbered/bulleted sections over dense pipe tables. "
                        "Never wrap the entire answer in an outer markdown fence."
                    ),
                },
                {"role": "user", "content": enhanced_prompt},
            ],
            max_tokens=out_cap,
            temperature=0.3,
            timeout=180.0,
        )
        result = (getattr(response.choices[0].message, "content", None) or "").strip()

    if not result:
        raise RuntimeError("empty_response")
    return result


def get_ai_response(
    prompt: str,
    context: Optional[str] = None,
    *,
    include_project_context: bool = False,
    max_tokens: Optional[int] = None,
) -> Optional[str]:
    """Gets a response from the AI with optional context.

    On provider failures, uses the same ModelFailover rotation as the agent
    (same catalog order as /model).
    """
    from core.agent.failover import ModelFailover, SOFT_STREAK_LIMIT
    from core.agent.provider_util import (
        classify_provider_error,
        empty_response_fault,
    )
    from core.agent import ui as agent_ui
    from core.display import status_line
    from core.interrupt import Cancelled

    if not runtime.AI_ENABLED:
        print_with_rich("AI disabled - run /setup", "warning")
        return None

    thinking_active = show_ai_thinking()
    failover = ModelFailover()

    try:
        max_network_retries = 2
        network_attempts = 0
        while network_attempts <= max_network_retries:
            is_connected, connection_message = check_internet_for_ai()
            if is_connected:
                break
            if network_attempts >= max_network_retries:
                stop_ai_thinking(thinking_active)
                print_with_rich(connection_message, "error")
                should_retry = handle_network_error("AI Response Generation")
                if not should_retry:
                    return None
                thinking_active = show_ai_thinking()
                network_attempts = 0
            else:
                network_attempts += 1
                continue

        if include_project_context:
            comprehensive_context = build_comprehensive_context(
                cwd=os.getcwd(), include_files=True
            )
            if context:
                full_context = f"{comprehensive_context}\n\n=== USER CONTEXT ===\n{context}"
            else:
                full_context = comprehensive_context
            enhanced_prompt = f"{full_context}\n\n=== USER REQUEST ===\n{prompt}"
        else:
            enhanced_prompt = f"{context}\n\n{prompt}" if context else prompt

        if hasattr(runtime.session, "ai_interactions"):
            runtime.session.ai_interactions += 1

        while True:
            try:
                out_cap = _out_cap(max_tokens)
                result = _complete_once(enhanced_prompt, out_cap)
                stop_ai_thinking(thinking_active)
                failover.note_success()
                return result
            except KeyboardInterrupt:
                stop_ai_thinking(thinking_active)
                raise Cancelled("AI request cancelled by user (Ctrl+C)")
            except requests.exceptions.Timeout as e:
                fault = classify_provider_error(e)
            except RuntimeError as e:
                if str(e) == "empty_response":
                    fault = empty_response_fault()
                elif "OpenAI client unavailable" in str(e):
                    stop_ai_thinking(thinking_active)
                    print_with_rich(str(e), "error")
                    return None
                else:
                    fault = classify_provider_error(e)
            except Exception as e:
                fault = classify_provider_error(e)

            # Pause spinner so fault / switch lines are readable
            stop_ai_thinking(thinking_active)
            switch = failover.note_failure(fault)
            agent_ui.provider_fault(
                fault,
                streak=switch.streak if switch else 0,
                soft_limit=SOFT_STREAK_LIMIT,
            )
            log_session(f"AI Error: {fault.line()}")

            if switch and switch.ok:
                agent_ui.model_failover(switch)
                thinking_active = show_ai_thinking()
                continue

            if switch and switch.reason in {"exhausted", "limit"}:
                agent_ui.model_failover(switch)
                return None

            # Soft failure #1 - retry same model once more
            if switch and switch.reason == "none":
                thinking_active = show_ai_thinking()
                continue

            status_line("request failed - try /model or /setup")
            return None

    except Cancelled:
        stop_ai_thinking(thinking_active)
        raise
    except Exception as e:
        stop_ai_thinking(thinking_active)
        fault = classify_provider_error(e)
        print_with_rich(fault.line(), "error")
        log_session(f"AI Error: {e}")
        return None
