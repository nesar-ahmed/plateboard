"""Auth dependencies: the two permission tiers every route plugs into.

* ``require_login`` - valid session cookie, else 401
* ``require_cook``  - logged in *and* holds the cook role, else 403

Both return the ``User`` row; routes never touch the cookie themselves.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.api.auth import service
from app.api.auth.exceptions import ForbiddenError, UnauthenticatedError
from app.api.auth.models import User, UserSession
from app.api.deps import DbSession
from app.core.config import get_settings

__all__ = [
    "CookRequired",
    "CurrentSession",
    "CurrentUser",
    "LoginRequired",
    "SessionToken",
    "require_cook",
    "require_login",
]


def get_session_token(request: Request) -> str:
    """Read the session cookie; absence is a 401, not a missing-argument 422."""
    token = request.cookies.get(get_settings().SESSION_COOKIE_NAME)
    if not token:
        raise UnauthenticatedError
    return token


SessionToken = Annotated[str, Depends(get_session_token)]


async def require_current_session(db: DbSession, token: SessionToken) -> UserSession:
    return await service.get_active_session(db, token)


async def require_login(db: DbSession, token: SessionToken) -> User:
    """Any authenticated user."""
    return await service.current_user(db, token)


async def require_cook(user: LoginRequired) -> User:
    """Authenticated *and* carrying the cook role; 403 otherwise.

    401 always wins over 403: an anonymous request cannot learn which roles
    the endpoint would demand.
    """
    if not user.is_cook:
        raise ForbiddenError("This action requires the cook role")
    return user


CurrentSession = Annotated[UserSession, Depends(require_current_session)]
LoginRequired = Annotated[User, Depends(require_login)]
CookRequired = Annotated[User, Depends(require_cook)]

# Back-compatible alias for the earlier /api/me annotation.
CurrentUser = LoginRequired
