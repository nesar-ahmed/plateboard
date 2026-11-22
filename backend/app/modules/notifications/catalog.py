"""The notification catalog: every type, what it carries, who may get it, and
what it says.

One :class:`NotificationSpec` per :class:`NotificationType`:

* ``payload`` - the Pydantic model of the row's ``data`` snapshot. Writers
  pass an instance (``service.notify`` refuses any other model), so a typo in
  a field name fails in tests, not in someone's inbox.
* ``subject`` - the :class:`SubjectKind` the notification links to, or
  ``None``; ``service.notify`` insists on a ``subject_id`` exactly when the
  spec has one.
* ``render`` - one renderer per audience the type may be sent to. The same
  event can read differently per panel (``order.placed`` is a confirmation in
  ``/account`` and a new request in ``/cook``); sending a type to any other
  audience is a programming error.

Text is rendered at *read* time from the stored snapshot, so wording can
change without a data migration. Unknown types (retired from this file) and
snapshots that no longer validate fall back to a generic title rather than
breaking the inbox.

Adding a type = a member in :class:`NotificationType`, a payload (or reuse
one) and an entry in :data:`CATALOG`; ``tests/test_notifications.py`` renders
every entry for every audience it allows.
"""

from __future__ import annotations

import dataclasses
import logging
import uuid
from collections.abc import Callable, Mapping
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.modules.notifications.models import Audience, SubjectKind

logger = logging.getLogger(__name__)

__all__ = [
    "CATALOG",
    "AccountPayload",
    "CookApplicationPayload",
    "Fulfilment",
    "NoPayload",
    "NotificationPayload",
    "NotificationSpec",
    "NotificationType",
    "OrderPayload",
    "PasswordChangedPayload",
    "Rendered",
    "ReviewPayload",
    "order_ref",
    "render",
]


class NotificationType(str, Enum):
    """Everything the platform notifies about (stored in ``notifications.type``)."""

    # --- the account (/account) ----------------------------------------------------
    ACCOUNT_WELCOME = "account.welcome"
    ACCOUNT_PASSWORD_CHANGED = "account.password_changed"

    # --- becoming a cook: request -> admin decision ------------------------------------
    COOK_APPLICATION_SUBMITTED = "cook_application.submitted"  # -> admins
    COOK_APPLICATION_ACCEPTED = "cook_application.accepted"  # -> the applicant
    COOK_APPLICATION_REJECTED = "cook_application.rejected"  # -> the applicant

    # --- the kitchen's verified badge ----------------------------------------------
    KITCHEN_VERIFIED = "kitchen.verified"
    KITCHEN_VERIFICATION_REVOKED = "kitchen.verification_revoked"

    # --- the order lifecycle ---------------------------------------------------------
    ORDER_PLACED = "order.placed"  # customer: confirmation; cook: new request
    ORDER_ACCEPTED = "order.accepted"
    ORDER_REJECTED = "order.rejected"  # the cook declined a placed order
    ORDER_CANCELLED_BY_CUSTOMER = "order.cancelled_by_customer"
    ORDER_CANCELLED_BY_COOK = "order.cancelled_by_cook"  # after accepting it
    ORDER_READY = "order.ready"  # for pickup (default) or out for delivery
    ORDER_RECEIVED = "order.received"  # the customer confirmed receipt

    # --- reviews ------------------------------------------------------------------
    REVIEW_POSTED = "review.posted"  # -> the cook, who replies to it
    REVIEW_REPLIED = "review.replied"  # -> the reviewer


# --- payloads (the ``data`` snapshot) --------------------------------------------------


class NotificationPayload(BaseModel):
    """Base for every payload: unknown keys are errors, instances immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class NoPayload(NotificationPayload):
    """For types whose text needs nothing beyond the type itself."""


class AccountPayload(NotificationPayload):
    name: str | None = Field(default=None, description="the account's display name")


class PasswordChangedPayload(NotificationPayload):
    signed_out_sessions: int = Field(
        default=0, ge=0, description="other sessions ended by the change"
    )


class CookApplicationPayload(NotificationPayload):
    applicant_name: str | None = None
    headline: str | None = Field(default=None, description="the kitchen's headline")
    reason: str | None = Field(default=None, description="why it was rejected")


#: How an order reaches the customer. ``pickup`` is the platform default;
#: ``delivery`` is reserved for when orders carry a delivery option.
Fulfilment = Literal["pickup", "delivery"]


class OrderPayload(NotificationPayload):
    """Snapshot of the order at the moment of the event."""

    cook_name: str | None = None
    customer_name: str | None = None
    item_count: int = Field(ge=1, description="portions")
    total: int = Field(ge=1, description="minor units")
    fulfilment: Fulfilment = "pickup"
    reason: str | None = Field(
        default=None, description="the cook's reason for rejecting/cancelling"
    )


class ReviewPayload(NotificationPayload):
    dish_name: str
    rating: int = Field(ge=1, le=5)
    customer_name: str | None = None
    cook_name: str | None = None
    comment: str | None = Field(default=None, description="the review's words, shortened")


# --- rendering ---------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Rendered:
    title: str
    body: str | None = None


#: Shown when a row cannot be rendered (retired type, outdated snapshot).
FALLBACK = Rendered(title="Notification")

type Renderer = Callable[[Any, uuid.UUID | None], Rendered]


@dataclasses.dataclass(frozen=True)
class NotificationSpec:
    payload: type[NotificationPayload]
    subject: SubjectKind | None
    render: Mapping[Audience, Renderer]

    @property
    def audiences(self) -> frozenset[Audience]:
        return frozenset(self.render)


def order_ref(order_id: uuid.UUID | None) -> str:
    """``#0CA946F8`` - the short order reference the frontend shows
    (``orderRef`` in ``frontend/src/lib/format.ts``)."""
    return f"#{str(order_id)[:8].upper()}" if order_id else "#"


def _portions(count: int) -> str:
    return f"{count} portion" if count == 1 else f"{count} portions"


def _cook(data: OrderPayload) -> str:
    return data.cook_name or "Your cook"


def _customer(data: OrderPayload) -> str:
    return data.customer_name or "A customer"


def _reason(reason: str | None) -> str:
    return f' Reason: "{reason}"' if reason else ""


# account ------------------------------------------------------------------------


def _welcome(data: AccountPayload, _subject: uuid.UUID | None) -> Rendered:
    return Rendered(
        title=f"Welcome to Plateboard, {data.name}!"
        if data.name
        else "Welcome to Plateboard!",
        body="Find home-cooked dishes near you, save a delivery address and set "
        "your food preferences to filter the menu.",
    )


def _password_changed(
    data: PasswordChangedPayload, _subject: uuid.UUID | None
) -> Rendered:
    ended = data.signed_out_sessions
    signed_out = (
        f" {ended} other session{'s were' if ended != 1 else ' was'} signed out."
        if ended
        else ""
    )
    return Rendered(
        title="Your password was changed",
        body=f"If this wasn't you, change it again now.{signed_out}",
    )


# cook application -----------------------------------------------------------------


def _application_submitted(
    data: CookApplicationPayload, _subject: uuid.UUID | None
) -> Rendered:
    who = data.applicant_name or "A user"
    headline = f': "{data.headline}"' if data.headline else ""
    return Rendered(
        title="New cook application",
        body=f"{who} wants to open a kitchen{headline}. Review it to accept or reject.",
    )


def _application_accepted(
    _data: CookApplicationPayload, _subject: uuid.UUID | None
) -> Rendered:
    return Rendered(
        title="Your kitchen is approved",
        body="You can now add dishes and take orders from your kitchen panel.",
    )


def _application_rejected(
    data: CookApplicationPayload, _subject: uuid.UUID | None
) -> Rendered:
    return Rendered(
        title="Your cook application was not approved",
        body="The platform team reviewed your kitchen and could not approve it."
        + _reason(data.reason),
    )


# kitchen verification ------------------------------------------------------------------


def _verified(_data: NoPayload, _subject: uuid.UUID | None) -> Rendered:
    return Rendered(
        title="Your kitchen is verified",
        body="Customers now see the verified badge on your kitchen page and cards.",
    )


def _verification_revoked(_data: NoPayload, _subject: uuid.UUID | None) -> Rendered:
    return Rendered(
        title="Your kitchen's verified badge was removed",
        body="Customers no longer see the badge. Contact the platform team to "
        "find out why.",
    )


# orders -------------------------------------------------------------------------


def _placed_for_customer(data: OrderPayload, order_id: uuid.UUID | None) -> Rendered:
    return Rendered(
        title=f"Order {order_ref(order_id)} placed with {_cook(data)}",
        body=f"{_portions(data.item_count)} - waiting for the cook to accept it.",
    )


def _placed_for_cook(data: OrderPayload, order_id: uuid.UUID | None) -> Rendered:
    return Rendered(
        title=f"New order request from {_customer(data)}",
        body=f"Order {order_ref(order_id)}: {_portions(data.item_count)}. "
        "Accept or reject it.",
    )


def _accepted(data: OrderPayload, order_id: uuid.UUID | None) -> Rendered:
    return Rendered(
        title=f"{_cook(data)} accepted your order",
        body=f"Order {order_ref(order_id)} is being prepared.",
    )


def _rejected(data: OrderPayload, order_id: uuid.UUID | None) -> Rendered:
    return Rendered(
        title=f"{_cook(data)} couldn't take your order",
        body=f"Order {order_ref(order_id)} was declined." + _reason(data.reason),
    )


def _cancelled_by_customer(data: OrderPayload, order_id: uuid.UUID | None) -> Rendered:
    return Rendered(
        title=f"{_customer(data)} cancelled their order",
        body=f"Order {order_ref(order_id)} was cancelled before you accepted it.",
    )


def _cancelled_by_cook_for_customer(
    data: OrderPayload, order_id: uuid.UUID | None
) -> Rendered:
    return Rendered(
        title=f"{_cook(data)} cancelled your order",
        body=f"Order {order_ref(order_id)} was cancelled by the kitchen."
        + _reason(data.reason),
    )


def _cancelled_by_cook_for_admin(
    data: OrderPayload, order_id: uuid.UUID | None
) -> Rendered:
    return Rendered(
        title=f"{_cook(data)} cancelled an accepted order",
        body=f"Order {order_ref(order_id)} from {_customer(data)}."
        + _reason(data.reason),
    )


def _ready(data: OrderPayload, order_id: uuid.UUID | None) -> Rendered:
    if data.fulfilment == "delivery":
        return Rendered(
            title="Your order is on its way",
            body=f"Order {order_ref(order_id)} from {_cook(data)} is out for "
            "delivery. Confirm once it arrives.",
        )
    return Rendered(
        title="Your order is ready for pickup",
        body=f"Order {order_ref(order_id)} from {_cook(data)} is ready. "
        "Confirm once you have it.",
    )


def _received(data: OrderPayload, order_id: uuid.UUID | None) -> Rendered:
    return Rendered(
        title=f"{_customer(data)} received their order",
        body=f"Order {order_ref(order_id)} is complete.",
    )


# reviews ------------------------------------------------------------------------


def _review_posted(data: ReviewPayload, _review_id: uuid.UUID | None) -> Rendered:
    who = data.customer_name or "A customer"
    said = f'{who} wrote: "{data.comment}"' if data.comment else f"{who} left a rating."
    return Rendered(
        title=f"New {data.rating}-star review of {data.dish_name}",
        body=f"{said} Reply to thank them or answer - it shows under the review.",
    )


def _review_replied(data: ReviewPayload, _review_id: uuid.UUID | None) -> Rendered:
    cook = data.cook_name or "The cook"
    return Rendered(
        title=f"{cook} replied to your review",
        body=f"Your {data.rating}-star review of {data.dish_name} has an answer.",
    )


ACCOUNT, COOK, ADMIN = Audience.ACCOUNT, Audience.COOK, Audience.ADMIN
ORDER, KITCHEN, REVIEW = SubjectKind.ORDER, SubjectKind.KITCHEN, SubjectKind.REVIEW

CATALOG: Mapping[NotificationType, NotificationSpec] = {
    NotificationType.ACCOUNT_WELCOME: NotificationSpec(
        AccountPayload, None, {ACCOUNT: _welcome}
    ),
    NotificationType.ACCOUNT_PASSWORD_CHANGED: NotificationSpec(
        PasswordChangedPayload, None, {ACCOUNT: _password_changed}
    ),
    # The applicant is not a cook while the request is open (or after a
    # rejection), so the decision lands in their /account inbox.
    NotificationType.COOK_APPLICATION_SUBMITTED: NotificationSpec(
        CookApplicationPayload, KITCHEN, {ADMIN: _application_submitted}
    ),
    NotificationType.COOK_APPLICATION_ACCEPTED: NotificationSpec(
        CookApplicationPayload, KITCHEN, {ACCOUNT: _application_accepted}
    ),
    NotificationType.COOK_APPLICATION_REJECTED: NotificationSpec(
        CookApplicationPayload, KITCHEN, {ACCOUNT: _application_rejected}
    ),
    NotificationType.KITCHEN_VERIFIED: NotificationSpec(
        NoPayload, KITCHEN, {COOK: _verified}
    ),
    NotificationType.KITCHEN_VERIFICATION_REVOKED: NotificationSpec(
        NoPayload, KITCHEN, {COOK: _verification_revoked}
    ),
    NotificationType.ORDER_PLACED: NotificationSpec(
        OrderPayload, ORDER, {ACCOUNT: _placed_for_customer, COOK: _placed_for_cook}
    ),
    NotificationType.ORDER_ACCEPTED: NotificationSpec(
        OrderPayload, ORDER, {ACCOUNT: _accepted}
    ),
    NotificationType.ORDER_REJECTED: NotificationSpec(
        OrderPayload, ORDER, {ACCOUNT: _rejected}
    ),
    NotificationType.ORDER_CANCELLED_BY_CUSTOMER: NotificationSpec(
        OrderPayload, ORDER, {COOK: _cancelled_by_customer}
    ),
    NotificationType.ORDER_CANCELLED_BY_COOK: NotificationSpec(
        OrderPayload,
        ORDER,
        {ACCOUNT: _cancelled_by_cook_for_customer, ADMIN: _cancelled_by_cook_for_admin},
    ),
    NotificationType.ORDER_READY: NotificationSpec(
        OrderPayload, ORDER, {ACCOUNT: _ready}
    ),
    NotificationType.ORDER_RECEIVED: NotificationSpec(
        OrderPayload, ORDER, {COOK: _received}
    ),
    NotificationType.REVIEW_POSTED: NotificationSpec(
        ReviewPayload, REVIEW, {COOK: _review_posted}
    ),
    NotificationType.REVIEW_REPLIED: NotificationSpec(
        ReviewPayload, REVIEW, {ACCOUNT: _review_replied}
    ),
}


def render(
    type_: str, audience: str, subject_id: uuid.UUID | None, data: dict[str, Any]
) -> Rendered:
    """Title + body of a stored row; :data:`FALLBACK` if it cannot be rendered."""
    try:
        spec = CATALOG[NotificationType(type_)]
        renderer = spec.render[Audience(audience)]
        payload = spec.payload.model_validate(data)
    except (ValueError, KeyError, ValidationError):  # ValidationError: outdated data
        logger.warning("cannot render notification %s for %s", type_, audience)
        return FALLBACK
    return renderer(payload, subject_id)
