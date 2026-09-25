"""«Подключить MCP» (spec §8): issue/revoke a per-session bearer token for the
external `/mcp` Streamable HTTP endpoint."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request

from app.api.deps import check_origin, get_service, require_session
from app.api.schemas import McpTokenResponse
from app.db import repo
from app.mcp_server.auth import TOKEN_PREFIX
from app.services.sessions import hash_token

router = APIRouter(prefix="/api/mcp-token", tags=["mcp"])

TOKEN_TTL_DAYS = 7


@router.post("", dependencies=[Depends(check_origin)])
async def create_mcp_token(
    request: Request, session_id: uuid.UUID = Depends(require_session)
) -> McpTokenResponse:
    settings = request.app.state.settings
    service = get_service(request)
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=TOKEN_TTL_DAYS)
    async with service.sessionmaker() as db, db.begin():
        await repo.revoke_mcp_tokens(db, session_id, now)
        await repo.create_mcp_token(
            db,
            session_id=session_id,
            token_hash=hash_token(token),
            prefix=token[: len(TOKEN_PREFIX) + 8],
            expires_at=expires_at,
        )
    url = f"{settings.public_origin}/mcp"
    return McpTokenResponse(
        token=token,
        expires_at=expires_at,
        url=url,
        claude_code_command=(
            f"claude mcp add --transport http planner {url} "
            f'--header "Authorization: Bearer {token}"'
        ),
        claude_desktop_config={
            "mcpServers": {
                "planner": {
                    "url": url,
                    "headers": {"Authorization": f"Bearer {token}"},
                }
            }
        },
    )


@router.delete("", status_code=204, dependencies=[Depends(check_origin)])
async def revoke_mcp_token(
    request: Request, session_id: uuid.UUID = Depends(require_session)
) -> None:
    service = get_service(request)
    now = datetime.now(UTC)
    async with service.sessionmaker() as db, db.begin():
        await repo.revoke_mcp_tokens(db, session_id, now)
