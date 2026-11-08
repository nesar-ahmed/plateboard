"""Cart feature: the signed-in user's cart of dishes and quantities.

* ``models.CartItem`` - one row per (user, dish) with a quantity
* ``cart_router``     - ``/api/me/cart`` (view, add, set/adjust quantity,
  remove, clear)
"""

from app.modules.cart.router import cart_router

__all__ = ["cart_router"]
