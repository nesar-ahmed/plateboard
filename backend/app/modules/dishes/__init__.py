"""Dish feature: cook-owned menu CRUD plus the public menu read.

* ``dish_router``         - ``/api/me/dishes`` CRUD (role: cook, ownership: 404)
* ``public_dish_router``  - ``/api/dishes``: active dishes only, unauth,
  name search + pagination + ``/api/dishes/{id}`` detail.

The ``Dish`` model lives here (``app.modules.dishes.models``) and is registered
for Alembic through the central import point ``app.models``.
"""

from app.modules.dishes.router import dish_router, public_dish_router

__all__ = ["dish_router", "public_dish_router"]
