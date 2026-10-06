"""Robust JSON extract/repair for tool-call arguments (no user-facing leakage)."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple


def strip_fences(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json|JSON)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def extract_json_object(text: str) -> Optional[str]:
    """Extract outermost JSON object or array substring."""
    text = strip_fences(text)
    if not text:
        return None
    # Prefer object
    start_obj = text.find("{")
    start_arr = text.find("[")
    if start_obj == -1 and start_arr == -1:
        return None
    if start_obj == -1:
        start = start_arr
        open_c, close_c = "[", "]"
    elif start_arr == -1 or start_obj < start_arr:
        start = start_obj
        open_c, close_c = "{", "}"
    else:
        start = start_arr
        open_c, close_c = "[", "]"

    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_c:
            depth += 1
        elif ch == close_c:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _light_repair(blob: str) -> str:
    # trailing commas before } or ]
    blob = re.sub(r",\s*([}\]])", r"\1", blob)
    # smart quotes
    blob = blob.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    return blob


def _escape_controls_in_strings(blob: str) -> str:
    """Turn raw newlines/tabs/controls inside JSON strings into escapes.

    Models often emit multi-line HTML/JS inside tool arguments without \\n.
    """
    out: List[str] = []
    in_str = False
    escape = False
    for ch in blob:
        if in_str:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == '"':
                out.append(ch)
                in_str = False
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                out.append("\\r")
                continue
            if ch == "\t":
                out.append("\\t")
                continue
            if ord(ch) < 0x20:
                out.append(f"\\u{ord(ch):04x}")
                continue
            out.append(ch)
        else:
            if ch == '"':
                in_str = True
            out.append(ch)
    return "".join(out)


def _decode_json_string_body(body: str) -> str:
    """Decode a JSON string body (content between quotes), leniently."""
    try:
        return json.loads(f'"{body}"')
    except Exception:
        # Fallback: unescape common sequences manually
        return (
            body.replace("\\n", "\n")
            .replace("\\r", "\r")
            .replace("\\t", "\t")
            .replace('\\"', '"')
            .replace("\\\\", "\\")
        )


def _scan_json_string(src: str, start: int) -> Tuple[Optional[str], int]:
    """
    Read a JSON string starting at src[start] (must be '\"').
    Tolerates unescaped quotes when the next structural token is , or }.
    Returns (decoded_value, index_after_closing_quote) or (None, start).
    """
    if start >= len(src) or src[start] != '"':
        return None, start
    i = start + 1
    buf: List[str] = []
    escape = False
    while i < len(src):
        ch = src[i]
        if escape:
            buf.append("\\")
            buf.append(ch)
            escape = False
            i += 1
            continue
        if ch == "\\":
            escape = True
            i += 1
            continue
        if ch == '"':
            j = i + 1
            while j < len(src) and src[j] in " \t\n\r":
                j += 1
            # Real end of string if followed by structure, or end of input
            if j >= len(src) or src[j] in ",}]:" :
                return _decode_json_string_body("".join(buf)), i + 1
            # Likely an unescaped quote inside HTML/JS - keep it
            buf.append('\\"')
            i += 1
            continue
        if ch == "\n":
            buf.append("\\n")
            i += 1
            continue
        if ch == "\r":
            buf.append("\\r")
            i += 1
            continue
        if ch == "\t":
            buf.append("\\t")
            i += 1
            continue
        buf.append(ch)
        i += 1
    return None, start


_PATH_KEY = re.compile(r'"(?:path|filename|file|filepath|name)"\s*:')
_CONTENT_KEY = re.compile(r'"(?:content|text|body|data|source)"\s*:')


def salvage_write_files_args(raw: str) -> Optional[Dict[str, Any]]:
    """Recover {files:[{path, content}, ...]} from broken write_files JSON."""
    if not raw or not str(raw).strip():
        return None
    text = strip_fences(str(raw))
    files: List[Dict[str, str]] = []
    pos = 0
    while True:
        pm = _PATH_KEY.search(text, pos)
        if not pm:
            break
        # skip whitespace to opening quote of path value
        i = pm.end()
        while i < len(text) and text[i] in " \t\n\r":
            i += 1
        path, after_path = _scan_json_string(text, i)
        if path is None:
            pos = pm.end()
            continue
        # find content key after path
        cm = _CONTENT_KEY.search(text, after_path)
        # Also allow content before path in the same object - search back a little
        if cm is None or (cm.start() - after_path) > 800:
            # look for content between previous brace and path
            window_start = max(0, pm.start() - 4000)
            cm2 = None
            for m in _CONTENT_KEY.finditer(text, window_start, pm.start()):
                cm2 = m
            if cm2 is not None:
                i2 = cm2.end()
                while i2 < len(text) and text[i2] in " \t\n\r":
                    i2 += 1
                content, _ = _scan_json_string(text, i2)
                if content is not None and path.strip():
                    files.append({"path": path.strip(), "content": content})
                pos = after_path
                continue
            pos = after_path
            continue
        i = cm.end()
        while i < len(text) and text[i] in " \t\n\r":
            i += 1
        content, after_content = _scan_json_string(text, i)
        if content is not None and path.strip():
            files.append({"path": path.strip(), "content": content})
            pos = after_content
        else:
            pos = after_path
    if not files:
        return None
    # de-dupe by path keeping last
    by_path: Dict[str, str] = {}
    for f in files:
        by_path[f["path"]] = f["content"]
    return {"files": [{"path": p, "content": c} for p, c in by_path.items()]}


def loads_lenient(text: str) -> Tuple[Optional[Any], Optional[str]]:
    """
    Parse JSON from model text. Returns (value, error).
    Never raises.
    """
    if text is None:
        return None, "empty"
    if isinstance(text, (dict, list)):
        return text, None
    raw = str(text).strip()
    if not raw:
        return None, "empty"
    candidates = [raw, strip_fences(raw)]
    extracted = extract_json_object(raw)
    if extracted:
        candidates.append(extracted)
        candidates.append(_light_repair(extracted))
        candidates.append(_escape_controls_in_strings(extracted))
        candidates.append(_escape_controls_in_strings(_light_repair(extracted)))
    candidates.append(_light_repair(strip_fences(raw)))
    candidates.append(_escape_controls_in_strings(strip_fences(raw)))
    candidates.append(_escape_controls_in_strings(_light_repair(strip_fences(raw))))

    seen = set()
    for c in candidates:
        if not c or c in seen:
            continue
        seen.add(c)
        try:
            return json.loads(c), None
        except Exception:
            continue
    return None, "json_parse_failed"


def parse_tool_arguments(
    raw: Any,
    *,
    tool_name: str = "",
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Parse tool arguments into a dict.
    On failure returns ({"arguments_invalid": True, "error": ...}, error_msg)
    - callers should feed this back to the model, not show raw JSON to users.
    """
    if isinstance(raw, dict):
        return raw, None
    if raw is None:
        return {}, None
    if not isinstance(raw, str):
        try:
            return dict(raw), None  # type: ignore[arg-type]
        except Exception:
            return {
                "arguments_invalid": True,
                "error": f"unsupported argument type: {type(raw).__name__}",
            }, "unsupported_type"

    value, err = loads_lenient(raw)
    if err and tool_name in {"write_files", "write_file"}:
        salvaged = salvage_write_files_args(raw)
        if salvaged:
            if tool_name == "write_file" and salvaged.get("files"):
                first = salvaged["files"][0]
                return first, None
            return salvaged, None
    if err:
        hint = (
            "Resend with valid JSON. For websites prefer write_file one file at a time, "
            "or write_files with 1–2 files per turn (HTML/CSS quotes break big JSON)."
        )
        return {
            "arguments_invalid": True,
            "error": err,
            "hint": hint,
        }, err
    if isinstance(value, dict):
        return value, None
    if isinstance(value, list) and tool_name in {"write_files", ""}:
        # Top-level array of file objects
        return {"files": value}, None
    return {"value": value}, None


def _as_list(value: Any) -> Optional[List[Any]]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        parsed, err = loads_lenient(value)
        if err is None and isinstance(parsed, list):
            return parsed
        if err is None and isinstance(parsed, dict):
            return [parsed]
        return None
    if isinstance(value, dict):
        return [value]
    return None


def _file_entry(item: Any) -> Optional[Dict[str, str]]:
    """Normalize one write_files entry to {path, content}."""
    if isinstance(item, str):
        # "path\n---\ncontent" or bare path (invalid without content)
        if "\n" in item and ("---" in item or ":" in item[:80]):
            parts = re.split(r"\n---+\n", item, maxsplit=1)
            if len(parts) == 2 and parts[0].strip():
                return {"path": parts[0].strip(), "content": parts[1]}
        return None
    if not isinstance(item, dict):
        return None
    path = (
        item.get("path")
        or item.get("filename")
        or item.get("file")
        or item.get("name")
        or item.get("filepath")
    )
    content = item.get("content")
    if content is None:
        content = item.get("text")
    if content is None:
        content = item.get("body")
    if content is None:
        content = item.get("data")
    if content is None:
        content = item.get("source")
    if path is None or content is None:
        return None
    return {"path": str(path), "content": str(content)}


def _coerce_write_files(args: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(args)
    files = out.get("files")
    if files is None and "value" in out:
        files = out.get("value")
    if files is None:
        for key in ("file", "items", "writes", "documents"):
            if key in out:
                files = out.get(key)
                break
    # Top-level single file: {path, content}
    if files is None and (out.get("path") or out.get("filename")):
        entry = _file_entry(out)
        if entry:
            out["files"] = [entry]
            return out
    # Map of path -> content
    if isinstance(files, dict) and not (
        "path" in files or "content" in files or "filename" in files
    ):
        mapped = []
        for k, v in files.items():
            if v is None:
                continue
            mapped.append({"path": str(k), "content": str(v)})
        if mapped:
            out["files"] = mapped
            return out

    lst = _as_list(files)
    if lst is None:
        return out
    normalized = []
    for item in lst:
        entry = _file_entry(item)
        if entry:
            normalized.append(entry)
    if normalized:
        out["files"] = normalized
    return out


def _coerce_todo_write(args: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(args)
    items = out.get("items")
    if items is None:
        for key in ("todos", "tasks", "plan", "steps", "checklist"):
            if key in out:
                items = out.get(key)
                break
    lst = _as_list(items)
    if lst is None:
        # Single todo object at top level
        if out.get("content") or out.get("task") or out.get("text"):
            lst = [out]
        else:
            return out
    cleaned: List[Dict[str, Any]] = []
    for i, it in enumerate(lst, start=1):
        if isinstance(it, str):
            text = it.strip()
            if text:
                cleaned.append({"id": str(i), "content": text, "status": "pending"})
            continue
        if not isinstance(it, dict):
            continue
        content = it.get("content") or it.get("task") or it.get("text") or it.get("title") or it.get("step")
        if content is None:
            continue
        status = str(it.get("status") or "pending").lower()
        if status in {"completed", "complete", "finished"}:
            status = "done"
        cleaned.append(
            {
                "id": str(it.get("id") or i),
                "content": str(content).strip(),
                "status": status,
            }
        )
    if cleaned:
        out["items"] = cleaned
    return out


def _coerce_apply_edits(args: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(args)
    edits = out.get("edits")
    if edits is None:
        for key in ("changes", "patches", "items"):
            if key in out:
                edits = out.get(key)
                break
    # Single edit at top level
    if edits is None and out.get("path") and (
        out.get("old_string") is not None or out.get("old") is not None
    ):
        edits = [out]
    lst = _as_list(edits)
    if lst is None:
        return out
    normalized = []
    for item in lst:
        if not isinstance(item, dict):
            continue
        path = item.get("path") or item.get("file") or item.get("filename")
        old = item.get("old_string") if "old_string" in item else item.get("old")
        if old is None:
            old = item.get("search")
        new = item.get("new_string") if "new_string" in item else item.get("new")
        if new is None:
            new = item.get("replace")
        if path is None or old is None or new is None:
            continue
        normalized.append({"path": str(path), "old_string": str(old), "new_string": str(new)})
    if normalized:
        out["edits"] = normalized
    return out


def coerce_tool_arguments(name: str, args: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Normalize common weak-model argument shapes before tool handlers run.
    LLaMA/free models often omit the wrapper key or use todos/file aliases.
    """
    if not args or not isinstance(args, dict):
        return {}
    if args.get("arguments_invalid"):
        return args
    # Nested double-wrap: {"arguments": {...}}
    if set(args.keys()) <= {"arguments", "args", "parameters"} or (
        "arguments" in args and len(args) <= 2 and not any(
            k in args for k in ("files", "items", "path", "edits", "command")
        )
    ):
        inner = args.get("arguments") or args.get("args") or args.get("parameters")
        if isinstance(inner, str):
            inner, _ = parse_tool_arguments(inner)
        if isinstance(inner, dict) and inner:
            args = inner

    if name == "write_files":
        return _coerce_write_files(args)
    if name == "todo_write":
        return _coerce_todo_write(args)
    if name == "apply_edits":
        return _coerce_apply_edits(args)
    if name == "write_file":
        entry = _file_entry(args)
        if entry:
            return entry
    if name == "run_command":
        return _coerce_run_command(args)
    return args


_SHELLISH_TOOL_NAMES = frozenset(
    {
        "pytest",
        "py_compile",
        "compileall",
        "python",
        "python3",
        "npm",
        "npx",
        "cargo",
        "go",
        "make",
        "git",
        "ls",
        "pwd",
        "shell",
        "bash",
        "sh",
        "run",
        "exec",
        "command",
        "terminal",
    }
)


def rewrite_shell_command(command: str) -> str:
    """Map common model shortcuts to real non-interactive shell commands."""
    cmd = (command or "").strip()
    if not cmd:
        return cmd
    # Bare py_compile / py_compile path → python3 -m …
    m = re.match(r"^py_compile(?:\s+(.+))?$", cmd, re.I)
    if m:
        target = (m.group(1) or "").strip() or "."
        if target in {".", "./"} or "/" not in target and not target.endswith(".py"):
            return f"python3 -m compileall -q -f {target}"
        return f"python3 -m py_compile {target}"
    m = re.match(r"^compileall(?:\s+(.+))?$", cmd, re.I)
    if m:
        target = (m.group(1) or ".").strip() or "."
        return f"python3 -m compileall -q -f {target}"
    if re.match(r"^pytest(?:\s|$)", cmd, re.I) and not cmd.lower().startswith("python"):
        rest = cmd[6:].strip()
        return f"python3 -m pytest {rest}".rstrip() if rest else "python3 -m pytest -q"
    return cmd


def _coerce_run_command(args: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(args)
    cmd = out.get("command")
    if cmd is None and isinstance(out.get("cmd"), str):
        cmd = out.pop("cmd")
    if isinstance(cmd, str):
        out["command"] = rewrite_shell_command(cmd)
    return out


def repair_tool_call(
    name: str,
    arguments: Optional[Dict[str, Any]],
    *,
    known_tools: Optional[set] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Recover when weak models emit JSON-as-name or invent shell tools.

    Examples that become run_command:
      name='{"command": "py_compile"}'
      name='py_compile' / 'pytest'
      name='python -m py_compile core/foo.py'
    """
    args: Dict[str, Any] = dict(arguments or {}) if isinstance(arguments, dict) else {}
    raw_name = (name or "").strip()
    known = known_tools or set()

    # 1) Whole tool name is a JSON object (common Ministral / free-model bug)
    if raw_name.startswith("{") and ("command" in raw_name or "name" in raw_name):
        parsed, err = loads_lenient(raw_name)
        if not err and isinstance(parsed, dict):
            if isinstance(parsed.get("command"), str):
                return "run_command", _coerce_run_command({"command": parsed["command"], **{
                    k: v for k, v in parsed.items() if k != "command" and k in {"cwd", "timeout_seconds"}
                }})
            inner_name = str(parsed.get("name") or parsed.get("tool") or "").strip()
            inner_args = parsed.get("arguments") if isinstance(parsed.get("arguments"), dict) else {}
            if not inner_args and isinstance(parsed.get("args"), dict):
                inner_args = parsed["args"]
            if inner_name:
                return repair_tool_call(inner_name, inner_args, known_tools=known)

    # 2) Already a real tool
    if raw_name in known:
        if raw_name == "run_command":
            return raw_name, _coerce_run_command(args)
        return raw_name, args

    # 3) Arguments already look like run_command payload
    if isinstance(args.get("command"), str) and args.get("command").strip():
        return "run_command", _coerce_run_command(args)

    # 4) Invented shell-ish tool name → run_command
    base = raw_name.split()[0].lower() if raw_name else ""
    if base in _SHELLISH_TOOL_NAMES or raw_name.lower().startswith(
        ("python ", "python3 ", "npm ", "npx ", "cargo ", "go ", "make ", "git ")
    ):
        # Prefer explicit command arg; else use the whole name as the command string
        cmd = args.get("command") if isinstance(args.get("command"), str) else raw_name
        return "run_command", _coerce_run_command({"command": str(cmd), **{
            k: v for k, v in args.items() if k in {"cwd", "timeout_seconds"}
        }})

    return raw_name, args


def looks_like_protocol_or_tool_json(text: str) -> bool:
    t = strip_fences(text or "")
    if not t.startswith("{") and '"type"' not in t and '"name"' not in t:
        return False
    value, err = loads_lenient(t)
    if err or not isinstance(value, dict):
        # Still looks like JSON blob
        return t.lstrip().startswith("{") and ("tool" in t or "arguments" in t or "finish_task" in t)
    if value.get("type") in {"tool", "final"}:
        return True
    if "name" in value and "arguments" in value:
        return True
    if isinstance(value.get("tool_calls"), list):
        return True
    return False


def sanitize_text_to_tool_calls(text: str) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """
    If assistant text is protocol/tool JSON, convert to tool call dicts.
    Returns (clean_text_or_None, list of {name, arguments}).
    """
    value, err = loads_lenient(text or "")
    if err or not isinstance(value, dict):
        return (text.strip() if text else None), []

    # Protocol shapes
    if value.get("type") == "tool":
        name = str(value.get("name") or "")
        args = value.get("arguments") if isinstance(value.get("arguments"), dict) else {}
        if name:
            return None, [{"name": name, "arguments": args}]
        return None, []

    if value.get("type") == "final":
        content = value.get("content")
        if isinstance(content, str):
            return content.strip() or None, []
        return None, []

    if "name" in value and ("arguments" in value or "args" in value):
        name = str(value.get("name") or "")
        args = value.get("arguments") or value.get("args") or {}
        if not isinstance(args, dict):
            args, _ = parse_tool_arguments(args)
        if name:
            return None, [{"name": name, "arguments": args}]

    # OpenAI-like embedded tool_calls in text (rare)
    tcs = value.get("tool_calls")
    if isinstance(tcs, list) and tcs:
        out = []
        for tc in tcs:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") or tc
            name = str((fn or {}).get("name") or "")
            args_raw = (fn or {}).get("arguments") or (fn or {}).get("args") or {}
            args, _ = parse_tool_arguments(args_raw)
            if name:
                out.append({"name": name, "arguments": args})
        if out:
            return None, out

    # Plain dict that isn't tool protocol - treat as normal text only if not JSON-looking junk
    return (text.strip() if text else None), []
