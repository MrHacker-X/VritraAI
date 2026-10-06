"""Lightweight persistent config for provider keys / model selection."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from core import runtime
from core.models_catalog import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GROQ_MODEL,
    DEFAULT_MISTRAL_MODEL,
    DEFAULT_NVIDIA_MODEL,
    DEFAULT_OPENROUTER_MODEL,
    resolve_gemini_model,
)
from core.providers import (
    PROVIDER_ORDER,
    get_provider,
)

DEFAULTS: Dict[str, Any] = {
    "api_key": "",
    "gemini_api_key": "",
    "groq_api_key": "",
    "mistral_api_key": "",
    "nvidia_api_key": "",
    "api_base": "gemini",
    "model": DEFAULT_GEMINI_MODEL,
    "ai_enabled": False,
    "last_gemini_model": DEFAULT_GEMINI_MODEL,
    "last_openrouter_model": DEFAULT_OPENROUTER_MODEL,
    "last_groq_model": DEFAULT_GROQ_MODEL,
    "last_mistral_model": DEFAULT_MISTRAL_MODEL,
    "last_nvidia_model": DEFAULT_NVIDIA_MODEL,
}


def config_path() -> Path:
    return Path(runtime.CONFIG_DIR) / "config.json"


def load_config() -> Dict[str, Any]:
    path = config_path()
    data = dict(DEFAULTS)
    if not path.exists():
        return data
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            data.update(raw)
    except Exception:
        pass
    return data


def save_config(updates: Dict[str, Any]) -> bool:
    """Merge updates into config.json atomically."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_config()
    data.update(updates)
    try:
        fd, tmp = tempfile.mkstemp(prefix="vritra-config-", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        return True
    except Exception:
        return False


def _keys_from_cfg(cfg: Dict[str, Any]) -> Dict[str, str]:
    from core.tui import sanitize_secret

    return {
        "gemini": sanitize_secret(str(cfg.get("gemini_api_key") or "")),
        "openrouter": sanitize_secret(str(cfg.get("api_key") or "")),
        "groq": sanitize_secret(str(cfg.get("groq_api_key") or "")),
        "mistral": sanitize_secret(str(cfg.get("mistral_api_key") or "")),
        "nvidia": sanitize_secret(str(cfg.get("nvidia_api_key") or "")),
    }


def _first_configured(keys: Dict[str, str], prefer: str = "") -> Optional[str]:
    if prefer and keys.get(prefer):
        return prefer
    for pid in PROVIDER_ORDER:
        if keys.get(pid):
            return pid
    return None


def apply_config_to_runtime(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Load config into runtime + configure active OpenAI-compat client if needed."""
    cfg = cfg or load_config()
    keys = _keys_from_cfg(cfg)
    api_base = (cfg.get("api_base") or "gemini").strip().lower()
    model = cfg.get("model") or DEFAULTS["model"]

    # If preferred provider has no key, fall over to any configured one
    if not keys.get(api_base):
        fallback = _first_configured(keys)
        if fallback:
            api_base = fallback
            spec = get_provider(api_base)
            if spec:
                model = cfg.get(spec.last_model_key) or spec.default_model or model

    spec = get_provider(api_base)
    if spec is None:
        api_base = "gemini"
        spec = get_provider("gemini")

    assert spec is not None
    if api_base == "gemini":
        model = resolve_gemini_model(str(model))
    elif not model:
        model = cfg.get(spec.last_model_key) or spec.default_model

    active_key = keys.get(api_base) or ""
    ai_enabled = bool(active_key)

    runtime.set_provider_state(
        ai_enabled=ai_enabled,
        api_base=api_base,
        model=str(model),
        provider_keys=keys,
    )

    try:
        if spec.is_openai_compat() and active_key:
            runtime.configure_openai_client(
                active_key,
                base_url=spec.base_url or runtime.OPENROUTER_BASE_URL,
                timeout=spec.timeout,
                default_headers=spec.default_headers,
            )
        else:
            runtime.clear_openai_client()
    except Exception:
        runtime.clear_openai_client()

    return cfg


def mask_key(key: str) -> str:
    """Short mask - never widen the UI (AIza…N9gc)."""
    if not key:
        return ""
    if len(key) <= 10:
        return "*" * len(key)
    return f"{key[:4]}…{key[-4:]}"


def provider_status() -> Dict[str, bool]:
    return {pid: bool(runtime.get_provider_key(pid)) for pid in PROVIDER_ORDER}


def any_provider_configured() -> bool:
    return any(provider_status().values())
