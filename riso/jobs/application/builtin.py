"""Job kinds every installation has. `noop` does nothing; tests and the worker's smoke checks
use it."""

from typing import Any

from pydantic import BaseModel, ConfigDict

from riso.jobs.application.registry import JobContext, JobRegistry


class NoopPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = None


def run_noop(payload: NoopPayload, context: JobContext) -> dict[str, Any]:
    return {"note": payload.note, "attempt": context.attempt}


def register_builtin(registry: JobRegistry) -> JobRegistry:
    registry.register("noop", NoopPayload, run_noop)
    return registry
