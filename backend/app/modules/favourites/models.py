"""ORM model for favourite dishes: a customer's saved list of dishes.

* ``FavouriteDish`` - one row per (customer, dish); the pair is the primary
  key, so a dish is on a list at most once. ``created_at`` is when it was
  saved (it orders the list, newest first).

Deleting an account or a dish deletes its favourites (CASCADE, like cart
lines). A dish the cook *hides* (``Dish.active = false``) stays on the list -
the API marks it unavailable - so the customer sees what happened instead of
a dish silently vanishing; it comes back as available when the cook
publishes it again.

At most :data:`MAX_FAVOURITES` per account; the service enforces it with a
single conditional ``INSERT`` so concurrent adds can never overshoot.

No ORM relationships on purpose (same rule as the cart and orders): every
read is an explicit query, so nothing can trigger an implicit lazy load under
asyncio. No ``updated_at``: a favourite is written once, then only deleted.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base import Base, utcnow

#: The most dishes one account may keep as favourites.
MAX_FAVOURITES = 50


class FavouriteDish(Base):
    __tablename__ = "favourite_dishes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # Indexed on its own (the PK leads with user_id) for the dish-delete cascade.
    dish_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dishes.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), default=utcnow, server_default=func.now(), nullable=False
    )
