"""ORM model for menu dishes and the fixed allergen vocabulary.

A dish belongs to exactly one cook (``cook_id`` -> ``users.id``) and dies with
the account (CASCADE). ``price`` is an *integer minor-unit amount* (e.g. 8900
= 89.00) - float money rounds, integers never do - guarded in the database by
a CHECK constraint so no code path can persist a free or negative dish.
"""

from __future__ import annotations

import uuid
from enum import Enum

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Allergen(str, Enum):
    """The declared allergen groups a dish may contain. This enum is the
    closed vocabulary: the schema layer rejects any unknown value as a 422,
    so the stored JSON list always holds exactly these lowercase tokens.
    """

    GLUTEN = "gluten"
    CRUSTACEANS = "crustaceans"
    EGGS = "eggs"
    FISH = "fish"
    PEANUTS = "peanuts"
    MILK = "milk"
    NUTS = "nuts"
    CELERY = "celery"
    MUSTARD = "mustard"
    SESAME = "sesame"
    SOY = "soy"
    LUPIN = "lupin"
    MOLLUSCS = "molluscs"
    SULPHITES = "sulphites"


ALLERGEN_VALUES: tuple[str, ...] = tuple(allergen.value for allergen in Allergen)


class Dish(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A cook's menu item.

    ``ingredients``, ``allergens`` and ``dietary_tags`` are JSON string lists
    (same approach as ``User.roles`` / ``CookProfile.specialties``); allergens
    are validated against :class:`Allergen`, the other two are normalized
    free-text tags (see ``schemas.py``). ``active=False`` means *deactivated*:
    the cook keeps the row and can reactivate it, but the public menu hides it.

    The CHECK constraints below are the last line of defense - the API
    validation (schemas.py) produces the friendly 422 before these fire.
    """

    __tablename__ = "dishes"
    __table_args__ = (
        CheckConstraint("price > 0", name="price_positive"),
        CheckConstraint("portions > 0", name="portions_positive"),
    )

    cook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    portions: Mapped[int] = mapped_column(Integer, nullable=False)
    ingredients: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    allergens: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    dietary_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
