"""Lightweight OpenAI-compatible HTTP client (requests only).

Termux and other platforms without Rust wheels cannot install `jiter`, which
modern `openai` SDK releases require. This module duck-types the small surface
VritraAI uses:

    client.chat.completions.create(...)

No native extensions. Pure Python + requests.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Optional, Union

import requests


def _ns(**kwargs: Any) -> SimpleNamespace:
    return SimpleNamespace(**kwargs)


def _coerce_timeout(timeout: Any) -> tuple:
    """Normalize SDK-style timeouts to requests (connect, read)."""
    if timeout is None:
        return (15.0, 180.0)
    if isinstance(timeout, (int, float)):
        return (15.0, float(timeout))
    if isinstance(timeout, (tuple, list)) and len(timeout) >= 2:
        return (float(timeout[0]), float(timeout[1]))
    # httpx.Timeout-like
    read = getattr(timeout, "read", None)
    connect = getattr(timeout, "connect", None)
    if read is not None or connect is not None:
        return (float(connect or 15.0), float(read or 180.0))
    try:
        return (15.0, float(timeout))
    except Exception:
        return (15.0, 180.0)


def _message_from_dict(msg: Dict[str, Any]) -> SimpleNamespace:
    tool_calls_raw = msg.get("tool_calls") or None
    tool_calls = None
    if tool_calls_raw:
        tool_calls = []
        for tc in tool_calls_raw:
            fn = tc.get("function") or {}
            tool_calls.append(
                _ns(
                    id=tc.get("id") or "",
                    type=tc.get("type") or "function",
                    function=_ns(
                        name=fn.get("name") or "",
                        arguments=fn.get("arguments") or "{}",
                    ),
                )
            )
    return _ns(
        role=msg.get("role") or "assistant",
        content=msg.get("content"),
        tool_calls=tool_calls,
    )


def _response_from_dict(data: Dict[str, Any]) -> SimpleNamespace:
    choices = []
    for ch in data.get("choices") or []:
        msg = ch.get("message") or {}
        choices.append(
            _ns(
                index=ch.get("index", 0),
                finish_reason=ch.get("finish_reason"),
                message=_message_from_dict(msg),
            )
        )
    return _ns(
        id=data.get("id"),
        object=data.get("object"),
        model=data.get("model"),
        choices=choices,
        usage=data.get("usage"),
    )


def _delta_from_dict(delta: Dict[str, Any]) -> SimpleNamespace:
    tool_calls_raw = delta.get("tool_calls")
    tool_calls = None
    if tool_calls_raw:
        tool_calls = []
        for tc in tool_calls_raw:
            fn = tc.get("function") or {}
            tool_calls.append(
                _ns(
                    index=tc.get("index", 0),
                    id=tc.get("id"),
                    type=tc.get("type"),
                    function=_ns(
                        name=fn.get("name"),
                        arguments=fn.get("arguments") or "",
                    ),
                )
            )
    return _ns(
        role=delta.get("role"),
        content=delta.get("content"),
        tool_calls=tool_calls,
    )


def _chunk_from_dict(data: Dict[str, Any]) -> SimpleNamespace:
    choices = []
    for ch in data.get("choices") or []:
        delta = ch.get("delta") or {}
        choices.append(
            _ns(
                index=ch.get("index", 0),
                finish_reason=ch.get("finish_reason"),
                delta=_delta_from_dict(delta),
            )
        )
    return _ns(
        id=data.get("id"),
        object=data.get("object"),
        model=data.get("model"),
        choices=choices,
    )


class _Stream:
    """Iterable SSE stream with .close()."""

    def __init__(self, response: requests.Response) -> None:
        self._response = response
        self._closed = False

    def __iter__(self) -> Iterator[SimpleNamespace]:
        try:
            for raw in self._response.iter_lines(decode_unicode=True):
                if self._closed:
                    break
                if not raw:
                    continue
                line = raw.strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    break
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                yield _chunk_from_dict(data)
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._response.close()
        except Exception:
            pass


class Completions:
    def __init__(self, client: "OpenAICompatClient") -> None:
        self._client = client

    def create(self, **kwargs: Any) -> Union[SimpleNamespace, _Stream]:
        stream = bool(kwargs.pop("stream", False))
        timeout = _coerce_timeout(kwargs.pop("timeout", None))

        body: Dict[str, Any] = dict(kwargs)
        body["stream"] = stream

        url = self._client._url("/chat/completions")
        headers = self._client._headers()

        if stream:
            resp = self._client._session.post(
                url,
                headers=headers,
                data=json.dumps(body),
                timeout=timeout,
                stream=True,
            )
            if resp.status_code >= 400:
                # Read body for error detail then raise
                try:
                    detail = resp.text
                except Exception:
                    detail = ""
                err = requests.HTTPError(
                    f"{resp.status_code} Error for url: {url}",
                    response=resp,
                )
                # attach text for classifiers that inspect response
                try:
                    resp._content = detail.encode("utf-8", errors="replace")
                except Exception:
                    pass
                raise err
            return _Stream(resp)

        resp = self._client._session.post(
            url,
            headers=headers,
            data=json.dumps(body),
            timeout=timeout,
        )
        if resp.status_code >= 400:
            raise requests.HTTPError(
                f"{resp.status_code} Error for url: {url}",
                response=resp,
            )
        return _response_from_dict(resp.json())


class Chat:
    def __init__(self, client: "OpenAICompatClient") -> None:
        self.completions = Completions(client)


class OpenAICompatClient:
    """Drop-in replacement for openai.OpenAI used by VritraAI."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 180.0,
        default_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.api_key = api_key or ""
        self.base_url = (base_url or "").rstrip("/")
        self.timeout = float(timeout)
        self.default_headers = dict(default_headers or {})
        self._session = requests.Session()
        self.chat = Chat(self)

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        headers.update(self.default_headers)
        return headers
