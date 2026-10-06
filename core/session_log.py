"""Session logging helpers (paths injected via runtime)."""
from __future__ import annotations

from core import runtime

def log_session(message: str):
    """Log runtime.session activity to file."""
    try:
        with open(runtime.SESSION_LOG_FILE, 'a', encoding='utf-8') as f:
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"[{timestamp}] {message}\n")
    except Exception as e:
        pass  # Silent fail for logging

