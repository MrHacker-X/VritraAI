"""Workspace path boundaries - keep file/shell ops inside the active project."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple


class WorkspaceManager:
    def __init__(self, root: Optional[str] = None) -> None:
        self.root = Path(root or os.getcwd()).resolve()

    def resolve(self, path: str) -> Tuple[Optional[Path], Optional[str]]:
        """Resolve path under workspace. Returns (path, error)."""
        if not path or not str(path).strip():
            return None, "Empty path"
        raw = os.path.expanduser(os.path.expandvars(str(path).strip()))
        p = Path(raw)
        if not p.is_absolute():
            p = self.root / p
        try:
            resolved = p.resolve()
        except Exception as e:
            return None, f"Invalid path: {e}"

        try:
            resolved.relative_to(self.root)
        except ValueError:
            return None, f"Path escapes workspace: {resolved} (workspace={self.root})"
        return resolved, None

    def rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)

    def ensure_parent(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
