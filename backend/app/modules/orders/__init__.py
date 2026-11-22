"""Order feature: the cart, placed - one customer, one cook, frozen prices.

* ``models.Order`` / ``models.OrderItem`` - the order and its snapshot lines
* ``my_orders_router``   - ``/api/me/orders`` (place, list, detail, cancel)
* ``cook_orders_router`` - ``/api/cooks/me/orders`` (incoming orders + status)

Status flow: placed -> accepted -> ready -> completed; cancelled from placed
(customer or cook) or accepted (cook).
"""

from app.modules.orders.router import cook_orders_router, my_orders_router

__all__ = ["cook_orders_router", "my_orders_router"]
