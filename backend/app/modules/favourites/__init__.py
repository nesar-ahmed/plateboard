"""Favourite-dish feature: a customer's saved list of dishes.

* ``models.FavouriteDish`` - one row per (customer, dish), at most 50 per account
* ``favourite_router``     - ``/api/me/favourites`` (list, save, remove, and
  add a saved dish to the cart)
"""

from app.modules.favourites.router import favourite_router

__all__ = ["favourite_router"]
