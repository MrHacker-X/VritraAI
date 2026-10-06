"""Provider specification types."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional


@dataclass(frozen=True)
class ProviderSpec:
    """Static metadata for a chat provider."""

    id: str
    label: str
    config_key: str
    last_model_key: str
    client_kind: str  # gemini | openai_compat
    catalog: Mapping[str, Dict[str, Any]]
    default_model: str
    base_url: Optional[str] = None
    default_headers: Optional[Dict[str, str]] = None
    key_url: str = ""
    timeout: float = 180.0

    def is_openai_compat(self) -> bool:
        return self.client_kind == "openai_compat"
