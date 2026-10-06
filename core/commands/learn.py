"""Learn / cheat commands."""
from __future__ import annotations

from typing import List

from core import runtime
from core.client import get_ai_response
from core.display import clean_ai_response, print_ai_response, print_with_rich, status_line
from core.tui import print_cmd_help


def learn_command(args: List[str]):
    """AI-powered learning assistant."""
    if not runtime.AI_ENABLED:
        print_with_rich("AI is required for learning features", "warning")
        return

    if not args:
        print_cmd_help(
            "Learn",
            [
                ("/learn <topic>", "practical lesson with examples"),
                ("examples", "bash loops · git rebase · python decorators"),
            ],
        )
        return

    topic = " ".join(args)

    prompt = f"""Teach "{topic}" for a terminal user. Keep it short and scannable.

Structure (use these exact headings):
## What it is
## Common uses
## Examples
## Tips
## Mistakes to avoid

Rules:
- Prefer short bullets
- For code/commands use proper Markdown fenced blocks with a language tag (bash/python/…)
- Do NOT wrap the whole answer in an outer ``` fence
- Do NOT use dense pipe tables
- Max ~400 words"""

    status_line(f"learning {topic}")
    explanation = get_ai_response(
        prompt,
        include_project_context=False,
        max_tokens=900,
    )

    if not explanation:
        return

    cleaned = clean_ai_response(explanation)
    print()
    print(f"\033[1;97m{topic}\033[0m")
    print("\033[38;5;240m" + "─" * min(44, max(12, len(topic) + 4)) + "\033[0m")
    print_ai_response(cleaned, use_typewriter=False)

    try:
        with open(runtime.LEARNING_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n## {topic}\n\n{cleaned}\n\n---\n")
        status_line(f"notes saved · {runtime.LEARNING_FILE}")
    except Exception as e:
        print_with_rich(f"Could not save learning notes: {e}", "warning")


def cheat_command(args: List[str]):
    """Show cheatsheet for commands or topics."""
    if not runtime.AI_ENABLED:
        print_with_rich("AI is required for cheatsheets", "warning")
        return

    if not args:
        print_cmd_help(
            "Cheatsheet",
            [
                ("/cheatsheet <topic>", "quick reference for a topic"),
                ("examples", "git · docker · vim"),
            ],
        )
        return

    topic = " ".join(args)

    prompt = f"""Create a compact cheatsheet for {topic}.

Rules:
- Short sections with colon headers
- Bullet lists of commands + one-line meaning
- For multi-line examples use Markdown fenced code blocks with language tags
- No outer wrapper fence around the whole answer
- No dense pipe tables
- No emoji"""

    status_line(f"cheatsheet {topic}")
    cheatsheet = get_ai_response(
        prompt,
        include_project_context=False,
        max_tokens=900,
    )

    if not cheatsheet:
        return

    cleaned = clean_ai_response(cheatsheet)
    print()
    print(f"\033[1;97m{topic.title()} cheatsheet\033[0m")
    print("\033[38;5;240m" + "─" * 44 + "\033[0m")
    print_ai_response(cleaned, use_typewriter=False)
