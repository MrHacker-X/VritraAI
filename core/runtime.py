"""Runtime state shared by core AI modules.

API/model setup UI is intentionally NOT migrated here. Credentials and provider
selection will be injected later via set_provider_state().
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, Dict, Mapping, Optional

from core.openai_compat import OpenAICompatClient

try:
    from rich.console import Console

    RICH_AVAILABLE = True
    console = Console()
except ImportError:  # pragma: no cover
    RICH_AVAILABLE = False
    console = None

CONFIG_DIR = os.path.expanduser("~/.config-vritrasecz/vritraai")
try:
    os.makedirs(CONFIG_DIR, exist_ok=True)
except Exception:
    pass
SESSION_LOG_FILE = os.path.join(CONFIG_DIR, "session.log")
LEARNING_FILE = os.path.join(CONFIG_DIR, "learning.md")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_DEFAULT_HEADERS: Dict[str, str] = {
    "HTTP-Referer": "http://localhost",
    "X-Title": "VritraAI",
}
OPENROUTER_TIMEOUT = 180.0

# Provider state - filled later by setup layer
AI_ENABLED: bool = False
API_BASE: str = "gemini"
MODEL: str = "gemini-3.8-flash"
# Back-compat aliases (openrouter / gemini)
API_KEY: str = ""
GEMINI_API_KEY: str = ""
# All provider keys by provider id
PROVIDER_KEYS: Dict[str, str] = {
    "gemini": "",
    "openrouter": "",
    "groq": "",
    "mistral": "",
    "nvidia": "",
}

# OpenAI-compatible HTTP client (requests-based; no openai/jiter). None until configure.
openai_client: Optional[Any] = None
# Back-compat alias - some call sites historically checked `runtime.openai is None`.
openai = None  # type: ignore

session = SimpleNamespace(
    commands_history=[],
    modified_files=[],
    ai_interactions=0,
    notes=[],
)

config_state = SimpleNamespace(theme="matrix", prompt_style="hacker", paranoid_mode=False)
THEMES = {
    "matrix": {
        "warning": "#ffb86c",
        "error": "#ff5555",
        "info": "#8be9fd",
        "success": "#50fa7b",
    },
}


def get_style():
    """Stub for legacy backup_file prompt_toolkit styling."""
    return None


def set_provider_state(
    *,
    ai_enabled: Optional[bool] = None,
    api_base: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    provider_keys: Optional[Mapping[str, str]] = None,
) -> None:
    """Inject provider credentials from the setup / config layer."""
    global AI_ENABLED, API_BASE, MODEL, API_KEY, GEMINI_API_KEY, PROVIDER_KEYS
    if provider_keys is not None:
        for pid, key in provider_keys.items():
            PROVIDER_KEYS[str(pid)] = str(key or "")
        API_KEY = PROVIDER_KEYS.get("openrouter", "")
        GEMINI_API_KEY = PROVIDER_KEYS.get("gemini", "")
    if ai_enabled is not None:
        AI_ENABLED = ai_enabled
    if api_base is not None:
        API_BASE = api_base
    if model is not None:
        MODEL = model
    if api_key is not None:
        API_KEY = api_key
        PROVIDER_KEYS["openrouter"] = api_key
    if gemini_api_key is not None:
        GEMINI_API_KEY = gemini_api_key
        PROVIDER_KEYS["gemini"] = gemini_api_key


def get_provider_key(provider_id: str) -> str:
    return PROVIDER_KEYS.get(provider_id, "") or ""


def get_openai_client() -> Optional[Any]:
    """Return the configured OpenAI() client, or None if unavailable."""
    return openai_client


def configure_openai_client(
    api_key: str,
    *,
    base_url: str = OPENROUTER_BASE_URL,
    timeout: float = OPENROUTER_TIMEOUT,
    default_headers: Optional[Dict[str, str]] = None,
) -> Optional[Any]:
    """Build / replace the OpenAI-compatible client for an openai_compat provider."""
    global openai_client, openai
    if not api_key:
        openai_client = None
        openai = None
        return None
    # Empty dict is valid (Groq/Mistral/NVIDIA); only OpenRouter passes custom headers.
    headers = dict(default_headers) if default_headers is not None else {}
    openai_client = OpenAICompatClient(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        default_headers=headers or None,
    )
    openai = openai_client
    return openai_client


def clear_openai_client() -> None:
    global openai_client, openai
    openai_client = None
    openai = None
