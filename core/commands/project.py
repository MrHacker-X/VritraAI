"""Project intelligence AI commands."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from core import runtime
from core.client import get_ai_response
from core.context import detect_project_type
from core.display import (
    status_line,
    clean_ai_response,
    print_ai_response,
    print_ai_response_with_code_blocks,
    print_with_rich,
)
from core.files import expand_path, read_file_content
from core.lang import get_file_language
from core.session_log import log_session
from core.tui import print_cmd_help

def project_command(args: List[str]):
    """Project intelligence - /project [analyze|type|deps|health|missing|optimize]."""
    if not args:
        project_type = detect_project_type()
        if project_type:
            print_with_rich(f"Current project type: {project_type}", "info")
            print_with_rich(f"Working directory: {os.getcwd()}", "info")
        else:
            print_with_rich("No specific project type detected in current directory", "info")
        print_cmd_help(
            "Project",
            [
                ("/project analyze", "AI project overview"),
                ("/project type [path]", "detect type & stack"),
                ("/project deps [path]", "check dependency files"),
                ("/project health [path]", "health report"),
                ("/project missing [path]", "suggest missing files"),
                ("/project optimize [path]", "project-level optimizations"),
            ],
        )
        return

    subcmd = args[0].lower()
    rest = args[1:]

    if subcmd == "type":
        project_type_command(rest)
        return
    if subcmd in {"deps", "dependencies"}:
        dependencies_check_command(rest)
        return
    if subcmd == "health":
        project_health_command(rest)
        return
    if subcmd == "missing":
        missing_files_command(rest)
        return
    if subcmd == "optimize":
        project_optimize_command(rest)
        return

    if subcmd == "analyze":
        # Analyze project with AI
        if not runtime.AI_ENABLED:
            print_with_rich("AI is required for project analysis but is not enabled.", "warning")
            return
        
        try:
            # Get basic project info
            project_type = detect_project_type()
            cwd = os.getcwd()
            
            status_line(f"analyzing {cwd}")
            
            # List main files in the project
            files = []
            try:
                for root, dirs, filenames in os.walk(".", topdown=True):
                    # Skip common build/cache directories
                    dirs[:] = [d for d in dirs if d not in [".git", "__pycache__", "node_modules", ".env", "build", "dist"]]
                    
                    for filename in filenames:
                        if (filename.startswith(".") or 
                            filename.endswith((".pyc", ".pyo", ".log", ".tmp"))):
                            continue
                        files.append(os.path.join(root, filename))
                        if len(files) >= 15:  # Limit to 15 files for the analysis
                            break
                    if len(files) >= 15:
                        break
            except Exception as e:
                print_with_rich(f"Error scanning files: {e}", "warning")
                files = []
            
            # Create a prompt for AI analysis
            file_contents = []
            for file in files[:3]:  # Analyze only first 3 files to avoid token limits
                try:
                    content = read_file_content(file)
                    if content and len(content.strip()) > 0:
                        truncated_content = content[:800]  # Limit content size
                        file_contents.append(f"File: {file}\nContent preview:\n```\n{truncated_content}\n```\n")
                except Exception as e:
                    print_with_rich(f"Warning: Could not read {file}: {e}", "warning")
                    continue
            
            # Build analysis prompt
            files_list = ', '.join(files[:10]) if files else 'No readable files found'
            content_preview = '\n'.join(file_contents) if file_contents else 'No file content available'
            
            prompt = f"""Analyze this project and provide an overview:

Project directory: {cwd}
Detected project type: {project_type or 'Unknown'}
Total files found: {len(files)}

Key files:
{files_list}

Sample content:
{content_preview}

Please provide:
1. Project purpose and functionality
2. Technology stack used
3. Project structure analysis
4. Suggestions for improvement

Keep the analysis concise but informative."""
            
            status_line("analyzing project")
            analysis = get_ai_response(prompt, include_project_context=False, max_tokens=2500)
            
            if analysis:
                # Clean formatting - remove borders and clean markdown
                cleaned_analysis = clean_ai_response(analysis)
                print("\n\033[1;97mProject analysis\033[0m")
                # Use streaming effect for better readability
                print_ai_response(cleaned_analysis, use_typewriter=True)
            else:
                print_with_rich("Failed to get AI analysis", "error")
                
        except Exception as e:
            print_with_rich(f"Error during project analysis: {e}", "error")
            import traceback
            traceback.print_exc()
        return

    print_cmd_help(
        "Project",
        [
            ("/project analyze", "AI project overview"),
            ("/project type [path]", "detect type & stack"),
            ("/project deps [path]", "check dependency files"),
            ("/project health [path]", "health report"),
            ("/project missing [path]", "suggest missing files"),
            ("/project optimize [path]", "project-level optimizations"),
        ],
    )

def project_type_command(args: List[str]):
    """Enhanced project type detection with AI analysis."""
    target_dir = args[0] if args else "."
    # Expand ~ and environment variables
    target_dir = expand_path(target_dir)
    
    if not os.path.isdir(target_dir):
        print_with_rich(f"Directory not found: {target_dir}", "error")
        return
    
    status_line(f"structure · {os.path.abspath(target_dir)}")
    
    # Enhanced project detection
    project_info = _analyze_project_structure(target_dir)
    
    # Display basic project info
    print_with_rich(f"\n Project Analysis Results:", "success")
    print_with_rich("=" * 50, "info")
    
    print_with_rich(f"Primary Type: {project_info['primary_type']}", "info")
    if project_info['secondary_types']:
        print_with_rich(f"Secondary Types: {', '.join(project_info['secondary_types'])}", "info")
    
    print_with_rich(f"Confidence: {project_info['confidence']}", "info")
    print_with_rich(f"Total Files: {project_info['total_files']}", "info")
    print_with_rich(f"Code Files: {project_info['code_files']}", "info")
    
    # Show key indicators
    if project_info['key_files']:
        print_with_rich(f"\nKey Project Files:", "info")
        for file in project_info['key_files'][:10]:  # Limit to 10
            print_with_rich(f"  • {file}", "info")
    
    # Show technologies
    if project_info['technologies']:
        print_with_rich(f"\nTechnologies Detected:", "info")
        for tech in project_info['technologies']:
            print_with_rich(f"  • {tech}", "info")
    
    # Show frameworks
    if project_info['frameworks']:
        print_with_rich(f"\nFrameworks/Libraries:", "info")
        for framework in project_info['frameworks']:
            print_with_rich(f"  • {framework}", "info")
    
    # AI-powered deeper analysis if AI is enabled
    if runtime.AI_ENABLED and len(args) == 0:  # Only for current directory
        _ai_project_analysis(target_dir, project_info)

def _analyze_project_structure(directory: str) -> dict:
    """Analyze project structure and detect technologies."""
    project_info = {
        'primary_type': 'Unknown',
        'secondary_types': [],
        'confidence': 'Low',
        'total_files': 0,
        'code_files': 0,
        'key_files': [],
        'technologies': [],
        'frameworks': [],
        'languages': {},
        'build_tools': [],
        'package_managers': []
    }
    
    # File patterns for different project types
    patterns = {
        'Python': {
            'key_files': ['requirements.txt', 'setup.py', 'pyproject.toml', 'Pipfile', 'conda.yml', 'environment.yml'],
            'extensions': ['.py'],
            'frameworks': ['flask', 'django', 'fastapi', 'streamlit', 'pytest', 'numpy', 'pandas'],
            'build_tools': ['poetry', 'pipenv', 'setuptools']
        },
        'Node.js': {
            'key_files': ['package.json', 'package-lock.json', 'yarn.lock', 'node_modules'],
            'extensions': ['.js', '.ts', '.jsx', '.tsx'],
            'frameworks': ['react', 'vue', 'angular', 'express', 'next', 'nuxt', 'svelte'],
            'build_tools': ['webpack', 'vite', 'rollup', 'parcel']
        },
        'Java': {
            'key_files': ['pom.xml', 'build.gradle', 'gradlew', 'mvnw'],
            'extensions': ['.java', '.jar', '.war'],
            'frameworks': ['spring', 'junit', 'hibernate', 'maven', 'gradle'],
            'build_tools': ['maven', 'gradle', 'ant']
        },
        'C#/.NET': {
            'key_files': ['.csproj', '.sln', 'packages.config', 'project.json'],
            'extensions': ['.cs', '.vb', '.fs'],
            'frameworks': ['asp.net', 'entity framework', 'xamarin', 'unity'],
            'build_tools': ['msbuild', 'dotnet', 'nuget']
        },
        'Go': {
            'key_files': ['go.mod', 'go.sum', 'Gopkg.toml', 'glide.yaml'],
            'extensions': ['.go'],
            'frameworks': ['gin', 'echo', 'fiber', 'gorilla'],
            'build_tools': ['go modules', 'dep', 'glide']
        },
        'Rust': {
            'key_files': ['Cargo.toml', 'Cargo.lock'],
            'extensions': ['.rs'],
            'frameworks': ['actix', 'rocket', 'warp', 'tokio'],
            'build_tools': ['cargo']
        },
        'PHP': {
            'key_files': ['composer.json', 'composer.lock', 'index.php'],
            'extensions': ['.php'],
            'frameworks': ['laravel', 'symfony', 'codeigniter', 'wordpress'],
            'build_tools': ['composer']
        },
        'Ruby': {
            'key_files': ['Gemfile', 'Gemfile.lock', 'Rakefile', 'config.ru'],
            'extensions': ['.rb'],
            'frameworks': ['rails', 'sinatra', 'hanami'],
            'build_tools': ['bundler', 'gem']
        },
        'Docker': {
            'key_files': ['Dockerfile', 'docker-compose.yml', 'docker-compose.yaml', '.dockerignore'],
            'extensions': [],
            'frameworks': ['docker', 'docker-compose', 'kubernetes'],
            'build_tools': ['docker']
        },
        'Frontend': {
            'key_files': ['index.html', 'webpack.config.js', 'vite.config.js', '.babelrc'],
            'extensions': ['.html', '.css', '.scss', '.less', '.vue'],
            'frameworks': ['bootstrap', 'tailwind', 'material-ui', 'bulma'],
            'build_tools': ['webpack', 'vite', 'gulp', 'grunt']
        }
    }
    
    # Analyze files
    for root, dirs, files in os.walk(directory):
        # Skip hidden and common ignore directories
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'target', 'build', 'dist', 'bin', 'obj']]
        
        for file in files:
            if file.startswith('.'):
                continue
                
            project_info['total_files'] += 1
            file_path = os.path.join(root, file)
            
            # Check for key files
            for proj_type, proj_patterns in patterns.items():
                if file.lower() in [f.lower() for f in proj_patterns['key_files']]:
                    project_info['key_files'].append(file_path.replace(directory, '.').replace('\\', '/'))
                    if proj_type not in project_info['secondary_types']:
                        project_info['secondary_types'].append(proj_type)
            
            # Count code files and languages
            file_ext = os.path.splitext(file.lower())[1]
            if file_ext in ['.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cs', '.go', '.rs', '.php', '.rb', '.cpp', '.c', '.h', '.swift', '.kt']:
                project_info['code_files'] += 1
                lang = get_file_language(file_path)
                if lang != 'Unknown':
                    project_info['languages'][lang] = project_info['languages'].get(lang, 0) + 1
    
    # Determine primary type based on key files and file counts
    type_scores = {}
    for proj_type, proj_patterns in patterns.items():
        score = 0
        
        # Score based on key files found
        for key_file in proj_patterns['key_files']:
            if any(key_file.lower() in kf.lower() for kf in project_info['key_files']):
                score += 10
        
        # Score based on file extensions
        for ext in proj_patterns['extensions']:
            lang = get_file_language(f"dummy{ext}")
            if lang in project_info['languages']:
                score += project_info['languages'][lang] * 2
        
        type_scores[proj_type] = score
    
    # Determine primary type
    if type_scores:
        primary_type = max(type_scores, key=type_scores.get)
        max_score = type_scores[primary_type]
        
        if max_score > 0:
            project_info['primary_type'] = primary_type
            project_info['confidence'] = 'High' if max_score >= 20 else 'Medium' if max_score >= 10 else 'Low'
            
            # Add technologies and build tools for primary type
            if primary_type in patterns:
                project_info['technologies'].extend(patterns[primary_type]['frameworks'])
                project_info['build_tools'].extend(patterns[primary_type]['build_tools'])
    
    # Remove duplicates
    project_info['secondary_types'] = list(set(project_info['secondary_types']))
    if project_info['primary_type'] in project_info['secondary_types']:
        project_info['secondary_types'].remove(project_info['primary_type'])
    
    return project_info

def _ai_project_analysis(directory: str, project_info: dict):
    """AI-powered deeper project analysis."""
    status_line("deeper analysis")
    
    # Prepare project summary for AI
    summary = f"""Project Directory: {directory}
Primary Type: {project_info['primary_type']}
Secondary Types: {', '.join(project_info['secondary_types'])}
Total Files: {project_info['total_files']}
Code Files: {project_info['code_files']}
Key Files: {', '.join(project_info['key_files'][:10])}
Languages: {', '.join([f'{lang} ({count} files)' for lang, count in project_info['languages'].items()])}"""
    
    prompt = f"""As a software architecture expert, analyze this project structure and provide insights:

{summary}

Please provide:
📈 **Architecture Assessment**: Overall project structure and organization
🎯 **Purpose Detection**: What this project likely does based on structure
🛠️ **Technology Stack**: Detailed analysis of technologies used
📉 **Complexity Level**: Beginner/Intermediate/Advanced project assessment
📊 **Quality Indicators**: Code organization, best practices observed
🕰️ **Development Stage**: Early/Active/Mature development assessment
💡 **Recommendations**: Suggestions for improvement or missing components
🔍 **Potential Issues**: Areas that might need attention

Provide a comprehensive but concise analysis."""
    
    ai_analysis = get_ai_response(prompt, include_project_context=False, max_tokens=2500)
    if ai_analysis:
        print("\n\033[1;97mProject analysis\033[0m")
        print_ai_response(ai_analysis, use_typewriter=True)
        print()

def dependencies_check_command(args: List[str]):
    """Check for outdated dependencies and security issues."""
    target_dir = args[0] if args else "."
    # Expand ~ and environment variables
    target_dir = expand_path(target_dir)
    
    if not os.path.isdir(target_dir):
        print_with_rich(f"Directory not found: {target_dir}", "error")
        return
    
    status_line(f"deps · {os.path.abspath(target_dir)}")
    
    dependency_files = _find_dependency_files(target_dir)
    
    if not dependency_files:
        print_with_rich("No dependency files found in project", "warning")
        print_with_rich("Common dependency files: package.json, requirements.txt, Gemfile, composer.json, go.mod, Cargo.toml", "info")
        return
    
    print_with_rich(f"\n Found {len(dependency_files)} dependency files:", "success")
    for dep_file in dependency_files:
        print_with_rich(f"  • {dep_file}", "info")
    
    # Analyze each dependency file
    for dep_file in dependency_files:
        _analyze_dependency_file(os.path.join(target_dir, dep_file))

def _find_dependency_files(directory: str) -> list:
    """Find dependency management files."""
    dependency_patterns = [
        'package.json', 'package-lock.json', 'yarn.lock',  # Node.js
        'requirements.txt', 'Pipfile', 'poetry.lock', 'pyproject.toml',  # Python
        'Gemfile', 'Gemfile.lock',  # Ruby
        'composer.json', 'composer.lock',  # PHP
        'go.mod', 'go.sum',  # Go
        'Cargo.toml', 'Cargo.lock',  # Rust
        'pom.xml', 'build.gradle',  # Java
        'project.json', '*.csproj',  # .NET
        'pubspec.yaml'  # Dart/Flutter
    ]
    
    found_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower() in [p.lower() for p in dependency_patterns if not p.startswith('*')]:
                rel_path = os.path.relpath(os.path.join(root, file), directory)
                found_files.append(rel_path.replace('\\', '/'))
    
    return found_files

def _analyze_dependency_file(file_path: str):
    """Analyze a specific dependency file."""
    if not os.path.exists(file_path):
        return
    
    file_name = os.path.basename(file_path)
    print_with_rich(f"\n Analyzing: {file_name}", "info")
    
    try:
        content = read_file_content(file_path)
        if not content:
            return
        
        # Basic analysis based on file type
        if file_name == 'package.json':
            _analyze_package_json(content)
        elif file_name in ['requirements.txt', 'Pipfile']:
            _analyze_python_deps(content)
        elif file_name == 'Gemfile':
            _analyze_gemfile(content)
        elif file_name == 'composer.json':
            _analyze_composer_json(content)
        elif file_name in ['go.mod', 'Cargo.toml', 'pom.xml']:
            _analyze_generic_deps(content, file_name)
        
        # AI-powered analysis if enabled
        if runtime.AI_ENABLED:
            _ai_dependency_analysis(file_path, content, file_name)
            
    except Exception as e:
        print_with_rich(f"Error analyzing {file_name}: {e}", "error")

def _analyze_package_json(content: str):
    """Analyze Node.js package.json file."""
    try:
        import json
        data = json.loads(content)
        
        deps = data.get('dependencies', {})
        dev_deps = data.get('devDependencies', {})
        
        print_with_rich(f"Dependencies: {len(deps)}, Dev Dependencies: {len(dev_deps)}", "info")
        
        # Look for common frameworks
        frameworks = []
        if 'react' in deps: frameworks.append('React')
        if 'vue' in deps: frameworks.append('Vue.js')
        if '@angular/core' in deps: frameworks.append('Angular')
        if 'express' in deps: frameworks.append('Express.js')
        if 'next' in deps: frameworks.append('Next.js')
        
        if frameworks:
            print_with_rich(f"Frameworks detected: {', '.join(frameworks)}", "success")
        
    except json.JSONDecodeError:
        print_with_rich("Invalid JSON format", "error")

def _analyze_python_deps(content: str):
    """Analyze Python dependency files."""
    lines = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith('#')]
    deps = [line.split('==')[0].split('>=')[0].split('~=')[0] for line in lines if '==' in line or '>=' in line or '~=' in line]
    
    print_with_rich(f"Python packages: {len(deps)}", "info")
    
    # Look for common frameworks
    frameworks = []
    for dep in deps:
        dep_lower = dep.lower()
        if 'django' in dep_lower: frameworks.append('Django')
        elif 'flask' in dep_lower: frameworks.append('Flask')
        elif 'fastapi' in dep_lower: frameworks.append('FastAPI')
        elif 'streamlit' in dep_lower: frameworks.append('Streamlit')
        elif 'pandas' in dep_lower: frameworks.append('Pandas (Data Science)')
        elif 'tensorflow' in dep_lower: frameworks.append('TensorFlow (ML)')
        elif 'pytorch' in dep_lower: frameworks.append('PyTorch (ML)')
    
    if frameworks:
        print_with_rich(f"Frameworks detected: {', '.join(set(frameworks))}", "success")

def _analyze_gemfile(content: str):
    """Analyze Ruby Gemfile."""
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    gems = [line for line in lines if line.startswith('gem ')]
    
    print_with_rich(f"Ruby gems: {len(gems)}", "info")
    
    if any('rails' in line for line in gems):
        print_with_rich("Ruby on Rails detected", "success")

def _analyze_composer_json(content: str):
    """Analyze PHP composer.json."""
    try:
        import json
        data = json.loads(content)
        
        deps = data.get('require', {})
        dev_deps = data.get('require-dev', {})
        
        print_with_rich(f"PHP packages: {len(deps)}, Dev: {len(dev_deps)}", "info")
        
        # Look for frameworks
        frameworks = []
        for dep in deps:
            if 'laravel' in dep.lower(): frameworks.append('Laravel')
            elif 'symfony' in dep.lower(): frameworks.append('Symfony')
            elif 'codeigniter' in dep.lower(): frameworks.append('CodeIgniter')
        
        if frameworks:
            print_with_rich(f"Frameworks: {', '.join(frameworks)}", "success")
            
    except json.JSONDecodeError:
        print_with_rich("Invalid JSON format", "error")

def _analyze_generic_deps(content: str, file_name: str):
    """Generic dependency analysis."""
    lines = len([line for line in content.split('\n') if line.strip()])
    print_with_rich(f"{file_name}: {lines} lines of configuration", "info")

def _ai_dependency_analysis(file_path: str, content: str, file_name: str):
    """AI-powered dependency analysis."""
    if len(content) > 4000:
        content = content[:4000] + "\n... [Content truncated]"
    
    prompt = f"""As a software security and dependency management expert, analyze this {file_name} file:

File: {file_path}

{content}

Please provide:
⚠️ **Security Issues**: Outdated packages, known vulnerabilities
📈 **Version Analysis**: Packages that should be updated
🕰️ **Maintenance**: Packages that are no longer maintained
📦 **Dependencies**: Analysis of dependency tree complexity
💡 **Recommendations**: Best practices and improvements
🔒 **Security**: Potential security concerns
🏃 **Performance**: Dependencies that might impact performance

Focus on actionable recommendations for dependency management."""
    
    analysis = get_ai_response(prompt, include_project_context=False, max_tokens=2500)
    if analysis:
        print_with_rich(f"\n Dependency Analysis: {file_name}\n", "warning")
        print_ai_response(analysis, use_typewriter=True)
        print()

def project_health_command(args: List[str]):
    """Comprehensive project health analysis."""
    target_dir = args[0] if args else "."
    # Expand ~ and environment variables
    target_dir = expand_path(target_dir)
    
    if not os.path.isdir(target_dir):
        print_with_rich(f"Directory not found: {target_dir}", "error")
        return
    
    status_line(f"health · {os.path.abspath(target_dir)}")
    
    health_report = _generate_health_report(target_dir)
    _display_health_report(health_report)
    
    # AI-powered health analysis
    if runtime.AI_ENABLED:
        _ai_health_analysis(target_dir, health_report)

def _generate_health_report(directory: str) -> dict:
    """Generate comprehensive project health report."""
    report = {
        'documentation': {'score': 0, 'details': []},
        'testing': {'score': 0, 'details': []},
        'structure': {'score': 0, 'details': []},
        'dependencies': {'score': 0, 'details': []},
        'security': {'score': 0, 'details': []},
        'maintenance': {'score': 0, 'details': []},
        'overall_score': 0
    }
    
    # Check documentation
    doc_files = ['README.md', 'README.txt', 'README.rst', 'docs/', 'documentation/']
    found_docs = []
    for root, dirs, files in os.walk(directory):
        for item in doc_files:
            if item in files or item.rstrip('/') in dirs:
                found_docs.append(item)
    
    report['documentation']['score'] = min(len(found_docs) * 25, 100)
    report['documentation']['details'] = found_docs if found_docs else ['No documentation files found']
    
    # Check testing
    test_patterns = ['test_', '_test.', 'tests/', 'test/', 'spec/', '__tests__/']
    test_files = 0
    for root, dirs, files in os.walk(directory):
        for file in files:
            if any(pattern in file.lower() for pattern in test_patterns):
                test_files += 1
        for dir_name in dirs:
            if any(pattern.rstrip('/') in dir_name.lower() for pattern in test_patterns):
                test_files += 5  # Bonus for test directories
    
    report['testing']['score'] = min(test_files * 10, 100)
    report['testing']['details'] = [f'Found {test_files} test files/directories']
    
    # Check project structure
    structure_score = 0
    structure_details = []
    
    # Check for common project files
    project_files = ['.gitignore', 'LICENSE', 'CHANGELOG.md', '.github/', 'ci/', '.ci/']
    found_structure = []
    for root, dirs, files in os.walk(directory):
        for item in project_files:
            if item in files or item.rstrip('/') in dirs:
                found_structure.append(item)
                structure_score += 15
    
    report['structure']['score'] = min(structure_score, 100)
    report['structure']['details'] = found_structure if found_structure else ['Basic project files missing']
    
    # Check dependencies
    dep_files = _find_dependency_files(directory)
    dep_score = min(len(dep_files) * 30, 100)
    report['dependencies']['score'] = dep_score
    report['dependencies']['details'] = dep_files if dep_files else ['No dependency management files']
    
    # Security check (basic)
    security_issues = []
    security_score = 100  # Start with full score, deduct for issues
    
    # Check for common security issues
    for root, dirs, files in os.walk(directory):
        for file in files:
            file_lower = file.lower()
            if any(pattern in file_lower for pattern in ['.env', 'secret', 'password', 'key', 'token']):
                if not file_lower.endswith('.example'):
                    security_issues.append(f'Potential secrets file: {file}')
                    security_score -= 20
    
    report['security']['score'] = max(security_score, 0)
    report['security']['details'] = security_issues if security_issues else ['No obvious security issues']
    
    # Maintenance indicators
    maintenance_score = 50  # Neutral starting point
    maintenance_details = []
    
    # Check for recent activity (if git repo)
    git_dir = os.path.join(directory, '.git')
    if os.path.exists(git_dir):
        maintenance_details.append('Git repository detected')
        maintenance_score += 25
    
    report['maintenance']['score'] = maintenance_score
    report['maintenance']['details'] = maintenance_details
    
    # Calculate overall score
    scores = [report[category]['score'] for category in report if category != 'overall_score']
    report['overall_score'] = sum(scores) // len(scores)
    
    return report

def _display_health_report(report: dict):
    """Display the project health report."""
    print("\n\033[1;97mProject health report\033[0m")
    print_with_rich("=" * 50, "info")
    
    # Overall score with color coding
    overall = report['overall_score']
    if overall >= 80:
        score_color = "success"
        score_emoji = "🌟"
    elif overall >= 60:
        score_color = "warning"
        score_emoji = "🟡"
    else:
        score_color = "error"
        score_emoji = "🔴"
    
    print_with_rich(f"\n{score_emoji} Overall Health Score: {overall}/100", score_color)
    
    # Category breakdown
    categories = {
        'documentation': '📚 Documentation',
        'testing': '🧪 Testing',
        'structure': '🏧 Project Structure',
        'dependencies': '📦 Dependencies',
        'security': '🔒 Security',
        'maintenance': '🔧 Maintenance'
    }
    
    for category, emoji_name in categories.items():
        score = report[category]['score']
        details = report[category]['details']
        
        # Color code based on score
        if score >= 70:
            color = "success"
        elif score >= 40:
            color = "warning"
        else:
            color = "error"
        
        print_with_rich(f"\n{emoji_name}: {score}/100", color)
        for detail in details[:3]:  # Limit details
            print_with_rich(f"  • {detail}", "info")

def _ai_health_analysis(directory: str, health_report: dict):
    """AI-powered project health analysis."""
    status_line("health analysis")
    
    # Prepare health summary
    summary = f"""Project Health Summary:
Overall Score: {health_report['overall_score']}/100

Category Scores:
- Documentation: {health_report['documentation']['score']}/100
- Testing: {health_report['testing']['score']}/100
- Structure: {health_report['structure']['score']}/100
- Dependencies: {health_report['dependencies']['score']}/100
- Security: {health_report['security']['score']}/100
- Maintenance: {health_report['maintenance']['score']}/100

Key Issues Identified:
- Documentation: {', '.join(health_report['documentation']['details'])}
- Testing: {', '.join(health_report['testing']['details'])}
- Security: {', '.join(health_report['security']['details'])}"""
    
    prompt = f"""As a software project consultant, analyze this project health report and provide actionable recommendations:

{summary}

Please provide:
🎯 **Priority Issues**: Most critical problems that need immediate attention
🛣️ **Action Plan**: Step-by-step plan to improve project health
📊 **Quick Wins**: Easy improvements that can boost the health score
📚 **Documentation**: Specific documentation recommendations
🧪 **Testing**: Testing strategy recommendations
🔒 **Security**: Security hardening suggestions
🔧 **Maintenance**: Long-term maintenance recommendations
💯 **Best Practices**: Industry best practices for this project type

Provide specific, actionable recommendations prioritized by impact and effort."""
    
    analysis = get_ai_response(prompt, include_project_context=False, max_tokens=2500)
    if analysis:
        cleaned_analysis = clean_ai_response(analysis)
        
        # Clean output with typewriter effect - NO BORDERS!
        print()
        print_with_rich("="*60, "info")
        print_with_rich("Project Health Recommendations", "success")
        print_with_rich("="*60, "info")
        print()
        
        # Use typewriter effect for AI response with code block highlighting
        print_ai_response_with_code_blocks(cleaned_analysis)
        print()
        print_with_rich("="*60, "info")

def missing_files_command(args: List[str]):
    """AI suggests missing files for the project."""
    target_dir = args[0] if args else "."
    # Expand ~ and environment variables
    target_dir = expand_path(target_dir)
    
    if not os.path.isdir(target_dir):
        print_with_rich(f"Directory not found: {target_dir}", "error")
        return
    
    if not runtime.AI_ENABLED:
        print_with_rich("AI disabled - run /setup", "error")
        return
    
    status_line(f"missing · {os.path.abspath(target_dir)}")
    
    # Get project structure
    project_info = _analyze_project_structure(target_dir)
    
    # Get file list
    existing_files = []
    for root, dirs, files in os.walk(target_dir):
        # Skip hidden and common ignore directories
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'target', 'build', 'dist']]
        
        for file in files:
            if not file.startswith('.'):
                rel_path = os.path.relpath(os.path.join(root, file), target_dir).replace('\\', '/')
                existing_files.append(rel_path)
    
    prompt = f"""As a software project consultant, analyze this project structure and suggest missing files that would improve the project:

Project Type: {project_info['primary_type']}
Secondary Types: {', '.join(project_info['secondary_types'])}
Total Files: {project_info['total_files']}
Code Files: {project_info['code_files']}
Languages: {', '.join([f'{lang} ({count})' for lang, count in project_info['languages'].items()])}

Existing Key Files:
{chr(10).join([f'- {f}' for f in project_info['key_files'][:20]])}

Existing Files (sample):
{chr(10).join([f'- {f}' for f in existing_files[:30]])}

Please suggest missing files that would benefit this project:

📚 **Documentation**: README, CHANGELOG, API docs, etc.
🧪 **Testing**: Test files, test configuration
🔧 **Configuration**: Build files, CI/CD, linting configs
🔒 **Security**: Security policies, .gitignore, etc.
🏃 **Development**: Development helpers, scripts
📦 **Deployment**: Docker files, deployment configs
📄 **Legal**: License, contributing guidelines
🎯 **Quality**: Code quality tools, formatting configs

For each suggestion:
- Explain why it's needed
- Provide template content where helpful
- Indicate priority level (High/Medium/Low)

Focus on files that would have the biggest positive impact on project quality and maintainability."""
    
    status_line("suggesting missing files")
    suggestions = get_ai_response(prompt, include_project_context=False, max_tokens=2500)
    
    if suggestions:
        cleaned_suggestions = clean_ai_response(suggestions)
        
        # Clean output with typewriter effect - NO BORDERS!
        print()
        print_with_rich("="*60, "info")
        print_with_rich("Missing Files Suggestions", "info")
        print_with_rich("="*60, "info")
        print()
        
        # Use typewriter effect for AI response with code block highlighting
        print_ai_response_with_code_blocks(cleaned_suggestions)
        print()
        print_with_rich("="*60, "info")
        
        log_session(f"Missing files analysis: {target_dir}")
    else:
        print_with_rich("Failed to get missing files suggestions", "error")

def project_optimize_command(args: List[str]):
    """AI suggests project optimizations."""
    target_dir = args[0] if args else "."
    # Expand ~ and environment variables
    target_dir = expand_path(target_dir)
    
    if not os.path.isdir(target_dir):
        print_with_rich(f"Directory not found: {target_dir}", "error")
        return
    
    if not runtime.AI_ENABLED:
        print_with_rich("AI disabled - run /setup", "error")
        return
    
    status_line(f"optimize · {os.path.abspath(target_dir)}")
    
    # Comprehensive project analysis
    project_info = _analyze_project_structure(target_dir)
    health_report = _generate_health_report(target_dir)
    dependency_files = _find_dependency_files(target_dir)
    
    # Analyze project size and complexity
    total_size = 0
    large_files = []
    file_types = {}
    all_files = []  # Track all files for debugging
    
    # Properly resolve target directory path
    target_dir_abs = os.path.abspath(target_dir)
    
    for root, dirs, files in os.walk(target_dir_abs):
        # Filter directories but don't skip completely - just common build directories
        dirs[:] = [d for d in dirs if d not in ['node_modules', '__pycache__', 'target', 'build', 'dist', '.git', '__MACOSX']]
        
        for file in files:
            # Skip only Mac metadata files and truly hidden system files
            if file in ['.DS_Store', 'Thumbs.db', 'desktop.ini']:
                continue
            
            file_path = os.path.join(root, file)
            try:
                size = os.path.getsize(file_path)
                total_size += size
                
                # Track relative path
                rel_path = os.path.relpath(file_path, target_dir_abs)
                all_files.append((rel_path, size))
                
                if size > 1024 * 1024:  # Files larger than 1MB
                    large_files.append((rel_path, size))
                
                ext = os.path.splitext(file)[1].lower()
                if ext:  # Only track files with extensions
                    file_types[ext] = file_types.get(ext, 0) + 1
                else:
                    file_types['[no extension]'] = file_types.get('[no extension]', 0) + 1
                
            except (OSError, PermissionError) as e:
                # Log but continue on error
                continue
    
    # Debug output to verify we're finding files
    if len(all_files) == 0:
        print_with_rich("No files found in directory. Check permissions.", "warning")
    else:
        print_with_rich(f"Found {len(all_files)} files totaling {total_size / (1024*1024):.2f} MB", "success")
    
    # Prepare comprehensive analysis for AI with actual file samples
    sample_files_str = "\n".join([f"- {file} ({size} bytes)" for file, size in all_files[:20]])
    if len(all_files) > 20:
        sample_files_str += f"\n... and {len(all_files) - 20} more files"
    
    analysis_data = f"""Project Optimization Analysis:

Project Information:
- Type: {project_info['primary_type']}
- Secondary Types: {', '.join(project_info['secondary_types'])}
- Total Files: {len(all_files)} (found in directory walk)
- Code Files: {project_info['code_files']}
- Total Size: {total_size / (1024*1024):.2f} MB
- Languages: {', '.join([f'{lang} ({count})' for lang, count in project_info['languages'].items()])}

Actual Files in Project:
{sample_files_str}

Health Scores:
- Overall: {health_report['overall_score']}/100
- Documentation: {health_report['documentation']['score']}/100
- Testing: {health_report['testing']['score']}/100
- Structure: {health_report['structure']['score']}/100
- Security: {health_report['security']['score']}/100

Dependency Management:
- Dependency Files: {len(dependency_files)}
- Files: {', '.join(dependency_files) if dependency_files else 'None'}

File Distribution:
{chr(10).join([f'- {ext}: {count} files' for ext, count in sorted(file_types.items(), key=lambda x: x[1], reverse=True)[:10]])}

Large Files (>1MB):
{chr(10).join([f'- {file}: {size/(1024*1024):.1f}MB' for file, size in large_files[:5]]) if large_files else 'None'}"""
    
    prompt = f"""As a software optimization expert, analyze this project and provide comprehensive optimization recommendations:

{analysis_data}

Please provide optimization suggestions in these areas:

🚀 **Performance Optimizations**:
- Build process improvements
- Bundle size reduction
- Runtime performance enhancements
- Database/query optimizations

💾 **Storage & Size Optimizations**:
- File size reduction strategies
- Asset optimization
- Dependency cleanup
- Build artifact optimization

🏧 **Project Structure**:
- Code organization improvements
- Modularization suggestions
- Architecture enhancements
- Design pattern recommendations

🔧 **Development Workflow**:
- Build tool optimizations
- Development environment improvements
- CI/CD pipeline enhancements
- Automation opportunities

📦 **Dependency Management**:
- Dependency optimization
- Version management
- Security updates
- Tree shaking opportunities

🔒 **Security Optimizations**:
- Security hardening
- Vulnerability mitigation
- Best practice implementation

📊 **Monitoring & Analytics**:
- Performance monitoring setup
- Error tracking
- Usage analytics

For each recommendation:
- Explain the benefits
- Provide implementation steps
- Estimate effort and impact
- Suggest tools or techniques

Prioritize recommendations by impact vs effort ratio."""
    
    status_line("project optimization")
    optimization_result = get_ai_response(prompt, include_project_context=False, max_tokens=2500)
    
    if optimization_result:
        cleaned_result = clean_ai_response(optimization_result)
        
        # Clean output with typewriter effect - NO BORDERS!
        print()
        print_with_rich("="*60, "info")
        print_with_rich("Project Optimization Recommendations", "success")
        print_with_rich("="*60, "info")
        print()
        
        # Use typewriter effect for AI response with code block highlighting
        print_ai_response_with_code_blocks(cleaned_result)
        print()
        print_with_rich("="*60, "info")
        
        log_session(f"Project optimization analysis: {target_dir}")
    else:
        print_with_rich("Failed to get optimization recommendations", "error")

