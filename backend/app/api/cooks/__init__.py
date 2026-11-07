"""Cook feature: the become-a-cook action and cook-only profile endpoints.

The ``CookProfile`` model itself lives in ``app.api.auth.models`` (it is a
1:1 extension of the account aggregate); this package owns the HTTP surface:

* POST  /api/cooks              - become a cook (any logged-in user)
* GET   /api/cooks/me           - my cook profile            (cook only -> 403)
* PATCH /api/cooks/me           - update headline/tags        (cook only -> 403)
* GET   /api/cooks              - public cook directory (paginated)
* GET   /api/cooks/{user_id}    - public cook profile page (404 if absent)
"""

from app.api.cooks.router import cook_router

__all__ = ["cook_router"]
