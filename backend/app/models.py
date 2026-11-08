"""Central import point for every ORM model.

Alembic's ``env.py`` imports this module so that all mappers are configured
before metadata or relationships are used. Adding a model means adding one
import here - nothing else needs to know the model list.
"""

from app.modules.auth.models import CookProfile, User, UserSession
from app.modules.cart.models import CartItem
from app.modules.dishes.models import Dish
from app.modules.zones.models import Zone
from app.shared.base import Base

__all__ = ["Base", "CartItem", "CookProfile", "Dish", "User", "UserSession", "Zone"]
