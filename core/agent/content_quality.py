"""Reject comment-only / placeholder stub writes before approval."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


_PLACEHOLDER_RE = re.compile(
    r"(?i)\b(todo|tbd|fixme|placeholder|coming soon|lorem ipsum|"
    r"add content here|insert .+ here|your content here)\b"
)


def _strip_comments(path: str, text: str) -> str:
    ext = Path(path).suffix.lower()
    out = text or ""
    if ext in {".html", ".htm", ".svg"}:
        out = re.sub(r"<!--.*?-->", "", out, flags=re.S)
    if ext in {".css", ".scss", ".less"}:
        out = re.sub(r"/\*.*?\*/", "", out, flags=re.S)
    if ext in {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}:
        out = re.sub(r"/\*.*?\*/", "", out, flags=re.S)
        out = re.sub(r"//.*?$", "", out, flags=re.M)
    if ext in {".py"}:
        out = re.sub(r"'''.*?'''|\"\"\".*?\"\"\"", "", out, flags=re.S)
        out = re.sub(r"#.*?$", "", out, flags=re.M)
    # Collapse whitespace for length checks
    return re.sub(r"\s+", " ", out).strip()


def stub_reject_reason(path: str, content: str) -> Optional[str]:
    """
    Return a short error if content is a useless stub for this file type.
    Allows empty only for intentionally empty paths we don't gate.
    """
    rel = (path or "").replace("\\", "/")
    ext = Path(rel).suffix.lower()
    raw = content if content is not None else ""
    if not str(raw).strip():
        return f"{rel}: content is empty - write a real usable file"

    stripped = _strip_comments(rel, str(raw))
    if not stripped:
        return (
            f"{rel}: content is only comments/placeholders. "
            "Write real markup, styles, or code - not stub comments."
        )

    if ext in {".html", ".htm"}:
        low = stripped.lower()
        if len(stripped) < 280:
            return (
                f"{rel}: HTML too thin ({len(stripped)} chars after comments). "
                "Ship a complete page (doctype, head, body, real sections/copy), not a stub."
            )
        if not any(tag in low for tag in ("<!doctype", "<html", "<body", "<main", "<header")):
            return f"{rel}: HTML must include a real document structure (<!doctype>/<html>/<body>)."
        # Comment-heavy: comments dominate raw length
        if len(stripped) < max(80, int(len(str(raw)) * 0.35)):
            return f"{rel}: mostly comments - fill with real page content."
        # Hollow page: chrome/nav only - body has almost no section copy
        body_m = re.search(r"(?is)<body[^>]*>(.*)</body>", str(raw))
        if body_m:
            body_html = body_m.group(1)
            body_only = _strip_comments(rel, body_html)
            has_section = bool(
                re.search(r"(?i)<(main|section|article|aside)\b", body_html)
            )
            body_main = re.sub(
                r"(?is)<(header|nav|footer|script|style)\b[^>]*>.*?</\1>",
                " ",
                body_html,
            )
            body_main = _strip_comments(rel, body_main)
            body_main = re.sub(r"<[^>]+>", " ", body_main)
            body_main = re.sub(r"\s+", " ", body_main).strip()
            if not has_section and len(body_main) < 60 and len(body_only) < 500:
                return (
                    f"{rel}: page body is hollow (chrome/nav only). "
                    "Add real sections and copy, or split into write_files - not an empty shell."
                )

    elif ext in {".css", ".scss", ".less"}:
        if len(stripped) < 120 or "{" not in stripped or ":" not in stripped:
            return (
                f"{rel}: CSS too thin. Include real rules (selectors + properties), "
                "not a single comment."
            )

    elif ext in {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}:
        if len(stripped) < 80:
            return (
                f"{rel}: script too thin. Include real behavior "
                "(listeners, DOM updates, or module exports) - not a stub comment."
            )

    elif ext in {".md"} and ("readme" in Path(rel).name.lower() or rel.lower().endswith("/readme.md")):
        if len(stripped) < 80:
            return f"{rel}: README too thin - describe the project and how to open/run it."

    # Generic placeholder bait
    if len(stripped) < 200 and _PLACEHOLDER_RE.search(str(raw)):
        return f"{rel}: looks like a placeholder - replace with finished content."

    return None
