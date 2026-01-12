"""Base Tool Interface for GLM CLI

Defines the common interface for all tools.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class ToolParameterType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


@dataclass
class ToolParameter:
    """Tool parameter definition"""
    name: str
    type: ToolParameterType
    description: str
    required: bool = False
    default: Any = None
    enum: Optional[List[str]] = None


@dataclass
class ToolResult:
    """Result of tool execution"""
    success: bool
    content: Any
    error: Optional[str] = None
    is_error: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for API response"""
        if self.is_error:
            return {
                "type": "error",
                "error": self.error or str(self.content)
            }
        return {
            "type": "text",
            "text": str(self.content) if not isinstance(self.content, str) else self.content
        }


class Tool(ABC):
    """Base class for all tools"""

    name: str = ""
    description: str = ""
    parameters: List[ToolParameter] = []

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters"""
        pass

    def get_schema(self) -> Dict[str, Any]:
        """Get Anthropic-compatible tool schema"""
        properties = {}
        required = []

        for param in self.parameters:
            prop = {
                "type": param.type.value,
                "description": param.description
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default

            properties[param.name] = prop

            if param.required:
                required.append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }

    def validate_params(self, **kwargs) -> Optional[str]:
        """Validate parameters. Returns error message if invalid."""
        for param in self.parameters:
            if param.required and param.name not in kwargs:
                return f"Missing required parameter: {param.name}"
        return None
