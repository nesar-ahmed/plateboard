"""Who hears about what in an order's life - the one place that decides.

Called by ``orders.service`` inside the transaction of the change (before its
commit), and by ``scripts/seed.py`` for the demo history (``at`` backdates).

=====================================  ==========================================
Event                                  Notified (audience)
=====================================  ==========================================
placed                                 customer (account: confirmation),
                                       cook (cook: new request)
accepted                               customer
rejected (cook cancels a placed one)   customer (with the cook's reason)
cancelled by the cook after accepting  customer + every admin (a quality signal)
cancelled by the customer              cook
ready                                  customer (for pickup / out for delivery)
completed (customer confirmed receipt) cook
=====================================  ==========================================

Actionable notifications are resolved when acted on: the cook's "new order
request" is marked read once the request is answered (or withdrawn), the
customer's "ready" once they confirm receipt.

Every event uses ``order:{id}:{type}`` as its dedupe key, so a retried or
re-seeded event is never stored twice for the same person.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications import service as notifications
from app.modules.notifications.catalog import NotificationType, OrderPayload
from app.modules.notifications.models import Audience
from app.modules.orders.models import Order, OrderStatus, Party

__all__ = ["move_event", "order_placed", "status_changed"]


def _payload(
    order: Order,
    *,
    cook_name: str | None,
    customer_name: str | None,
    reason: str | None = None,
) -> OrderPayload:
    return OrderPayload(
        cook_name=cook_name,
        customer_name=customer_name,
        item_count=order.item_count,
        total=order.total,
        fulfilment=order.fulfilment,  # type: ignore[arg-type]  # CHECK-constrained
        reason=reason,
    )


def _key(order_id: uuid.UUID, kind: NotificationType) -> str:
    return f"order:{order_id}:{kind.value}"


async def _tell(
    session: AsyncSession,
    order: Order,
    kind: NotificationType,
    payload: OrderPayload,
    *,
    recipient: tuple[uuid.UUID, Audience],
    actor_id: uuid.UUID,
    at: datetime | None,
) -> None:
    recipient_id, audience = recipient
    await notifications.notify(
        session,
        recipient_id=recipient_id,
        audience=audience,
        kind=kind,
        payload=payload,
        subject_id=order.id,
        actor_id=actor_id,
        dedupe_key=_key(order.id, kind),
        created_at=at,
    )


async def order_placed(
    session: AsyncSession,
    order: Order,
    *,
    cook_name: str | None,
    customer_name: str | None,
    at: datetime | None = None,
) -> None:
    """A confirmation for the customer and a new request for the kitchen."""
    payload = _payload(order, cook_name=cook_name, customer_name=customer_name)
    for recipient in (
        (order.customer_id, Audience.ACCOUNT),
        (order.cook_id, Audience.COOK),
    ):
        await _tell(
            session,
            order,
            NotificationType.ORDER_PLACED,
            payload,
            recipient=recipient,
            actor_id=order.customer_id,
            at=at,
        )


def move_event(
    order: Order, previous: OrderStatus, target: OrderStatus, by: Party
) -> tuple[NotificationType, tuple[uuid.UUID, Audience]]:
    """The notification a status move produces and who gets it (the admins'
    copy of a late cancellation is added by :func:`status_changed`)."""
    customer = (order.customer_id, Audience.ACCOUNT)
    cook = (order.cook_id, Audience.COOK)
    if target is OrderStatus.ACCEPTED:
        return NotificationType.ORDER_ACCEPTED, customer
    if target is OrderStatus.READY:
        return NotificationType.ORDER_READY, customer
    if target is OrderStatus.COMPLETED:
        return NotificationType.ORDER_RECEIVED, cook
    if target is OrderStatus.CANCELLED and by is Party.CUSTOMER:
        return NotificationType.ORDER_CANCELLED_BY_CUSTOMER, cook
    if target is OrderStatus.CANCELLED and previous is OrderStatus.PLACED:
        return NotificationType.ORDER_REJECTED, customer
    if target is OrderStatus.CANCELLED:
        return NotificationType.ORDER_CANCELLED_BY_COOK, customer
    msg = f"no notification for an order moving to {target.value}"
    raise ValueError(msg)


async def status_changed(
    session: AsyncSession,
    order: Order,
    *,
    previous: OrderStatus,
    target: OrderStatus,
    by: Party,
    reason: str | None = None,
    cook_name: str | None,
    customer_name: str | None,
    at: datetime | None = None,
) -> None:
    """Notify the other party (and admins, for a cook's late cancellation)
    that ``order`` moved from ``previous`` to ``target``, acted on ``by``."""
    payload = _payload(
        order, cook_name=cook_name, customer_name=customer_name, reason=reason
    )
    actor_id = order.customer_id if by is Party.CUSTOMER else order.cook_id
    kind, recipient = move_event(order, previous, target, by)
    await _tell(
        session, order, kind, payload, recipient=recipient, actor_id=actor_id, at=at
    )
    if kind is NotificationType.ORDER_CANCELLED_BY_COOK:
        await notifications.notify_admins(
            session,
            kind=kind,
            payload=payload,
            subject_id=order.id,
            actor_id=actor_id,
            dedupe_key=_key(order.id, kind),
            created_at=at,
        )

    # Resolve what was waiting on this move.
    if target is OrderStatus.COMPLETED:  # the customer has the food
        await notifications.resolve(
            session,
            kind=NotificationType.ORDER_READY,
            subject_id=order.id,
            recipient_id=order.customer_id,
        )
    if previous is OrderStatus.PLACED:  # the request was answered or withdrawn
        await notifications.resolve(
            session,
            kind=NotificationType.ORDER_PLACED,
            subject_id=order.id,
            recipient_id=order.cook_id,
        )
