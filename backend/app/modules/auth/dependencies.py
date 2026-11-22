"""Auth dependencies: the two permission tiers every route plugs into.

* ``require_login``    - valid session cookie, else 401
* ``require_customer`` - logged in *and* holds the customer role, else 403
* ``require_cook``     - logged in *and* holds the cook role, else 403
* ``require_admin``    - logged in *and* holds the admin role, else 403
* ``optional_user`` - the user if the session is valid, else ``None`` (for
  endpoints guests may use too, like the cart)

They return the ``User`` row; routes never touch the cookie themselves.

Every account registered through the API is a customer (cooks too - roles
only grow); the accounts *without* the customer role are operator-made, such
as the seed's admin-only account.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.api.deps import DbSession
from app.core.config import get_settings
from app.modules.auth import service
from app.modules.auth.exceptions import ForbiddenError, UnauthenticatedError
from app.modules.auth.models import User, UserSession

__all__ = [
    "AdminRequired",
    "CookRequired",
    "CurrentSession",
    "CurrentUser",
    "CustomerRequired",
    "LoginRequired",
    "OptionalUser",
    "SessionToken",
    "optional_user",
    "require_admin",
    "require_cook",
    "require_customer",
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


async def optional_user(db: DbSession, request: Request) -> User | None:
    """The logged-in user, or ``None``. A missing, expired or revoked session
    is simply "a guest" here - never a 401."""
    token = request.cookies.get(get_settings().SESSION_COOKIE_NAME)
    if not token:
        return None
    try:
        return await service.current_user(db, token)
    except UnauthenticatedError:
        return None


async def require_customer(user: LoginRequired) -> User:
    """Authenticated *and* carrying the customer role; 403 otherwise (401
    still wins for anonymous callers, exactly like ``require_cook``).

    For what only shoppers do - e.g. keeping favourite dishes. A cook is a
    customer too, so they pass; an admin-only account does not.
    """
    if not user.is_customer:
        raise ForbiddenError("This action requires the customer role")
    return user


async def require_cook(user: LoginRequired) -> User:
    """Authenticated *and* carrying the cook role; 403 otherwise.

    401 always wins over 403: an anonymous request cannot learn which roles
    the endpoint would demand.
    """
    if not user.is_cook:
        raise ForbiddenError("This action requires the cook role")
    return user


async def require_admin(user: LoginRequired) -> User:
    """Authenticated *and* carrying the admin role; 403 otherwise (401 still
    wins for anonymous callers, exactly like ``require_cook``)."""
    if not user.is_admin:
        raise ForbiddenError("This action requires the admin role")
    return user


CurrentSession = Annotated[UserSession, Depends(require_current_session)]
LoginRequired = Annotated[User, Depends(require_login)]
CustomerRequired = Annotated[User, Depends(require_customer)]
CookRequired = Annotated[User, Depends(require_cook)]
AdminRequired = Annotated[User, Depends(require_admin)]
OptionalUser = Annotated[User | None, Depends(optional_user)]

# Back-compatible alias for the earlier /api/me annotation.
CurrentUser = LoginRequired
