"""Live unified-diff rendering for agent edits (with syntax highlighting)."""
from __future__ import annotations

import difflib
import re
from typing import List, Optional, Sequence


def unified_diff_text(
    path: str,
    before: str,
    after: str,
    *,
    context: int = 3,
    max_lines: int = 120,
) -> str:
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    diff = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
            n=context,
        )
    )
    if not diff:
        return "(no textual diff)"
    if len(diff) > max_lines:
        head = diff[:max_lines]
        head.append(f"… +{len(diff) - max_lines} more diff lines")
        return "\n".join(head)
    return "\n".join(diff)


def print_diff(path: str, before: str, after: str, *, title: Optional[str] = None) -> None:
    """Print a colored live diff with syntax-highlighted code (divider layout)."""
    raw = unified_diff_text(path, before, after)
    before_hl = _highlight_source_lines(path, before)
    after_hl = _highlight_source_lines(path, after)
    lines = _render_diff_lines(raw.splitlines(), before_hl, after_hl)
    _print_panel(title or f"Diff  {path}", lines, precolored=True)


def print_new_file(path: str, content: str, *, max_lines: int = 80) -> None:
    source_lines = content.splitlines()
    highlighted = _highlight_source_lines(path, content)
    if not source_lines:
        out = [_paint("+ (empty file)", "\033[38;5;114m")]
    else:
        shown = highlighted[:max_lines]
        out = []
        green = "\033[38;5;114m"
        reset = "\033[0m"
        for hl in shown:
            # Keep syntax colors on code; marker stays green
            out.append(f"{green}+{reset} {hl}")
        if len(source_lines) > max_lines:
            out.append(_paint(f"… +{len(source_lines) - max_lines} more lines", "\033[90m"))
    _print_panel(f"Create  {path}", out, precolored=True)


def print_delete_preview(path: str, *, is_dir: bool = False) -> None:
    kind = "directory" if is_dir else "file"
    _print_panel(f"Delete  {path}", [f"- remove {kind}: {path}"], danger=True)


def _render_diff_lines(
    diff_lines: Sequence[str],
    before_hl: Sequence[str],
    after_hl: Sequence[str],
) -> List[str]:
    """Attach syntax colors to +/-/context lines using hunk line numbers."""
    muted = "\033[90m"
    red = "\033[38;5;203m"
    green = "\033[38;5;114m"
    cyan = "\033[38;5;110m"
    reset = "\033[0m"

    out: List[str] = []
    old_i = 0
    new_i = 0

    for line in diff_lines:
        if line.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if m:
                old_i = int(m.group(1)) - 1
                new_i = int(m.group(2)) - 1
            out.append(f"{cyan}{line}{reset}")
            continue
        if line.startswith("---") or line.startswith("+++"):
            out.append(f"{cyan}{line}{reset}")
            continue
        if line.startswith("…"):
            out.append(f"{muted}{line}{reset}")
            continue
        if line.startswith("+"):
            body = after_hl[new_i] if 0 <= new_i < len(after_hl) else line[1:].lstrip(" ")
            out.append(f"{green}+{reset} {body}")
            new_i += 1
            continue
        if line.startswith("-"):
            body = before_hl[old_i] if 0 <= old_i < len(before_hl) else line[1:].lstrip(" ")
            out.append(f"{red}-{reset} {body}")
            old_i += 1
            continue
        # context line
        if line.startswith(" "):
            if 0 <= new_i < len(after_hl):
                body = after_hl[new_i]
            elif 0 <= old_i < len(before_hl):
                body = before_hl[old_i]
            else:
                body = line[1:]
            out.append(f"  {body}")
            old_i += 1
            new_i += 1
            continue
        out.append(f"{muted}{line}{reset}")
    return out


def _highlight_source_lines(path: str, source: str) -> List[str]:
    """Return ANSI syntax-highlighted lines for source (no markers)."""
    if source is None:
        return []
    text = source if source.endswith("\n") or not source else source
    try:
        from pygments import highlight
        from pygments.formatters import Terminal256Formatter
        from pygments.lexers import TextLexer, guess_lexer_for_filename
        from pygments.util import ClassNotFound

        try:
            lexer = guess_lexer_for_filename(path or "file.txt", text)
        except ClassNotFound:
            lexer = TextLexer()
        formatter = Terminal256Formatter(style="monokai")
        rendered = highlight(text, lexer, formatter)
        # Drop trailing formatter newline artifact
        lines = rendered.rstrip("\n").split("\n")
        # If source was empty
        if not source:
            return []
        # Ensure line count matches (pygments rarely differs)
        raw_count = len(source.splitlines())
        if raw_count and len(lines) > raw_count:
            lines = lines[:raw_count]
        elif raw_count and len(lines) < raw_count:
            # pad with plain leftovers
            plain = source.splitlines()
            lines.extend(plain[len(lines) :])
        return lines
    except Exception:
        return source.splitlines()


def _paint(text: str, color: str) -> str:
    return f"{color}{text}\033[0m"


def _print_panel(
    title: str,
    lines: Sequence[str],
    *,
    new_file: bool = False,
    danger: bool = False,
    precolored: bool = False,
) -> None:
    """Clean title + divider + body (no boxed frame)."""
    try:
        from core.agent.status import stop_status

        stop_status(clear=True)
    except Exception:
        pass
    muted = "\033[90m"
    reset = "\033[0m"
    white = "\033[1;97m"
    red = "\033[38;5;203m"
    green = "\033[38;5;114m"
    cyan = "\033[38;5;110m"
    accent = red if danger else cyan

    visible_lens = [len(_strip(l)) for l in lines] or [20]
    width = min(88, max(40, max(visible_lens), len(title) + 2))

    print()
    print(f"{white}{title}{reset}")
    print(f"{accent}{'─' * width}{reset}")
    for line in lines:
        if precolored:
            colored = line
        else:
            colored = _color_diff_line(
                line,
                new_file=new_file,
                danger=danger,
                red=red,
                green=green,
                cyan=cyan,
                muted=muted,
                reset=reset,
            )
        if len(_strip(line)) > width:
            colored = _truncate_ansi(colored, width)
        print(colored)
    print(f"{muted}{'─' * width}{reset}")
    print()


def _color_diff_line(
    line: str,
    *,
    new_file: bool,
    danger: bool,
    red: str,
    green: str,
    cyan: str,
    muted: str,
    reset: str,
) -> str:
    if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
        return f"{cyan}{line}{reset}"
    if line.startswith("+") or (new_file and line.startswith("+")):
        return f"{green}{line}{reset}"
    if line.startswith("-") or danger:
        return f"{red}{line}{reset}"
    return f"{muted}{line}{reset}"


def _strip(s: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", s)


def _truncate_ansi(s: str, max_visible: int) -> str:
    """Truncate ANSI string to max_visible columns, preserving reset."""
    out = []
    visible = 0
    i = 0
    while i < len(s) and visible < max_visible:
        if s[i] == "\033":
            m = re.match(r"\033\[[0-9;]*m", s[i:])
            if m:
                out.append(m.group(0))
                i += len(m.group(0))
                continue
        out.append(s[i])
        visible += 1
        i += 1
    out.append("\033[0m")
    return "".join(out)
