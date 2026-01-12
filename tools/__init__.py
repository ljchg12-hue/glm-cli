"""GLM CLI Tool System - Claude Code Style

Provides local tools (Read, Write, Bash), MCP integration, agents, and skills.
"""

from .registry import ToolRegistry, tool_registry
from .base import Tool, ToolResult, ToolParameter
from .local import ReadTool, WriteTool, EditTool, BashTool, GlobTool, GrepTool
from .agents import agent_registry, Agent
from .skills import skill_registry, Skill

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
    'agent_registry',
    'Agent',
    'skill_registry',
    'Skill',
]
