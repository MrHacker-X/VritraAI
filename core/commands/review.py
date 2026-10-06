"""Code review commands."""
from __future__ import annotations

import os
from typing import List

from core import runtime
from core.client import get_ai_response
from core.display import clean_ai_response, print_ai_response, print_with_rich, status_line
from core.files import confirm_action, read_file_content
from core.lang import get_file_language
from core.session_log import log_session
from core.tui import print_cmd_help


def review_command(args: List[str]):
    """AI-powered comprehensive code review."""
    if not args:
        print_cmd_help(
            "Code review",
            [
                ("/review <file>", "comprehensive code review"),
                ("/review <file> --focus=<area>", "focus: security, performance, style"),
                ("/review <directory>", "review all files in directory"),
            ],
        )
        return

    target = args[0]
    focus_area = None

    if len(args) > 1 and args[1].startswith("--focus="):
        focus_area = args[1].split("=", 1)[1]

    if os.path.isfile(target):
        _review_single_file(target, focus_area)
    elif os.path.isdir(target):
        _review_directory(target, focus_area)
    else:
        print_with_rich(f"File or directory not found: {target}", "error")


def _review_single_file(file_path: str, focus_area: str = None):
    """Review a single code file."""
    if not runtime.AI_ENABLED:
        print_with_rich("AI disabled - run /setup", "error")
        return

    code_content = read_file_content(file_path)
    if not code_content:
        print_with_rich("Could not read file content", "error")
        return

    language = get_file_language(file_path)
    file_size = len(code_content)
    line_count = len(code_content.splitlines())

    if len(code_content) > 8000:
        code_content = code_content[:8000] + "\n... [File truncated for analysis]"
        status_line("large file truncated for analysis")

    focus_instruction = ""
    if focus_area:
        focus_areas = {
            "security": "Focus on security vulnerabilities, input validation, authentication.",
            "performance": "Focus on performance, algorithms, memory, bottlenecks.",
            "style": "Focus on style, naming, and best practices.",
            "bugs": "Focus on bugs, logic errors, edge cases.",
            "maintainability": "Focus on maintainability, readability, modularity.",
        }
        focus_instruction = focus_areas.get(
            focus_area.lower(), f"Focus on {focus_area} aspects of the code."
        )

    prompt = f"""Senior code review for this {language} file.

File: {file_path}
Size: {file_size} chars, {line_count} lines
{focus_instruction}

Cover:
## Bugs & Issues
## Performance
## Security
## Code Quality
## Recommendations

Rules:
- Severity labels: Critical / High / Medium / Low
- Line references when useful
- Code examples in proper fenced blocks with language tags
- Prefer stacked sections over dense pipe tables
- No emoji
- Do not wrap the whole answer in an outer fence

Code:
```{language.lower()}
{code_content}
```"""

    status_line(f"reviewing {os.path.basename(file_path)}")
    review_result = get_ai_response(
        prompt,
        include_project_context=False,
        max_tokens=2500,
    )

    if review_result:
        cleaned = clean_ai_response(review_result)
        print()
        print(f"\033[1;97mCode review · {os.path.basename(file_path)}\033[0m")
        print("\033[38;5;240m" + "─" * 44 + "\033[0m")
        print_ai_response(cleaned, use_typewriter=False)
        print()
        log_session(f"Code review completed: {file_path} ({language})")
    else:
        print_with_rich("Failed to get AI code review", "error")


def _review_directory(directory: str, focus_area: str = None):
    """Review all code files in a directory."""
    code_extensions = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cs", ".cpp", ".c",
        ".go", ".rs", ".php", ".rb", ".swift", ".kt", ".scala",
    }

    code_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if any(file.lower().endswith(ext) for ext in code_extensions):
                code_files.append(os.path.join(root, file))

    if not code_files:
        print_with_rich(f"No code files found in {directory}", "warning")
        return

    status_line(f"found {len(code_files)} code files")

    if len(code_files) > 5:
        if not confirm_action(f"Review {len(code_files)} files? This may take a while", default_yes=False):
            return

    for i, file_path in enumerate(code_files, 1):
        status_line(f"reviewing file {i}/{len(code_files)}")
        _review_single_file(file_path, focus_area)
        if i < len(code_files):
            import time

            time.sleep(0.5)
