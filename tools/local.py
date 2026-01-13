"""Local Tools for GLM CLI

Implements Read, Write, Bash, Glob, Grep tools.
"""

import asyncio
import os
import glob as glob_module
import re
from pathlib import Path
from typing import Optional, List
from .base import Tool, ToolResult, ToolParameter, ToolParameterType


class ReadTool(Tool):
    """Read file contents"""

    name = "read_file"
    description = "Read the contents of a file. Returns the file content as text."
    parameters = [
        ToolParameter(
            name="path",
            type=ToolParameterType.STRING,
            description="The absolute path to the file to read",
            required=True
        ),
        ToolParameter(
            name="offset",
            type=ToolParameterType.INTEGER,
            description="Line number to start reading from (1-based)",
            required=False,
            default=1
        ),
        ToolParameter(
            name="limit",
            type=ToolParameterType.INTEGER,
            description="Maximum number of lines to read",
            required=False
        )
    ]

    async def execute(self, path: str, offset: int = 1, limit: Optional[int] = None, **kwargs) -> ToolResult:
        """Read file contents"""
        try:
            path = os.path.expanduser(path)

            if not os.path.exists(path):
                return ToolResult(
                    success=False,
                    content="",
                    error=f"File not found: {path}",
                    is_error=True
                )

            if os.path.isdir(path):
                return ToolResult(
                    success=False,
                    content="",
                    error=f"Path is a directory: {path}",
                    is_error=True
                )

            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()

            # Apply offset (1-based)
            start_idx = max(0, offset - 1)
            lines = lines[start_idx:]

            # Apply limit
            if limit:
                lines = lines[:limit]

            # Format with line numbers
            result_lines = []
            for i, line in enumerate(lines, start=offset):
                result_lines.append(f"{i:6}\t{line.rstrip()}")

            return ToolResult(
                success=True,
                content="\n".join(result_lines)
            )

        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=str(e),
                is_error=True
            )


class WriteTool(Tool):
    """Write content to a file"""

    name = "write_file"
    description = "Write content to a file. Creates the file if it doesn't exist."
    parameters = [
        ToolParameter(
            name="path",
            type=ToolParameterType.STRING,
            description="The absolute path to the file to write",
            required=True
        ),
        ToolParameter(
            name="content",
            type=ToolParameterType.STRING,
            description="The content to write to the file",
            required=True
        )
    ]

    async def execute(self, path: str, content: str, **kwargs) -> ToolResult:
        """Write content to file"""
        try:
            path = os.path.expanduser(path)

            # Create parent directories if needed
            parent = os.path.dirname(path)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)

            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)

            return ToolResult(
                success=True,
                content=f"Successfully wrote {len(content)} bytes to {path}"
            )

        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=str(e),
                is_error=True
            )


class EditTool(Tool):
    """Edit file by replacing text"""

    name = "edit_file"
    description = "Edit a file by replacing old_string with new_string."
    parameters = [
        ToolParameter(
            name="path",
            type=ToolParameterType.STRING,
            description="The absolute path to the file to edit",
            required=True
        ),
        ToolParameter(
            name="old_string",
            type=ToolParameterType.STRING,
            description="The text to replace",
            required=True
        ),
        ToolParameter(
            name="new_string",
            type=ToolParameterType.STRING,
            description="The replacement text",
            required=True
        ),
        ToolParameter(
            name="replace_all",
            type=ToolParameterType.BOOLEAN,
            description="Replace all occurrences (default: False)",
            required=False,
            default=False
        )
    ]

    async def execute(self, path: str, old_string: str, new_string: str,
                      replace_all: bool = False, **kwargs) -> ToolResult:
        """Edit file by replacing text"""
        try:
            path = os.path.expanduser(path)

            if not os.path.exists(path):
                return ToolResult(
                    success=False,
                    content="",
                    error=f"File not found: {path}",
                    is_error=True
                )

            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Count occurrences
            count = content.count(old_string)
            if count == 0:
                return ToolResult(
                    success=False,
                    content="",
                    error=f"String not found in file: {old_string[:50]}...",
                    is_error=True
                )

            if count > 1 and not replace_all:
                return ToolResult(
                    success=False,
                    content="",
                    error=f"String found {count} times. Use replace_all=True or provide more context.",
                    is_error=True
                )

            # Replace
            if replace_all:
                new_content = content.replace(old_string, new_string)
            else:
                new_content = content.replace(old_string, new_string, 1)

            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            return ToolResult(
                success=True,
                content=f"Successfully edited {path} ({count} replacement(s))"
            )

        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=str(e),
                is_error=True
            )


class BashTool(Tool):
    """Execute bash commands"""

    name = "bash"
    description = "Execute a bash command and return the output."
    parameters = [
        ToolParameter(
            name="command",
            type=ToolParameterType.STRING,
            description="The bash command to execute",
            required=True
        ),
        ToolParameter(
            name="timeout",
            type=ToolParameterType.INTEGER,
            description="Timeout in seconds (default: 120)",
            required=False,
            default=120
        ),
        ToolParameter(
            name="cwd",
            type=ToolParameterType.STRING,
            description="Working directory for the command",
            required=False
        )
    ]

    # Commands that should be blocked for safety
    BLOCKED_COMMANDS = [
        # Destructive file operations
        "rm -rf /",
        "rm -rf /*",
        "rm -rf ~",
        "rm -rf $HOME",
        # Disk operations
        "mkfs",
        "dd if=/dev/zero",
        "dd if=/dev/random",
        "> /dev/sda",
        "> /dev/nvme",
        # Dangerous permissions
        "chmod -R 777 /",
        "chmod 777 /",
        "chown -R",
        # System destruction
        ":(){ :|:& };:",  # Fork bomb
        "mv /* /dev/null",
        "cat /dev/zero >",
        # Network attacks
        "nc -l",  # Listening netcat
        # Credential theft
        "cat /etc/shadow",
        "cat /etc/passwd",
        # History manipulation
        "history -c",
        "shred",
    ]

    # Patterns to warn about (not block)
    WARNING_PATTERNS = [
        "sudo ",
        "chmod 777",
        "> /dev/",
        "curl | bash",
        "wget | bash",
        "eval ",
    ]

    async def execute(self, command: str, timeout: int = 120,
                      cwd: Optional[str] = None, **kwargs) -> ToolResult:
        """Execute bash command"""
        try:
            # Safety check - normalize whitespace for better pattern matching
            normalized_cmd = ' '.join(command.split())  # Collapse multiple spaces
            for blocked in self.BLOCKED_COMMANDS:
                normalized_blocked = ' '.join(blocked.split())
                if normalized_blocked in normalized_cmd:
                    return ToolResult(
                        success=False,
                        content="",
                        error=f"Blocked dangerous command pattern: {blocked}",
                        is_error=True
                    )

            # Expand paths
            if cwd:
                cwd = os.path.expanduser(cwd)

            # Execute command
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd or os.getcwd()
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return ToolResult(
                    success=False,
                    content="",
                    error=f"Command timed out after {timeout} seconds",
                    is_error=True
                )

            output = stdout.decode('utf-8', errors='replace')
            error_output = stderr.decode('utf-8', errors='replace')

            # Combine output
            result = output
            if error_output:
                result += f"\n[stderr]\n{error_output}"

            # Truncate if too long
            if len(result) > 30000:
                result = result[:30000] + "\n...[truncated]"

            if process.returncode != 0:
                return ToolResult(
                    success=False,
                    content=result,
                    error=f"Command exited with code {process.returncode}",
                    is_error=True
                )

            return ToolResult(success=True, content=result)

        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=str(e),
                is_error=True
            )


class GlobTool(Tool):
    """Find files matching glob pattern"""

    name = "glob"
    description = "Find files matching a glob pattern."
    parameters = [
        ToolParameter(
            name="pattern",
            type=ToolParameterType.STRING,
            description="Glob pattern (e.g., '**/*.py', 'src/**/*.ts')",
            required=True
        ),
        ToolParameter(
            name="path",
            type=ToolParameterType.STRING,
            description="Base directory to search in",
            required=False
        )
    ]

    async def execute(self, pattern: str, path: Optional[str] = None, **kwargs) -> ToolResult:
        """Find files matching glob pattern"""
        try:
            base_path = os.path.expanduser(path) if path else os.getcwd()

            # Make pattern relative to base path
            full_pattern = os.path.join(base_path, pattern)

            # Find matching files
            matches = glob_module.glob(full_pattern, recursive=True)

            # Sort by modification time (newest first)
            # Use try-except to handle files deleted between glob and sort
            def safe_getmtime(path):
                try:
                    return os.path.getmtime(path)
                except (OSError, FileNotFoundError):
                    return 0
            matches.sort(key=safe_getmtime, reverse=True)

            if not matches:
                return ToolResult(
                    success=True,
                    content="No files found matching pattern"
                )

            # Limit results
            total_count = len(matches)
            if total_count > 100:
                matches = matches[:100]
                result = "\n".join(matches) + f"\n...(showing first 100 of {total_count} matches)"
            else:
                result = "\n".join(matches)

            return ToolResult(success=True, content=result)

        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=str(e),
                is_error=True
            )


class GrepTool(Tool):
    """Search for pattern in files"""

    name = "grep"
    description = "Search for a pattern in files using regex."
    parameters = [
        ToolParameter(
            name="pattern",
            type=ToolParameterType.STRING,
            description="Regex pattern to search for",
            required=True
        ),
        ToolParameter(
            name="path",
            type=ToolParameterType.STRING,
            description="File or directory to search in",
            required=False
        ),
        ToolParameter(
            name="glob",
            type=ToolParameterType.STRING,
            description="Glob pattern to filter files (e.g., '*.py')",
            required=False
        ),
        ToolParameter(
            name="case_insensitive",
            type=ToolParameterType.BOOLEAN,
            description="Case insensitive search",
            required=False,
            default=False
        )
    ]

    async def execute(self, pattern: str, path: Optional[str] = None,
                      glob: Optional[str] = None, case_insensitive: bool = False,
                      **kwargs) -> ToolResult:
        """Search for pattern in files"""
        try:
            base_path = os.path.expanduser(path) if path else os.getcwd()

            # Compile regex
            flags = re.IGNORECASE if case_insensitive else 0
            regex = re.compile(pattern, flags)

            results = []

            # Get files to search
            if os.path.isfile(base_path):
                files = [base_path]
            else:
                if glob:
                    file_pattern = os.path.join(base_path, "**", glob)
                else:
                    file_pattern = os.path.join(base_path, "**", "*")
                files = glob_module.glob(file_pattern, recursive=True)
                files = [f for f in files if os.path.isfile(f)]

            # Search in files
            for file_path in files[:100]:  # Limit files
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                results.append(f"{file_path}:{line_num}: {line.rstrip()}")
                                if len(results) >= 500:  # Limit results
                                    break
                except Exception:
                    continue

                if len(results) >= 500:
                    break

            if not results:
                return ToolResult(
                    success=True,
                    content=f"No matches found for pattern: {pattern}"
                )

            result = "\n".join(results)
            if len(results) >= 500:
                result += "\n...(truncated at 500 matches)"

            return ToolResult(success=True, content=result)

        except re.error as e:
            return ToolResult(
                success=False,
                content="",
                error=f"Invalid regex pattern: {e}",
                is_error=True
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=str(e),
                is_error=True
            )


# Register all local tools
def register_local_tools(registry):
    """Register all local tools with the registry"""
    from .base import Tool
    registry.register(ReadTool())
    registry.register(WriteTool())
    registry.register(EditTool())
    registry.register(BashTool())
    registry.register(GlobTool())
    registry.register(GrepTool())


# Export EditTool
__all__ = ['ReadTool', 'WriteTool', 'EditTool', 'BashTool', 'GlobTool', 'GrepTool', 'register_local_tools']
