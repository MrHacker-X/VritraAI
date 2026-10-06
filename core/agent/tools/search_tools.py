"""Text / glob search tools."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from core.agent.tools.base import ToolRegistry
from core.agent.types import ToolResult, ToolSpec
from core.agent.workspace import WorkspaceManager

_SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    "VritraAI-og",
}


def register_search_tools(registry: ToolRegistry, workspace: WorkspaceManager) -> None:
    def search_text(args: Dict[str, Any]) -> ToolResult:
        query = (args.get("query") or "").strip()
        if not query:
            return ToolResult("", "search_text", False, "query required")
        root_s = args.get("path") or "."
        root, err = workspace.resolve(root_s)
        if err or root is None:
            return ToolResult("", "search_text", False, err or "bad path")
        max_hits = int(args.get("max_results") or 40)
        hits: List[str] = []

        # Prefer ripgrep when available
        try:
            proc = subprocess.run(
                [
                    "rg",
                    "-n",
                    "--no-heading",
                    "--color",
                    "never",
                    "-g",
                    "!**/.git/**",
                    "-g",
                    "!**/node_modules/**",
                    "-g",
                    "!**/VritraAI-og/**",
                    "-m",
                    str(max_hits),
                    query,
                    str(root),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode in (0, 1):
                out = (proc.stdout or "").strip()
                return ToolResult("", "search_text", True, out or "No matches")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        pattern = re.compile(re.escape(query), re.I)
        base = root if root.is_dir() else root.parent
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
            for name in filenames:
                fp = Path(dirpath) / name
                try:
                    if fp.stat().st_size > 1_000_000:
                        continue
                    text = fp.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if pattern.search(line):
                        hits.append(f"{workspace.rel(fp)}:{i}:{line.strip()}")
                        if len(hits) >= max_hits:
                            return ToolResult("", "search_text", True, "\n".join(hits))
        return ToolResult("", "search_text", True, "\n".join(hits) if hits else "No matches")

    def glob_files(args: Dict[str, Any]) -> ToolResult:
        pattern = (args.get("pattern") or "").strip()
        if not pattern:
            return ToolResult("", "glob_files", False, "pattern required")
        root_s = args.get("path") or "."
        root, err = workspace.resolve(root_s)
        if err or root is None:
            return ToolResult("", "glob_files", False, err or "bad path")
        base = root if root.is_dir() else root.parent
        # Support ** patterns via rglob of suffix/name
        matches: List[str] = []
        try:
            if "**" in pattern or "*" in pattern or "?" in pattern:
                # Path.match is relative; use rglob with simplified pattern
                rel_pat = pattern.replace("**/", "")
                for p in base.rglob(rel_pat):
                    if any(part in _SKIP_DIRS for part in p.parts):
                        continue
                    matches.append(workspace.rel(p))
                    if len(matches) >= 200:
                        break
            else:
                p, e = workspace.resolve(pattern)
                if p and p.exists():
                    matches.append(workspace.rel(p))
        except Exception as e:
            return ToolResult("", "glob_files", False, str(e))
        return ToolResult("", "glob_files", True, "\n".join(matches) if matches else "No matches")

    def code_search(args: Dict[str, Any]) -> ToolResult:
        """Ranked code search by intent (keyword/path heuristics + optional AI brief)."""
        query = (args.get("query") or "").strip()
        if not query:
            return ToolResult("", "code_search", False, "query required")
        root_s = args.get("path") or "."
        root, err = workspace.resolve(root_s)
        if err or root is None:
            return ToolResult("", "code_search", False, err or "bad path")

        terms = [t.lower() for t in re.split(r"\W+", query) if len(t) >= 2]
        if not terms:
            terms = [query.lower()]

        scored: List[tuple] = []
        try:
            from core.files import _iter_code_files

            files = _iter_code_files(str(root))
        except Exception:
            files = []
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                if any(part in _SKIP_DIRS for part in p.parts):
                    continue
                if p.suffix.lower() in {
                    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
                    ".md", ".html", ".css", ".json", ".toml", ".yml", ".yaml",
                }:
                    files.append(str(p))

        for fpath in files[:400]:
            try:
                p = Path(fpath)
                if not p.is_file():
                    continue
                # Keep relative paths inside workspace when possible
                try:
                    rel = workspace.rel(p.resolve())
                except Exception:
                    rel = str(p)
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if len(text) > 400_000:
                text = text[:400_000]
            low = text.lower()
            path_l = rel.lower()
            score = 0
            for t in terms:
                if t in path_l:
                    score += 8
                score += min(low.count(t), 12)
            if score <= 0:
                continue
            lines = text.splitlines()
            hits = []
            for i, ln in enumerate(lines, start=1):
                ll = ln.lower()
                if any(t in ll for t in terms):
                    hits.append(f"{i}:{ln.strip()[:160]}")
                    if len(hits) >= 4:
                        break
            snippet = "\n".join(hits) if hits else "\n".join(
                f"{i}:{ln[:120]}" for i, ln in enumerate(lines[:6], start=1)
            )
            scored.append((score, rel, snippet))

        scored.sort(key=lambda x: -x[0])
        top = scored[:8]
        if not top:
            return ToolResult(
                "",
                "code_search",
                True,
                f"No ranked hits for {query!r}. Try search_text with an exact symbol.",
            )

        blocks = [f"Query: {query}", f"Top {len(top)} files:\n"]
        corpus_for_ai = []
        for score, rel, snippet in top:
            blocks.append(f"### {rel} (score={score})\n{snippet}\n")
            corpus_for_ai.append(f"{rel}\n{snippet}")

        # Optional short AI orientation when AI is enabled
        try:
            from core import runtime
            from core.agent.lean import lean_complete

            if runtime.AI_ENABLED and corpus_for_ai:
                brief = lean_complete(
                    "You rank code search hits. Be concise. No tool JSON.",
                    (
                        f"User query: {query}\n\nHits:\n"
                        + "\n\n".join(corpus_for_ai[:6])
                        + "\n\nIn under 12 lines: which files matter, why, and where to read next."
                    ),
                )
                if brief:
                    blocks.append("## Orientation\n" + brief.strip()[:2000])
        except Exception:
            pass

        return ToolResult("", "code_search", True, "\n".join(blocks), {"hits": len(top)})

    registry.register(
        ToolSpec(
            "search_text",
            "Search for a text/regex-like substring across the workspace (ripgrep if available).",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "path": {"type": "string"},
                    "max_results": {"type": "integer"},
                },
                "required": ["query"],
            },
            "safe",
        ),
        search_text,
    )
    registry.register(
        ToolSpec(
            "glob_files",
            "Find files by glob pattern under the workspace (e.g. **/*.py).",
            {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string"},
                },
                "required": ["pattern"],
            },
            "safe",
        ),
        glob_files,
    )
    registry.register(
        ToolSpec(
            "code_search",
            "Intent-oriented code search: ranks files/snippets by query terms (and optional AI brief). Prefer over guessing paths.",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "path": {"type": "string"},
                },
                "required": ["query"],
            },
            "safe",
        ),
        code_search,
    )
