"""GLM API communication module with tool_use support

Uses Z.AI's Anthropic-compatible API format with tool calling.
"""

import asyncio
import json
import time
from typing import AsyncGenerator, Dict, List, Optional, Any, Tuple
import aiohttp

from config import config


class GLMAPIError(Exception):
    """GLM API Error"""
    pass


class GLMAPI:
    """GLM API Client with tool_use support (Anthropic-compatible)"""

    # Z.AI API configuration
    DEFAULT_BASE_URL = "https://api.z.ai/api/anthropic/v1"
    DEFAULT_MODEL = "glm-4.7"
    ANTHROPIC_VERSION = "2023-06-01"

    def __init__(self):
        self.api_key = config.get_api_key()
        self.api_base = config.get("api_base", self.DEFAULT_BASE_URL)
        self.model = config.get("model", self.DEFAULT_MODEL)
        self._session: Optional[aiohttp.ClientSession] = None
        self._available_models: List[Dict] = []
        self._last_model_check: float = 0

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close the session"""
        if self._session and not self._session.closed:
            await self._session.close()

    def _get_headers(self) -> Dict[str, str]:
        """Get API headers for Anthropic-compatible API"""
        return {
            "x-api-key": self.api_key,
            "anthropic-version": self.ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }

    async def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """Chat completion with tool support (non-streaming)"""
        if not self.api_key:
            raise GLMAPIError("API key not found. Set ZAI_API_KEY or GLM_API_KEY environment variable.")

        session = await self._get_session()
        url = f"{self.api_base}/messages"

        # Convert to Anthropic format
        system_msg = None
        api_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_msg = msg["content"]
            else:
                api_messages.append(msg)

        payload = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "stream": False,
        }

        if system_msg:
            payload["system"] = system_msg

        if tools:
            payload["tools"] = tools

        try:
            async with session.post(url, headers=self._get_headers(), json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise GLMAPIError(f"API Error ({response.status}): {error_text}")

                data = await response.json()
                return data

        except aiohttp.ClientError as e:
            raise GLMAPIError(f"Connection error: {e}")

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """Stream chat completion using Anthropic-compatible API"""
        if not self.api_key:
            raise GLMAPIError("API key not found. Set ZAI_API_KEY or GLM_API_KEY environment variable.")

        session = await self._get_session()
        url = f"{self.api_base}/messages"

        # Convert to Anthropic format (system message separate)
        system_msg = None
        api_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                api_messages.append(msg)

        payload = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "stream": True,
        }

        if system_msg:
            payload["system"] = system_msg

        try:
            async with session.post(url, headers=self._get_headers(), json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise GLMAPIError(f"API Error ({response.status}): {error_text}")

                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if not line:
                        continue

                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            event_type = chunk.get("type", "")

                            # Handle Anthropic streaming format
                            if event_type == "content_block_delta":
                                delta = chunk.get("delta", {})
                                text = delta.get("text", "")
                                if text:
                                    yield text
                            elif event_type == "message_delta":
                                # End of message
                                pass
                        except json.JSONDecodeError:
                            continue

                    elif line.startswith("event: "):
                        # SSE event line, skip
                        continue

        except aiohttp.ClientError as e:
            raise GLMAPIError(f"Connection error: {e}")

    async def chat_stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[Tuple[str, Optional[Dict[str, Any]]], None]:
        """Stream chat completion with tool support

        Yields tuples of (content_type, content):
        - ("text", "some text") for text content
        - ("tool_use", {"id": ..., "name": ..., "input": ...}) for tool calls
        - ("end", None) when message is complete
        """
        if not self.api_key:
            raise GLMAPIError("API key not found. Set ZAI_API_KEY or GLM_API_KEY environment variable.")

        session = await self._get_session()
        url = f"{self.api_base}/messages"

        # Convert to Anthropic format
        system_msg = None
        api_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_msg = msg["content"]
            else:
                api_messages.append(msg)

        payload = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "stream": True,
        }

        if system_msg:
            payload["system"] = system_msg

        if tools:
            payload["tools"] = tools

        try:
            async with session.post(url, headers=self._get_headers(), json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise GLMAPIError(f"API Error ({response.status}): {error_text}")

                current_tool_use = None

                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if not line:
                        continue

                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data)
                            event_type = chunk.get("type", "")

                            if event_type == "content_block_start":
                                content_block = chunk.get("content_block", {})
                                if content_block.get("type") == "tool_use":
                                    current_tool_use = {
                                        "id": content_block.get("id", ""),
                                        "name": content_block.get("name", ""),
                                        "input": {}
                                    }

                            elif event_type == "content_block_delta":
                                delta = chunk.get("delta", {})
                                delta_type = delta.get("type", "")

                                if delta_type == "text_delta":
                                    text = delta.get("text", "")
                                    if text:
                                        yield ("text", text)

                                elif delta_type == "input_json_delta":
                                    # Accumulate tool input JSON
                                    if current_tool_use:
                                        partial_json = delta.get("partial_json", "")
                                        # This is a partial JSON, we need to accumulate
                                        if "partial_input" not in current_tool_use:
                                            current_tool_use["partial_input"] = ""
                                        current_tool_use["partial_input"] += partial_json

                            elif event_type == "content_block_stop":
                                if current_tool_use:
                                    # Parse accumulated JSON
                                    if "partial_input" in current_tool_use:
                                        try:
                                            current_tool_use["input"] = json.loads(current_tool_use["partial_input"])
                                        except json.JSONDecodeError:
                                            current_tool_use["input"] = {}
                                        del current_tool_use["partial_input"]

                                    yield ("tool_use", current_tool_use)
                                    current_tool_use = None

                            elif event_type == "message_stop":
                                yield ("end", None)

                        except json.JSONDecodeError:
                            continue

        except aiohttp.ClientError as e:
            raise GLMAPIError(f"Connection error: {e}")

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Non-streaming chat completion"""
        if not self.api_key:
            raise GLMAPIError("API key not found. Set ZAI_API_KEY or GLM_API_KEY environment variable.")

        session = await self._get_session()
        url = f"{self.api_base}/messages"

        # Convert to Anthropic format
        system_msg = None
        api_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                api_messages.append(msg)

        payload = {
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "stream": False,
        }

        if system_msg:
            payload["system"] = system_msg

        try:
            async with session.post(url, headers=self._get_headers(), json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise GLMAPIError(f"API Error ({response.status}): {error_text}")

                data = await response.json()
                # Anthropic format response
                content = data.get("content", [])
                if content and len(content) > 0:
                    return content[0].get("text", "")
                return ""
        except aiohttp.ClientError as e:
            raise GLMAPIError(f"Connection error: {e}")

    async def get_available_models(self, force_refresh: bool = False) -> List[Dict]:
        """Get available models (Z.AI API)"""
        return [
            {"id": "glm-4.7", "name": "GLM-4.7", "owned_by": "zhipu"},
            {"id": "glm-4-plus", "name": "GLM-4 Plus", "owned_by": "zhipu"},
            {"id": "glm-4", "name": "GLM-4", "owned_by": "zhipu"},
            {"id": "glm-4-flash", "name": "GLM-4 Flash", "owned_by": "zhipu"},
        ]

    async def check_model_updates(self) -> Optional[Dict[str, Any]]:
        """Check for model updates (placeholder for Z.AI)"""
        # Z.AI uses fixed model mapping, no updates to check
        return None


# Global API instance
api = GLMAPI()
