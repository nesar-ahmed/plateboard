"""Auth dependencies: resolve the session cookie to a user or session row."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.api.auth import service
from app.api.auth.exceptions import UnauthenticatedError
from app.api.auth.models import User, UserSession
from app.api.deps import DbSession
from app.core.config import get_settings

__all__ = [
    "CurrentSession",
    "CurrentUser",
    "get_session_token",
    "require_current_session",
    "require_current_user",
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


async def require_current_user(db: DbSession, token: SessionToken) -> User:
    return await service.current_user(db, token)


CurrentSession = Annotated[UserSession, Depends(require_current_session)]
CurrentUser = Annotated[User, Depends(require_current_user)]
