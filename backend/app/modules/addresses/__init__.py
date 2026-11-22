"""Address book: the signed-in user's delivery addresses.

* ``models.Address`` - up to 10 per account, one default (partial unique index)
* ``address_router`` - ``/api/me/addresses`` (list, add, edit, delete)

Orders copy the chosen address (``Order.delivery_address``) at placement.
"""

from app.modules.addresses.router import address_router

__all__ = ["address_router"]
