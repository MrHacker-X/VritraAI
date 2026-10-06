"""Explain command."""
from __future__ import annotations

from core.client import get_ai_response
from core.display import clean_ai_response, print_ai_response, print_with_rich, status_line
from core.tui import print_cmd_help


def explain_command(args):
    """Handles the 'explain' command."""
    if not args:
        print_cmd_help(
            "Explain",
            [
                ("/explain <command>", "explain a command or concept"),
            ],
        )
        return

    command_to_explain = " ".join(args)
    prompt = f"""Explain this command/concept for a terminal user: {command_to_explain}

Use these headings:
## What it does
## Key options
## Common uses
## Examples
## Tips

Rules:
- Short bullets where possible
- Code/commands in proper Markdown fenced blocks with a language tag
- No dense pipe tables
- No emoji
- Do not wrap the whole answer in an outer fence"""

    status_line(f"explaining {command_to_explain}")
    explanation = get_ai_response(
        prompt,
        include_project_context=False,
        max_tokens=1500,
    )

    if explanation:
        cleaned = clean_ai_response(explanation)
        print()
        print(f"\033[1;97m{command_to_explain}\033[0m")
        print("\033[38;5;240m" + "─" * min(44, max(12, len(command_to_explain) + 4)) + "\033[0m")
        print_ai_response(cleaned, use_typewriter=False)
    else:
        print_with_rich("No explanation returned.", "warning")
