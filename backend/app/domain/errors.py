from typing import Any


class DomainError(Exception):
    code = "domain_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}


class PlanValidationError(DomainError):
    code = "invalid_plan"


class CycleError(PlanValidationError):
    code = "cycle"

    def __init__(self, cycle: list[int]) -> None:
        path = " → ".join(str(i) for i in [*cycle, cycle[0]])
        super().__init__(f"Циклическая зависимость: {path}", details={"cycle": cycle})
        self.cycle = cycle


class OperationError(DomainError):
    code = "invalid_operation"

    def __init__(
        self, message: str, *, index: int | None = None, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message, details=details)
        self.index = index


class ConfirmationRequired(DomainError):
    code = "confirmation_required"
