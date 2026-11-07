"""Authentication feature: register / login / logout / whoami.

Server-side sessions stored in the ``sessions`` table, carried to the client
as an HTTP-only cookie. Mounted un-versioned under ``/api`` next to
``/api/health`` (see ``app/api/router.py``); versioned resources belong in
``app/api/v1``.
"""

from app.api.auth.router import auth_router

__all__ = ["auth_router"]
