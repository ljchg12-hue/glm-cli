"""GLM CLI Tool System - Claude Code Style

Provides local tools (Read, Write, Bash) and MCP integration.
"""

from .registry import ToolRegistry, tool_registry
from .base import Tool, ToolResult, ToolParameter
from .local import ReadTool, WriteTool, EditTool, BashTool, GlobTool, GrepTool

__all__ = [
    'ToolRegistry',
    'tool_registry',
    'Tool',
    'ToolResult',
    'ToolParameter',
    'ReadTool',
    'WriteTool',
    'BashTool',
    'GlobTool',
    'GrepTool',
    'EditTool',
]
