"""Auto-switch model after consecutive provider failures."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from core import runtime
from core.agent.provider_util import ProviderFault, is_free_openrouter_model
from core.config_store import apply_config_to_runtime, provider_status, save_config
from core.providers import get_provider, iter_providers, last_model_key

# Soft faults need this many consecutive hits; hard faults switch on first.
SOFT_STREAK_LIMIT = 2
MAX_SWITCHES_PER_RUN = 6
# After this many not_found on one provider, burn the whole provider (stops Gemini thrash).
NOT_FOUND_BURN_AFTER = 2

CatalogRow = Tuple[str, str, Dict]  # provider, mid, info

# Credits / denied → burn that provider. Rate-limit on Gemini too.
# OpenRouter rate-limit only burns the one model (other :free may still work).
_BURN_PROVIDER_CODES = frozenset({"credits", "denied"})

# Prefer these providers when jumping away (free-tier friendly).
_PROVIDER_JUMP_ORDER = ("groq", "openrouter", "gemini", "mistral", "nvidia")


@dataclass
class SwitchResult:
    ok: bool
    from_provider: str = ""
    from_model: str = ""
    from_display: str = ""
    to_provider: str = ""
    to_model: str = ""
    to_display: str = ""
    reason: str = ""  # switched | exhausted | limit | none
    streak: int = 0


def _display_for(provider: str, model: str) -> str:
    spec = get_provider(provider)
    catalog = spec.catalog if spec else {}
    for info in catalog.values():
        if info.get("name") == model:
            return str(info.get("display_name") or model)
    return model


def configured_catalog() -> List[CatalogRow]:
    """Same order as /model picker - only providers with keys."""
    status = provider_status()
    rows: List[CatalogRow] = []
    for spec in iter_providers():
        if not status.get(spec.id):
            continue
        for mid, info in spec.catalog.items():
            rows.append((spec.id, mid, info))
    return rows


def _key(provider: str, model: str) -> str:
    return f"{provider}::{model}"


def _provider_rank(provider: str) -> int:
    try:
        return _PROVIDER_JUMP_ORDER.index(provider)
    except ValueError:
        return len(_PROVIDER_JUMP_ORDER)


class ModelFailover:
    """Track consecutive failures; auto-select next catalog model."""

    def __init__(self) -> None:
        self.streak = 0
        self.streak_key = ""
        self.failed: set[str] = set()
        self.failed_providers: set[str] = set()
        self.switches = 0
        self.free_only_openrouter = False
        self.provider_not_found: Dict[str, int] = {}

    def note_success(self) -> None:
        self.streak = 0
        self.streak_key = ""

    def note_failure(self, fault: ProviderFault) -> Optional[SwitchResult]:
        provider = runtime.API_BASE or "gemini"
        model = runtime.MODEL or ""
        key = _key(provider, model)

        if key != self.streak_key:
            self.streak = 0
            self.streak_key = key

        # Soft: need 2 consecutive. Hard (404 / bad model / credits / rate limit): switch now.
        self.streak = SOFT_STREAK_LIMIT if fault.hard else self.streak + 1
        self.failed.add(key)

        # Credits / denied → burn whole provider. Gemini rate-limit → burn Gemini
        # (one key is shared). OpenRouter rate-limit → only this model (other :free OK).
        if fault.code in _BURN_PROVIDER_CODES:
            self._burn_provider(provider)
        elif fault.code == "rate_limit" and provider != "openrouter":
            self._burn_provider(provider)

        # Credits → never climb into paid OpenRouter for the rest of this run
        if fault.code == "credits":
            self.free_only_openrouter = True
            self._burn_paid_openrouter()
        if fault.code == "rate_limit" and provider == "openrouter":
            self.free_only_openrouter = True
            self._burn_paid_openrouter()

        # not_found thrash: after N misses on one provider, burn it
        if fault.code == "not_found":
            self.provider_not_found[provider] = self.provider_not_found.get(provider, 0) + 1
            if self.provider_not_found[provider] >= NOT_FOUND_BURN_AFTER:
                self._burn_provider(provider)

        # Ministral / small Mistral often reject tool schemas - skip rest of family
        if fault.code == "bad_request" and provider == "mistral":
            low = (model or "").lower()
            if low.startswith("ministral"):
                self._burn_mistral_non_codestral()

        streak_now = self.streak
        from_display = _display_for(provider, model)

        if self.streak < SOFT_STREAK_LIMIT:
            return SwitchResult(
                ok=False,
                from_provider=provider,
                from_model=model,
                from_display=from_display,
                reason="none",
                streak=streak_now,
            )

        if self.switches >= MAX_SWITCHES_PER_RUN:
            return SwitchResult(
                ok=False,
                from_provider=provider,
                from_model=model,
                from_display=from_display,
                reason="limit",
                streak=streak_now,
            )

        # Stay on OpenRouter free pool after a free-model rate limit / empty -
        # jumping to Groq burns the last switch on another 429.
        prefer_other = fault.code in {"credits", "denied", "bad_request", "not_found"}
        if fault.code == "rate_limit" and provider != "openrouter":
            prefer_other = True
        if fault.code == "rate_limit" and provider == "openrouter":
            prefer_other = False

        free_or_only = self.free_only_openrouter or fault.code in {
            "credits",
            "rate_limit",
            "empty",
        }
        nxt = self._pick_next(
            provider,
            model,
            prefer_other_provider=prefer_other,
            free_openrouter_only=free_or_only,
        )
        if not nxt:
            return SwitchResult(
                ok=False,
                from_provider=provider,
                from_model=model,
                from_display=from_display,
                reason="exhausted",
                streak=streak_now,
            )

        to_provider, _mid, info = nxt
        to_model = str(info["name"])
        to_display = str(info.get("display_name") or to_model)

        if not self._apply(to_provider, to_model):
            return SwitchResult(
                ok=False,
                from_provider=provider,
                from_model=model,
                from_display=from_display,
                reason="exhausted",
                streak=streak_now,
            )

        self.switches += 1
        self.streak = 0
        self.streak_key = ""
        return SwitchResult(
            ok=True,
            from_provider=provider,
            from_model=model,
            from_display=from_display,
            to_provider=to_provider,
            to_model=to_model,
            to_display=to_display,
            reason="switched",
            streak=streak_now,
        )

    def _burn_provider(self, provider: str) -> None:
        self.failed_providers.add(provider)
        for p, _mid, info in configured_catalog():
            if p != provider:
                continue
            name = str(info.get("name") or "")
            if name:
                self.failed.add(_key(p, name))

    def _burn_paid_openrouter(self) -> None:
        """Mark paid OpenRouter models failed so failover only lands on :free."""
        self.free_only_openrouter = True
        for p, _mid, info in configured_catalog():
            if p != "openrouter":
                continue
            name = str(info.get("name") or "")
            if name and not is_free_openrouter_model(name):
                self.failed.add(_key(p, name))

    def _burn_mistral_non_codestral(self) -> None:
        """Ministral rejects many tool payloads - keep Codestral only if present."""
        for p, _mid, info in configured_catalog():
            if p != "mistral":
                continue
            name = str(info.get("name") or "")
            if name and not name.startswith("codestral"):
                self.failed.add(_key(p, name))

    def _eligible(self, provider: str, name: str, *, free_openrouter_only: bool) -> bool:
        if not name:
            return False
        if _key(provider, name) in self.failed:
            return False
        if provider in self.failed_providers:
            return False
        if free_openrouter_only and provider == "openrouter" and not is_free_openrouter_model(
            name
        ):
            return False
        return True

    def _pick_next(
        self,
        provider: str,
        model: str,
        *,
        prefer_other_provider: bool = False,
        free_openrouter_only: bool = False,
    ) -> Optional[CatalogRow]:
        rows = configured_catalog()
        if not rows:
            return None

        # Always: other providers first, then same - stops climbing paid after Gemini fail.
        same = [
            r
            for r in rows
            if r[0] == provider and r[0] not in self.failed_providers
        ]
        other = [
            r
            for r in rows
            if r[0] != provider and r[0] not in self.failed_providers
        ]

        # Prefer Groq (and other free-friendly) before paid OpenRouter.
        # Within free OpenRouter, openrouter/free auto-router first.
        def _row_rank(r: CatalogRow) -> Tuple:
            p, _mid, info = r
            name = str(info.get("name") or "")
            free = is_free_openrouter_model(name)
            auto = 0 if name.lower() == "openrouter/free" else 1
            return (_provider_rank(p), 0 if free else 1, auto if p == "openrouter" else 0)

        other.sort(key=_row_rank)
        if free_openrouter_only or provider == "openrouter":
            same.sort(key=_row_rank)

        # Other providers first (stops Gemini thrash); same-provider only after.
        # When staying on OpenRouter free, scan ALL remaining same-provider free
        # models first - catalog order must not skip openrouter/free sitting above us.
        if prefer_other_provider:
            ordered = other + same
            start = 0
            for i, (p, _m, info) in enumerate(ordered):
                if p == provider and info.get("name") == model:
                    start = i + 1
                    break
            candidates = ordered[start:] + ordered[:start]
        else:
            candidates = same + other

        for r in candidates:
            p, _mid, info = r
            name = str(info.get("name") or "")
            if not self._eligible(p, name, free_openrouter_only=free_openrouter_only):
                continue
            if p == provider and name == model:
                continue
            return r
        return None

    @staticmethod
    def _apply(provider: str, model: str) -> bool:
        updates = {
            "api_base": provider,
            "model": model,
            "ai_enabled": True,
            last_model_key(provider): model,
        }
        if not save_config(updates):
            runtime.set_provider_state(api_base=provider, model=model, ai_enabled=True)
            return True
        apply_config_to_runtime()
        return True
