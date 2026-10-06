"""Refactor command."""
from __future__ import annotations

import os
from typing import List

from core import runtime
from core.client import get_ai_response
from core.display import print_ai_response, print_with_rich, status_line
from core.files import backup_file, confirm_action, read_file_content
from core.lang import get_file_language
from core.session_log import log_session
from core.tui import print_cmd_help


def refactor_command(args: List[str]):
    """AI-powered code refactoring suggestions."""
    if not args:
        print_cmd_help(
            "Refactor",
            [
                ("/refactor <file> <goal>", "refactor with a specific goal"),
                ("patterns", "extract-method · extract-class · simplify · modernize"),
            ],
        )
        return

    if len(args) < 2:
        print_cmd_help(
            "Refactor",
            [
                ("/refactor <file> <goal>", "refactor with a specific goal"),
            ],
        )
        return

    file_path = args[0]
    refactor_instruction = " ".join(args[1:])

    if not os.path.isfile(file_path):
        print_with_rich(f"File not found: {file_path}", "error")
        return

    if not runtime.AI_ENABLED:
        print_with_rich("AI disabled - run /setup", "error")
        return

    is_language_conversion = False
    target_language = None
    conversion_keywords = ["convert", "translate", "port", "rewrite", "change language", "to"]

    language_mappings = [
        (["bash", "bash script", "bash scripting", "shell", "shell script", "sh"], ("bash", ".sh")),
        (["python", "py"], ("python", ".py")),
        (["javascript", "js", "node"], ("javascript", ".js")),
        (["typescript", "ts"], ("typescript", ".ts")),
        (["java"], ("java", ".java")),
        (["go", "golang"], ("go", ".go")),
        (["rust", "rs"], ("rust", ".rs")),
        (["c++", "cpp"], ("c++", ".cpp")),
        (["c language", "c code"], ("c", ".c")),
        (["ruby", "rb"], ("ruby", ".rb")),
        (["php"], ("php", ".php")),
    ]

    instruction_lower = refactor_instruction.lower()
    for keyword in conversion_keywords:
        if keyword in instruction_lower:
            for lang_aliases, lang_info in language_mappings:
                for alias in lang_aliases:
                    if alias in instruction_lower:
                        is_language_conversion = True
                        target_language = lang_info
                        break
                if is_language_conversion:
                    break
            break

    code_content = read_file_content(file_path)
    if not code_content:
        return

    language = get_file_language(file_path)

    if len(code_content) > 8000:
        code_content = code_content[:8000] + "\n... [File truncated for analysis]"
        status_line("large file truncated for analysis")

    if refactor_instruction.startswith("--pattern="):
        pattern = refactor_instruction.split("=", 1)[1]
        pattern_guides = {
            "extract-method": "Extract repeated code into reusable methods/functions.",
            "extract-class": "Extract related functionality into separate classes.",
            "simplify": "Simplify complex logic, reduce nesting, improve readability.",
            "modernize": "Update code to use modern language features and best practices.",
            "single-responsibility": "Ensure each function/class has a single responsibility.",
            "dependency-injection": "Apply dependency injection patterns.",
            "strategy-pattern": "Apply strategy pattern for conditional logic.",
        }
        refactor_instruction = pattern_guides.get(
            pattern.lower(), f"Apply {pattern} refactoring pattern."
        )

    if is_language_conversion and target_language:
        target_lang_name, _ = target_language
        prompt = f"""Convert this {language} code to {target_lang_name}.

File: {file_path}
Goal: {refactor_instruction}

## Analysis
## Converted code
## Notes

Rules:
- Full working {target_lang_name} in one fenced code block
- No emoji, no dense tables
- Do not wrap the whole answer in an outer fence

Original:
```{language.lower()}
{code_content}
```"""
    else:
        prompt = f"""Refactor this {language} code.

File: {file_path}
Goal: {refactor_instruction}

## Analysis
## Plan
## Improved code
## Benefits
## Considerations

Rules:
- Complete refactored code in a fenced block with language tag
- No emoji, no dense tables
- Do not wrap the whole answer in an outer fence

Original:
```{language.lower()}
{code_content}
```"""

    status_line(f"refactoring {os.path.basename(file_path)}")
    refactor_result = get_ai_response(
        prompt,
        include_project_context=False,
        max_tokens=3000,
    )

    if refactor_result:
        print()
        print(f"\033[1;97mRefactor · {os.path.basename(file_path)}\033[0m")
        print("\033[38;5;240m" + "─" * 44 + "\033[0m")
        print_ai_response(refactor_result, use_typewriter=False)
        print()

        if is_language_conversion and target_language:
            target_lang_name, ext = target_language
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            new_file = f"{base_name}{ext}"

            if confirm_action(f"Create converted file '{new_file}'?", default_yes=True):
                _create_converted_file(new_file, refactor_result, target_lang_name)
        else:
            if confirm_action("Apply this refactoring to the file?", default_yes=False):
                _apply_refactoring_interactively(file_path, refactor_result)

        log_session(f"Code refactoring analysis: {file_path} - {refactor_instruction}")
    else:
        print_with_rich("Failed to get refactoring suggestions", "error")


def _create_converted_file(new_file: str, ai_response: str, target_language: str):
    """Create a new file with converted code from AI response."""
    try:
        import re

        code_pattern = r"```(?:[a-zA-Z]+)?\s*\n(.*?)```"
        matches = re.findall(code_pattern, ai_response, re.DOTALL)

        if matches:
            converted_code = max(matches, key=len).strip()
            with open(new_file, "w", encoding="utf-8") as f:
                f.write(converted_code)
            print_with_rich(f"Created · {new_file}", "success")
            log_session(f"Language conversion: created {new_file}")
        else:
            print_with_rich("No code block found - create the file manually.", "warning")
    except Exception as e:
        print_with_rich(f"Error creating converted file: {e}", "error")


def _apply_refactoring_interactively(file_path: str, refactor_result: str):
    """Interactively apply refactoring suggestions."""
    try:
        backup_path = backup_file(file_path)
        if backup_path:
            status_line(f"backup · {os.path.basename(backup_path)}")
        print_with_rich(
            "Manual apply recommended - review the plan above and edit carefully.",
            "warning",
        )
    except Exception as e:
        print_with_rich(f"Error during refactoring: {e}", "error")
