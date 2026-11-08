"""Job kinds: a name, the Pydantic model of its payload, and the function that runs it
(guide §6.8). A handler must be idempotent, because a retry may run it twice."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from riso.shared.context import RequestContext
from riso.shared.errors import NotFound, ValidationFailed


@dataclass(frozen=True, slots=True)
class JobContext:
    """What a running job knows about itself. `request` carries the user who started the
    job, so the permission checks and the audit of the use cases it calls stay meaningful."""

    job_id: str
    kind: str
    attempt: int
    customer_id: str | None
    created_by: str | None
    request: RequestContext


Handler = Callable[[Any, JobContext], dict[str, Any] | None]


@dataclass(frozen=True, slots=True)
class JobKind:
    name: str
    payload: type[BaseModel]
    handler: Handler
    max_attempts: int = 3


class JobRegistry:
    def __init__(self) -> None:
        self._kinds: dict[str, JobKind] = {}

    def register(
        self,
        name: str,
        payload: type[BaseModel],
        handler: Handler,
        *,
        max_attempts: int = 3,
    ) -> None:
        if name in self._kinds:
            raise ValueError(f"job kind {name} is registered twice")
        self._kinds[name] = JobKind(name, payload, handler, max_attempts)

    def kind(self, name: str) -> JobKind:
        try:
            return self._kinds[name]
        except KeyError:
            raise NotFound(f"no job kind {name}") from None

    def names(self) -> list[str]:
        return sorted(self._kinds)

    def validate(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """The payload as its kind's model reads it, ready to store as JSON."""
        model = self.kind(name).payload
        try:
            return model.model_validate(payload).model_dump(mode="json")
        except ValidationError as exc:
            raise ValidationFailed(f"invalid payload for job kind {name}") from exc
