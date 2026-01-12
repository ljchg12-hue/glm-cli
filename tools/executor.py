"""Tool Executor for GLM CLI

Handles tool execution loop and result formatting.
"""

import json
from typing import Any, Dict, List, Optional, Tuple
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from .registry import tool_registry
from .local import register_local_tools
from .mcp_client import mcp_client
from .base import ToolResult

console = Console()


class ToolExecutor:
    """Executes tools and manages the tool loop"""

    def __init__(self):
        self.enabled = True
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize tool system"""
        if self._initialized:
            return

        # Register local tools
        register_local_tools(tool_registry)

        # Load MCP configuration
        mcp_client.load_config()

        self._initialized = True

    def get_all_tools(self) -> List[Dict[str, Any]]:
        """Get all available tool schemas"""
        schemas = tool_registry.get_all_schemas()
        schemas.extend(mcp_client.get_all_schemas())
        return schemas

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """Execute a single tool"""
        # Check if it's an MCP tool
        if tool_name.startswith("mcp__"):
            return await mcp_client.call_tool(tool_name, arguments)

        # Execute local tool
        return await tool_registry.execute(tool_name, **arguments)

    def display_tool_use(self, tool_name: str, arguments: Dict[str, Any]) -> None:
        """Display tool use to user"""
        args_str = json.dumps(arguments, indent=2, ensure_ascii=False)
        console.print(f"\n[bold cyan]🔧 Using tool:[/bold cyan] {tool_name}")
        if len(args_str) < 200:
            console.print(f"[dim]{args_str}[/dim]")

    def display_tool_result(self, result: ToolResult) -> None:
        """Display tool result to user"""
        if result.is_error:
            console.print(f"[bold red]❌ Error:[/bold red] {result.error}")
        else:
            content = str(result.content)
            if len(content) > 500:
                content = content[:500] + "...[truncated]"
            console.print(f"[dim]{content}[/dim]")

    def format_tool_result_for_api(self, tool_use_id: str, result: ToolResult) -> Dict[str, Any]:
        """Format tool result for API message"""
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": result.content if not result.is_error else result.error,
            "is_error": result.is_error
        }

    async def connect_mcp_server(self, server_name: str) -> bool:
        """Connect to an MCP server"""
        return await mcp_client.connect(server_name)

    async def disconnect_all_mcp(self) -> None:
        """Disconnect from all MCP servers"""
        await mcp_client.disconnect_all()

    def list_mcp_servers(self) -> List[str]:
        """List available MCP servers"""
        return mcp_client.list_servers()

    def list_connected_mcp(self) -> List[str]:
        """List connected MCP servers"""
        return mcp_client.list_connected()


# Global executor instance
tool_executor = ToolExecutor()
