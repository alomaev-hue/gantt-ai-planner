import uuid
from contextvars import ContextVar

current_session: ContextVar[uuid.UUID | None] = ContextVar("current_session", default=None)
current_turn: ContextVar[uuid.UUID | None] = ContextVar("current_turn", default=None)
