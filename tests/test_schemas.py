from pydantic import ValidationError

from src.core.orchestrator import InferenceRequest
from src.mcp.servers.base import ToolCall
from src.mcp.servers.database_server import DatabaseToolServer


def test_inference_request_schema_boundaries():
    request = InferenceRequest(prompt="Summarize the incident", max_tokens=512)
    assert request.max_tokens == 512

    try:
        InferenceRequest(prompt="", max_tokens=-1)
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected validation error for invalid request structure")


def test_tool_call_arguments_are_enforced():
    call = ToolCall(name="database", arguments={"query": "SELECT 1", "limit": 25})
    assert call.name == "database"
    assert call.arguments["limit"] == 25

    try:
        DatabaseToolServer().execute(ToolCall(name="database", arguments={"query": "SELECT 1", "limit": 500}))
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected validation error for oversize tool args")
