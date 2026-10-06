"""Provider registry - OpenAI-compat + Gemini specs."""
from __future__ import annotations

from core.providers.registry import (
    PROVIDER_ORDER,
    PROVIDERS,
    catalog_for,
    default_model,
    get_provider,
    iter_providers,
    last_model_key,
    openai_compat_providers,
    provider_label,
)
from core.providers.types import ProviderSpec

__all__ = [
    "PROVIDER_ORDER",
    "PROVIDERS",
    "ProviderSpec",
    "catalog_for",
    "default_model",
    "get_provider",
    "iter_providers",
    "last_model_key",
    "openai_compat_providers",
    "provider_label",
]
