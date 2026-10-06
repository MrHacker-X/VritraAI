"""Language helpers."""
from __future__ import annotations

import os

def get_file_language(file_path: str) -> str:
    """Detect programming language from file extension."""
    ext_to_lang = {
        '.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript', '.jsx': 'React JSX',
        '.tsx': 'React TSX', '.java': 'Java', '.cs': 'C#', '.cpp': 'C++', '.c': 'C',
        '.go': 'Go', '.rs': 'Rust', '.php': 'PHP', '.rb': 'Ruby', '.swift': 'Swift',
        '.kt': 'Kotlin', '.scala': 'Scala', '.r': 'R', '.m': 'MATLAB', '.sh': 'Bash',
        '.ps1': 'PowerShell', '.bat': 'Batch', '.sql': 'SQL', '.html': 'HTML',
        '.css': 'CSS', '.scss': 'SCSS', '.less': 'LESS', '.xml': 'XML', '.json': 'JSON',
        '.yaml': 'YAML', '.yml': 'YAML', '.toml': 'TOML', '.ini': 'INI', '.cfg': 'Config'
    }
    
    file_ext = os.path.splitext(file_path.lower())[1]
    return ext_to_lang.get(file_ext, 'Unknown')

