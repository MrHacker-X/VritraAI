"""File helpers used by AI commands."""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import List, Optional

from core import runtime
from core.display import print_with_rich
from core.session_log import log_session

def confirm_action(prompt, default_yes=True):
    """Enhanced confirmation prompt with better UX.
    
    Args:
        prompt: The question to ask the user
        default_yes: If True, pressing Enter defaults to 'yes' (Y/n)
                    If False, pressing Enter defaults to 'no' (y/N)
    
    Returns:
        bool: True if user confirms, False otherwise
    """
    if default_yes:
        choices = "[Y/n]"
        default_response = "y"
    else:
        choices = "[y/N]"
        default_response = "n"
    
    try:
        full_prompt = f"{prompt} {choices}: "
        user_input = input(full_prompt).strip().lower()
        
        # If user just presses Enter, use the default
        if not user_input:
            user_input = default_response
        
        return user_input in ['y', 'yes']
        
    except (EOFError, KeyboardInterrupt):
        print()  # Add newline for better formatting
        return False  # Default to no on interruption

def expand_path(path: str) -> str:
    """Expand shell path variables like ~ and $VAR to actual paths.
    
    Args:
        path: Path string that may contain ~ or environment variables
        
    Returns:
        Expanded path string
    """
    if not path:
        return path
    try:
        # Expand ~ to home directory
        expanded = os.path.expanduser(path)
        # Expand environment variables like $HOME, ${VAR}
        expanded = os.path.expandvars(expanded)
        return expanded
    except Exception:
        return path

def sanitize_path(path: str) -> str:
    """Sanitize a path for privacy when paranoid_mode is enabled."""
    try:
        home = os.path.expanduser('~')
        if path.startswith(home):
            path = path.replace(home, '~', 1)
        # Optionally reduce depth
        parts = path.split(os.sep)
        if len(parts) > 3:
            return os.sep.join(parts[:2] + ['...', parts[-1]])
        return path
    except Exception:
        return path

def backup_file(filepath: str) -> str:
    """Create a backup of a file before modifying it."""
    backup_path = f"{filepath}.backup_{int(time.time())}"
    try:
        shutil.copy2(filepath, backup_path)
        return backup_path
    except Exception as e:
        print_with_rich(f"Warning: Could not create backup: {e}", "warning")
        return ""

def generate_unique_filename(base_filename: str, use_timestamp: bool = False) -> str:
    """Generate a unique filename that won't conflict with existing files.
    
    Args:
        base_filename: The desired filename (e.g., "index.html", "script.py")
        use_timestamp: If True, use timestamp format; otherwise use counter format
    
    Returns:
        A unique filename that doesn't exist in the current directory
        
    Examples:
        If index.html exists:
        - Counter mode: index_2.html, index_3.html, ...
        - Timestamp mode: index_20250110_150640.html
    """
    # If file doesn't exist, return as-is
    if not os.path.exists(base_filename):
        return base_filename
    
    # Split filename into name and extension
    name, ext = os.path.splitext(base_filename)
    
    if use_timestamp:
        # Use timestamp format: filename_YYYYMMDD_HHMMSS.ext
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{name}_{timestamp}{ext}"
        
        # Edge case: if timestamp file also exists, add counter
        counter = 2
        while os.path.exists(unique_filename):
            unique_filename = f"{name}_{timestamp}_{counter}{ext}"
            counter += 1
    else:
        # Use counter format: filename_2.ext, filename_3.ext, ...
        counter = 2
        unique_filename = f"{name}_{counter}{ext}"
        while os.path.exists(unique_filename):
            counter += 1
            unique_filename = f"{name}_{counter}{ext}"
    
    return unique_filename

def get_smart_filename_for_content(base_filename: str, content: str = "", description: str = "") -> str:
    """Get smart filename based on content analysis and existing files.
    
    This function:
    1. Analyzes the content/description to suggest better filenames
    2. Checks for existing files and generates unique names
    3. Uses intelligent naming conventions
    
    Args:
        base_filename: Initial filename suggestion
        content: File content (optional, for analysis)
        description: Description of what the file does (optional)
    
    Returns:
        A unique, descriptive filename
    """
    # Extract meaningful keywords from description if provided
    if description:
        description_lower = description.lower()
        
        # Map common keywords to better filename prefixes
        keyword_mapping = {
            'phone': 'phone_lookup',
            'ip lookup': 'ip_lookup',
            'network scan': 'network_scanner',
            'port scan': 'port_scanner',
            'web scraper': 'web_scraper',
            'api': 'api_client',
            'calculator': 'calculator',
            'converter': 'converter',
            'parser': 'parser',
            'validator': 'validator',
            'generator': 'generator',
            'monitor': 'monitor',
            'tracker': 'tracker',
            'analyzer': 'analyzer',
            'manager': 'manager',
            'bot': 'bot',
            'scraper': 'scraper',
            'crawler': 'crawler',
            'fetcher': 'fetcher',
            'downloader': 'downloader',
            'uploader': 'uploader',
        }
        
        # Try to find a better base name from description
        for keyword, prefix in keyword_mapping.items():
            if keyword in description_lower:
                # Get extension from original filename
                _, ext = os.path.splitext(base_filename)
                base_filename = f"{prefix}{ext}"
                break
    
    # Generate unique filename
    return generate_unique_filename(base_filename, use_timestamp=False)

def read_file_content(filepath: str) -> Optional[str]:
    """Read file content safely."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(filepath, 'r', encoding='latin-1') as f:
                return f.read()
        except Exception as e:
            print_with_rich(f"Error reading file {filepath}: {e}", "error")
            return None
    except Exception as e:
        print_with_rich(f"Error reading file {filepath}: {e}", "error")
        return None

def write_file_content(filepath: str, content: str, create_backup: bool = True) -> bool:
    """Write content to file with optional backup."""
    try:
        if os.path.exists(filepath) and create_backup:
            backup_path = backup_file(filepath)
            if backup_path:
                runtime.session.modified_files.append(filepath)
                backup_filename = os.path.basename(backup_path)
                print_with_rich(f"📋 Backup created: {backup_filename}", "info")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        log_session(f"File written: {filepath}")
        return True
    except Exception as e:
        print_with_rich(f"Error writing to file {filepath}: {e}", "error")
        return False

def _iter_code_files(base_path: str) -> List[str]:
    """Collect code-like files under a path (used by search/navigation commands).

    NOTE: Also includes common script extensions like .sh so project-level
    docs (e.g. `doc readme`) see shell tools as part of the codebase.
    """
    code_exts = {
        '.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.cs', '.cpp', '.c', '.h',
        '.go', '.rs', '.php', '.rb', '.swift', '.kt', '.scala', '.html', '.css',
        '.sh'
    }
    collected: List[str] = []
    for root, dirs, files in os.walk(base_path):
        # Skip heavy/irrelevant dirs
        dirs[:] = [d for d in dirs if d not in {'.git', 'node_modules', '__pycache__', 'dist', 'build'}]
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext in code_exts:
                collected.append(os.path.join(root, name))
    return collected

