"""Security scan commands."""
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


def security_scan_command(args: List[str]):
    """AI-powered security vulnerability scan."""
    if not args:
        print_cmd_help(
            "Security scan",
            [
                ("/security <file>", "scan file for security issues"),
                ("/security <directory>", "scan all files in directory"),
            ],
        )
        return

    target = args[0]

    if os.path.isfile(target):
        _security_scan_file(target)
    elif os.path.isdir(target):
        _security_scan_directory(target)
    else:
        print_with_rich(f"File or directory not found: {target}", "error")


def _security_scan_file(file_path: str):
    """Security scan for a single file."""
    if not runtime.AI_ENABLED:
        print_with_rich("AI disabled - run /setup", "error")
        return

    code_content = read_file_content(file_path)
    if not code_content:
        return

    language = get_file_language(file_path)

    if len(code_content) > 8000:
        code_content = code_content[:8000] + "\n... [File truncated for analysis]"

    prompt = f"""Security assessment for this {language} file.

File: {file_path}
Language: {language}

For each finding use this stacked format (NOT a pipe table):

### FINDING-ID - Severity
Location: line range or function
Impact: one short paragraph
Why it matters: one short paragraph
Fix: concrete remediation steps
Example (optional): a fenced code block with language tag

Severity buckets: Critical, High, Medium, Low.

Also end with:
## Summary
## Priority fixes

Rules:
- No dense markdown tables
- No HTML <br> tags
- No emoji
- Proper fenced code blocks only
- Do not wrap the whole answer in an outer fence

Code:
```{language.lower()}
{code_content}
```"""

    status_line(f"security scan · {os.path.basename(file_path)}")
    security_result = get_ai_response(
        prompt,
        include_project_context=False,
        max_tokens=2500,
    )

    if security_result:
        cleaned = clean_ai_response(security_result)
        print()
        print(f"\033[1;97mSecurity scan · {os.path.basename(file_path)}\033[0m")
        print("\033[38;5;240m" + "─" * 44 + "\033[0m")
        print_ai_response(cleaned, use_typewriter=False)
        print()
        log_session(f"Security scan completed: {file_path}")
    else:
        print_with_rich("Failed to get security analysis", "error")


def _security_scan_directory(directory: str):
    """Security scan for all files in directory."""
    code_extensions = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cs", ".cpp", ".c",
        ".go", ".rs", ".php", ".rb", ".swift", ".kt", ".scala", ".sql",
    }

    code_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if any(file.lower().endswith(ext) for ext in code_extensions):
                code_files.append(os.path.join(root, file))

    if not code_files:
        print_with_rich(f"No code files found in {directory}", "warning")
        return

    status_line(f"found {len(code_files)} files for security scanning")

    if len(code_files) > 3:
        if not confirm_action(
            f"Scan {len(code_files)} files for security issues? This may take a while",
            default_yes=False,
        ):
            return

    for i, file_path in enumerate(code_files, 1):
        status_line(f"scanning file {i}/{len(code_files)}")
        _security_scan_file(file_path)
        if i < len(code_files):
            import time

            time.sleep(0.5)
