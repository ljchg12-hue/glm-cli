"""MCP Client for GLM CLI

Connects to MCP servers and provides tool integration.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from .base import ToolResult


@dataclass
class MCPServer:
    """MCP Server configuration"""
    name: str
    command: str
    args: List[str]
    env: Optional[Dict[str, str]] = None


class MCPClient:
    """Client for Model Context Protocol servers"""

    # Connection settings
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0  # seconds
    REQUEST_TIMEOUT = 30  # seconds

    def __init__(self):
        self.servers: Dict[str, MCPServer] = {}
        self.connections: Dict[str, Tuple[asyncio.StreamReader, asyncio.StreamWriter, asyncio.subprocess.Process]] = {}
        self.tools: Dict[str, Dict[str, Any]] = {}
        self._request_id = 0

    def load_config(self, config_path: str = "~/.mcp.json") -> None:
        """Load MCP server configuration"""
        config_path = os.path.expanduser(config_path)

        if not os.path.exists(config_path):
            return

        try:
            with open(config_path, 'r') as f:
                config = json.load(f)

            for name, server_config in config.get("mcpServers", {}).items():
                self.servers[name] = MCPServer(
                    name=name,
                    command=server_config.get("command", ""),
                    args=server_config.get("args", []),
                    env=server_config.get("env")
                )
        except Exception as e:
            print(f"Error loading MCP config: {e}", file=sys.stderr)

    async def connect(self, server_name: str, retry: bool = True) -> bool:
        """Connect to an MCP server with retry logic

        Args:
            server_name: Name of the server to connect to
            retry: Whether to retry on failure (default: True)

        Returns:
            True if connected successfully, False otherwise
        """
        if server_name not in self.servers:
            return False

        if server_name in self.connections:
            return True  # Already connected

        server = self.servers[server_name]
        max_attempts = self.MAX_RETRIES if retry else 1

        for attempt in range(max_attempts):
            try:
                # Prepare environment
                env = os.environ.copy()
                if server.env:
                    env.update(server.env)

                # Start the server process
                process = await asyncio.create_subprocess_exec(
                    server.command,
                    *server.args,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env
                )

                # Store connection
                self.connections[server_name] = (
                    process.stdout,
                    process.stdin,
                    process
                )

                # Initialize the connection
                await self._initialize(server_name)

                # List available tools
                await self._list_tools(server_name)

                return True

            except Exception as e:
                # Clean up failed connection
                if server_name in self.connections:
                    del self.connections[server_name]

                if attempt < max_attempts - 1:
                    print(f"Connection attempt {attempt + 1} failed, retrying in {self.RETRY_DELAY}s...", file=sys.stderr)
                    await asyncio.sleep(self.RETRY_DELAY)
                else:
                    print(f"Error connecting to MCP server {server_name} after {max_attempts} attempts: {e}", file=sys.stderr)

        return False

    async def disconnect(self, server_name: str) -> None:
        """Disconnect from an MCP server"""
        if server_name not in self.connections:
            return

        _, writer, process = self.connections[server_name]

        try:
            writer.close()
            await writer.wait_closed()
            process.terminate()
            await process.wait()
        except Exception:
            pass

        del self.connections[server_name]

        # Remove tools from this server
        self.tools = {
            k: v for k, v in self.tools.items()
            if not k.startswith(f"mcp__{server_name}__")
        }

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers"""
        server_names = list(self.connections.keys())
        for name in server_names:
            await self.disconnect(name)

    def _get_request_id(self) -> int:
        """Get next request ID"""
        self._request_id += 1
        return self._request_id

    async def _send_request(self, server_name: str, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send JSON-RPC request to MCP server"""
        if server_name not in self.connections:
            raise RuntimeError(f"Not connected to server: {server_name}")

        reader, writer, _ = self.connections[server_name]

        request = {
            "jsonrpc": "2.0",
            "id": self._get_request_id(),
            "method": method,
            "params": params or {}
        }

        # Send request
        request_str = json.dumps(request) + "\n"
        writer.write(request_str.encode('utf-8'))
        await writer.drain()

        # Read response
        response_line = await asyncio.wait_for(reader.readline(), timeout=30)
        response = json.loads(response_line.decode('utf-8'))

        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")

        return response.get("result", {})

    async def _initialize(self, server_name: str) -> None:
        """Initialize MCP connection"""
        await self._send_request(server_name, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
                "prompts": {},
                "resources": {},
                "sampling": {}
            },
            "clientInfo": {
                "name": "glm-cli",
                "version": "1.2.0"
            }
        })

        # Send initialized notification
        if server_name in self.connections:
            _, writer, _ = self.connections[server_name]
            notification = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            writer.write((json.dumps(notification) + "\n").encode('utf-8'))
            await writer.drain()

    async def _list_tools(self, server_name: str) -> List[Dict[str, Any]]:
        """List tools from an MCP server"""
        result = await self._send_request(server_name, "tools/list")
        tools = result.get("tools", [])

        # Register tools
        for tool in tools:
            tool_name = f"mcp__{server_name}__{tool['name']}"
            self.tools[tool_name] = {
                "server": server_name,
                "original_name": tool["name"],
                "schema": {
                    "name": tool_name,
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("inputSchema", {"type": "object", "properties": {}})
                }
            }

        return tools

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """Call an MCP tool"""
        if tool_name not in self.tools:
            return ToolResult(
                success=False,
                content="",
                error=f"Unknown MCP tool: {tool_name}",
                is_error=True
            )

        tool_info = self.tools[tool_name]
        server_name = tool_info["server"]
        original_name = tool_info["original_name"]

        if server_name not in self.connections:
            # Try to connect
            if not await self.connect(server_name):
                return ToolResult(
                    success=False,
                    content="",
                    error=f"Could not connect to MCP server: {server_name}",
                    is_error=True
                )

        try:
            result = await self._send_request(server_name, "tools/call", {
                "name": original_name,
                "arguments": arguments
            })

            # Parse result content
            content = result.get("content", [])
            if content:
                # Handle different content types
                text_parts = []
                for item in content:
                    if item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    elif item.get("type") == "image":
                        text_parts.append(f"[Image: {item.get('mimeType', 'unknown')}]")

                return ToolResult(
                    success=True,
                    content="\n".join(text_parts)
                )

            return ToolResult(success=True, content="")

        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=str(e),
                is_error=True
            )

    def get_all_schemas(self) -> List[Dict[str, Any]]:
        """Get schemas for all MCP tools"""
        return [tool["schema"] for tool in self.tools.values()]

    def list_servers(self) -> List[str]:
        """List configured MCP servers"""
        return list(self.servers.keys())

    def list_connected(self) -> List[str]:
        """List connected MCP servers"""
        return list(self.connections.keys())


# Global MCP client instance
mcp_client = MCPClient()
