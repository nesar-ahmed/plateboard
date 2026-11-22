"""Cook feature: the cook application and cook-only profile endpoints.

The ``CookProfile`` model itself lives in ``app.modules.auth.models`` (it is a
1:1 extension of the account aggregate); this package owns the HTTP surface:

* POST  /api/cooks              - apply to cook (any logged-in user); an
                                  admin accepts or rejects the application
* GET   /api/cooks/me/application - my application: pending / accepted / rejected
* GET   /api/cooks/me           - my cook profile            (cook only -> 403)
* PATCH /api/cooks/me           - update headline/tags/zone   (cook only -> 403)
* GET|PUT /api/cooks/me/availability - time zone, weekly hours, pause (cook only)
* GET   /api/cooks              - public cook directory (paginated; verified +
                                  availability on each card)
* GET   /api/cooks/{user_id}    - public cook profile page + stats (404 if absent)
"""

from app.modules.cooks.router import cook_router

__all__ = ["cook_router"]
