"""Code optimize command."""
from __future__ import annotations

import os
from typing import List

from core import runtime
from core.client import get_ai_response
from core.display import print_ai_response, print_with_rich, status_line
from core.files import confirm_action, read_file_content
from core.lang import get_file_language
from core.session_log import log_session
from core.tui import print_cmd_help


def optimize_code_command(args: List[str]):
    """AI-powered code optimization suggestions."""
    if not args:
        print_cmd_help(
            "Optimize",
            [
                ("/optimize <file>", "optimization suggestions"),
                ("/optimize <file> --type=<focus>", "performance · memory · algorithm · readability"),
            ],
        )
        return

    file_path = args[0]
    optimization_type = None

    if len(args) > 1 and args[1].startswith("--type="):
        optimization_type = args[1].split("=", 1)[1]

    if not os.path.isfile(file_path):
        print_with_rich(f"File not found: {file_path}", "error")
        return

    if not runtime.AI_ENABLED:
        print_with_rich("AI disabled - run /setup", "error")
        return

    code_content = read_file_content(file_path)
    if not code_content:
        return

    language = get_file_language(file_path)

    if len(code_content) > 8000:
        code_content = code_content[:8000] + "\n... [File truncated for analysis]"

    optimization_focus = ""
    if optimization_type:
        focus_types = {
            "performance": "Focus on execution speed, algorithms, and runtime.",
            "memory": "Focus on memory usage and allocations.",
            "algorithm": "Focus on algorithms and data structures.",
            "readability": "Focus on clarity and structure.",
            "scalability": "Focus on concurrency and resource use.",
        }
        optimization_focus = focus_types.get(
            optimization_type.lower(), f"Focus on {optimization_type} optimizations."
        )

    prompt = f"""Optimize this {language} code.

File: {file_path}
{optimization_focus}

Structure:
## Opportunities
## Impact (High/Medium/Low)
## Optimized code

Rules:
- Include a COMPLETE optimized version in one fenced code block with language tag
- Prefer sections over pipe tables
- No emoji
- Do not wrap the whole answer in an outer fence

Code:
```{language.lower()}
{code_content}
```"""

    status_line(f"optimizing {os.path.basename(file_path)}")
    optimization_result = get_ai_response(
        prompt,
        include_project_context=False,
        max_tokens=3000,
    )

    if optimization_result:
        print()
        print(f"\033[1;97mOptimize · {os.path.basename(file_path)}\033[0m")
        print("\033[38;5;240m" + "─" * 44 + "\033[0m")
        print_ai_response(optimization_result, use_typewriter=False)
        print()

        import re

        code_pattern = r"```(?:[a-zA-Z]+)?\s*\n(.*?)```"
        matches = re.findall(code_pattern, optimization_result, re.DOTALL)

        if matches:
            optimized_code = max(matches, key=len).strip()
            status_line("save optimized code?")
            if confirm_action("Save optimized code to a new file?", default_yes=True):
                base_name = os.path.splitext(file_path)[0]
                extension = os.path.splitext(file_path)[1]
                optimized_filename = f"{base_name}_optimized{extension}"

                custom_name = input(
                    f"Enter filename (press Enter for '{optimized_filename}'): "
                ).strip()
                if custom_name:
                    optimized_filename = custom_name

                try:
                    with open(optimized_filename, "w", encoding="utf-8") as f:
                        f.write(optimized_code)
                    print_with_rich(f"Saved · {optimized_filename}", "success")
                    log_session(f"Optimized code saved: {optimized_filename}")
                except Exception as e:
                    print_with_rich(f"Error saving file: {e}", "error")

        log_session(f"Code optimization analysis: {file_path}")
    else:
        print_with_rich("Failed to get optimization suggestions", "error")
