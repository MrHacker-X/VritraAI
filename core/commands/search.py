"""Semantic search command."""
from __future__ import annotations

import os
from typing import List

from core import runtime
from core.client import get_ai_response
from core.display import clean_ai_response, print_ai_response, print_with_rich
from core.files import _iter_code_files, read_file_content
from core.tui import print_cmd_help

def search_semantic_command(args: List[str]):
    """AI-powered semantic code search - /search <query> [path]."""
    if not args:
        print_cmd_help(
            "Search",
            [
                ("/search <query>", "semantic code search in project"),
                ("/search <query> <path>", "limit search to a path"),
            ],
        )
        return

    if not runtime.AI_ENABLED:
        print_with_rich("AI is required for semantic search but is not enabled.", "warning")
        return

    query = " ".join(args[:-1]) if len(args) > 1 and os.path.exists(args[-1]) else " ".join(args)
    target = args[-1] if len(args) > 1 and os.path.exists(args[-1]) else "."

    if not os.path.exists(target):
        print_with_rich(f"Path not found: {target}", "error")
        return

    base_path = target if os.path.isdir(target) else os.path.dirname(target) or "."
    code_files = _iter_code_files(base_path)
    if not code_files:
        print_with_rich("No code files found for semantic search.", "warning")
        return

    # Collect a small corpus of relevant snippets
    snippets = []
    max_files = 12
    max_chars_per_file = 600

    for path in code_files[:max_files]:
        try:
            content = read_file_content(path)
            if not content:
                continue
            if query.lower() in content.lower():
                snippet = content[:max_chars_per_file]
            else:
                snippet = content[:max_chars_per_file]
            snippets.append(f"File: {path}\n\n```\n{snippet}\n```\n")
        except Exception:
            continue

    if not snippets:
        print_with_rich("Could not collect snippets for semantic search.", "warning")
        return

    prompt = f"""You are a code search engine embedded in a terminal.

The user query is:
"{query}"

You are given snippets from several project files. Identify where in the codebase the query is most relevant and answer:

1) Which files/snippets are most relevant (with reasons)
2) What the code does related to the query
3) Where to start reading or editing (file + rough line ranges)
4) Any potential pitfalls or related symbols to inspect

Snippets:
{''.join(snippets)}

Respond with a concise, structured explanation suitable for terminal output.
"""

    print_with_rich("🤖 VritraAI performing semantic search...", "info")
    result = get_ai_response(prompt)
    if result:
        cleaned = clean_ai_response(result)
        print_with_rich("\n🔍 Semantic Search Results\n", "info")
        print_ai_response(cleaned, use_typewriter=True)

