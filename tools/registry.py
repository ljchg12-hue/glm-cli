"""Tool Registry for GLM CLI

Central registry for all tools (local and MCP).
"""

from typing import Dict, List, Optional, Any
from .base import Tool, ToolResult


class ToolRegistry:
    """Central registry for all tools"""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._mcp_tools: Dict[str, Dict[str, Any]] = {}

    def register(self, tool: Tool) -> None:
        """Register a local tool"""
        self._tools[tool.name] = tool

    def register_mcp_tool(self, server_name: str, tool_name: str, schema: Dict[str, Any]) -> None:
        """Register an MCP tool"""
        full_name = f"mcp__{server_name}__{tool_name}"
        self._mcp_tools[full_name] = {
            "server": server_name,
            "name": tool_name,
            "schema": schema
        }

    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name"""
        return self._tools.get(name)

    def get_mcp_tool(self, name: str) -> Optional[Dict[str, Any]]:
        """Get an MCP tool by name"""
        return self._mcp_tools.get(name)

    def list_tools(self) -> List[str]:
        """List all registered tools"""
        return list(self._tools.keys()) + list(self._mcp_tools.keys())

    def get_all_schemas(self) -> List[Dict[str, Any]]:
        """Get schemas for all tools (for API)"""
        schemas = []

        # Local tools
        for tool in self._tools.values():
            schemas.append(tool.get_schema())

        # MCP tools
        for mcp_tool in self._mcp_tools.values():
            schemas.append(mcp_tool["schema"])

        return schemas

    async def execute(self, tool_name: str, **kwargs) -> ToolResult:
        """Execute a tool by name"""
        # Check local tools first
        tool = self.get_tool(tool_name)
        if tool:
            error = tool.validate_params(**kwargs)
            if error:
                return ToolResult(success=False, content="", error=error, is_error=True)
            return await tool.execute(**kwargs)

        # Check MCP tools
        mcp_tool = self.get_mcp_tool(tool_name)
        if mcp_tool:
            # MCP tools are executed via MCP client
            return ToolResult(
                success=False,
                content="",
                error="MCP tool execution requires MCP client",
                is_error=True
            )

        return ToolResult(
            success=False,
            content="",
            error=f"Unknown tool: {tool_name}",
            is_error=True
        )

    def is_mcp_tool(self, tool_name: str) -> bool:
        """Check if a tool is an MCP tool"""
        return tool_name.startswith("mcp__")


# Global registry instance
tool_registry = ToolRegistry()
