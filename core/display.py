"""AI response display / formatting helpers."""
from __future__ import annotations

import re
import sys
import time
import threading
from typing import Optional

from core import runtime

def print_with_rich(text: str, style: str = "default"):
    """Print text using rich if available, fallback to plain text.
    If the text already contains ANSI escape sequences, print directly to preserve colors.
    """
    # Never fight the thinking spinner - clear it before writing a new line
    try:
        from core.agent.status import status_active, stop_status

        if status_active():
            stop_status(clear=True)
    except Exception:
        pass
    try:
        # Detect ANSI sequences and bypass Rich to preserve coloring
        if isinstance(text, str) and "\033[" in text:
            print(text)
            return
        if runtime.RICH_AVAILABLE and runtime.console:
            if style == "error":
                runtime.console.print(text, style="bold red")
            elif style == "success":
                runtime.console.print(text, style="bold green")
            elif style == "warning":
                runtime.console.print(text, style="bold yellow")
            elif style == "info":
                # Match new flow: muted status tone, not bright blue banners
                runtime.console.print(text, style="dim")
            elif style == "dim":
                runtime.console.print(text, style="dim")
            else:
                runtime.console.print(text)
        else:
            print(text)
    except Exception:
        # Fallback to basic print if rich fails
        print(text)

def typewriter_print(text: str, style: str = "default", speed: float = 0.003, fast_mode: bool = False):
    """Print text with optimized typewriter effect - character by character.
    
    Args:
        text: Text to print
        style: Color style to use
        speed: Base delay between characters (default: 0.003 for fast output)
        fast_mode: If True, use even faster chunked printing for very long text
    """
    import sys
    import time
    
    if not text:
        return
    
    # For very long text (>500 chars), use chunked fast mode
    if len(text) > 500 or fast_mode:
        return typewriter_print_chunked(text, style, chunk_size=10, delay=0.015)
    
    # Determine color codes based on style
    color_codes = {
        "error": "\033[91m",      # Red
        "success": "\033[92m",    # Green  
        "warning": "\033[93m",    # Yellow
        "info": "\033[94m",       # Blue
        "ai": "\033[96m",         # Cyan for AI responses
        "default": "\033[0m"      # Default
    }
    
    reset_code = "\033[0m"
    color_code = color_codes.get(style, color_codes["default"])
    
    # Start with color code
    if style != "default":
        sys.stdout.write(color_code)
    
    # Optimized character printing with reduced delays
    for i, char in enumerate(text):
        sys.stdout.write(char)
        
        # Flush every few characters for better performance
        if i % 5 == 0 or char in '\n.,!?;:':
            sys.stdout.flush()
        
        # Much faster, optimized speed based on character type
        if char in '.,!?;:':
            time.sleep(speed * 8)  # Brief pause for punctuation (reduced from *3)
        elif char == ' ':
            time.sleep(speed * 3)  # Quick pause for spaces (reduced from *1.5)
        elif char == '\n':
            time.sleep(speed * 10)  # Pause for new lines (reduced from *2)
        else:
            time.sleep(speed)  # Very fast for letters/numbers
    
    # Final flush and reset
    sys.stdout.flush()
    if style != "default":
        sys.stdout.write(reset_code)
    sys.stdout.write('\n')
    sys.stdout.flush()

def typewriter_print_chunked(text: str, style: str = "default", chunk_size: int = 10, delay: float = 0.015):
    """Ultra-fast chunked typewriter effect for long text.
    
    Args:
        text: Text to print
        style: Color style
        chunk_size: Number of characters to print at once
        delay: Delay between chunks
    """
    import sys
    import time
    
    # Color codes
    color_codes = {
        "error": "\033[91m", "success": "\033[92m", "warning": "\033[93m",
        "info": "\033[94m", "ai": "\033[96m", "default": "\033[0m"
    }
    
    reset_code = "\033[0m"
    color_code = color_codes.get(style, color_codes["default"])
    
    # Start with color
    if style != "default":
        sys.stdout.write(color_code)
    
    # Print in chunks for much faster display
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        sys.stdout.write(chunk)
        sys.stdout.flush()
        
        # Very brief delay between chunks
        if '\n' in chunk or any(p in chunk for p in '.,!?;:'):
            time.sleep(delay * 2)  # Slightly longer for chunks with breaks/punctuation
        else:
            time.sleep(delay)
    
    # Reset and finish
    if style != "default":
        sys.stdout.write(reset_code)
    sys.stdout.write('\n')
    sys.stdout.flush()

def format_text_only(text: str) -> str:
    """Format text without code blocks (headers, bold, lists, etc.)."""
    import re
    
    lines = text.split('\n')
    formatted_lines = []
    
    for line in lines:
        # Skip separator lines
        stripped = line.strip()
        if len(stripped) >= 3:
            separator_chars = sum(1 for c in stripped if c in '=-_*+#~^')
            if separator_chars / len(stripped) > 0.8:
                continue
        
        # Convert headers
        header_match = re.match(r'^(#{1,6})\s+(.*)', line)
        if header_match:
            header_text = header_match.group(2)
            header_text = re.sub(r'\*\*(.+?)\*\*', r'\1', header_text)
            formatted_lines.append(f"\033[1;33m{header_text}\033[0m")
            continue
        
        # Convert list items
        if re.match(r'^\s*[-+]\s+', line):
            content = re.sub(r'^\s*[-+]\s+', '', line)
            content = re.sub(r'\*\*(.+?)\*\*', r'\033[1;32m\1\033[0m', content)
            formatted_lines.append(f"  • {content}")
            continue
        
        # Handle ** bold ** - remove markers and highlight
        while '**' in line:
            line = re.sub(r'\*\*([^*]+?)\*\*', r'\033[1;32m\1\033[0m', line, count=1)
            if line.count('**') < 2:
                line = line.replace('**', '')
                break
        
        # Handle inline code
        if '`' in line:
            line = re.sub(r'`([^`]+)`', r'\033[33m\1\033[0m', line)
        
        # Remove markdown links
        line = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', line)
        
        formatted_lines.append(line)
    
    return '\n'.join(formatted_lines)

def print_ai_response_with_code_blocks(text: str):
    """Print AI response with syntax highlighting for fenced code blocks."""
    parts = []
    current_pos = 0

    # Allow optional spaces after lang; tolerate missing newline after lang tag
    pattern = r"```([a-zA-Z0-9_+-]*)[ \t]*\r?\n([\s\S]*?)```"

    for match in re.finditer(pattern, text):
        if match.start() > current_pos:
            text_part = text[current_pos : match.start()]
            parts.append(("text", text_part))

        lang = match.group(1) if match.group(1) else "text"
        code = match.group(2).rstrip("\n")
        parts.append(("code", lang, code))
        current_pos = match.end()

    if current_pos < len(text):
        parts.append(("text", text[current_pos:]))

    # If no fences matched but backticks present, fall back to plain text formatter
    if not any(p[0] == "code" for p in parts):
        formatted = format_text_only(clean_ai_response(text))
        if formatted.strip():
            print(formatted)
        return

    for part in parts:
        if part[0] == "text":
            formatted = format_text_only(part[1])
            if formatted.strip():
                print(formatted)
        elif part[0] == "code":
            lang = part[1]
            code = part[2]
            print()
            pygments_success = False
            try:
                from pygments import highlight
                from pygments.lexers import get_lexer_by_name, guess_lexer
                from pygments.formatters import Terminal256Formatter
                from pygments.util import ClassNotFound

                try:
                    lexer = get_lexer_by_name(lang.lower(), stripall=True)
                except ClassNotFound:
                    try:
                        lexer = guess_lexer(code)
                    except Exception:
                        from pygments.lexers import TextLexer

                        lexer = TextLexer()

                formatter = Terminal256Formatter(style="monokai")
                highlighted = highlight(code, lexer, formatter)
                print(highlighted, end="")
                pygments_success = True
            except Exception:
                pass

            if not pygments_success:
                for line in code.split("\n"):
                    print(line)
            print()


def print_ai_response(text: str, use_typewriter: bool = False):
    """Print AI response with clean formatting (no emoji chrome)."""
    if not text:
        return
    text = clean_ai_response(text)
    has_code_blocks = "```" in text

    if has_code_blocks:
        print_ai_response_with_code_blocks(text)
        return

    formatted_text = format_ai_response_for_terminal(text)
    if use_typewriter and 20 < len(formatted_text) < 1200:
        typewriter_print(formatted_text, "default", speed=0.001, fast_mode=True)
    else:
        print(formatted_text)

def show_ai_thinking():
    """
    Professional single-line status for the normal assistant.
    Same Codex-style spinner as the agent (no emoji stage labels).
    Returns a truthy handle for stop_ai_thinking().
    """
    from core.agent.status import PHASES_ASSISTANT, start_status, status_active

    start_status("Calling model", phases=PHASES_ASSISTANT, kind="model")
    return status_active


def stop_ai_thinking(thinking_active=None):
    """Stop the assistant thinking spinner and clear the line."""
    from core.agent.status import stop_status

    stop_status(clear=True)


def status_line(msg: str) -> None:
    """Muted Codex-style status (no emoji / no blue banner)."""
    try:
        from core.agent.status import status_active, stop_status

        if status_active():
            stop_status(clear=True)
    except Exception:
        pass
    print(f"\033[38;5;245m·\033[0m \033[38;5;245m{msg}\033[0m")


def strip_markdown_fences(text: str) -> str:
    """Remove wrapping ``` / ```markdown fences from model output (for file writes).

    Only strips when the *entire* document is wrapped in one fence.
    Does not touch trailing fences that close an inner code block.
    """
    if not text:
        return text
    t = text.strip()
    m = re.match(
        r"^```(?:markdown|md|text|plaintext|readme)?\s*\r?\n([\s\S]*?)\r?\n```\s*$",
        t,
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    # Leading wrapper only (no matching close as sole document fence)
    m2 = re.match(
        r"^```(?:markdown|md|text|plaintext|readme)\s*\r?\n([\s\S]*)$",
        t,
        flags=re.IGNORECASE,
    )
    if m2 and t.rstrip().endswith("```") and t.count("```") == 2:
        inner = m2.group(1)
        if inner.rstrip().endswith("```"):
            inner = re.sub(r"\r?\n```\s*$", "", inner)
        return inner.strip()
    return t


def _unescape_literal_newlines(text: str) -> str:
    """If the model emitted literal \\n more than real newlines, expand them."""
    if not text:
        return text
    literal = text.count("\\n")
    real = text.count("\n")
    if literal >= 3 and literal > real:
        return text.replace("\\n", "\n").replace("\\t", "\t")
    return text


def _repair_broken_fences(text: str) -> str:
    """Fix common model fence mistakes like ``lang\\n… → ```lang."""
    if not text:
        return text
    # ``python or ``markdown (double backtick) → proper triple fence
    text = re.sub(
        r"(?<!`)``([a-zA-Z0-9_+-]*)\\n",
        lambda m: f"```{m.group(1)}\n",
        text,
    )
    text = re.sub(
        r"(?<!`)``([a-zA-Z0-9_+-]*)\n",
        lambda m: f"```{m.group(1)}\n",
        text,
    )
    return text


def _format_pipe_heavy_lines(text: str) -> str:
    """Turn dense pipe-separated rows into readable stacked blocks."""
    out: list[str] = []
    for line in text.split("\n"):
        raw = line.rstrip()
        # Need at least 2 pipes → 3+ cells (id | sev | …)
        if raw.count("|") < 2:
            out.append(line)
            continue
        cells = [c.strip() for c in raw.strip("|").split("|")]
        cells = [c for c in cells if c]
        if len(cells) < 3:
            out.append(line)
            continue
        # markdown separator row
        if all(re.fullmatch(r":?-{3,}:?", c or "") for c in cells):
            continue
        # Header-looking wide rows (File | Why | Template…) - print as section title only once
        title = cells[0]
        meta = cells[1] if len(cells) > 1 else ""
        out.append("")
        if meta:
            out.append(f"{title}  ·  {meta}")
        else:
            out.append(title)
        for cell in cells[2:]:
            cell = cell.replace("<br>", "\n  ").replace("<br/>", "\n  ").replace("<br />", "\n  ")
            if len(cell) > 96:
                # Prefer break on sentence/clause boundaries
                chunk = cell
                while chunk:
                    cut = 96
                    if len(chunk) > cut:
                        sp = chunk.rfind(" ", 60, cut)
                        if sp > 40:
                            cut = sp
                    out.append(f"  {chunk[:cut].strip()}")
                    chunk = chunk[cut:].strip()
            else:
                out.append(f"  {cell}")
    return "\n".join(out)


def clean_ai_response(text: str) -> str:
    """Clean AI response for terminal display / file writes."""
    if not text:
        return text

    text = _unescape_literal_newlines(text)
    text = _repair_broken_fences(text)
    # Only strip an outer document wrapper - never eat inner code fences
    text = strip_markdown_fences(text)

    lines = text.split("\n")
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()

        # Skip lines that are mostly box-drawing borders (not markdown tables)
        if stripped:
            border_chars = sum(1 for c in stripped if c in "│┌┐└┘├┤┬┴┼─━═║╔╗╚╝╠╣╦╩╬+")
            # Don't treat pipe tables as borders
            if "|" in stripped and stripped.count("|") >= 2:
                cleaned_lines.append(line)
                continue
            if len(stripped) > 0 and border_chars / len(stripped) > 0.7:
                continue

        line = re.sub(r"^[│]\s*", "", line)
        line = re.sub(r"\s*[│]$", "", line)
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Keep bold markers for the formatter; strip only for plain fallback later
    text = _format_pipe_heavy_lines(text)
    return text.strip()

def format_ai_response_for_terminal(text: str) -> str:
    """Format AI response for clean, professional terminal output.
    
    Converts markdown to terminal-friendly format:
    - Preserves code blocks with Rich syntax highlighting
    - Converts headers to bold text
    - Converts ** and ** to highlighted text  
    - Converts - and + at line start to bullet points
    - Removes excessive formatting
    """
    if not text:
        return text
    
    import re
    
    lines = text.split('\n')
    formatted_lines = []
    in_code_block = False
    code_block_lang = None
    code_block_lines = []
    
    for line in lines:
        # Detect code blocks (both ``` and ````)
        if re.match(r'^````?([a-zA-Z]*)', line):
            if in_code_block:
                # End of code block - render with Rich syntax highlighting
                if code_block_lines and runtime.RICH_AVAILABLE:
                    try:
                        from rich.syntax import Syntax
                        from rich.console import Console
                        
                        code_content = '\n'.join(code_block_lines)
                        # Detect language or use bash as default for commands
                        if not code_block_lang:
                            # Try to detect if it's a bash command
                            lang = 'bash' if any(line.strip() and not line.strip().startswith('#') for line in code_block_lines) else 'text'
                        else:
                            lang = code_block_lang
                        
                        # Create a temporary runtime.console to capture the syntax highlighted output
                        import io
                        import sys
                        
                        # Use a buffer with ANSI support
                        buffer = io.StringIO()
                        temp_console = Console(
                            file=buffer,
                            force_terminal=True,
                            width=120,
                            legacy_windows=False,
                            color_system='truecolor'
                        )
                        
                        syntax = Syntax(
                            code_content,
                            lang,
                            theme="monokai",
                            line_numbers=False,
                            word_wrap=False,
                            background_color="default"
                        )
                        temp_console.print(syntax)
                        
                        # Get the rendered output
                        rendered = buffer.getvalue()
                        if rendered.strip():
                            formatted_lines.append(rendered.rstrip())
                        else:
                            # If rendering failed, fall back
                            raise Exception("Empty render")
                    except Exception as e:
                        # Fallback to simple colored output if Rich fails
                        formatted_lines.append(f"\033[90m--- Code ({code_block_lang or 'text'}) ---\033[0m")
                        for code_line in code_block_lines:
                            formatted_lines.append(f"\033[36m{code_line}\033[0m")
                        formatted_lines.append(f"\033[90m--- End Code ---\033[0m")
                else:
                    # Fallback when Rich not available
                    formatted_lines.append(f"\033[90m--- Code ({code_block_lang or 'text'}) ---\033[0m")
                    for code_line in code_block_lines:
                        formatted_lines.append(f"\033[36m{code_line}\033[0m")
                    formatted_lines.append(f"\033[90m--- End Code ---\033[0m")
                
                code_block_lines = []
                in_code_block = False
                code_block_lang = None
            else:
                # Start of code block
                match = re.match(r'^````?([a-zA-Z]*)', line)
                code_block_lang = match.group(1) if match else None
                in_code_block = True
            continue
        
        # If inside code block, preserve line exactly
        if in_code_block:
            code_block_lines.append(line)
            continue
        
        # Skip separator lines
        stripped = line.strip()
        if len(stripped) >= 3:
            separator_chars = sum(1 for c in stripped if c in '=-_*+#~^')
            if separator_chars / len(stripped) > 0.8:
                continue
        
        # Convert headers (###, ##, #) to bold highlighted text
        # First clean any ** markers in the header
        header_match = re.match(r'^(#{1,6})\s+(.*)', line)
        if header_match:
            header_level = len(header_match.group(1))
            header_text = header_match.group(2)
            # Remove ** markers from headers
            header_text = re.sub(r'\*\*(.+?)\*\*', r'\1', header_text)
            # Bold yellow for headers
            formatted_lines.append(f"\033[1;33m{header_text}\033[0m")
            continue
        
        # Convert list items (- or +) at start of line to bullet points
        if re.match(r'^\s*[-+]\s+', line):
            content = re.sub(r'^\s*[-+]\s+', '', line)
            # Also remove ** from list items
            content = re.sub(r'\*\*(.+?)\*\*', r'\033[1;32m\1\033[0m', content)
            formatted_lines.append(f"  • {content}")
            continue
        
        # Handle ** bold ** formatting - highlight these words AND remove markers
        # Use a more aggressive pattern to catch all **text** instances
        while '**' in line:
            # Replace **text** with highlighted text (no ** markers shown)
            line = re.sub(r'\*\*([^*]+?)\*\*', r'\033[1;32m\1\033[0m', line, count=1)
            # Break if no more ** pairs found
            if line.count('**') < 2:
                # Remove any remaining single ** markers
                line = line.replace('**', '')
                break
        
        # Handle inline code with backticks - show with different color
        if '`' in line:
            line = re.sub(r'`([^`]+)`', r'\033[33m\1\033[0m', line)
        
        # Remove markdown links but keep the text
        line = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', line)
        
        formatted_lines.append(line)
    
    # Handle unclosed code block
    if in_code_block and code_block_lines:
        if runtime.RICH_AVAILABLE:
            try:
                from rich.syntax import Syntax
                from rich.console import Console
                import io
                
                code_content = '\n'.join(code_block_lines)
                # Detect language or use bash as default for commands
                if not code_block_lang:
                    lang = 'bash' if any(line.strip() and not line.strip().startswith('#') for line in code_block_lines) else 'text'
                else:
                    lang = code_block_lang
                
                buffer = io.StringIO()
                temp_console = Console(
                    file=buffer,
                    force_terminal=True,
                    width=120,
                    legacy_windows=False,
                    color_system='truecolor'
                )
                
                syntax = Syntax(
                    code_content,
                    lang,
                    theme="monokai",
                    line_numbers=False,
                    word_wrap=False,
                    background_color="default"
                )
                temp_console.print(syntax)
                
                rendered = buffer.getvalue()
                if rendered.strip():
                    formatted_lines.append(rendered.rstrip())
                else:
                    raise Exception("Empty render")
            except Exception:
                formatted_lines.append(f"\033[90m--- Code ({code_block_lang or 'text'}) ---\033[0m")
                for code_line in code_block_lines:
                    formatted_lines.append(f"\033[36m{code_line}\033[0m")
                formatted_lines.append(f"\033[90m--- End Code ---\033[0m")
        else:
            formatted_lines.append(f"\033[90m--- Code ({code_block_lang or 'text'}) ---\033[0m")
            for code_line in code_block_lines:
                formatted_lines.append(f"\033[36m{code_line}\033[0m")
            formatted_lines.append(f"\033[90m--- End Code ---\033[0m")
    
    result = '\n'.join(formatted_lines)
    
    # Clean up excessive newlines
    result = re.sub(r'\n{3,}', '\n\n', result)
    
    return result.strip()

