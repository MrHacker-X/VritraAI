#!/usr/bin/env python3
"""VritraAI - AI coding assistant for the terminal."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# Ensure project root is importable when launched as a script
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.agent import run_agent
from core.agent.approval import TRUST_MODE_LABELS
from core.commands.doc import doc_command
from core.commands.explain import explain_command
from core.commands.learn import cheat_command, learn_command
from core.commands.models import models_command
from core.commands.optimize import optimize_code_command
from core.commands.project import project_command
from core.commands.refactor import refactor_command
from core.commands.review import review_command
from core.commands.security import security_scan_command
from core.commands.setup import setup_command
from core.commands.summarize import summarize_command
from core.config_store import apply_config_to_runtime
from core.interrupt import Cancelled, clear_cancel, install_sigint_handler, operation
from core.tui import SLASH_ALIASES, SLASH_COMMANDS
from core import runtime

# Session approval mode set at launch (ask | auto | safe)
SESSION_APPROVAL = "ask"

VERSION = "1.0.2-cli"
PRODUCT = "VritraAI"
TAGLINE = "AI Interactive Assistant"

# Brand palette (original UI) - only the prompt line uses a quieter style
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"

    WHITE = "\033[97m"
    GRAY = "\033[90m"
    MUTED = "\033[38;5;245m"

    TEAL = "\033[38;5;44m"
    TEAL_BRIGHT = "\033[38;5;51m"
    TEAL_DEEP = "\033[38;5;30m"
    CYAN = "\033[38;5;81m"
    AMBER = "\033[38;5;214m"
    GOLD = "\033[38;5;178m"
    GREEN = "\033[38;5;114m"
    RED = "\033[38;5;203m"
    BLUE = "\033[38;5;75m"

    LOGO_ROW = (
        "\033[38;5;39m",
        "\033[38;5;45m",
        "\033[38;5;51m",
        "\033[38;5;87m",
        "\033[38;5;123m",
        "\033[38;5;159m",
        "\033[38;5;195m",
    )
    LOGO_EDGE = "\033[38;5;31m"
    LOGO_GLOW = "\033[38;5;24m"

    # Prompt-only (vritraai ›) - steel mist blue
    PROMPT = "\033[38;5;110m"
    PROMPT_MARK = "\033[38;5;67m"


# Clean block mark - reads VRITRAAI (not VRITRA alone)
LOGO_LINES = [
    r"▄▄    ▄▄  ▄▄▄▄▄▄     ▄▄▄▄▄▄   ▄▄▄▄▄▄▄▄  ▄▄▄▄▄▄       ▄▄        ▄▄    ▄▄▄▄▄▄  ",
    r"▀██  ██▀  ██▀▀▀▀██   ▀▀██▀▀   ▀▀▀██▀▀▀  ██▀▀▀▀██    ████      ████    ▀▀██▀▀  ",
    r" ██  ██   ██    ██     ██        ██     ██    ██    ████      ████      ██    ",
    r" ██  ██   ███████      ██        ██     ███████    ██  ██    ██  ██     ██    ",
    r"  ████    ██  ▀██▄     ██        ██     ██  ▀██▄   ██████    ██████     ██    ",
    r"  ████    ██    ██   ▄▄██▄▄      ██     ██    ██  ▄██  ██▄  ▄██  ██▄  ▄▄██▄▄  ",
    r"  ▀▀▀▀    ▀▀    ▀▀▀  ▀▀▀▀▀▀      ▀▀     ▀▀    ▀▀▀ ▀▀    ▀▀  ▀▀    ▀▀  ▀▀▀▀▀▀  ",
]

SUBMARK = "A I   A S S I S T A N T"


def supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


USE_COLOR = supports_color()


def c(text: str, *codes: str) -> str:
    if not USE_COLOR or not codes:
        return text
    return f"{''.join(codes)}{text}{C.RESET}"


def clear_screen() -> None:
    if sys.stdout.isatty():
        os.system("cls" if os.name == "nt" else "clear")


def short_path(path: str | None = None) -> str:
    p = Path(path or os.getcwd()).resolve()
    home = Path.home().resolve()
    try:
        return "~/" + str(p.relative_to(home)).replace("\\", "/")
    except ValueError:
        return str(p)


def term_width() -> int:
    return max(60, shutil.get_terminal_size((88, 24)).columns)


def box(lines: list[str], width: int | None = None) -> list[str]:
    """Rounded Codex-style box. `lines` are already color-wrapped content."""
    # Visible length helper (strip ANSI)
    import re

    ansi = re.compile(r"\033\[[0-9;]*m")

    def vis(s: str) -> int:
        return len(ansi.sub("", s))

    inner = width or max((vis(x) for x in lines), default=40)
    inner = max(inner, 48)
    out = [c("╭" + "─" * (inner + 2) + "╮", C.MUTED)]
    for line in lines:
        pad = inner - vis(line)
        out.append(c("│ ", C.MUTED) + line + (" " * max(0, pad)) + c(" │", C.MUTED))
    out.append(c("╰" + "─" * (inner + 2) + "╯", C.MUTED))
    return out


def _paint_logo_line(line: str, row: int) -> str:
    """Paint one logo row: edge glyphs darker, fill glyphs cyan-gradient."""
    if not USE_COLOR:
        return line

    n = max(len(line), 1)
    row_bias = min(row, len(C.LOGO_ROW) - 1)
    out: list[str] = []
    for i, ch in enumerate(line):
        if ch == " ":
            out.append(ch)
            continue
        idx = min(row_bias + int(i / n * (len(C.LOGO_ROW) - row_bias)), len(C.LOGO_ROW) - 1)
        mix = C.LOGO_ROW[idx]
        if ch in "▄▀":
            out.append(f"{C.LOGO_EDGE}{ch}{C.RESET}")
        else:
            out.append(f"{mix}{C.BOLD}{ch}{C.RESET}")
    return "".join(out)


def render_logo() -> None:
    logo_width = max(len(line) for line in LOGO_LINES)

    print()
    if USE_COLOR:
        for line in LOGO_LINES:
            glow = "".join(ch if ch == " " else "░" for ch in line)
            print(f"{C.LOGO_GLOW}{glow}{C.RESET}")
        sys.stdout.write(f"\033[{len(LOGO_LINES)}A")

    for i, line in enumerate(LOGO_LINES):
        print(_paint_logo_line(line, i))

    print(c(SUBMARK, C.AMBER, C.BOLD))

    rule = "─" * logo_width
    print(c(rule, C.TEAL_DEEP))
    print()


def show_ui() -> None:
    clear_screen()
    cwd = short_path()

    render_logo()

    model_label = runtime.MODEL or "not set"
    info_lines = [
        c(f">_ {PRODUCT}", C.WHITE, C.BOLD)
        + c(f" ({VERSION})", C.CYAN),
        c("model: ", C.MUTED)
        + c(f"{runtime.API_BASE} / {model_label}", C.TEAL_BRIGHT)
        + c("  /model to change", C.GRAY),
        c("directory: ", C.MUTED) + c(cwd, C.GREEN),
    ]
    if not runtime.AI_ENABLED:
        info_lines.append(
            c("status: ", C.MUTED)
            + c("no API key  ", C.AMBER)
            + c("/setup to configure", C.GRAY)
        )
    for row in box(info_lines, width=62):
        print(row)

    print()
    print(
        c("Tip: ", C.MUTED)
        + f"Type {c('/', C.AMBER, C.BOLD)} for commands · plain text runs the coding agent"
    )
    print(
        c("• ", C.MUTED)
        + f"{c('/setup', C.AMBER)} keys · {c('/model', C.AMBER)} model · {c('/help', C.AMBER)} list · {c('/exit', C.AMBER)} quit"
    )
    print()


def print_reply(message: str) -> None:
    rows = box(
        [
            c("VritraAI", C.TEAL_BRIGHT, C.BOLD),
            "",
            c(message, C.WHITE),
            c("Core assistant features are under construction.", C.MUTED),
        ],
        width=54,
    )
    print()
    for row in rows:
        print(row)
    print()


def status_bar() -> None:
    left = c(f"{PRODUCT} {VERSION}", C.GOLD)
    mid = c("·", C.MUTED)
    right = c(short_path(), C.GREEN)
    print(f"{left}  {mid}  {right}")


def _build_prompt_session():
    """Codex-style prompt: slash menu, ↑/↓ select, Enter runs, backspace keeps menu."""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.formatted_text import HTML
        from prompt_toolkit.history import InMemoryHistory
        from prompt_toolkit.styles import Style as PTStyle

        from core.tui import make_slash_completer, make_slash_key_bindings

        style = PTStyle.from_dict(
            {
                # Prompt only - steel mist blue
                "prompt": "#8ba3c7 bold",
                "mark": "#5c718a",
                # Slash menu: no separate gray panel - blend with terminal
                "completion-menu": "bg:default",
                "completion-menu.completion": "bg:default #94a3b8",
                "completion-menu.completion.current": "bg:default #e2e8f0 bold",
                "completion-menu.meta.completion": "bg:default #475569",
                "completion-menu.meta.completion.current": "bg:default #94a3b8",
                "scrollbar.background": "bg:default",
                "scrollbar.button": "bg:default",
            }
        )
        return PromptSession(
            message=HTML("<prompt>vritraai</prompt> <mark>›</mark> "),
            completer=make_slash_completer(),
            complete_while_typing=True,
            complete_in_thread=False,
            key_bindings=make_slash_key_bindings(),
            history=InMemoryHistory(),
            style=style,
            reserve_space_for_menu=8,
        )
    except Exception:
        return None


_PROMPT_SESSION = None


def prompt_line() -> str:
    global _PROMPT_SESSION
    if _PROMPT_SESSION is None:
        _PROMPT_SESSION = _build_prompt_session()
    if _PROMPT_SESSION is not None:
        return _PROMPT_SESSION.prompt()
    label = c("vritraai", C.PROMPT, C.BOLD)
    mark = c("›", C.PROMPT_MARK)
    return input(f"{label} {mark} ")


def show_help() -> None:
    """/help - command in accent, description in grey."""
    print()
    print(c("Slash commands", C.WHITE, C.BOLD))
    print()
    for cmd, desc in SLASH_COMMANDS:
        print(f"  {c(f'{cmd:<12}', C.AMBER)}  {c(desc, C.GRAY)}")
    print()
    print(c("Type a task in plain language to run the coding agent.", C.MUTED))
    print()


def dispatch(user_input: str) -> None:
    """Route /commands; plain text starts the coding agent."""
    text = user_input.strip()
    if not text:
        return

    # Natural language → autonomous coding agent (iterative tool loop)
    if not text.startswith("/"):
        mode = (
            os.environ.get("VRITRA_APPROVAL", "").strip().lower()
            or SESSION_APPROVAL
            or "ask"
        )
        try:
            max_iter = int(os.environ.get("VRITRA_AGENT_MAX_ITER", "32"))
        except ValueError:
            max_iter = 32
        run_agent(text, approval_mode=mode, max_iterations=max_iter)
        return

    parts = text.split()
    cmd = parts[0].lower()
    args = parts[1:]  # keep original case for paths / topics
    cmd = SLASH_ALIASES.get(cmd, cmd)

    if cmd == "/setup":
        setup_command(args)
        return
    if cmd == "/clear":
        clear_screen()
        return
    if cmd == "/model":
        models_command(args)
        return
    if cmd == "/explain":
        explain_command(args)
        return
    if cmd == "/summarize":
        summarize_command(args)
        return
    if cmd == "/review":
        review_command(args)
        return
    if cmd == "/security":
        security_scan_command(args)
        return
    if cmd == "/optimize":
        optimize_code_command(args)
        return
    if cmd == "/refactor":
        refactor_command(args)
        return
    if cmd == "/learn":
        learn_command(args)
        return
    if cmd == "/cheatsheet":
        cheat_command(args)
        return
    if cmd == "/doc":
        doc_command(args)
        return
    if cmd == "/project":
        project_command(args)
        return
    if cmd == "/help":
        show_help()
        return

    print_reply(f"Unknown command: {cmd}\nType /help for the list.")


def cli_invocation(argv: list[str] | None = None) -> str:
    """How this process was launched, for usage lines (never a hardcoded script name)."""
    argv = argv if argv is not None else sys.argv
    raw = (argv[0] if argv else "") or Path(__file__).name
    name = Path(raw).name or raw
    if name.endswith(".py"):
        py = Path(sys.executable).name or "python3"
        return f"{py} {name}"
    return name


def _launch_error(
    *,
    title: str,
    detail: str,
    hint: str = "",
    usage: str = "",
) -> None:
    """Professional launch failure card (missing/invalid workspace, bad args)."""
    muted = C.MUTED
    white = f"{C.BOLD}{C.WHITE}"
    amber = C.AMBER
    reset = C.RESET
    width = 56
    print()
    print(f"{muted}╭{'─' * (width + 2)}╮{reset}")
    print(f"{muted}│{reset} {amber}{title}{' ' * max(0, width - len(title))}{reset} {muted}│{reset}")
    if detail:
        for i in range(0, len(detail), width):
            chunk = detail[i : i + width]
            print(f"{muted}│{reset} {white}{chunk}{' ' * max(0, width - len(chunk))}{reset} {muted}│{reset}")
    if hint:
        print(f"{muted}│{' ' * (width + 2)}│{reset}")
        for i in range(0, len(hint), width):
            chunk = hint[i : i + width]
            print(f"{muted}│{reset} {muted}{chunk}{' ' * max(0, width - len(chunk))}{reset} {muted}│{reset}")
    if usage:
        print(f"{muted}│{' ' * (width + 2)}│{reset}")
        u = f"Usage: {usage}"
        for i in range(0, len(u), width):
            chunk = u[i : i + width]
            print(f"{muted}│{reset} {muted}{chunk}{' ' * max(0, width - len(chunk))}{reset} {muted}│{reset}")
    print(f"{muted}╰{'─' * (width + 2)}╯{reset}")
    print()


def print_version() -> None:
    print(f"{PRODUCT} {VERSION}")


def print_help(argv: list[str] | None = None) -> None:
    inv = cli_invocation(argv)
    print(
        f"""{PRODUCT} {VERSION} - terminal-native AI coding agent

Usage:
  {inv} [directory]
  {inv} -h | --help
  {inv} -v | --version

Arguments:
  directory          Project folder to open (default: current directory)

Options:
  -h, --help         Show this help and exit
  -v, --version      Show version and exit

Inside the REPL:
  plain text         Run the coding agent on a task
  /setup             Configure API keys
  /model             Choose the active model
  /help              List slash commands
  /exit              Quit

Docs: https://vritraai.vritrasec.com/
"""
    )


def parse_launch_argv(argv: list[str]) -> tuple[str, Path | None]:
    """
    Returns (action, workspace).
      action = "run" | "help" | "version" | "error"
      workspace is set only for action == "run"
    """
    usage = f"{cli_invocation(argv)} [directory]"
    args = argv[1:]

    if not args:
        return "run", Path.cwd().resolve()

    # Flag-only forms (also allow flag before/after directory is not needed for v1)
    if len(args) == 1 and args[0] in {"-h", "--help", "help"}:
        return "help", None
    if len(args) == 1 and args[0] in {"-v", "--version", "version"}:
        return "version", None

    # Unknown lone option
    if len(args) == 1 and args[0].startswith("-"):
        _launch_error(
            title="Unknown option",
            detail=args[0],
            hint="Try --help, --version, or pass a workspace directory.",
            usage=usage,
        )
        return "error", None

    if len(args) > 1:
        # Allow: vritraai --help  /  vritraai -v  already handled
        # Reject mixed junk like: vritraai foo bar
        if any(a.startswith("-") for a in args):
            bad = next(a for a in args if a.startswith("-"))
            _launch_error(
                title="Unknown option",
                detail=bad,
                hint="Options cannot be mixed with a directory. Use --help or --version alone.",
                usage=usage,
            )
            return "error", None
        _launch_error(
            title="Too many arguments",
            detail="Expected at most one workspace directory.",
            hint="Pass a single project folder, or omit it to use the current directory.",
            usage=usage,
        )
        return "error", None

    raw = args[0]
    target = Path(raw).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    try:
        target = target.resolve()
    except Exception:
        _launch_error(
            title="Invalid path",
            detail=raw,
            hint="Check spelling, permissions, and that the path is readable.",
            usage=usage,
        )
        return "error", None

    if not target.exists():
        _launch_error(
            title="Workspace not found",
            detail=str(target),
            hint="Create the directory first, or pass an existing project path.",
            usage=usage,
        )
        return "error", None
    if not target.is_dir():
        _launch_error(
            title="Not a directory",
            detail=str(target),
            hint="The workspace argument must be a folder, not a file.",
            usage=usage,
        )
        return "error", None
    return "run", target


def main() -> int:
    global SESSION_APPROVAL

    action, workspace = parse_launch_argv(sys.argv)
    if action == "help":
        print_help(sys.argv)
        return 0
    if action == "version":
        print_version()
        return 0
    if action == "error" or workspace is None:
        return 1

    # Bind agent workspace to launch directory
    try:
        os.chdir(workspace)
    except Exception as e:
        print(c(f"Cannot enter workspace: {e}", C.AMBER))
        return 1

    apply_config_to_runtime()

    # Trust: env override → per-directory cache → prompt (Codex-style)
    env_mode = os.environ.get("VRITRA_APPROVAL", "").strip().lower()
    if os.environ.get("VRITRA_RESET_TRUST", "").strip().lower() in {"1", "true", "yes"}:
        from core.agent.approval import clear_workspace_trust

        clear_workspace_trust(workspace)

    cached = None
    if env_mode not in {"ask", "auto", "safe"}:
        from core.agent.approval import get_workspace_trust

        cached = get_workspace_trust(workspace)

    if env_mode in {"ask", "auto", "safe"}:
        SESSION_APPROVAL = env_mode
        trust_source = "env"
    elif cached:
        SESSION_APPROVAL = cached
        trust_source = "cache"
    else:
        clear_screen()
        try:
            from core.agent.approval import prompt_session_trust, set_workspace_trust

            mode = prompt_session_trust()
            trust_source = "prompt"
        except KeyboardInterrupt:
            print()
            print(c("Launch cancelled.", C.MUTED))
            return 130
        if mode is None:
            print()
            print(c("Launch cancelled.", C.MUTED))
            return 130
        set_workspace_trust(workspace, mode)
        SESSION_APPROVAL = mode

    install_sigint_handler()
    show_ui()  # clears again, then logo + main window
    mode_label = TRUST_MODE_LABELS.get(SESSION_APPROVAL, SESSION_APPROVAL)
    trust_note = {
        "env": "env",
        "cache": "saved for this folder",
        "prompt": "saved for this folder",
    }.get(trust_source, trust_source)
    print(c(f"Permissions: {mode_label}  ·  {trust_note}", C.MUTED))
    print(c(f"Workspace:   {short_path(str(workspace))}", C.MUTED))
    status_bar()
    print()

    while True:
        clear_cancel()
        try:
            user_input = prompt_line().strip()
        except KeyboardInterrupt:
            # Idle prompt: cancel only - never quit VritraAI
            print()
            print(c("Cancelled. Type /exit to quit.", C.MUTED))
            continue
        except EOFError:
            print()
            print(c("Bye.", C.MUTED))
            return 0

        if not user_input:
            continue

        lowered = user_input.lower()
        if lowered in {"exit", "quit", "q", "/exit", "/quit"}:
            print(c("Bye.", C.MUTED))
            return 0

        try:
            with operation("dispatch"):
                dispatch(user_input)
        except (KeyboardInterrupt, Cancelled):
            print()
            print(c("Cancelled. Back to prompt.", C.MUTED))
            continue


if __name__ == "__main__":
    sys.exit(main())
