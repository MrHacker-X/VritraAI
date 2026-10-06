"""Locate old_string in file text with light normalization + helpful miss diagnostics."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class OldMatch:
    """Exact substring as it appears in the file (safe to .replace)."""

    old: str
    count: int
    strategy: str  # exact | lf | crlf | trail_ws


def _to_lf(s: str) -> str:
    return (s or "").replace("\r\n", "\n").replace("\r", "\n")


def locate_old_string(text: str, old: str) -> Tuple[Optional[OldMatch], str]:
    """
    Find old_string in text. Returns (match, error_detail).
    On success error_detail is "".
    """
    if old is None or old == "":
        return None, "old_string is empty"
    if text is None:
        return None, "file is empty"

    if old in text:
        return OldMatch(old=old, count=text.count(old), strategy="exact"), ""

    text_lf = _to_lf(text)
    old_lf = _to_lf(old)

    if old_lf in text:
        return OldMatch(old=old_lf, count=text.count(old_lf), strategy="lf"), ""

    if old_lf in text_lf:
        # File likely uses CRLF - rebuild needle with file's newlines
        if "\r\n" in text:
            old_crlf = old_lf.replace("\n", "\r\n")
            if old_crlf in text:
                return OldMatch(old=old_crlf, count=text.count(old_crlf), strategy="crlf"), ""
        # Matched only in LF view; if text is already LF-equivalent length, use LF needle
        if text_lf == text and old_lf in text:
            return OldMatch(old=old_lf, count=text.count(old_lf), strategy="lf"), ""

    # Trailing whitespace per line (common LLM drift)
    flex = _match_trailing_ws(text, old_lf)
    if flex is not None:
        return flex, ""

    return None, diagnose_miss(text, old)


def _match_trailing_ws(text: str, old_lf: str) -> Optional[OldMatch]:
    lines = old_lf.split("\n")
    if not any(lines):
        return None
    parts = [re.escape(line.rstrip(" \t")) + r"[ \t]*" for line in lines]
    pattern = r"\n".join(parts)
    # Search LF view, then map back if needed
    text_lf = _to_lf(text)
    matches = list(re.finditer(pattern, text_lf))
    if not matches:
        return None
    if len(matches) > 1:
        # Ambiguous under flex - only accept if exact unique after strip normalize fails
        # Prefer unique match only
        return None
    matched_lf = matches[0].group(0)
    if matched_lf in text:
        return OldMatch(old=matched_lf, count=1, strategy="trail_ws")
    if "\r\n" in text:
        matched_crlf = matched_lf.replace("\n", "\r\n")
        if matched_crlf in text:
            return OldMatch(old=matched_crlf, count=1, strategy="trail_ws")
    return None


def diagnose_miss(text: str, old: str) -> str:
    """Human + model-facing reason when old_string cannot be located."""
    old_lf = _to_lf(old).strip("\n")
    preview = old_lf.replace("\n", "\\n")
    if len(preview) > 100:
        preview = preview[:97] + "…"

    lines = _to_lf(text).splitlines()
    hint_lines: list[str] = []
    # Closest single-line match to first needle line
    first = next((ln.strip() for ln in old_lf.splitlines() if ln.strip()), "")
    if first and lines:
        close = difflib.get_close_matches(first, lines, n=2, cutoff=0.45)
        for c in close:
            shown = c if len(c) <= 100 else c[:97] + "…"
            hint_lines.append(f"  near: {shown}")

    # If a distinctive short token from old appears, show surrounding line
    tokens = re.findall(r"[A-Za-z0-9_./#-]{4,}", old_lf)
    for tok in tokens[:4]:
        for i, ln in enumerate(lines):
            if tok in ln:
                shown = ln if len(ln) <= 100 else ln[:97] + "…"
                hint_lines.append(f"  line {i + 1}: {shown}")
                break
        if len(hint_lines) >= 3:
            break

    parts = [
        "old_string not found in file (exact match required).",
        f"looked for: {preview!r}",
        "Re-read with read_file and copy an exact contiguous snippet from the current file.",
        "Or use write_file to overwrite the whole file if the change is large.",
    ]
    if hint_lines:
        parts.append("closest content:")
        parts.extend(hint_lines[:3])
    return "\n".join(parts)
