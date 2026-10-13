from __future__ import annotations

from pydantic import BaseModel, Field

from .base import MCPToolServer, ToolCall


class DatabaseQuery(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=100)


class DatabaseToolServer(MCPToolServer):
    def execute(self, call: ToolCall) -> dict[str, object]:
        payload = DatabaseQuery.model_validate(call.arguments)
        return {
            "status": "ok",
            "tool": "database",
            "query": payload.query,
            "limit": payload.limit,
            "rows": [],
        }
