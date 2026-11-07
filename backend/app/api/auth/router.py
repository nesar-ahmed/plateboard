"""HTTP routes for authentication.

Mounted un-versioned under ``/api`` (same philosophy as ``/api/health``):

* POST /api/auth/register  - create an account
* POST /api/auth/login     - create a session, set the HTTP-only cookie
* POST /api/auth/logout    - revoke the session, clear the cookie
* GET  /api/me             - the authenticated user
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.api.auth import service
from app.api.auth.dependencies import CurrentSession, CurrentUser
from app.api.auth.schemas import LoginRequest, RegisterRequest, UserOut
from app.api.deps import DbSession
from app.core.config import get_settings

auth_router = APIRouter(prefix="/api", tags=["auth"])


def _cookie_attrs() -> dict:
    """Shared cookie kwargs; Secure only in production (HTTPS)."""
    return {"path": "/", "samesite": "lax", "secure": get_settings().is_production}


@auth_router.post("/auth/register", response_model=UserOut, status_code=201)
async def register(payload: RegisterRequest, db: DbSession) -> UserOut:
    user = await service.register(db, payload)
    return UserOut.model_validate(user)


@auth_router.post("/auth/login")
async def login(payload: LoginRequest, response: Response, db: DbSession) -> UserOut:
    user, token = await service.login(db, payload)
    response.set_cookie(
        key=get_settings().SESSION_COOKIE_NAME,
        value=token,
        # Max-Age must be integer seconds (a timedelta here would serialize
        # as "7 days, 0:00:00", which strict clients reject outright).
        max_age=get_settings().SESSION_TTL_DAYS * 86400,
        httponly=True,  # JS can never read it - XSS cannot steal the session
        **_cookie_attrs(),
    )
    return UserOut.model_validate(user)


@auth_router.post("/auth/logout", status_code=204)
async def logout(db: DbSession, current: CurrentSession) -> Response:
    await service.logout(db, current)
    response = Response(status_code=204)
    response.delete_cookie(key=get_settings().SESSION_COOKIE_NAME, **_cookie_attrs())
    return response


@auth_router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
