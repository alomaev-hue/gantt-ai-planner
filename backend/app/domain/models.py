from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_TASKS = 500
# Dependencies are stored in every snapshot (up to 50 versions) and walked by every schedule():
# without a cap one session could build a dense DAG of ~125k edges over 500 tasks. 2000 is
# ~4 predecessors per task on the largest plan, far above any real plan.
MAX_DEPENDENCIES = 2000
MAX_LAG = 365


class Task(BaseModel):
    id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    assignee: str | None = Field(default=None, max_length=100)
    duration: int = Field(ge=1, le=999)
    constraint_start: date | None = None

    @field_validator("name", "description", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @field_validator("assignee", mode="before")
    @classmethod
    def _blank_assignee_is_none(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v


class Dependency(BaseModel):
    model_config = ConfigDict(frozen=True)

    predecessor_id: int
    successor_id: int
    lag: int = Field(default=0, ge=0, le=MAX_LAG)


class Plan(BaseModel):
    project_start: date
    last_id: int = Field(default=0, ge=0)
    tasks: list[Task] = Field(default_factory=list)
    dependencies: list[Dependency] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sync_last_id(self) -> "Plan":
        max_id = max((t.id for t in self.tasks), default=0)
        if self.last_id < max_id:
            self.last_id = max_id
        return self
