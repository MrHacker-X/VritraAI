""" /models - Codex-style interactive model picker."""
from __future__ import annotations

from typing import Dict, List, Tuple

from core import runtime
from core.config_store import any_provider_configured, apply_config_to_runtime, provider_status, save_config
from core.display import print_with_rich
from core.providers import iter_providers, last_model_key, provider_label
from core.tui import Choice, arrow_select

CatalogRow = Tuple[str, str, Dict]


def _configured_catalog() -> List[CatalogRow]:
    status = provider_status()
    rows: List[CatalogRow] = []
    for spec in iter_providers():
        if not status.get(spec.id):
            continue
        for mid, info in spec.catalog.items():
            rows.append((spec.id, mid, info))
    return rows


def _find_current_index(rows: List[CatalogRow]) -> int:
    for i, (provider, _mid, info) in enumerate(rows):
        if provider == runtime.API_BASE and info.get("name") == runtime.MODEL:
            return i
    for i, (_provider, _mid, info) in enumerate(rows):
        if info.get("name") == runtime.MODEL:
            return i
    return 0


def _apply_selection(provider: str, mid: str, info: Dict) -> bool:
    model_name = info["name"]
    updates = {
        "api_base": provider,
        "model": model_name,
        "ai_enabled": True,
        last_model_key(provider): model_name,
    }

    if not save_config(updates):
        print_with_rich("Failed to save model selection.", "error")
        return False

    apply_config_to_runtime()
    print()
    print(
        f"  \033[92m✓\033[0m \033[97m{info.get('display_name')}\033[0m"
        f"  ·  \033[36m{provider_label(provider)}\033[0m"
    )
    print()
    return True


def models_command(args=None) -> None:
    """Codex-like /models picker with ↑/↓ selection."""
    apply_config_to_runtime()

    if not any_provider_configured():
        print()
        print_with_rich("No API keys. Run /setup first.", "warning")
        print()
        return

    rows = _configured_catalog()
    if not rows:
        print_with_rich("No models available.", "error")
        return

    print()
    print(
        f"  \033[90mcurrent\033[0m  "
        f"\033[97m{runtime.MODEL or '(none)'}\033[0m  ·  "
        f"\033[36m{provider_label(runtime.API_BASE)}\033[0m"
    )

    choices: List[Choice] = []
    for provider, mid, info in rows:
        name = info.get("display_name", info.get("name", mid))
        choices.append(Choice(f"{provider}|{mid}", name, provider_label(provider)))

    selected = arrow_select(
        "Model",
        choices,
        subtitle="highest capability first · configured providers only",
        initial=_find_current_index(rows),
    )
    if not selected:
        print_with_rich("Cancelled.", "warning")
        return

    provider, mid = selected.split("|", 1)
    info = None
    for p, m, inf in rows:
        if p == provider and m == mid:
            info = inf
            break
    if not info:
        print_with_rich("Selection not found.", "error")
        return
    _apply_selection(provider, mid, info)
