"""Filesystem tools bound to the workspace."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.agent import ui
from core.agent.approval import ApprovalManager
from core.agent.content_quality import stub_reject_reason
from core.agent.diffview import print_delete_preview, print_diff, print_new_file
from core.agent.edit_match import locate_old_string
from core.agent.tools.base import ToolRegistry
from core.agent.types import AgentState, ToolResult, ToolSpec
from core.agent.workspace import WorkspaceManager
from core.files import backup_file


def register_fs_tools(
    registry: ToolRegistry,
    workspace: WorkspaceManager,
    approval: ApprovalManager,
    state_files_read: List[str],
    state_files_changed: List[str],
    state: Optional[AgentState] = None,
) -> None:
    created = state.files_created if state is not None else []

    def _mark_known(rel: str) -> None:
        if rel not in state_files_read:
            state_files_read.append(rel)

    def _load_text(path: Path, rel: str) -> tuple[Optional[str], Optional[str]]:
        """Read file text and mark known. Returns (text, error)."""
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return None, str(e)
        _mark_known(rel)
        return text, None

    def read_file(args: Dict[str, Any]) -> ToolResult:
        path, err = workspace.resolve(args.get("path", ""))
        if err or path is None:
            return ToolResult("", "read_file", False, err or "bad path")
        if not path.is_file():
            return ToolResult("", "read_file", False, f"Not a file: {workspace.rel(path)}")
        rel = workspace.rel(path)
        text, load_err = _load_text(path, rel)
        if load_err or text is None:
            return ToolResult("", "read_file", False, load_err or "read failed")
        start = int(args.get("start_line") or 1)
        end = args.get("end_line")
        lines = text.splitlines()
        if start < 1:
            start = 1
        if end is None:
            chunk = lines[start - 1 : start - 1 + 400]
            end_used = start - 1 + len(chunk)
        else:
            end = int(end)
            chunk = lines[start - 1 : end]
            end_used = min(end, len(lines))
        numbered = [f"{i}|{line}" for i, line in enumerate(chunk, start=start)]
        return ToolResult(
            "",
            "read_file",
            True,
            f"{rel} lines {start}-{end_used} / {len(lines)}\n" + "\n".join(numbered),
            {"path": rel, "total_lines": len(lines)},
        )
    def read_files(args: Dict[str, Any]) -> ToolResult:
        paths = args.get("paths") or []
        if not isinstance(paths, list) or not paths:
            return ToolResult("", "read_files", False, "paths must be a non-empty list")
        chunks: List[str] = []
        for raw in paths[:12]:
            sub = read_file({"path": raw, "start_line": 1, "end_line": 200})
            header = f"===== {raw} ====="
            chunks.append(header + "\n" + sub.output)
        return ToolResult("", "read_files", True, "\n\n".join(chunks))

    def list_directory(args: Dict[str, Any]) -> ToolResult:
        path, err = workspace.resolve(args.get("path") or ".")
        if err or path is None:
            return ToolResult("", "list_directory", False, err or "bad path")
        if not path.is_dir():
            return ToolResult("", "list_directory", False, f"Not a directory: {workspace.rel(path)}")
        entries = []
        try:
            for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                if child.name.startswith(".") and child.name not in {".env.example"}:
                    continue
                kind = "dir" if child.is_dir() else "file"
                entries.append(f"{kind:4} {child.name}")
                if len(entries) >= 200:
                    entries.append("…truncated")
                    break
        except Exception as e:
            return ToolResult("", "list_directory", False, str(e))
        return ToolResult("", "list_directory", True, "\n".join(entries) or "(empty)")

    def write_file(args: Dict[str, Any]) -> ToolResult:
        path, err = workspace.resolve(args.get("path", ""))
        if err or path is None:
            return ToolResult("", "write_file", False, err or "bad path")
        content = args.get("content")
        if content is None:
            return ToolResult("", "write_file", False, "Missing content")
        content = str(content)
        rel = workspace.rel(path)
        stub_err = stub_reject_reason(rel, content)
        if stub_err:
            return ToolResult(
                "",
                "write_file",
                False,
                stub_err + " Resend write_file/write_files with a complete usable file.",
            )
        exists = path.exists() and path.is_file()
        before = ""
        if exists:
            try:
                before = path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                return ToolResult("", "write_file", False, str(e))
            print_diff(rel, before, content, title=f"Write  {rel}")
        else:
            print_new_file(rel, content)

        if not approval.approve(
            action="write file" if exists else "create file",
            risk="ask",
            detail=rel,
            kind="write",
        ):
            ui.event(f"Denied write {rel}", kind="err")
            return ToolResult("", "write_file", False, "User denied write")
        try:
            if exists:
                backup_file(str(path))
            workspace.ensure_parent(path)
            path.write_text(content, encoding="utf-8")
        except Exception as e:
            return ToolResult("", "write_file", False, str(e))
        if rel not in state_files_changed:
            state_files_changed.append(rel)
        if not exists and rel not in created:
            created.append(rel)
        _mark_known(rel)
        ui.event(f"Applied write {rel}", kind="ok")
        return ToolResult("", "write_file", True, f"Wrote {rel} ({len(content)} chars)")

    def ensure_dir(args: Dict[str, Any]) -> ToolResult:
        path, err = workspace.resolve(args.get("path", ""))
        if err or path is None:
            return ToolResult("", "ensure_dir", False, err or "bad path")
        rel = workspace.rel(path)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return ToolResult("", "ensure_dir", False, str(e))
        ui.event(f"Ensure dir {rel}", kind="ok")
        return ToolResult("", "ensure_dir", True, f"Directory ready: {rel}")

    def write_files(args: Dict[str, Any]) -> ToolResult:
        files = args.get("files")
        if not isinstance(files, list) or not files:
            return ToolResult(
                "",
                "write_files",
                False,
                'files must be a non-empty list of {path, content}. '
                'Example: {"files":[{"path":"site/index.html","content":"<!doctype html>..."}]}',
            )
        if len(files) > 12:
            return ToolResult(
                "",
                "write_files",
                False,
                f"Too many files ({len(files)}). Cap is 12 per turn - split across write_files calls.",
            )

        prepared: List[Dict[str, Any]] = []
        for item in files:
            if not isinstance(item, dict):
                continue
            path, err = workspace.resolve(item.get("path", ""))
            if err or path is None:
                prepared.append({"ok": False, "path": str(item.get("path") or "?"), "error": err or "bad path"})
                continue
            if item.get("content") is None:
                prepared.append({"ok": False, "path": workspace.rel(path), "error": "Missing content"})
                continue
            content = str(item.get("content"))
            rel = workspace.rel(path)
            stub_err = stub_reject_reason(rel, content)
            if stub_err:
                prepared.append({"ok": False, "path": rel, "error": stub_err})
                continue
            exists = path.exists() and path.is_file()
            before = ""
            if exists:
                try:
                    before = path.read_text(encoding="utf-8", errors="replace")
                except Exception as e:
                    prepared.append({"ok": False, "path": rel, "error": str(e)})
                    continue
                print_diff(rel, before, content, title=f"Write  {rel}")
            else:
                print_new_file(rel, content)
            prepared.append(
                {
                    "ok": True,
                    "path": rel,
                    "abspath": path,
                    "content": content,
                    "exists": exists,
                    "before": before,
                }
            )

        ok_items = [p for p in prepared if p.get("ok") and "abspath" in p]
        if not ok_items:
            lines = [f"FAIL {p['path']}: {p.get('error', 'unknown')}" for p in prepared]
            return ToolResult("", "write_files", False, "No valid files to write.\n" + "\n".join(lines))

        paths = [p["path"] for p in ok_items]
        if not approval.approve_batch(
            action=f"Write {len(ok_items)} files",
            paths=paths,
            risk="ask",
            kind="write",
        ):
            ui.event(f"Denied batch write ({len(ok_items)} files)", kind="err")
            return ToolResult(
                "",
                "write_files",
                False,
                "User denied batch write. Revise plan or request fewer/different files.",
            )

        report: List[str] = []
        applied = 0
        for p in prepared:
            if not p.get("ok") or "abspath" not in p:
                report.append(f"FAIL {p.get('path')}: {p.get('error', 'skipped')}")
                continue
            path: Path = p["abspath"]
            rel = p["path"]
            content = p["content"]
            try:
                if p["exists"]:
                    backup_file(str(path))
                workspace.ensure_parent(path)
                path.write_text(content, encoding="utf-8")
            except Exception as e:
                report.append(f"FAIL {rel}: {e}")
                continue
            applied += 1
            if rel not in state_files_changed:
                state_files_changed.append(rel)
            if not p["exists"] and rel not in created:
                created.append(rel)
            _mark_known(rel)
            report.append(f"OK {rel} ({len(content)} bytes)")

        if state is not None:
            state.batch_ops += 1

        ui.event(f"Applied {applied}/{len(ok_items)} files", kind="ok" if applied == len(ok_items) else "err")
        return ToolResult(
            "",
            "write_files",
            applied > 0,
            f"Batch write {applied}/{len(ok_items)}\n" + "\n".join(report),
            {"applied": applied, "requested": len(ok_items), "paths": paths},
        )

    def apply_edits(args: Dict[str, Any]) -> ToolResult:
        edits = args.get("edits")
        if not isinstance(edits, list) or not edits:
            return ToolResult("", "apply_edits", False, "edits must be a non-empty list")
        if len(edits) > 12:
            return ToolResult("", "apply_edits", False, "Too many edits (cap 12). Split across turns.")

        prepared: List[Dict[str, Any]] = []
        for item in edits:
            if not isinstance(item, dict):
                continue
            path, err = workspace.resolve(item.get("path", ""))
            if err or path is None:
                prepared.append({"ok": False, "path": str(item.get("path") or "?"), "error": err or "bad path"})
                continue
            rel = workspace.rel(path)
            old = item.get("old_string")
            new = item.get("new_string")
            if old is None or new is None:
                prepared.append({"ok": False, "path": rel, "error": "old_string and new_string required"})
                continue
            if not path.is_file():
                prepared.append({"ok": False, "path": rel, "error": "Not a file"})
                continue
            text, load_err = _load_text(path, rel)
            if load_err or text is None:
                prepared.append({"ok": False, "path": rel, "error": load_err or "read failed"})
                continue
            match, miss = locate_old_string(text, str(old))
            if match is None:
                # Include a short preview so the model can retry with an exact snippet
                preview = "\n".join(
                    f"{i}|{ln}" for i, ln in enumerate(text.splitlines()[:40], start=1)
                )
                prepared.append(
                    {
                        "ok": False,
                        "path": rel,
                        "error": f"{miss}\nCurrent {rel}:\n{preview}",
                    }
                )
                continue
            replace_all = bool(item.get("replace_all"))
            if match.count > 1 and not replace_all:
                prepared.append(
                    {
                        "ok": False,
                        "path": rel,
                        "error": (
                            f"old_string matched {match.count} times; "
                            "set replace_all=true or use a unique snippet"
                        ),
                    }
                )
                continue
            needle = match.old
            updated = (
                text.replace(needle, str(new))
                if replace_all
                else text.replace(needle, str(new), 1)
            )
            print_diff(rel, text, updated, title=f"Edit  {rel}")
            prepared.append(
                {
                    "ok": True,
                    "path": rel,
                    "abspath": path,
                    "updated": updated,
                    "n": match.count if replace_all else 1,
                }
            )

        ok_items = [p for p in prepared if p.get("ok") and "abspath" in p]
        if not ok_items:
            lines = [f"FAIL {p['path']}: {p.get('error', 'unknown')}" for p in prepared]
            return ToolResult("", "apply_edits", False, "No valid edits.\n" + "\n".join(lines))

        paths = [p["path"] for p in ok_items]
        if not approval.approve_batch(
            action=f"Edit {len(ok_items)} files",
            paths=paths,
            risk="ask",
            kind="edit",
        ):
            ui.event(f"Denied batch edit ({len(ok_items)} files)", kind="err")
            return ToolResult("", "apply_edits", False, "User denied batch edit.")

        report: List[str] = []
        applied = 0
        for p in prepared:
            if not p.get("ok") or "abspath" not in p:
                report.append(f"FAIL {p.get('path')}: {p.get('error', 'skipped')}")
                continue
            path = p["abspath"]
            rel = p["path"]
            try:
                backup_file(str(path))
                path.write_text(p["updated"], encoding="utf-8")
            except Exception as e:
                report.append(f"FAIL {rel}: {e}")
                continue
            applied += 1
            if rel not in state_files_changed:
                state_files_changed.append(rel)
            report.append(f"OK {rel} ({p['n']} replacement)")

        if state is not None:
            state.batch_ops += 1

        ui.event(f"Applied {applied}/{len(ok_items)} edits", kind="ok" if applied == len(ok_items) else "err")
        return ToolResult(
            "",
            "apply_edits",
            applied > 0,
            f"Batch edit {applied}/{len(ok_items)}\n" + "\n".join(report),
            {"applied": applied, "requested": len(ok_items), "paths": paths},
        )

    def replace_in_file(args: Dict[str, Any]) -> ToolResult:
        path, err = workspace.resolve(args.get("path", ""))
        if err or path is None:
            return ToolResult("", "replace_in_file", False, err or "bad path")
        old = args.get("old_string")
        new = args.get("new_string")
        if old is None or new is None:
            return ToolResult("", "replace_in_file", False, "old_string and new_string required")
        if not path.is_file():
            return ToolResult("", "replace_in_file", False, f"Not a file: {workspace.rel(path)}")
        rel = workspace.rel(path)
        text, load_err = _load_text(path, rel)
        if load_err or text is None:
            return ToolResult("", "replace_in_file", False, load_err or "read failed")
        match, miss = locate_old_string(text, str(old))
        if match is None:
            preview = "\n".join(
                f"{i}|{ln}" for i, ln in enumerate(text.splitlines()[:40], start=1)
            )
            return ToolResult(
                "",
                "replace_in_file",
                False,
                f"{miss}\nCurrent {rel}:\n{preview}\n"
                "Retry with an exact old_string from the content above, or use write_file.",
            )
        replace_all = bool(args.get("replace_all"))
        if match.count > 1 and not replace_all:
            return ToolResult(
                "",
                "replace_in_file",
                False,
                f"old_string matched {match.count} times; set replace_all=true or use a unique snippet",
            )
        needle = match.old
        updated = (
            text.replace(needle, str(new))
            if replace_all
            else text.replace(needle, str(new), 1)
        )
        print_diff(rel, text, updated, title=f"Edit  {rel}")
        if not approval.approve(action="edit file", risk="ask", detail=rel, kind="edit"):
            ui.event(f"Denied edit {rel}", kind="err")
            return ToolResult("", "replace_in_file", False, "User denied edit")
        backup_file(str(path))
        path.write_text(updated, encoding="utf-8")
        if rel not in state_files_changed:
            state_files_changed.append(rel)
        n = match.count if replace_all else 1
        ui.event(f"Applied edit {rel} ({n})", kind="ok")
        return ToolResult("", "replace_in_file", True, f"Updated {rel} ({n} replacement)")

    def delete_file(args: Dict[str, Any]) -> ToolResult:
        path, err = workspace.resolve(args.get("path", ""))
        if err or path is None:
            return ToolResult("", "delete_file", False, err or "bad path")
        rel = workspace.rel(path)
        if not path.exists():
            return ToolResult("", "delete_file", False, f"Not found: {rel}")
        print_delete_preview(rel, is_dir=path.is_dir())
        if not approval.approve(action="delete path", risk="dangerous", detail=rel, kind="delete"):
            ui.event(f"Denied delete {rel}", kind="err")
            return ToolResult("", "delete_file", False, "User denied delete")
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        except Exception as e:
            return ToolResult("", "delete_file", False, str(e))
        if rel not in state_files_changed:
            state_files_changed.append(rel)
        ui.event(f"Deleted {rel}", kind="ok")
        return ToolResult("", "delete_file", True, f"Deleted {rel}")

    def file_info(args: Dict[str, Any]) -> ToolResult:
        path, err = workspace.resolve(args.get("path", ""))
        if err or path is None:
            return ToolResult("", "file_info", False, err or "bad path")
        if not path.exists():
            return ToolResult("", "file_info", False, "Not found")
        st = path.stat()
        return ToolResult(
            "",
            "file_info",
            True,
            f"path={workspace.rel(path)}\ntype={'dir' if path.is_dir() else 'file'}\nsize={st.st_size}\nmtime={st.st_mtime}",
        )

    registry.register(
        ToolSpec(
            "read_file",
            "Read a text file from the workspace (optional start_line/end_line). Prefer ranged reads for large files.",
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                },
                "required": ["path"],
            },
            "safe",
        ),
        read_file,
    )
    registry.register(
        ToolSpec(
            "read_files",
            "Read multiple small/medium files at once (first ~200 lines each, max 12 paths).",
            {
                "type": "object",
                "properties": {
                    "paths": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["paths"],
            },
            "safe",
        ),
        read_files,
    )
    registry.register(
        ToolSpec(
            "list_directory",
            "List files and directories under a workspace path.",
            {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Directory path (default .)"}},
            },
            "safe",
        ),
        list_directory,
    )
    registry.register(
        ToolSpec(
            "ensure_dir",
            "Create a directory (and parents) inside the workspace.",
            {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            "safe",
        ),
        ensure_dir,
    )
    registry.register(
        ToolSpec(
            "write_file",
            "Create or overwrite a single file. For multi-file projects prefer write_files.",
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
            "ask",
        ),
        write_file,
    )
    registry.register(
        ToolSpec(
            "write_files",
            "Batch create/overwrite up to 12 files in one turn (one approval). Prefer for websites/apps. "
            "Each file must be a complete usable version - comment-only stubs are rejected. "
            "Split huge payloads across turns.",
            {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "content": {"type": "string"},
                            },
                            "required": ["path", "content"],
                        },
                    }
                },
                "required": ["files"],
            },
            "ask",
        ),
        write_files,
    )
    registry.register(
        ToolSpec(
            "replace_in_file",
            "Apply a targeted edit by replacing an exact old_string with new_string. "
                "Loads the file automatically; old_string must still match current content.",
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                    "replace_all": {"type": "boolean"},
                },
                "required": ["path", "old_string", "new_string"],
            },
            "ask",
        ),
        replace_in_file,
    )
    registry.register(
        ToolSpec(
            "apply_edits",
            "Batch replace_in_file-style edits (max 12). Auto-loads each file; one approval for the batch.",
            {
                "type": "object",
                "properties": {
                    "edits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "old_string": {"type": "string"},
                                "new_string": {"type": "string"},
                                "replace_all": {"type": "boolean"},
                            },
                            "required": ["path", "old_string", "new_string"],
                        },
                    }
                },
                "required": ["edits"],
            },
            "ask",
        ),
        apply_edits,
    )
    registry.register(
        ToolSpec(
            "delete_file",
            "Delete a file or directory inside the workspace (requires approval).",
            {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            "dangerous",
        ),
        delete_file,
    )
    registry.register(
        ToolSpec(
            "file_info",
            "Return basic metadata for a path.",
            {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            "safe",
        ),
        file_info,
    )
