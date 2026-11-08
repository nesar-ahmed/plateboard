"""ORM models for carts: a cart owned by an account *or* by a guest token,
holding dish lines with quantities.

* ``Cart`` - exactly one owner: ``user_id`` (signed-in) or ``token_hash``
  (guest; the SHA-256 of a random token kept in an HTTP-only cookie - a
  database leak cannot be replayed as someone's cart). A CHECK enforces
  "exactly one", and each is unique: one cart per account, one per guest.
* ``CartItem`` - one row per (cart, dish) with a quantity of 1..100.

Deleting an account deletes its cart; deleting a cart or a dish deletes the
lines (all CASCADE). A *deactivated* dish stays in carts, flagged unavailable
by the API, so the customer sees what happened. The one-cook-per-cart rule
lives in the service (it needs the dishes' cooks).

No ORM relationships on purpose: every cart read is an explicit query, so
nothing can trigger an implicit lazy load under asyncio.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

#: Smallest and largest quantity a cart line may hold.
MIN_QUANTITY = 1
MAX_QUANTITY = 100


class Cart(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "carts"
    __table_args__ = (
        # Exactly one owner: an account or a guest token, never both/neither.
        CheckConstraint(
            "(user_id IS NULL) <> (token_hash IS NULL)", name="exactly_one_owner"
        ),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=True
    )
    token_hash: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )

    @property
    def is_guest(self) -> bool:
        return self.user_id is None


class CartItem(Base, TimestampMixin):
    """``created_at`` is when the dish was first added (it orders the cart,
    newest first); ``updated_at`` moves with every quantity change."""

    __tablename__ = "cart_items"
    __table_args__ = (
        CheckConstraint(
            f"quantity >= {MIN_QUANTITY} AND quantity <= {MAX_QUANTITY}",
            name="quantity_range",
        ),
    )

    cart_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("carts.id", ondelete="CASCADE"), primary_key=True
    )
    # Indexed on its own (the PK leads with cart_id) for the dish-delete cascade.
    dish_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dishes.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
