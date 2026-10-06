""" /setup - smart missing-only API key onboarding (compact)."""
from __future__ import annotations

from typing import List, Optional

from core import runtime
from core.config_store import (
    any_provider_configured,
    apply_config_to_runtime,
    load_config,
    mask_key,
    provider_status,
    save_config,
)
from core.display import print_with_rich
from core.providers import PROVIDER_ORDER, get_provider, iter_providers, provider_label
from core.tui import Choice, arrow_select, read_secret_masked, sanitize_secret


def _read_secret(label: str) -> Optional[str]:
    print_with_rich(f"Paste {label} API key (* per char). Empty / skip to skip.", "dim")
    try:
        value = sanitize_secret(read_secret_masked("  › "))
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if not value or value.lower() in {"skip", "s", "q", "cancel"}:
        return None
    return value


def _default_model_for(provider: str) -> str:
    spec = get_provider(provider)
    return spec.default_model if spec else ""


def _save_provider_key(provider: str, key: str) -> bool:
    spec = get_provider(provider)
    if not spec:
        return False
    key = sanitize_secret(key)
    if not key:
        return False
    cfg = load_config()
    updates = {spec.config_key: key}

    # Activate this provider if nothing active has a key, or already on this provider
    st_keys = {
        "gemini": cfg.get("gemini_api_key") or "",
        "openrouter": cfg.get("api_key") or "",
        "groq": cfg.get("groq_api_key") or "",
        "mistral": cfg.get("mistral_api_key") or "",
        "nvidia": cfg.get("nvidia_api_key") or "",
    }
    st_keys[provider] = key
    active = runtime.API_BASE
    active_has_key = bool(st_keys.get(active))
    if active == provider or not active_has_key:
        model = cfg.get(spec.last_model_key) or spec.default_model
        updates["api_base"] = provider
        updates["model"] = model
        updates[spec.last_model_key] = model
        updates["ai_enabled"] = True

    ok = save_config(updates)
    apply_config_to_runtime()
    return ok


def _print_status() -> None:
    st = provider_status()
    for spec in iter_providers():
        key = runtime.get_provider_key(spec.id)
        mark = f"\033[92m✓\033[0m {mask_key(key)}" if st.get(spec.id) else "\033[90m○\033[0m"
        print(f"  {spec.label} {mark}")
    print(f"  \033[90mactive {provider_label(runtime.API_BASE)} · {runtime.MODEL or 'no model'}\033[0m")


def _prompt_key(provider: str) -> bool:
    spec = get_provider(provider)
    if not spec:
        return False
    print()
    print(f"\033[1m{spec.label} API key\033[0m")
    if spec.key_url:
        print(f"\033[90m{spec.key_url}\033[0m")
    key = _read_secret(spec.label)
    if not key:
        print_with_rich("Skipped.", "warning")
        return False
    if _save_provider_key(provider, key):
        print_with_rich(f"✓ {spec.label}  {mask_key(key)}", "success")
        return True
    print_with_rich(f"Failed to save {spec.label} key.", "error")
    return False


def _missing_providers() -> List[str]:
    st = provider_status()
    return [pid for pid in PROVIDER_ORDER if not st.get(pid)]


def _configure_missing() -> None:
    """Prompt only unset providers in registry order; skip is OK."""
    for pid in _missing_providers():
        _prompt_key(pid)


def _rebind_active_if_needed() -> None:
    """If active provider lost its key, switch to any remaining configured one."""
    st = provider_status()
    if st.get(runtime.API_BASE):
        return
    for pid in PROVIDER_ORDER:
        if st.get(pid):
            spec = get_provider(pid)
            if not spec:
                continue
            cfg = load_config()
            model = cfg.get(spec.last_model_key) or spec.default_model
            save_config({"api_base": pid, "model": model, "ai_enabled": True})
            apply_config_to_runtime()
            return
    save_config({"ai_enabled": False})
    apply_config_to_runtime()


def _clear_flow() -> None:
    choices = [Choice(pid, provider_label(pid)) for pid in PROVIDER_ORDER]
    choices.append(Choice("all", "All providers"))
    choices.append(Choice("cancel", "Cancel"))
    choice = arrow_select("Clear a key", choices)
    if not choice or choice == "cancel":
        print_with_rich("Cancelled.", "warning")
        return
    updates: dict = {}
    if choice == "all":
        for spec in iter_providers():
            updates[spec.config_key] = ""
        updates["ai_enabled"] = False
    else:
        spec = get_provider(choice)
        if not spec:
            print_with_rich("Unknown provider.", "error")
            return
        updates[spec.config_key] = ""
    if save_config(updates):
        apply_config_to_runtime()
        _rebind_active_if_needed()
        print_with_rich("Cleared.", "success")
    else:
        print_with_rich("Failed to update config.", "error")


def setup_command(args=None) -> None:
    """
    Smart /setup:
    - Missing keys → prompt only those (registry order; skip OK)
    - All set → compact update/clear menu
    """
    apply_config_to_runtime()
    st = provider_status()

    print()
    _print_status()
    print()

    missing = _missing_providers()
    if missing:
        labels = [provider_label(pid) for pid in missing]
        print(f"\033[90mConfiguring missing: {', '.join(labels)}\033[0m")
        _configure_missing()
        print()
        _print_status()
        print()
        if any_provider_configured():
            print_with_rich("You're set. Use /model to choose a model.", "success")
        else:
            print_with_rich("No keys yet. Run /setup anytime.", "warning")
        return

    # All providers already have keys - short management menu
    menu = [Choice(pid, f"Update {provider_label(pid)}") for pid in PROVIDER_ORDER]
    menu.append(Choice("clear", "Clear a key"))
    menu.append(Choice("done", "Done"))
    selected = arrow_select(
        "Setup",
        menu,
        subtitle="all keys already set",
        initial=len(menu) - 1,
    )
    if selected is None or selected == "done":
        return
    if selected == "clear":
        _clear_flow()
    elif selected in PROVIDER_ORDER:
        _prompt_key(selected)

    print()
    _print_status()
    print()
