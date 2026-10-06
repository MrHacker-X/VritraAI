"""Codex / Gemini CLI–style terminal UI helpers."""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple


@dataclass
class Choice:
    value: str
    label: str
    description: str = ""


# CSI / simple ESC sequences (arrows, etc.) that must never enter secrets
_ANSI_ESCAPE_RE = re.compile(
    r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|O[A-Za-z]|].*?(?:\x07|\x1b\\)|.)"
)


def sanitize_secret(value: str) -> str:
    """Strip ANSI/control junk (e.g. arrow keys) from pasted/typed secrets."""
    if not value:
        return ""
    cleaned = _ANSI_ESCAPE_RE.sub("", value)
    cleaned = "".join(ch for ch in cleaned if ord(ch) >= 32 and ch != "\x7f")
    return cleaned.strip()


def read_secret_masked(prompt: str = "  › ") -> str:
    """
    Read a secret from stdin, echoing '*' per character so typing/paste is visible.
    Supports Backspace and Ctrl+U (clear). Ignores arrow-key escape sequences.
    Falls back to getpass/input off-TTY.
    """
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        try:
            import getpass

            return sanitize_secret(getpass.getpass(prompt))
        except Exception:
            return sanitize_secret(input(prompt))

    try:
        import termios
        import tty
    except ImportError:
        import getpass

        return sanitize_secret(getpass.getpass(prompt))

    sys.stdout.write(prompt)
    sys.stdout.flush()
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    buf: List[str] = []
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if not ch:
                break
            if ch in ("\r", "\n"):
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                break
            if ch == "\x03":  # Ctrl+C
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                raise KeyboardInterrupt
            if ch == "\x04":  # Ctrl+D
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                raise EOFError
            if ch in ("\x7f", "\b"):  # Backspace
                if buf:
                    buf.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue
            if ch == "\x15":  # Ctrl+U clear
                while buf:
                    buf.pop()
                    sys.stdout.write("\b \b")
                sys.stdout.flush()
                continue
            # Swallow ANSI escapes (arrows / focus events) - never store them
            if ch == "\x1b":
                nxt = sys.stdin.read(1)
                if not nxt:
                    continue
                if nxt == "[":  # CSI: ESC [ ... final
                    while True:
                        c2 = sys.stdin.read(1)
                        if not c2 or 0x40 <= ord(c2) <= 0x7E:
                            break
                elif nxt == "O":  # SS3: ESC O A/B/C/D
                    sys.stdin.read(1)
                # else: lone ESC + one char - ignore both
                continue
            # Ignore other control chars
            if ord(ch) < 32:
                continue
            buf.append(ch)
            sys.stdout.write("*")
            sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return sanitize_secret("".join(buf))


def _vis_len(text: str) -> int:
    return len(re.sub(r"\033\[[0-9;]*m", "", text))


def panel(title: str, body_lines: Sequence[str], width: int = 48) -> None:
    """Compact rounded panel. Width grows only with content, capped."""
    cap = 56
    inner = min(cap, max(width, _vis_len(title) + 2))
    for line in body_lines:
        inner = min(cap, max(inner, _vis_len(line) + 2))

    print(f"\033[90m╭{'─' * (inner + 2)}╮\033[0m")
    print(f"\033[90m│\033[0m \033[1;97m{title}{' ' * (inner - _vis_len(title))}\033[0m \033[90m│\033[0m")
    if body_lines:
        print(f"\033[90m│{' ' * (inner + 2)}│\033[0m")
    for line in body_lines:
        # Truncate overflow instead of widening endlessly
        visible = _vis_len(line)
        if visible > inner:
            # strip ANSI for truncate - keep plain
            plain = re.sub(r"\033\[[0-9;]*m", "", line)
            line = plain[: max(0, inner - 1)] + "…"
            visible = _vis_len(line)
        pad = inner - visible
        print(f"\033[90m│\033[0m {line}{' ' * pad} \033[90m│\033[0m")
    print(f"\033[90m╰{'─' * (inner + 2)}╯\033[0m")


def arrow_select(
    title: str,
    choices: List[Choice],
    *,
    subtitle: str = "",
    initial: int = 0,
    footer: str = "↑/↓ · Enter · q cancel",
) -> Optional[str]:
    """↑/↓ highlighter. Returns choice.value or None if cancelled."""
    if not choices:
        return None

    def _fmt(ch: Choice, i: int, selected: bool) -> str:
        prefix = "● " if selected else "  "
        # Model/label bright; meta (provider) distinct cyan - avoid grey-on-grey
        label_c = "\033[1;97m" if selected else "\033[97m"
        line = f"{prefix}{i + 1}. {label_c}{ch.label}\033[0m"
        if ch.description:
            desc = ch.description
            if len(desc) > 28:
                desc = desc[:27] + "…"
            line += f"  \033[36m{desc}\033[0m"
        return line

    # Non-TTY / no prompt_toolkit fallback
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(f"\n{title}")
        if subtitle:
            print(f"\033[90m{subtitle}\033[0m")
        for i, ch in enumerate(choices):
            print(_fmt(ch, i, False))
        if footer:
            print(f"\033[90m{footer}\033[0m")
        try:
            raw = input("Select › ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1].value
        return None

    try:
        from prompt_toolkit.application import Application
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.layout import Layout
        from prompt_toolkit.layout.containers import HSplit, Window
        from prompt_toolkit.layout.controls import FormattedTextControl
        from prompt_toolkit.styles import Style
    except ImportError:
        print(f"\n{title}")
        for i, ch in enumerate(choices):
            print(_fmt(ch, i, False))
        if footer:
            print(f"\033[90m{footer}\033[0m")
        try:
            raw = input("Select › ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1].value
        return None

    state = {"idx": max(0, min(initial, len(choices) - 1)), "result": None}

    def get_text():
        fragments = []
        fragments.append(("class:title", f"{title}\n"))
        if subtitle:
            fragments.append(("class:subtitle", f"{subtitle}\n"))
        fragments.append(("", "\n"))
        for i, ch in enumerate(choices):
            selected = i == state["idx"]
            prefix = "● " if selected else "  "
            label_style = "class:selected" if selected else "class:item"
            fragments.append((label_style, f"{prefix}{i + 1}. {ch.label}"))
            if ch.description:
                desc = ch.description if len(ch.description) <= 28 else ch.description[:27] + "…"
                fragments.append(("class:meta", f"  {desc}"))
            fragments.append(("", "\n"))
        fragments.append(("", "\n"))
        if footer:
            fragments.append(("class:footer", f"{footer}\n"))
        return fragments

    kb = KeyBindings()

    @kb.add("up")
    @kb.add("k")
    def _up(event):  # noqa: ANN001
        state["idx"] = (state["idx"] - 1) % len(choices)

    @kb.add("down")
    @kb.add("j")
    def _down(event):  # noqa: ANN001
        state["idx"] = (state["idx"] + 1) % len(choices)

    @kb.add("enter")
    def _enter(event):  # noqa: ANN001
        state["result"] = choices[state["idx"]].value
        event.app.exit()

    @kb.add("q")
    @kb.add("c-c")
    @kb.add("escape")
    def _cancel(event):  # noqa: ANN001
        state["result"] = None
        event.app.exit()

    for n in range(1, min(10, len(choices) + 1)):
        @kb.add(str(n))
        def _num(event, n=n):  # noqa: ANN001
            state["idx"] = n - 1

    style = Style.from_dict(
        {
            "title": "bold #ffffff",
            "subtitle": "#888888",
            # Model name: bright; provider/meta: cyan (not the same grey)
            "selected": "bold #a3e635",
            "item": "#f0f0f0",
            "meta": "#38bdf8",
            "footer": "#666666",
        }
    )

    control = FormattedTextControl(get_text, focusable=True, show_cursor=False)
    app = Application(
        layout=Layout(HSplit([Window(control)])),
        key_bindings=kb,
        style=style,
        full_screen=False,
        mouse_support=False,
    )
    print()
    app.run()
    print()
    return state["result"]


# Shown in the slash suggestion menu (professional names only)
SLASH_COMMANDS: List[Tuple[str, str]] = [
    ("/cheatsheet", "quick reference for a topic"),
    ("/clear", "clear the screen"),
    ("/doc", "generate documentation"),
    ("/explain", "explain a command or concept"),
    ("/help", "show available commands"),
    ("/learn", "learn a topic with examples"),
    ("/model", "choose what model to use"),
    ("/optimize", "optimize a source file"),
    ("/project", "analyze · type · deps · health · missing · optimize"),
    ("/refactor", "refactor or convert a file"),
    ("/review", "AI code review"),
    ("/security", "security vulnerability scan"),
    ("/setup", "configure API keys"),
    ("/summarize", "summarize a file or directory"),
    ("/exit", "quit VritraAI"),
]

# Subcommands suggested after "/cmd "
SLASH_SUBCOMMANDS: dict[str, List[Tuple[str, str]]] = {
    "/doc": [
        ("docstring", "suggest docstrings for a file"),
        ("readme", "generate README.md"),
        ("diagram", "code-to-diagram (mermaid/plantuml/text)"),
    ],
    "/project": [
        ("analyze", "AI project overview"),
        ("type", "detect project type & stack"),
        ("deps", "check dependency files"),
        ("health", "project health report"),
        ("missing", "suggest missing files"),
        ("optimize", "project-level optimizations"),
    ],
}

# Hidden aliases - still dispatch, not listed in the menu
SLASH_ALIASES = {
    "/models": "/model",
    "/cheat": "/cheatsheet",
}


def print_cmd_help(title: str, rows: Sequence[Tuple[str, str]]) -> None:
    """Usage help: command amber, description grey (matches /help)."""
    amber = "\033[38;5;214m"
    gray = "\033[90m"
    white = "\033[1;97m"
    reset = "\033[0m"
    print()
    print(f"{white}{title}{reset}")
    print()
    width = max((len(usage) for usage, _ in rows), default=12)
    width = min(max(width, 12), 36)
    for usage, desc in rows:
        print(f"  {amber}{usage:<{width}}{reset}  {gray}{desc}{reset}")
    print()


def make_slash_completer():
    """prompt_toolkit completer - top-level /cmds + subcommands after space."""
    from prompt_toolkit.completion import Completer, Completion

    class SlashCompleter(Completer):
        def get_completions(self, document, complete_event):  # noqa: ANN001
            before = document.text_before_cursor
            after = document.text_after_cursor
            full = document.text

            if not full.startswith("/"):
                return

            # Top-level: match against the FULL first token (not only text before cursor).
            # Otherwise "/ch|wfwef" wrongly suggests /cheatsheet from prefix "/ch".
            if " " not in full:
                needle = full.lower()
                for cmd, desc in SLASH_COMMANDS:
                    if not cmd.startswith(needle):
                        continue
                    # Apply replaces `before`; keep `after` - insert so insert+after == cmd
                    insert = cmd[: len(cmd) - len(after)] if after else cmd
                    yield Completion(
                        insert,
                        start_position=-len(before),
                        display=cmd,
                        display_meta=desc,
                    )
                return

            # Subcommands: "/doc ", "/doc d", "/project an" - use full line
            parts = full.split()
            root = SLASH_ALIASES.get(parts[0].lower(), parts[0].lower())
            subs = SLASH_SUBCOMMANDS.get(root)
            if not subs:
                return

            # Only complete the first token after the command
            if len(parts) > 2 or (
                len(parts) == 2 and full.endswith(" ") and parts[1] in {s for s, _ in subs}
            ):
                return

            if full.endswith(" ") and len(parts) == 1:
                prefix = ""
                # Cursor may be after the space; replace nothing before cursor for the sub token
                start = 0
                after_sub = ""
            elif len(parts) >= 2:
                sub_token = parts[1]
                prefix = sub_token.lower()
                # How much of sub_token sits before the cursor?
                # full = "/doc foo|bar" → before ends mid-token
                cmd_prefix = parts[0] + " "
                if before.startswith(cmd_prefix):
                    before_sub = before[len(cmd_prefix) :]
                else:
                    before_sub = sub_token
                    # cursor before/inside command - skip awkward mid-edits
                    if " " not in before:
                        return
                after_sub = sub_token[len(before_sub) :] if sub_token.startswith(before_sub) else after
                start = -len(before_sub)
            else:
                return

            for sub, desc in subs:
                if not sub.startswith(prefix):
                    continue
                insert = sub[: len(sub) - len(after_sub)] if after_sub else sub
                yield Completion(
                    insert,
                    start_position=start,
                    display=sub,
                    display_meta=desc,
                )

    return SlashCompleter()


def make_slash_key_bindings():
    """
    Codex-like slash UX:
    - menu stays open / refreshes on backspace (without auto-selecting)
    - space after /doc|/project opens subcommand menu
    - ↑/↓ navigate · Enter applies + submits
    """
    from prompt_toolkit.key_binding import KeyBindings

    kb = KeyBindings()

    def _slash_completable(text: str) -> bool:
        if not text.startswith("/"):
            return False
        if " " not in text:
            return True
        parts = text.split()
        root = SLASH_ALIASES.get(parts[0].lower(), parts[0].lower())
        if root not in SLASH_SUBCOMMANDS:
            return False
        # still typing first subcommand token
        if len(parts) == 1 and text.endswith(" "):
            return True
        if len(parts) == 2 and not text.endswith(" "):
            return True
        return False

    def _refresh_if_slash(buf, *, select_first: bool = False) -> None:  # noqa: ANN001
        text = buf.text
        if _slash_completable(text):
            if buf.complete_state:
                buf.cancel_completion()
            buf.start_completion(select_first=select_first)
        elif buf.complete_state:
            buf.cancel_completion()

    @kb.add("/")
    def _slash(event):  # noqa: ANN001
        buf = event.app.current_buffer
        buf.insert_text("/")
        _refresh_if_slash(buf, select_first=True)

    @kb.add(" ")
    def _space(event):  # noqa: ANN001
        buf = event.app.current_buffer
        buf.insert_text(" ")
        _refresh_if_slash(buf, select_first=True)

    @kb.add("backspace")
    def _backspace(event):  # noqa: ANN001
        buf = event.app.current_buffer
        if buf.complete_state:
            buf.cancel_completion()
        if buf.selection_state:
            buf.cut_selection()
        elif buf.cursor_position > 0:
            buf.delete_before_cursor(count=1)
        _refresh_if_slash(buf, select_first=False)

    @kb.add("delete")
    def _delete(event):  # noqa: ANN001
        buf = event.app.current_buffer
        if buf.complete_state:
            buf.cancel_completion()
        buf.delete()
        _refresh_if_slash(buf, select_first=False)

    @kb.add("enter")
    def _enter(event):  # noqa: ANN001
        buf = event.app.current_buffer
        state = buf.complete_state
        if state and state.completions:
            completion = state.current_completion or state.completions[0]
            buf.apply_completion(completion)
            buf.cancel_completion()
            # After picking a parent with subcommands (e.g. /doc), offer subs
            text = buf.text.rstrip()
            root = SLASH_ALIASES.get(text.lower(), text.lower())
            if root in SLASH_SUBCOMMANDS and " " not in text:
                buf.insert_text(" ")
                _refresh_if_slash(buf, select_first=True)
                return
        buf.validate_and_handle()

    return kb
