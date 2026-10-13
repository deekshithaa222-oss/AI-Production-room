from __future__ import annotations

from pydantic import BaseModel, Field

from .base import MCPToolServer, ToolCall


class RunbookQuery(BaseModel):
    incident_id: str = Field(min_length=1, max_length=64)
    step_limit: int = Field(default=3, ge=1, le=20)


class RunbookToolServer(MCPToolServer):
    def execute(self, call: ToolCall) -> dict[str, object]:
        payload = RunbookQuery.model_validate(call.arguments)
        return {
            "status": "ok",
            "tool": "runbook",
            "incident_id": payload.incident_id,
            "steps": ["assess blast radius", "restart degraded service", "verify recovery"],
            "step_limit": payload.step_limit,
        }
