"""AI model catalogs for /model and /setup.

Ordered high → low capability. IDs verified live against OpenRouter and
Gemini APIs (2026-10-05). Dead free slugs and shutdown Gemini 2.0 omitted.
"""
from __future__ import annotations

from typing import Dict

# OpenRouter - strongest paid first, then free (largest → smallest).
OPENROUTER_MODELS = {
    "anthropic/claude-sonnet-4.6": {
        "name": "anthropic/claude-sonnet-4.6",
        "display_name": "Claude Sonnet 4.6",
        "description": "Top-tier agent and coding model",
        "provider": "Anthropic",
        "category": "Flagship",
    },
    "deepseek/deepseek-r1": {
        "name": "deepseek/deepseek-r1",
        "display_name": "DeepSeek R1",
        "description": "Strong reasoning / chain-of-thought",
        "provider": "DeepSeek",
        "category": "Reasoning",
    },
    "deepseek/deepseek-v4.1-flash": {
        "name": "deepseek/deepseek-v4.1-flash",
        "display_name": "DeepSeek V4.1 Flash",
        "description": "Latest DeepSeek flash tier",
        "provider": "DeepSeek",
        "category": "Chat",
    },
    "deepseek/deepseek-v3.2": {
        "name": "deepseek/deepseek-v3.2",
        "display_name": "DeepSeek V3.2",
        "description": "High-quality DeepSeek chat",
        "provider": "DeepSeek",
        "category": "Chat",
    },
    "deepseek/deepseek-chat-v3.1": {
        "name": "deepseek/deepseek-chat-v3.1",
        "display_name": "DeepSeek Chat v3.1",
        "description": "Reliable DeepSeek general chat",
        "provider": "DeepSeek",
        "category": "Chat",
    },
    "meta-llama/llama-4-maverick": {
        "name": "meta-llama/llama-4-maverick",
        "display_name": "LLaMA 4 Maverick",
        "description": "Meta LLaMA 4 flagship",
        "provider": "Meta",
        "category": "Large",
    },
    "meta-llama/llama-4-scout": {
        "name": "meta-llama/llama-4-scout",
        "display_name": "LLaMA 4 Scout",
        "description": "Meta LLaMA 4 balanced",
        "provider": "Meta",
        "category": "Large",
    },
    "qwen/qwen3-coder": {
        "name": "qwen/qwen3-coder",
        "display_name": "Qwen 3 Coder",
        "description": "Specialized coding assistant",
        "provider": "Qwen",
        "category": "Code",
    },
    "meta-llama/llama-3.3-70b-instruct": {
        "name": "meta-llama/llama-3.3-70b-instruct",
        "display_name": "LLaMA 3.3 70B Instruct",
        "description": "Strong 70B instruct model",
        "provider": "Meta",
        "category": "Large",
    },
    "z-ai/glm-4.6": {
        "name": "z-ai/glm-4.6",
        "display_name": "GLM 4.6",
        "description": "Z-AI general model",
        "provider": "Z-AI",
        "category": "Chat",
    },
    "qwen/qwen3-coder-flash": {
        "name": "qwen/qwen3-coder-flash",
        "display_name": "Qwen 3 Coder Flash",
        "description": "Faster Qwen coder variant",
        "provider": "Qwen",
        "category": "Code",
    },
    "mistralai/mistral-small-3.2-24b-instruct": {
        "name": "mistralai/mistral-small-3.2-24b-instruct",
        "display_name": "Mistral Small 3.2 24B",
        "description": "Efficient Mistral instruct",
        "provider": "Mistral AI",
        "category": "Chat",
    },
    "openai/gpt-oss-20b": {
        "name": "openai/gpt-oss-20b",
        "display_name": "GPT OSS 20B",
        "description": "OpenAI open-weight 20B",
        "provider": "OpenAI",
        "category": "Large",
    },
    "google/gemini-2.5-flash-lite": {
        "name": "google/gemini-2.5-flash-lite",
        "display_name": "Gemini 2.5 Flash Lite",
        "description": "Gemini Flash Lite via OpenRouter",
        "provider": "Google",
        "category": "Chat",
    },
    # Free - auto-router first, then known-good free IDs (skip dead slugs).
    "openrouter/free": {
        "name": "openrouter/free",
        "display_name": "OpenRouter Free Auto",
        "description": "Auto-routes to free models - best free default",
        "provider": "OpenRouter",
        "category": "Free",
    },
    "nvidia/nemotron-3-super-120b-a12b:free": {
        "name": "nvidia/nemotron-3-super-120b-a12b:free",
        "display_name": "Nemotron 3 Super 120B",
        "description": "Free large Nemotron with tools",
        "provider": "NVIDIA",
        "category": "Free",
    },
    "nvidia/nemotron-3-ultra-550b-a55b:free": {
        "name": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "display_name": "Nemotron 3 Ultra 550B",
        "description": "Largest free Nemotron (often slow / empty)",
        "provider": "NVIDIA",
        "category": "Free",
    },
    "google/gemma-4-26b-a4b-it:free": {
        "name": "google/gemma-4-26b-a4b-it:free",
        "display_name": "Gemma 4 26B A4B",
        "description": "Free Gemma 4 instruct",
        "provider": "Google",
        "category": "Free",
    },
    "nvidia/nemotron-3.5-lightning:free": {
        "name": "nvidia/nemotron-3.5-lightning:free",
        "display_name": "Nemotron 3.5 Lightning",
        "description": "Fast free Nemotron",
        "provider": "NVIDIA",
        "category": "Free",
    },
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free": {
        "name": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "display_name": "Nemotron 3 Nano Omni",
        "description": "Free reasoning-oriented nano",
        "provider": "NVIDIA",
        "category": "Free",
    },
    "poolside/laguna-s-2.1:free": {
        "name": "poolside/laguna-s-2.1:free",
        "display_name": "Laguna S 2.1",
        "description": "Free Poolside Laguna S",
        "provider": "Poolside",
        "category": "Free",
    },
    "cohere/north-mini-code:free": {
        "name": "cohere/north-mini-code:free",
        "display_name": "North Mini Code",
        "description": "Free Cohere coding model",
        "provider": "Cohere",
        "category": "Free",
    },
    "inclusionai/ling-3.0-flash-sante:free": {
        "name": "inclusionai/ling-3.0-flash-sante:free",
        "display_name": "Ling 3.0 Flash Sante",
        "description": "Free InclusionAI flash",
        "provider": "InclusionAI",
        "category": "Free",
    },
    "poolside/laguna-xs-2.1:free": {
        "name": "poolside/laguna-xs-2.1:free",
        "display_name": "Laguna XS 2.1",
        "description": "Free smaller Laguna",
        "provider": "Poolside",
        "category": "Free",
    },
    "apodex/apodex-1.1-mini:free": {
        "name": "apodex/apodex-1.1-mini:free",
        "display_name": "Apodex 1.1 Mini",
        "description": "Free Apodex mini",
        "provider": "Apodex",
        "category": "Free",
    },
    "liquid/lfm-2.5-2.6b:free": {
        "name": "liquid/lfm-2.5-2.6b:free",
        "display_name": "LFM 2.5 2.6B",
        "description": "Free LiquidAI small model",
        "provider": "LiquidAI",
        "category": "Free",
    },

}


# Gemini - prefer broadly available aliases first (many free keys reject gated 2.5/3.x).
# Order: flash-latest → lite-latest → numbered Flash → Pro / previews last.
GEMINI_MODELS = {
    "gemini-flash-latest": {
        "name": "gemini-flash-latest",
        "display_name": "Gemini Flash Latest",
        "description": "Stable Flash alias (hot-swapped) - best free-key default",
        "provider": "Google",
        "category": "Flagship",
    },
    "gemini-flash-lite-latest": {
        "name": "gemini-flash-lite-latest",
        "display_name": "Gemini Flash Lite Latest",
        "description": "Stable Flash Lite alias",
        "provider": "Google",
        "category": "Lite",
    },
    "gemini-2.0-flash": {
        "name": "gemini-2.0-flash",
        "display_name": "Gemini 2.0 Flash",
        "description": "Widely available Flash",
        "provider": "Google",
        "category": "Chat",
    },
    "gemini-2.0-flash-lite": {
        "name": "gemini-2.0-flash-lite",
        "display_name": "Gemini 2.0 Flash Lite",
        "description": "Previous-gen Flash Lite",
        "provider": "Google",
        "category": "Lite",
    },
    "gemini-2.5-flash": {
        "name": "gemini-2.5-flash",
        "display_name": "Gemini 2.5 Flash",
        "description": "Flash 2.5 (may need allowlisted / paid key)",
        "provider": "Google",
        "category": "Chat",
    },
    "gemini-2.5-flash-lite": {
        "name": "gemini-2.5-flash-lite",
        "display_name": "Gemini 2.5 Flash Lite",
        "description": "Fast low-cost Flash Lite",
        "provider": "Google",
        "category": "Lite",
    },
    "gemini-2.5-pro": {
        "name": "gemini-2.5-pro",
        "display_name": "Gemini 2.5 Pro",
        "description": "Stronger reasoning / coding",
        "provider": "Google",
        "category": "Pro",
    },
    "gemini-3.5-flash": {
        "name": "gemini-3.5-flash",
        "display_name": "Gemini 3.5 Flash",
        "description": "Newer Flash (may need paid / allowlisted key)",
        "provider": "Google",
        "category": "Chat",
    },
    "gemini-3.8-flash": {
        "name": "gemini-3.8-flash",
        "display_name": "Gemini 3.8 Flash",
        "description": "Latest Flash (may need paid / allowlisted key)",
        "provider": "Google",
        "category": "Flagship",
    },
    "gemini-3-flash-preview": {
        "name": "gemini-3-flash-preview",
        "display_name": "Gemini 3 Flash Preview",
        "description": "Gemini 3 Flash preview",
        "provider": "Google",
        "category": "Chat",
    },
    "gemini-3.1-flash-lite": {
        "name": "gemini-3.1-flash-lite",
        "display_name": "Gemini 3.1 Flash Lite",
        "description": "Newer lite (may need allowlisted key)",
        "provider": "Google",
        "category": "Lite",
    },
}

# Remap dead / invented IDs saved in user config → current stable model
DEPRECATED_GEMINI_MODELS: Dict[str, str] = {
    "gemini-3.7-flash": "gemini-flash-latest",
    "gemini-3.6-flash": "gemini-flash-latest",
    "gemini-1.5-flash": "gemini-flash-latest",
    "gemini-1.5-flash-latest": "gemini-flash-latest",
    "gemini-1.5-pro": "gemini-2.5-pro",
    "gemini-pro": "gemini-flash-latest",
    "gemini-2.0-flash-001": "gemini-2.0-flash",
    "gemini-2.0-flash-exp": "gemini-2.0-flash",
    "gemini-2.0-flash-lite-001": "gemini-2.0-flash-lite",
    "gemini-3-pro-preview": "gemini-2.5-pro",
    "gemini-3.5-flash-lite": "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite-preview": "gemini-3.1-flash-lite",
    "gemma-4-31b-it": "gemini-flash-latest",
    "gemma-4-26b-a4b-it": "gemini-flash-latest",
}


def resolve_gemini_model(model: str) -> str:
    """Map deprecated Gemini IDs to a current stable default."""
    name = (model or "").strip()
    if not name:
        return DEFAULT_GEMINI_MODEL
    return DEPRECATED_GEMINI_MODELS.get(name, name)


# Groq - verified from groq-test.py (high → low)
GROQ_MODELS = {
    "openai/gpt-oss-120b": {
        "name": "openai/gpt-oss-120b",
        "display_name": "GPT OSS 120B",
        "description": "Largest Groq open-weight model",
        "provider": "OpenAI",
        "category": "Flagship",
    },
    "qwen/qwen3.8-27b": {
        "name": "qwen/qwen3.8-27b",
        "display_name": "Qwen 3.8 27B",
        "description": "Qwen 3.8 on Groq",
        "provider": "Qwen",
        "category": "Large",
    },
    "openai/gpt-oss-20b": {
        "name": "openai/gpt-oss-20b",
        "display_name": "GPT OSS 20B",
        "description": "Faster Groq open-weight 20B",
        "provider": "OpenAI",
        "category": "Large",
    },
}

# Mistral - verified from test-mistral.py (code first, then size)
MISTRAL_MODELS = {
    "codestral-2508": {
        "name": "codestral-2508",
        "display_name": "Codestral 2508",
        "description": "Mistral coding model",
        "provider": "Mistral AI",
        "category": "Code",
    },
    "ministral-14b-2512": {
        "name": "ministral-14b-2512",
        "display_name": "Ministral 14B",
        "description": "Largest Ministral in catalog",
        "provider": "Mistral AI",
        "category": "Large",
    },
    "ministral-8b-2512": {
        "name": "ministral-8b-2512",
        "display_name": "Ministral 8B",
        "description": "Balanced Ministral",
        "provider": "Mistral AI",
        "category": "Medium",
    },
    "ministral-3b-2512": {
        "name": "ministral-3b-2512",
        "display_name": "Ministral 3B",
        "description": "Smallest Ministral",
        "provider": "Mistral AI",
        "category": "Small",
    },
}

# NVIDIA - verified from test-nvidia.py
NVIDIA_MODELS = {
    "google/diffusiongemma-26b-a4b-it": {
        "name": "google/diffusiongemma-26b-a4b-it",
        "display_name": "DiffusionGemma 26B A4B",
        "description": "NVIDIA Integrate API model",
        "provider": "Google",
        "category": "Chat",
    },
}


# Defaults: Gemini flash-latest (free-key safe); OpenRouter free auto.
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"
DEFAULT_OPENROUTER_MODEL = "openrouter/free"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
DEFAULT_MISTRAL_MODEL = "codestral-2508"
DEFAULT_NVIDIA_MODEL = "google/diffusiongemma-26b-a4b-it"

PROVIDER_LABELS = {
    "gemini": "Gemini",
    "openrouter": "OpenRouter",
    "groq": "Groq",
    "mistral": "Mistral",
    "nvidia": "NVIDIA",
}

# Catalog lookup by provider id (used by registry / failover / /model)
PROVIDER_CATALOGS = {
    "gemini": GEMINI_MODELS,
    "openrouter": OPENROUTER_MODELS,
    "groq": GROQ_MODELS,
    "mistral": MISTRAL_MODELS,
    "nvidia": NVIDIA_MODELS,
}

PROVIDER_DEFAULTS = {
    "gemini": DEFAULT_GEMINI_MODEL,
    "openrouter": DEFAULT_OPENROUTER_MODEL,
    "groq": DEFAULT_GROQ_MODEL,
    "mistral": DEFAULT_MISTRAL_MODEL,
    "nvidia": DEFAULT_NVIDIA_MODEL,
}
