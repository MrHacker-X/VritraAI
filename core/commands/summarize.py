"""Summarize command."""
from __future__ import annotations

import os
from typing import List

from core import runtime
from core.client import get_ai_response
from core.context import summarize_directory
from core.display import clean_ai_response, print_ai_response, print_with_rich, status_line
from core.files import expand_path, read_file_content


def summarize_command(args: List[str]):
    """Summarize directory or file."""
    target = args[0] if args else "."
    target = expand_path(target)

    if os.path.isdir(target):
        cwd = os.getcwd()
        try:
            if target != ".":
                os.chdir(target)
            summary = summarize_directory()
            print(summary)
        finally:
            if target != ".":
                os.chdir(cwd)
    elif os.path.isfile(target):
        if not runtime.AI_ENABLED:
            print_with_rich("AI is required for file summarization but is not enabled.", "warning")
            return

        content = read_file_content(target)
        if content:
            prompt = f"""Summarize this file for a developer.

File: {target}

## Purpose
## Key parts
## Notable details

Rules:
- Plain readable sections
- No dense tables, no emoji
- Do not wrap the whole answer in an outer fence

Content:
```
{content[:4000]}
```
{"...content truncated..." if len(content) > 4000 else ""}"""
            status_line(f"summarizing {os.path.basename(target)}")
            summary = get_ai_response(
                prompt,
                include_project_context=False,
                max_tokens=1500,
            )
            if summary:
                cleaned = clean_ai_response(summary)
                print()
                print(f"\033[1;97mSummary · {target}\033[0m")
                print("\033[38;5;240m" + "─" * 44 + "\033[0m")
                print_ai_response(cleaned, use_typewriter=False)
    else:
        print_with_rich(f"Path not found: {target}", "error")
