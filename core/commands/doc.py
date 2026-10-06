"""Documentation generator commands."""
from __future__ import annotations

import os
from typing import List

from core import runtime
from core.client import get_ai_response
from core.display import clean_ai_response, print_ai_response, print_with_rich, status_line, strip_markdown_fences
from core.exceptions import APIError, FileOperationError
from core.files import _iter_code_files, read_file_content, write_file_content
from core.lang import get_file_language
from core.commands.project import _analyze_project_structure, _generate_health_report
from core.tui import print_cmd_help


def execute_with_error_recovery(operation_func, *args, context: str = "", max_retries: int = 3, **kwargs):
    """Local shim - full recovery UI not migrated."""
    return operation_func(*args, **kwargs)

def doc_command(args: List[str]):
    """AI-powered documentation generator - /doc <subcommand>."""
    if not args or args[0] in {"help", "-h", "--help"}:
        print_cmd_help(
            "Documentation",
            [
                ("/doc docstring <file>", "suggest docstrings"),
                ("/doc readme [path]", "generate README.md for project/dir"),
                ("/doc readme <file>", "generate README for a file"),
                ("/doc diagram <file>", "code-to-diagram (mermaid/plantuml/text)"),
            ],
        )
        return

    sub = args[0]
    sub_args = args[1:]

    if sub == "docstring":
        _doc_docstring(sub_args)
    elif sub == "readme":
        _doc_readme(sub_args)
    elif sub == "tutorial":
        print_with_rich("Tutorial was removed. Use /doc readme or /learn <topic>.", "warning")
    elif sub == "diagram":
        _doc_diagram(sub_args)
    else:
        print_with_rich(f"Unknown doc subcommand: {sub}", "error")
        doc_command(["help"])

def _doc_docstring(args: List[str]):
    """Generate docstring suggestions for a given source file (optionally a symbol).

    Now integrated with the explain/recovery system so missing or unreadable
    files trigger helpful AI guidance instead of silent failures.
    """
    if not runtime.AI_ENABLED:
        print_with_rich("AI is required for docstring generation but is not enabled.", "warning")
        return

    if not args:
        print_cmd_help(
            "Documentation",
            [("/doc docstring <file> [symbol]", "suggest docstrings")],
        )
        return

    file_path = args[0]
    symbol = args[1] if len(args) > 1 else None

    def generate_docstrings():
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        content = read_file_content(file_path)
        if not content:
            raise FileOperationError(f"Could not read file: {file_path}")

        language = get_file_language(file_path)
        max_len = 6000
        code = content
        if len(code) > max_len:
            code = code[:max_len] + "\n... [truncated]"

        symbol_part = f" for symbol '{symbol}'" if symbol else ""
        prompt = f"""You are a senior {language} engineer.

The user wants to improve documentation by adding or improving docstrings{symbol_part} in this file:

File: {file_path}
Language: {language}

Code:
```{language.lower() if language != 'Unknown' else 'text'}
{code}
```

Suggest high-quality docstrings (or comments if the language doesn't use docstrings) for functions, methods, classes, and modules.

IMPORTANT:
- Do NOT rewrite the entire file.
- For each function/class, show the signature and the docstring you propose beneath it.
- Use the idiomatic style for {language} (e.g., Python triple-quoted docstrings, JSDoc for JS/TS, etc.).
- Focus only on documentation text, not code changes.
- Do not wrap the whole answer in an outer markdown fence.
"""

        status_line("generating docstrings")
        result = get_ai_response(prompt, include_project_context=False, max_tokens=3000)
        if not result:
            raise APIError("Failed to generate docstring suggestions.")

        cleaned = clean_ai_response(result)
        print()
        print("\033[1;97mDocstring suggestions\033[0m")
        print("\033[38;5;240m" + "─" * 44 + "\033[0m")
        print_ai_response(cleaned, use_typewriter=False)
        return True

    execute_with_error_recovery(generate_docstrings, context=f"Command: doc docstring {file_path}")

def _doc_readme(args: List[str]):
    """Generate README.md from project analysis or for a specific file.

    Modes:
        doc readme                 -> analyze current directory (project-level README)
        doc readme [path] [out]    -> directory/project-level README
        doc readme <file>          -> file-focused README next to that file

    Now integrates explain/recovery mode so invalid paths are handled
    gracefully and explained by the AI instead of silently falling back.
    """
    if not runtime.AI_ENABLED:
        print_with_rich("AI is required for README generation but is not enabled.", "warning")
        return

    target = args[0] if args else "."
    out_path = args[1] if len(args) >= 2 else None
    explicit_target = bool(args)

    # If user provided a target, validate that it exists before doing any AI work
    if explicit_target and not (os.path.isfile(target) or os.path.isdir(target)):
        def _missing_target():
            raise FileNotFoundError(f"Path not found: {target}")

        execute_with_error_recovery(_missing_target, context=f"Command: doc readme {target}")
        return

    # File-specific README mode
    if os.path.isfile(target):
        file_path = target

        def _generate_file_readme():
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

            content = read_file_content(file_path)
            if not content:
                raise FileOperationError(f"Could not read file: {file_path}")

            language = get_file_language(file_path)
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            default_out = os.path.join(os.path.dirname(file_path), f"{base_name}.README.generated.md")
            output = out_path or default_out

            file_prompt = f"""You are generating a high-quality README.md for a single source file.

File path: {file_path}
Language: {language}

File content (truncated if large):
```{language.lower() if language != 'Unknown' else 'text'}
{content[:6000]}
```

Write a detailed README in Markdown that documents this file as a standalone tool/module.
Include:
- Title & Short Description
- What the Script/Tool Does
- Inputs (CLI args, env vars, config)
- Outputs & Side Effects
- Usage Examples (sort)
- Dependencies (Libraries, APIs)
- Notes & Limitations
- How It Works (Internal Architecture)
- Security Considerations
- Error Handling & Troubleshooting 
- License detail (sort MIT based license)

Return ONLY the README body in Markdown.
Do NOT wrap the entire document in a ```markdown fence.
"""

            status_line("generating file README")
            result = get_ai_response(file_prompt, include_project_context=False, max_tokens=3500)
            if not result:
                raise APIError("Failed to generate README.")

            cleaned = strip_markdown_fences(clean_ai_response(result))
            if write_file_content(output, cleaned):
                print_with_rich(f"README written · {output}", "success")
            return True

        execute_with_error_recovery(_generate_file_readme, context=f"Command: doc readme {file_path}")
        return

    # Directory/project-level README mode
    # If no explicit target was provided, default to current directory.
    target_dir = target if os.path.isdir(target) else "."

    def _generate_project_readme():
        if not os.path.isdir(target_dir):
            raise FileNotFoundError(f"Directory not found: {target_dir}")

        project_info = _analyze_project_structure(target_dir)
        health = _generate_health_report(target_dir)
        code_files = _iter_code_files(target_dir)

        samples = []
        for path in code_files[:5]:
            snippet = read_file_content(path)
            if not snippet:
                continue
            samples.append(f"File: {path}\n```\n{snippet[:800]}\n```\n")

        summary = f"""Project directory: {os.path.abspath(target_dir)}
Primary type: {project_info['primary_type']}
Secondary types: {', '.join(project_info['secondary_types'])}
Languages: {', '.join([f'{k} ({v})' for k, v in project_info['languages'].items()])}
Health scores:
  - Overall: {health['overall_score']}/100
  - Documentation: {health['documentation']['score']}/100
  - Testing: {health['testing']['score']}/100
  - Structure: {health['structure']['score']}/100

Representative code files (truncated excerpts):
{''.join(samples)}
"""

        prompt = f"""You are generating a high-quality README.md for a small CLI/utility project.

Project summary:
{summary}

Write a detailed README in Markdown that includes:
- Project title and short tagline
- Overview / description
- Features
- Installation instructions
- Usage examples
- Dependencies (Libraries, APIs)
- Configuration (if relevant)
- Running tests (if applicable)
- Folder structure overview
- Security Considerations
- Error Handling & Troubleshooting
- Contributing guidelines (brief)
- License placeholder (MIT based)

Return ONLY the README body in Markdown.
Do NOT wrap the entire document in a ```markdown fence.
"""

        status_line("generating README")
        result = get_ai_response(prompt, include_project_context=False, max_tokens=3500)
        if not result:
            raise APIError("Failed to generate README.")

        cleaned = strip_markdown_fences(clean_ai_response(result))
        output = out_path or os.path.join(target_dir, "README.generated.md")
        if write_file_content(output, cleaned):
            print_with_rich(f"README written · {output}", "success")
        return True

    execute_with_error_recovery(_generate_project_readme, context=f"Command: doc readme {target}")


def _doc_diagram(args: List[str]):
    """Generate a code architecture diagram description from a file."""
    if not runtime.AI_ENABLED:
        print_with_rich("AI is required for diagram generation but is not enabled.", "warning")
        return

    if not args:
        print_cmd_help(
            "Documentation",
            [("/doc diagram <file> [symbol] [fmt]", "mermaid · plantuml · text")],
        )
        return

    file_path = args[0]
    symbol = args[1] if len(args) > 1 and not args[1].startswith("-") else None
    fmt = args[2] if len(args) > 2 else "mermaid"
    fmt = fmt.lower()
    if fmt not in {"mermaid", "plantuml", "text"}:
        print_with_rich("Format must be one of: mermaid, plantuml, text", "warning")
        fmt = "mermaid"

    def _generate_diagram():
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        content = read_file_content(file_path)
        if not content:
            raise FileOperationError(f"Could not read file: {file_path}")

        language = get_file_language(file_path)
        max_len = 6000
        code = content
        if len(code) > max_len:
            code = code[:max_len] + "\n... [truncated]"

        symbol_part = f" focusing on symbol '{symbol}'" if symbol else ""

        if fmt == "mermaid":
            diagram_hint = "Produce a mermaid diagram (e.g., classDiagram, sequenceDiagram, flowchart) that best represents the structure."
        elif fmt == "plantuml":
            diagram_hint = "Produce a PlantUML diagram (@startuml ... @enduml) that represents the structure."
        else:
            diagram_hint = "Describe the architecture and relationships as an ASCII/text diagram."

        prompt = f"""You are generating an architecture diagram for this code file{symbol_part}.

File: {file_path}
Language: {language}

Code:
```{language.lower() if language != 'Unknown' else 'text'}
{code}
```

The goal is to show the static architecture of the codebase, not a
runtime flowchart of HTTP errors or argument parsing.

{diagram_hint}

IMPORTANT:
- First, identify the main entry point function (e.g. main()) and show it clearly.
- Then, show all important helper functions and how data flows between them.
- Focus on modules, classes, functions, and their relationships.
- Highlight how input (CLI args, config, etc.) flows into HTTP calls / I/O and
  then back out to output/printing.
- Group related functions or components logically.
- Avoid listing every possible error branch unless it is structurally important.
- Return ONLY the diagram content in a fenced code block for {fmt}.
"""

        status_line(f"generating {fmt} diagram")
        result = get_ai_response(prompt, include_project_context=False, max_tokens=2500)
        if not result:
            raise APIError("Failed to generate diagram.")

        cleaned = result.strip()
        base, _ = os.path.splitext(file_path)
        out_path = f"{base}.diagram.{fmt}.md" if fmt != "text" else f"{base}.diagram.txt"
        if write_file_content(out_path, cleaned):
            print_with_rich(f"Diagram written · {out_path}", "success")
        return True

    execute_with_error_recovery(_generate_diagram, context=f"Command: doc diagram {file_path}")

