"""Core AI chat / generate commands."""
from __future__ import annotations

import json
import os
import re
from typing import List

from core import runtime
from core.client import get_ai_response
from core.context import build_comprehensive_context
from core.display import print_ai_response, print_with_rich
from core.files import (
    confirm_action,
    get_smart_filename_for_content,
    read_file_content,
    write_file_content,
)
from core.commands.explain import explain_command

def ai_command(prompt):
    """Handles commands sent to the AI."""
    if not prompt or not prompt.strip():
        print_with_rich("Please provide a prompt for the AI.", "info")
        return

    # Enhanced AI prompt with comprehensive context
    comprehensive_context = build_comprehensive_context(cwd=os.getcwd(), include_files=True)
    recent_commands = f"Recent commands: {[cmd['command'] for cmd in runtime.session.commands_history[-3:]] if runtime.session.commands_history else 'None'}"
    
    ai_prompt = f"""You are VritraAI, an intelligent terminal assistant. The user's request is: '{prompt}'

{comprehensive_context}

=== RECENT COMMAND HISTORY ===
{recent_commands}

IMPORTANT: For file creation requests (tools, scripts, programs, web apps, etc.), you MUST respond with ONLY JSON in this exact format:
{{"action": "create_file", "filename": "filename.ext", "content": "complete file content here"}}

CRITICAL RULES FOR FILE CREATION:
1. Respond with ONLY the JSON object - no explanations, no pip install commands, no extra text
2. The content field must contain the COMPLETE, FULLY-FUNCTIONAL, production-ready code
3. For web applications, include ALL necessary code (HTML, CSS, JavaScript) in a SINGLE file
4. NEVER split web apps into separate files - combine everything into one complete HTML file
5. Do NOT mention pip install, dependencies, or setup instructions
6. Do NOT show the JSON to the user - it will be executed automatically
7. The file will be created automatically with the content you provide
8. Make the code complete and ready to use immediately without any modifications

EXAMPLES OF COMPLETE FILE GENERATION:
- Web app request: Create ONE complete HTML file with embedded CSS in <style> and JavaScript in <script> tags
- Python tool: Include ALL functions, error handling, and complete implementation
- Bash script: Include ALL logic, error checking, and full functionality

For directory/folder creation requests, use:
{{"action": "run_command", "command": "mkdir foldername"}}

For other actions:
- Edit file: {{"action": "edit_file", "filename": "name.ext", "changes": "description"}}
- Read file: {{"action": "read_file", "filename": "name.ext"}}
- Run command: {{"action": "run_command", "command": "command to execute"}}
- Search files: {{"action": "search_file", "pattern": "pattern", "target": "path"}}

Examples of requests that need create_file action (RESPOND WITH ONLY JSON):
- "create a python phone lookup tool" - Use JSON with complete code in content
- "generate a network scanner in bash" - Use JSON with complete script
- "make a file that..." - Use JSON with complete code
- "create a tool using python" - Use JSON with complete code
- "build a web app" - Use JSON with ONE complete HTML file containing all HTML, CSS, and JS
- "generate a calculator web app" - Use JSON with complete HTML file with inline CSS and JavaScript

For general questions/explanations, provide helpful text responses.

CRITICAL FORMATTING RULES:
- For text responses (not JSON), provide PLAIN TEXT ONLY - NO MARKDOWN
- NEVER use ```bash, ```python, ```cmd, or any code blocks in text responses
- NEVER use ### headers, ** bold **, * italic *, or [links]()
- NEVER use backticks ` around commands or code
- When suggesting commands, write them as plain text without formatting"""


    generated_response = get_ai_response(ai_prompt)
    if generated_response:
        # First try to parse as JSON for structured actions
        action_handled = False
        try:
            # Clean the response - sometimes it has extra text around JSON
            json_start = generated_response.find('{')
            json_end = generated_response.rfind('}') + 1
            
            if json_start != -1 and json_end > json_start:
                json_part = generated_response[json_start:json_end]
                data = json.loads(json_part)
                action = data.get("action")

                if action == "create_file":
                    filename = data.get("filename")
                    content = data.get("content", "")
                    if filename and content:
                        # Use smart filename generation to prevent overwrites
                        final_filename = get_smart_filename_for_content(filename, content, prompt)
                        
                        if write_file_content(final_filename, content, create_backup=False):
                            print_with_rich(f"✅ Saved code in {final_filename}", "success")
                            # Track in runtime.session
                            if final_filename not in runtime.session.modified_files:
                                runtime.session.modified_files.append(final_filename)
                            action_handled = True
                            return
                    else:
                        print_with_rich("❌ Missing filename or content in AI response", "error")
                    action_handled = True
                    return  # Successfully handled JSON action
            
                elif action == "edit_file":
                    filename = data.get("filename")
                    changes = data.get("changes", "")
                    if filename and changes:
                        print_with_rich("edit_file action unavailable in assistant core (no shell).", "warning")
                    action_handled = True
                    return
                
                elif action == "read_file":
                    filename = data.get("filename")
                    if filename:
                        content = read_file_content(filename)
                        if content is None:
                            print_with_rich(f'Could not read file: {filename}', 'error')
                        else:
                            print_with_rich(f'Contents of {filename}:', 'info')
                            print_ai_response(content, use_typewriter=False)
                    action_handled = True
                    return
                
                elif action == "run_command":
                    command = data.get("command")
                    if command:
                        print_with_rich(f"🤖 VritraAI suggests running: {command}", "info")
                        if confirm_action("Execute this command?"):
                            print_with_rich(f"Suggested command (run in your terminal): {command}", "info")
                        else:
                            print_with_rich("Command cancelled", "info")
                    action_handled = True
                    return
                
                elif action == "search_file":
                    pattern = data.get("pattern")
                    target = data.get("target", ".")
                    if pattern:
                        print_with_rich("search_file action unavailable in assistant core (no shell).", "warning")
                    action_handled = True
                    return
                
                elif action == "explain":
                    command = data.get("command")
                    if command:
                        explain_command([command])
                    action_handled = True
                    return
                else:
                    # If we reach here, JSON was parsed but no valid action found
                    print_with_rich(f"Unknown action in AI response: {action}", "warning")
                    action_handled = True
                    return  # Return after handling unknown action

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            # Not a JSON response or malformed JSON, proceed as normal text response
            pass
        except KeyboardInterrupt:
            # Don't catch KeyboardInterrupt - let it propagate
            raise
        except Exception as e:
            print_with_rich(f"Error parsing AI response: {e}", "error")
            # Continue with text response instead of crashing
            pass

        # Only show text response if no JSON action was handled
        if not action_handled:
            print_ai_response(generated_response)

            # Check for command suggestions in response (more robust pattern)
            command_patterns = [
                r"```(?:bash|sh|cmd|powershell)?\s*\n(.*?)```",  # Standard code blocks
                r"Command:\s*([^\n]+)",                           # "Command: xyz"
                r"Run:\s*([^\n]+)",                              # "Run: xyz"
                r"Execute:\s*([^\n]+)",                          # "Execute: xyz"
                r"Try:\s*([^\n]+)",                              # "Try: xyz"
                r"Use:\s*([^\n]+)",                              # "Use: xyz"
            ]
            
            suggested_command = None
            for pattern in command_patterns:
                match = re.search(pattern, generated_response, re.DOTALL | re.IGNORECASE)
                if match:
                    suggested_command = match.group(1).strip()
                    # Filter out overly simple or generic suggestions
                    if len(suggested_command) > 2 and not suggested_command.lower() in ['cd', 'ls', 'dir', 'help']:
                        break
                    suggested_command = None

            if suggested_command:
                # Clean up the suggested command
                command_to_execute = suggested_command.strip()
                # Remove any remaining backticks or formatting
                command_to_execute = re.sub(r'^`+|`+$', '', command_to_execute)
                
                print_with_rich("\nThe AI has suggested a command.", "info")
                print_with_rich(f"Suggested: {command_to_execute}", "warning")
                # No shell in assistant core - surface the command only
                print_with_rich(
                    f"Run in your terminal: {command_to_execute}",
                    "info",
                )

def generate_command(args: List[str]):
    """Generate content using AI."""
    if not runtime.AI_ENABLED:
        print_with_rich("AI is required for content generation", "warning")
        return
    
    if not args:
        print_with_rich("Usage: generate <description>", "info")
        print_with_rich("Examples: generate 'README for Python project', generate 'bash script to backup files'", "info")
        return
    
    description = " ".join(args)
    ai_command(f"generate {description}")

