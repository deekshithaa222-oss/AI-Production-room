from __future__ import annotations

from abc import ABC, abstractmethod
from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, object] = Field(default_factory=dict)


class MCPToolServer(ABC):
    """Isolated server boundary for external tools."""

    @abstractmethod
    def execute(self, call: ToolCall) -> dict[str, object]:
        raise NotImplementedError
