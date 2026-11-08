"""Platform tools that belong to no context: the mail outbox viewer (plan §5.3, §10.9)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from riso.api.deps import Caller, ServicesDep, check_csrf, platform_context
from riso.identity.domain import Permission
from riso.platform.mail import OutboxMessage

router = APIRouter(prefix="/api/admin", dependencies=[Depends(check_csrf)], tags=["admin"])

OutboxReader = Annotated[Caller, Depends(platform_context(Permission.OUTBOX_READ))]


class OutboxItemOut(BaseModel):
    id: str
    created_at: datetime
    to_address: str
    subject: str
    template: str
    customer_id: str | None
    user_id: str | None
    sent_at: datetime | None


class OutboxMessageOut(OutboxItemOut):
    body: str

    @classmethod
    def of(cls, message: OutboxMessage) -> "OutboxMessageOut":
        return cls(
            id=message.id,
            created_at=message.created_at,
            to_address=message.to_address,
            subject=message.subject,
            template=message.template,
            customer_id=message.customer_id,
            user_id=message.user_id,
            sent_at=message.sent_at,
            body=message.body,
        )


class OutboxPageOut(BaseModel):
    items: list[OutboxItemOut]
    total: int


@router.get("/outbox", name="outbox.list")
def outbox_list(
    caller: OutboxReader,
    services: ServicesDep,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
    to: Annotated[str | None, Query(max_length=320)] = None,
) -> OutboxPageOut:
    """The outbox, newest first; `to` filters by part of the address."""
    caller.ctx.require(Permission.OUTBOX_READ)
    with services.uow(immediate=False) as uow:
        messages, total = uow.outbox.page(page=page, size=size, to=to)
    items = [OutboxItemOut(**OutboxMessageOut.of(m).model_dump(exclude={"body"})) for m in messages]
    return OutboxPageOut(items=items, total=total)


@router.get("/outbox/{message_id}", name="outbox.get")
def outbox_get(message_id: str, caller: OutboxReader, services: ServicesDep) -> OutboxMessageOut:
    caller.ctx.require(Permission.OUTBOX_READ)
    with services.uow(immediate=False) as uow:
        return OutboxMessageOut.of(uow.outbox.get(message_id))
