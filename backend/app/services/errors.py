from app.domain.errors import DomainError


class AgentBusy(DomainError):
    code = "agent_busy"

    def __init__(self) -> None:
        super().__init__("Агент сейчас редактирует план, подождите")


class RateLimited(DomainError):
    code = "rate_limited"


class NoSession(DomainError):
    code = "no_session"

    def __init__(self) -> None:
        super().__init__("Сессия не найдена")


class NothingToUndo(DomainError):
    code = "nothing_to_undo"

    def __init__(self) -> None:
        super().__init__("Нечего отменять")


class NothingToRedo(DomainError):
    code = "nothing_to_redo"

    def __init__(self) -> None:
        super().__init__("Нечего повторять")


class NotFound(DomainError):
    code = "not_found"


class BadOrigin(DomainError):
    code = "bad_origin"


class FileTooLarge(DomainError):
    code = "file_too_large"
