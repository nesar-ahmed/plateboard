"""Central import point for every ORM model.

Alembic's ``env.py`` imports this module so that all mappers are configured
before metadata or relationships are used. Adding a model means adding one
import here - nothing else needs to know the model list.
"""

from app.modules.addresses.models import Address
from app.modules.auth.models import CookProfile, User, UserSession
from app.modules.cart.models import CartItem
from app.modules.dishes.models import Dish
from app.modules.favourites.models import FavouriteDish
from app.modules.notifications.models import Notification
from app.modules.orders.models import Order, OrderItem
from app.modules.reviews.models import Review
from app.modules.zones.models import Zone
from app.shared.base import Base

__all__ = [
    "Address",
    "Base",
    "CartItem",
    "CookProfile",
    "Dish",
    "FavouriteDish",
    "Notification",
    "Order",
    "OrderItem",
    "Review",
    "User",
    "UserSession",
    "Zone",
]
