"""Shared provider limits + short, structured error formatting."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional, Union

from core import runtime

# Cap completion size so free OpenRouter balances aren't billed as 128k max_tokens.
OPENROUTER_MAX_TOKENS = 8192
GEMINI_MAX_OUTPUT_TOKENS = 8192
# Free OpenRouter / Groq reject large max_tokens ("can only afford N").
FREE_AGENT_MAX_TOKENS = 4096


def agent_max_tokens() -> int:
    """Completion budget for the agent turn - lower on free/Groq paths."""
    base = (getattr(runtime, "API_BASE", None) or "").strip().lower()
    model = (getattr(runtime, "MODEL", None) or "").strip().lower()
    if base == "groq":
        return FREE_AGENT_MAX_TOKENS
    if base == "openrouter" and (
        model.endswith(":free") or model == "openrouter/free" or "/free" in model
    ):
        return FREE_AGENT_MAX_TOKENS
    if base == "gemini":
        return GEMINI_MAX_OUTPUT_TOKENS
    return OPENROUTER_MAX_TOKENS


def is_free_openrouter_model(name: str) -> bool:
    n = (name or "").strip().lower()
    return n.endswith(":free") or n == "openrouter/free" or n.endswith("/free")


def model_call_timeout_sec() -> int:
    """Hard wall-clock limit for one model turn (stream or blocking).

    SDK/stream read timeouts reset between chunks, so without this waits can
    exceed any nominal timeout. Override with VRITRA_MODEL_TIMEOUT (seconds).
    """
    raw = (os.environ.get("VRITRA_MODEL_TIMEOUT") or "120").strip()
    try:
        return max(30, min(int(raw), 600))
    except ValueError:
        return 120


@dataclass(frozen=True)
class ProviderFault:
    """Clean fault for UI + failover (never carries raw dumps / keys)."""

    code: str  # not_found | rate_limit | credits | bad_request | denied | empty | network | unknown
    title: str
    detail: str
    model: str = ""
    provider: str = ""
    # Hard faults count as a full streak (instant switch after 1); soft need 2.
    hard: bool = False

    def line(self) -> str:
        return f"{self.title} - {self.detail}" if self.detail else self.title


def _redact(raw: str) -> str:
    raw = re.sub(r"key=AIza[0-9A-Za-z_-]+", "key=***", raw)
    raw = re.sub(r"AIza[0-9A-Za-z_-]{10,}", "AIza***", raw)
    raw = re.sub(r"sk-or-[0-9A-Za-z_-]+", "sk-or-***", raw)
    raw = re.sub(r"Bearer\s+[0-9A-Za-z._-]+", "Bearer ***", raw)
    # Drop requests/openai header dumps
    raw = re.split(r"\s*\{'Date':|\s*\{'error':|\s*\{'Content-Type':|\s*\{'Transfer-Encoding':", raw, maxsplit=1)[0]
    raw = re.sub(r"https?://[^\s)]+", "[url]", raw)
    return re.sub(r"\s+", " ", raw).strip()


def _provider_label(explicit: str = "") -> str:
    if explicit:
        return explicit
    try:
        from core.providers import provider_label

        return provider_label(getattr(runtime, "API_BASE", "") or "")
    except Exception:
        return "Gemini" if getattr(runtime, "API_BASE", "") == "gemini" else "Provider"


def _model_label() -> str:
    return (getattr(runtime, "MODEL", None) or "model").strip() or "model"


def as_provider_fault(
    err: Union[str, ProviderFault, None],
    *,
    provider: str = "",
) -> Optional[ProviderFault]:
    """Normalize string/fault errors; never re-lose hard classification."""
    if err is None:
        return None
    if isinstance(err, ProviderFault):
        return err
    return classify_provider_text(str(err), provider=provider)


def classify_provider_text(text: str, *, provider: str = "") -> ProviderFault:
    """Turn any exception/message string into a short ProviderFault."""
    raw = _redact(str(text or "") or "unknown error")
    low = raw.lower()
    model = _model_label()
    prov = _provider_label(provider)

    afford = re.search(r"afford\s+(\d+)", raw, re.I)
    if (
        "more credits" in low
        or "not enough credits" in low
        or "credits exhausted" in low
        or ("max_tokens" in low and ("402" in low or "credit" in low))
        or ("credit" in low and ("exhaust" in low or "afford" in low or "402" in low))
    ):
        detail = "Not enough credits for this request"
        if afford:
            detail += f" (covers ~{afford.group(1)} tokens)"
        detail += ". Prefer a :free model or add credits."
        return ProviderFault(
            code="credits",
            title="Credits exhausted",
            detail=detail,
            model=model,
            provider=prov,
            hard=True,
        )

    if (
        "404" in raw[:120]
        or "not found" in low
        or "not available" in low
        or "unavailable" in low
        or "is not found for api version" in low
        or "model not found" in low
        or "model unavailable" in low
    ):
        return ProviderFault(
            code="not_found",
            title="Model unavailable",
            detail=f"{model} is not available for this API key",
            model=model,
            provider=prov,
            hard=True,
        )

    if "429" in raw[:120] or "too many requests" in low or "resource_exhausted" in low or (
        "rate" in low and "limit" in low
    ) or "throttl" in low:
        return ProviderFault(
            code="rate_limit",
            title="Rate limited",
            detail=f"{model} is throttling - switching provider",
            model=model,
            provider=prov,
            hard=True,
        )

    if (
        "400" in raw[:120]
        or "bad request" in low
        or "invalid argument" in low
        or "invalid request" in low
        or "bad model" in low
        or "rejected the request" in low
    ):
        return ProviderFault(
            code="bad_request",
            title="Invalid request",
            detail=f"{model} rejected the request (bad model id or payload)",
            model=model,
            provider=prov,
            hard=True,
        )

    if "403" in raw[:120] or "permission" in low or "forbidden" in low:
        return ProviderFault(
            code="denied",
            title="Access denied",
            detail=f"No permission for {model} - check API key / billing",
            model=model,
            provider=prov,
            hard=True,
        )

    if "empty response" in low or raw.strip().lower() == "model returned empty response":
        return ProviderFault(
            code="empty",
            title="Empty response",
            detail=f"{model} returned no content",
            model=model,
            provider=prov,
            hard=True,  # soft-retry burns switch budget on free models that stay empty
        )

    if any(k in low for k in ("timeout", "timed out", "connection", "network", "dns")):
        return ProviderFault(
            code="network",
            title="Network error",
            detail="Could not reach the model provider",
            model=model,
            provider=prov,
            hard=False,
        )

    if "500" in raw[:120] or "internal error" in low or "internal server" in low:
        return ProviderFault(
            code="bad_request",
            title=f"{prov} error",
            detail=f"{model} returned a server error - switching model",
            model=model,
            provider=prov,
            hard=True,
        )

    # Last resort: short clipped detail, never a dump
    cut = raw
    if len(cut) > 120:
        cut = cut[:117] + "…"
    return ProviderFault(
        code="unknown",
        title=f"{prov} error",
        detail=cut or "Request failed",
        model=model,
        provider=prov,
        hard=False,
    )


def classify_provider_error(exc: BaseException, *, provider: str = "") -> ProviderFault:
    """Classify an exception; prefer HTTP status when present."""
    resp = getattr(exc, "response", None)
    status = getattr(resp, "status_code", None) if resp is not None else None
    msg = str(exc) or type(exc).__name__

    if resp is not None:
        try:
            body = resp.json()
            err = body.get("error") if isinstance(body, dict) else None
            if isinstance(err, dict) and err.get("message"):
                msg = str(err["message"])
            elif isinstance(err, str):
                msg = err
        except Exception:
            pass
        if status and str(status) not in msg:
            msg = f"{status} {msg}"

    return classify_provider_text(msg, provider=provider)


def format_provider_error(exc: BaseException, *, provider: str = "") -> str:
    """Backward-compatible one-line string for logs / lean_complete."""
    return classify_provider_error(exc, provider=provider).line()


def empty_response_fault() -> ProviderFault:
    return ProviderFault(
        code="empty",
        title="Empty response",
        detail=f"{_model_label()} returned no content",
        model=_model_label(),
        provider=_provider_label(),
        hard=True,
    )


def timeout_fault(elapsed: float, *, limit: Optional[int] = None) -> ProviderFault:
    lim = int(limit or model_call_timeout_sec())
    return ProviderFault(
        code="network",
        title="Model timeout",
        detail=(
            f"No complete reply within {lim}s (waited {int(elapsed)}s). "
            "Try /model or set VRITRA_MODEL_TIMEOUT."
        ),
        model=_model_label(),
        provider=_provider_label(),
        hard=False,
    )


def blocked_finish_hint(fault: ProviderFault) -> str:
    """Final summary when failover is exhausted - steer to free models."""
    free_picks: list[str] = ["openrouter/free", "gemini-flash-latest"]
    try:
        from core.config_store import provider_status

        status = provider_status()
        if status.get("groq") and "a Groq model" not in free_picks:
            free_picks.insert(0, "a Groq model")
    except Exception:
        pass

    picks = ", ".join(free_picks)
    hint = f"Try /model and pick {picks} (paid OpenRouter needs credits)."

    detail = fault.detail.strip() if fault.detail else ""
    if detail:
        detail = detail.rstrip(".")
        return f"Stopped: {fault.title} - {detail}. {hint}"
    return f"Stopped: {fault.title}. {hint}"
