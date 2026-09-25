import json
import uuid
from types import TracebackType
from typing import Any

from fastmcp import Client, FastMCP

from app.mcp_server.context import current_session, current_turn


class ToolCallResult:
    def __init__(self, text: str, is_error: bool, data: dict[str, Any] | None) -> None:
        self.text = text
        self.is_error = is_error
        self.data = data


class PlanToolClient:
    def __init__(self, mcp: FastMCP) -> None:
        self._client = Client(mcp)
        self._defs: list[dict[str, Any]] | None = None

    async def __aenter__(self) -> "PlanToolClient":
        await self._client.__aenter__()  # type: ignore[no-untyped-call]
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.__aexit__(exc_type, exc, tb)  # type: ignore[no-untyped-call]

    async def tool_definitions(self) -> list[dict[str, Any]]:
        if self._defs is None:
            tools = await self._client.list_tools()
            self._defs = [
                {"name": t.name, "description": t.description or "", "input_schema": t.input_schema}
                for t in tools
            ]
        return self._defs

    async def call(
        self,
        name: str,
        args: dict[str, Any],
        *,
        session_id: uuid.UUID | None,
        turn_id: uuid.UUID | None,
    ) -> ToolCallResult:
        s_token = current_session.set(session_id)
        t_token = current_turn.set(turn_id)
        try:
            res = await self._client.call_tool(name, args, raise_on_error=False)
        finally:
            current_session.reset(s_token)
            current_turn.reset(t_token)
        text = "\n".join(getattr(c, "text", "") for c in res.content)
        if not text:
            text = json.dumps(res.structured_content or {}, ensure_ascii=False)
        return ToolCallResult(text=text, is_error=bool(res.is_error), data=res.structured_content)
