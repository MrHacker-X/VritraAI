"""Context builders for AI prompts."""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

from core.files import sanitize_path

SMART_CTX_IGNORED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".idea",
    ".pytest_cache",
}
SMART_CTX_BINARY_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".pdf",
    ".zip",
    ".rar",
    ".7z",
    ".gz",
    ".tar",
    ".xz",
    ".mp4",
    ".mkv",
    ".mov",
    ".mp3",
    ".wav",
}
SMART_CTX_DEFAULTS = {
    "max_depth": 3,
    "max_entries": 50,
    "max_snippets": 5,
    "snippet_chars": 2000,
}


def get_os_info() -> Dict[str, str]:
    """Get operating system information with robust error handling.
    
    Handles cases where platform functions may fail or return empty values,
    especially in Termux/Android environments. Always returns a complete dict
    with fallback values.
    """
    os_info = {}
    
    # Detect Termux/Android environment
    env = os.environ
    is_termux = "TERMUX_VERSION" in env or (env.get("PREFIX", "").startswith("/data/data/com.termux"))
    is_android = bool(env.get("ANDROID_ROOT") or env.get("ANDROID_DATA"))
    
    # Get system name with fallback
    try:
        system = platform.system()
        if not system or system.strip() == "":
            if is_termux or is_android:
                system = "Android"
            else:
                system = "Unknown"
    except Exception:
        system = "Unknown"
    
    os_info['system'] = system
    
    # Get release version with fallback
    try:
        release = platform.release()
        if not release or release.strip() == "":
            # Try to get Android version from build.prop or fallback
            if is_termux or is_android:
                try:
                    # Try to read Android version from system properties
                    import subprocess
                    result = subprocess.run(['getprop', 'ro.build.version.release'], 
                                          capture_output=True, text=True, timeout=2)
                    if result.returncode == 0 and result.stdout.strip():
                        release = result.stdout.strip()
                    else:
                        release = "Unknown"
                except Exception:
                    release = "Unknown"
            else:
                release = "Unknown"
    except Exception:
        release = "Unknown"
    
    os_info['release'] = release
    
    # Get version string with fallback
    try:
        version = platform.version()
        if not version or version.strip() == "":
            version = "Unknown"
    except Exception:
        version = "Unknown"
    
    os_info['version'] = version
    
    # Get machine architecture with fallback
    try:
        machine = platform.machine()
        if not machine or machine.strip() == "":
            # Try alternative methods for Termux/Android
            if is_termux or is_android:
                try:
                    import subprocess
                    result = subprocess.run(['uname', '-m'], 
                                          capture_output=True, text=True, timeout=2)
                    if result.returncode == 0 and result.stdout.strip():
                        machine = result.stdout.strip()
                    else:
                        machine = "Unknown"
                except Exception:
                    machine = "Unknown"
            else:
                machine = "Unknown"
    except Exception:
        machine = "Unknown"
    
    os_info['machine'] = machine
    
    # Get processor info with fallback (this often fails in Termux)
    try:
        processor = platform.processor()
        if not processor or processor.strip() == "":
            # Try alternative methods
            if is_termux or is_android:
                try:
                    import subprocess
                    # Try to get CPU info from /proc/cpuinfo
                    result = subprocess.run(['uname', '-p'], 
                                          capture_output=True, text=True, timeout=2)
                    if result.returncode == 0 and result.stdout.strip():
                        processor = result.stdout.strip()
                    else:
                        # Try reading from /proc/cpuinfo
                        try:
                            with open('/proc/cpuinfo', 'r') as f:
                                for line in f:
                                    if 'model name' in line.lower() or 'Processor' in line:
                                        processor = line.split(':')[-1].strip()
                                        break
                            if not processor or processor.strip() == "":
                                processor = "Unknown"
                        except Exception:
                            processor = "Unknown"
                except Exception:
                    processor = "Unknown"
            else:
                processor = "Unknown"
    except Exception:
        processor = "Unknown"
    
    os_info['processor'] = processor
    
    # Add Termux/Android detection info
    if is_termux:
        os_info['environment'] = 'Termux'
    elif is_android:
        os_info['environment'] = 'Android'
    
    return os_info

def detect_project_type() -> Optional[str]:
    """Detect the type of project in current directory."""
    cwd = Path.cwd()
    
    # Check for common project files
    if (cwd / 'package.json').exists():
        return 'Node.js'
    elif (cwd / 'requirements.txt').exists() or (cwd / 'pyproject.toml').exists():
        return 'Python'
    elif (cwd / 'Cargo.toml').exists():
        return 'Rust'
    elif (cwd / 'go.mod').exists():
        return 'Go'
    elif (cwd / 'pom.xml').exists():
        return 'Java/Maven'
    elif (cwd / 'Dockerfile').exists():
        return 'Docker'
    elif (cwd / '.git').exists():
        return 'Git Repository'
    elif (cwd / 'Makefile').exists():
        return 'C/C++'
    
    return None

def sanitize_traceback_for_ai(traceback_str: str) -> str:
    """Remove vritraai.py references from traceback to avoid confusing AI.
    
    The AI should focus on the user's actual error, not the shell wrapper code.
    This function filters out lines containing vritraai.py file paths while preserving
    the traceback structure, exception type, and the actual user error message.
    """
    if not traceback_str:
        return traceback_str
    
    lines = traceback_str.split('\n')
    sanitized_lines = []
    skip_next_code_line = False
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        line_lower = line.lower()
        
        # Check if this line is a file path line referencing vritraai.py
        # Pattern: File "/path/to/vritraai.py", line X
        is_vritraai_file_line = (
            ('file "' in line_lower or "file '" in line_lower) and 
            'vritraai.py' in line_lower
        )
        
        if is_vritraai_file_line:
            # Skip this file path line and the next code line
            skip_next_code_line = True
            continue
        
        # If we're skipping the next code line (which is internal shell code)
        if skip_next_code_line:
            # Skip code lines that are clearly from vritraai.py internal code
            # But keep exception messages and important error info
            if (line_stripped.startswith('os.') or 
                line_stripped.startswith('subprocess.') or
                line_stripped.startswith('current_process') or
                line_stripped.startswith('result.') or
                line_stripped.startswith('execute_command') or
                line_stripped.startswith('handle_error') or
                (line_stripped and not line_stripped[0].isalpha() and '=' in line_stripped and 'vritraai' in line_lower)):
                skip_next_code_line = False
                continue
            # If it's an exception line or important info, keep it
            skip_next_code_line = False
        
        # Always keep exception type lines and error messages
        # These don't contain file paths and are important for AI
        sanitized_lines.append(line)
    
    # Join back and clean up any double newlines
    sanitized = '\n'.join(sanitized_lines)
    # Remove excessive blank lines (more than 2 consecutive)
    while '\n\n\n' in sanitized:
        sanitized = sanitized.replace('\n\n\n', '\n\n')
    
    return sanitized.strip()

def build_comprehensive_context(cwd: str = None, include_files: bool = True, limits: Dict[str, int] = None) -> str:
    """Build comprehensive context for AI including system info, directory structure, and project details."""
    if cwd is None:
        cwd = os.getcwd()
    
    limits = limits or SMART_CTX_DEFAULTS
    lines = []
    
    # System Information
    os_info = get_os_info()
    lines.append("=== SYSTEM INFORMATION ===")
    lines.append(f"OS: {os_info['system']} {os_info['release']}")
    lines.append(f"Version: {os_info['version']}")
    lines.append(f"Architecture: {os_info['machine']}")
    if os_info['processor']:
        lines.append(f"Processor: {os_info['processor']}")
    
    # Python version
    try:
        import sys
        lines.append(f"Python: {sys.version.split()[0]} ({sys.executable})")
    except:
        pass
    
    # Shell information
    try:
        shell = os.environ.get('SHELL', os.environ.get('COMSPEC', 'Unknown'))
        lines.append(f"Shell: {shell}")
    except:
        pass
    
    # Current Working Directory
    lines.append(f"\n=== CURRENT DIRECTORY ===")
    lines.append(f"Path: {cwd}")
    
    # Project Type
    project_type = detect_project_type()
    if project_type:
        lines.append(f"Project Type: {project_type}")
    
    # Directory Structure
    if include_files:
        lines.append(f"\n=== DIRECTORY STRUCTURE ===")
        try:
            entries = sorted(os.listdir(cwd))
            dirs = []
            files = []
            
            for name in entries:
                if name in SMART_CTX_IGNORED_DIRS:
                    continue
                path = os.path.join(cwd, name)
                if os.path.isdir(path):
                    dirs.append(name)
                else:
                    files.append(name)
            
            # List directories
            if dirs:
                lines.append("Directories:")
                for d in dirs[:limits.get('max_entries', 50)]:
                    lines.append(f"  📁 {d}/")
            
            # List files
            if files:
                lines.append("Files:")
                for f in files[:limits.get('max_entries', 50)]:
                    # Get file size for context
                    try:
                        size = os.path.getsize(os.path.join(cwd, f))
                        size_str = f" ({size} bytes)" if size < 1024 else f" ({size/1024:.1f} KB)"
                    except:
                        size_str = ""
                    lines.append(f"  📄 {f}{size_str}")
            
            # Always mention important manifest files
            important_files = ['requirements.txt', 'pyproject.toml', 'package.json', 'setup.cfg', 'Dockerfile', 
                             'Cargo.toml', 'go.mod', 'pom.xml', 'Makefile', 'CMakeLists.txt', '.gitignore']
            manifest_info = []
            for mf in important_files:
                p = os.path.join(cwd, mf)
                if os.path.exists(p):
                    manifest_info.append(mf)
            
            if manifest_info:
                lines.append(f"\nImportant Files Found: {', '.join(manifest_info)}")
                
        except Exception as e:
            lines.append(f"Could not list directory: {e}")
    
    return '\n'.join(lines)

def build_smart_error_context(cwd: str, error: Exception, context_str: str, traceback_str: str, paranoid: bool, limits: Dict[str, int] = None) -> str:
    """Build comprehensive context for AI error recovery including system info, directory structure, and error details."""
    limits = limits or SMART_CTX_DEFAULTS
    lines = []
    
    # Build comprehensive system and directory context
    comprehensive_ctx = build_comprehensive_context(cwd, include_files=True, limits=limits)
    lines.append(comprehensive_ctx)
    
    # Error Information
    lines.append(f"\n=== ERROR INFORMATION ===")
    disp_cwd = sanitize_path(cwd) if paranoid else cwd
    lines.append(f"Context: {context_str}" if context_str else f"Location: {disp_cwd}")
    lines.append(f"Error Type: {type(error).__name__}")
    lines.append(f"Error Message: {str(error)}")
    
    # Include sanitized traceback (tail only)
    if traceback_str:
        sanitized_tb = sanitize_traceback_for_ai(traceback_str)
        if sanitized_tb:
            tb_short = '\n'.join(sanitized_tb.strip().splitlines()[-12:])
            lines.append(f"\n=== TRACEBACK (last 12 lines) ===")
            lines.append(tb_short)
    
    return '\n'.join(lines)

def summarize_directory() -> str:
    """Generate a summary of the current directory."""
    try:
        cwd = Path.cwd()
        files = list(cwd.glob('*'))
        
        summary = []
        summary.append(f"Directory: {cwd}")
        summary.append(f"Total items: {len(files)}")
        
        dirs = [f for f in files if f.is_dir()]
        regular_files = [f for f in files if f.is_file()]
        
        if dirs:
            summary.append(f"Directories ({len(dirs)}): {', '.join([d.name for d in dirs[:10]])}")
            if len(dirs) > 10:
                summary.append(f"... and {len(dirs) - 10} more directories")
        
        if regular_files:
            # Group by extension
            extensions = {}
            for f in regular_files:
                ext = f.suffix.lower() or 'no extension'
                extensions[ext] = extensions.get(ext, 0) + 1
            
            summary.append(f"Files ({len(regular_files)}):")
            for ext, count in sorted(extensions.items()):
                summary.append(f"  {ext}: {count} files")
        
        project_type = detect_project_type()
        if project_type:
            summary.append(f"Project type detected: {project_type}")
        
        return "\n".join(summary)
    except Exception as e:
        return f"Error summarizing directory: {e}"

