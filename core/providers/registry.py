"""Central provider registry - catalogs, URLs, config keys."""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from core.models_catalog import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GROQ_MODEL,
    DEFAULT_MISTRAL_MODEL,
    DEFAULT_NVIDIA_MODEL,
    DEFAULT_OPENROUTER_MODEL,
    GEMINI_MODELS,
    GROQ_MODELS,
    MISTRAL_MODELS,
    NVIDIA_MODELS,
    OPENROUTER_MODELS,
    PROVIDER_LABELS,
)
from core.providers.types import ProviderSpec
from core.runtime import OPENROUTER_DEFAULT_HEADERS, OPENROUTER_TIMEOUT

# Display / iteration order
PROVIDER_ORDER: List[str] = [
    "gemini",
    "openrouter",
    "groq",
    "mistral",
    "nvidia",
]

PROVIDERS: Dict[str, ProviderSpec] = {
    "gemini": ProviderSpec(
        id="gemini",
        label=PROVIDER_LABELS["gemini"],
        config_key="gemini_api_key",
        last_model_key="last_gemini_model",
        client_kind="gemini",
        catalog=GEMINI_MODELS,
        default_model=DEFAULT_GEMINI_MODEL,
        key_url="https://aistudio.google.com/apikey",
    ),
    "openrouter": ProviderSpec(
        id="openrouter",
        label=PROVIDER_LABELS["openrouter"],
        config_key="api_key",
        last_model_key="last_openrouter_model",
        client_kind="openai_compat",
        catalog=OPENROUTER_MODELS,
        default_model=DEFAULT_OPENROUTER_MODEL,
        base_url="https://openrouter.ai/api/v1",
        default_headers=dict(OPENROUTER_DEFAULT_HEADERS),
        key_url="https://openrouter.ai/keys",
        timeout=OPENROUTER_TIMEOUT,
    ),
    "groq": ProviderSpec(
        id="groq",
        label=PROVIDER_LABELS["groq"],
        config_key="groq_api_key",
        last_model_key="last_groq_model",
        client_kind="openai_compat",
        catalog=GROQ_MODELS,
        default_model=DEFAULT_GROQ_MODEL,
        base_url="https://api.groq.com/openai/v1",
        default_headers={},
        key_url="https://console.groq.com/keys",
        timeout=180.0,
    ),
    "mistral": ProviderSpec(
        id="mistral",
        label=PROVIDER_LABELS["mistral"],
        config_key="mistral_api_key",
        last_model_key="last_mistral_model",
        client_kind="openai_compat",
        catalog=MISTRAL_MODELS,
        default_model=DEFAULT_MISTRAL_MODEL,
        base_url="https://api.mistral.ai/v1",
        default_headers={},
        key_url="https://console.mistral.ai/api-keys",
        timeout=180.0,
    ),
    "nvidia": ProviderSpec(
        id="nvidia",
        label=PROVIDER_LABELS["nvidia"],
        config_key="nvidia_api_key",
        last_model_key="last_nvidia_model",
        client_kind="openai_compat",
        catalog=NVIDIA_MODELS,
        default_model=DEFAULT_NVIDIA_MODEL,
        base_url="https://integrate.api.nvidia.com/v1",
        default_headers={},
        key_url="https://build.nvidia.com/",
        timeout=180.0,
    ),
}


def get_provider(provider_id: str) -> Optional[ProviderSpec]:
    return PROVIDERS.get((provider_id or "").strip().lower())


def iter_providers() -> Iterable[ProviderSpec]:
    for pid in PROVIDER_ORDER:
        spec = PROVIDERS.get(pid)
        if spec:
            yield spec


def provider_label(provider_id: str) -> str:
    spec = get_provider(provider_id)
    if spec:
        return spec.label
    return PROVIDER_LABELS.get(provider_id, (provider_id or "").replace("_", " ").title() or "Provider")


def catalog_for(provider_id: str) -> Dict:
    spec = get_provider(provider_id)
    return dict(spec.catalog) if spec else {}


def default_model(provider_id: str) -> str:
    spec = get_provider(provider_id)
    return spec.default_model if spec else ""


def last_model_key(provider_id: str) -> str:
    spec = get_provider(provider_id)
    return spec.last_model_key if spec else f"last_{provider_id}_model"


def openai_compat_providers() -> List[ProviderSpec]:
    return [s for s in iter_providers() if s.is_openai_compat()]
