"""Lean single-shot LLM calls (no project-context dump, no tool registry)."""
from __future__ import annotations

import json
from typing import Optional

import requests

from core import runtime
from core.agent.provider_util import (
    agent_max_tokens,
)
from core.interrupt import Cancelled, check_cancelled


def lean_complete(system: str, user: str) -> Optional[str]:
    """Single-shot completion without dumping the whole project into context."""
    if not runtime.AI_ENABLED:
        return None
    check_cancelled()
    try:
        if runtime.API_BASE == "gemini":
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{runtime.MODEL}:generateContent?key={runtime.GEMINI_API_KEY}"
            )
            payload = {
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": agent_max_tokens(),
                },
            }
            response = requests.post(
                url,
                headers={"Content-Type": "application/json", "Connection": "close"},
                data=json.dumps(payload),
                timeout=(15, 180),
            )
            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        client = runtime.get_openai_client()
        if client is None:
            return None
        response = client.chat.completions.create(
            model=runtime.MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=agent_max_tokens(),
            timeout=180.0,
        )
        content = getattr(response.choices[0].message, "content", None) or ""
        return content.strip() or None
    except KeyboardInterrupt as e:
        raise Cancelled("AI request cancelled by user (Ctrl+C)") from e
    except Exception:
        # Quiet - agent loop surfaces ProviderFaults when the whole turn fails.
        return None
