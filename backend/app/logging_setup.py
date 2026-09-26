"""Privacy-safe request logging: one line per request, no bodies/query/cookies/headers.

``configure()`` wires stdlib logging to stdout and silences uvicorn's own
access log (which would otherwise log the raw request line, including the
query string). ``AccessLogMiddleware`` is pure ASGI — it only wraps
``send``/observes the scope, never buffers the request or response body —
so it is safe to put in front of streaming responses (SSE) too.
"""

import logging
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("app.access")

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
App = Callable[[Scope, Receive, Send], Awaitable[None]]


def configure(level: str) -> None:
    """Configure stdlib logging to stdout and disable uvicorn's access log.

    Uvicorn's own access log line includes the raw request target (path +
    query string); we replace it with our redacted ``app.access`` line, so
    it must stay disabled. Uvicorn is invoked with ``--no-access-log`` in
    the Docker CMD as a second, belt-and-suspenders safeguard.
    """
    logging.basicConfig(level=level.upper(), format="%(message)s", stream=sys.stdout, force=True)
    logging.getLogger("uvicorn.access").disabled = True


class AccessLogMiddleware:
    """Pure-ASGI middleware: logs ``method path status duration_ms sid=<...>``.

    Never logs the query string, request/response bodies, cookies, headers,
    prompts, or plan contents/names — only the four fields above.
    """

    def __init__(self, app: App) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        status_holder = {"status": 500}  # default if the app raises before responding

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.monotonic() - start) * 1000
            logger.info(
                "%s %s %s %.1f sid=%s",
                scope.get("method", "-"),
                scope.get("path", "-"),
                status_holder["status"],
                duration_ms,
                _session_id_prefix(scope),
            )


def _session_id_prefix(scope: Scope) -> str:
    session_id = scope.get("state", {}).get("session_id")
    if isinstance(session_id, uuid.UUID):
        return str(session_id)[:8]
    return "-"
