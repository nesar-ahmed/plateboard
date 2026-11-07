"""Auth business logic. The only layer that touches users/sessions queries.

Sessions own their transaction: each function commits when its unit of work
is complete (the request-scoped ``DbSession`` only rolls back on error).
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.exceptions import (
    CredentialsError,
    EmailTakenError,
    UnauthenticatedError,
)
from app.api.auth.models import User, UserSession
from app.api.auth.schemas import LoginRequest, ProfilePatchRequest, RegisterRequest
from app.api.auth.security import (
    hash_password,
    hash_token,
    new_session_token,
    verify_login_attempt,
)
from app.core.config import get_settings
from app.shared.base import utcnow


def normalize_email(email: str) -> str:
    """Case-insensitive uniqueness by storage convention, not by dialect magic."""
    return email.strip().lower()


async def register(session: AsyncSession, payload: RegisterRequest) -> User:
    email = normalize_email(payload.email)
    if await _find_user(session, email):
        raise EmailTakenError
    user = User(email=email, password_hash=hash_password(payload.password))
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:  # race: another request inserted the same email
        await session.rollback()
        raise EmailTakenError from None
    await session.refresh(user)
    return user


async def login(session: AsyncSession, payload: LoginRequest) -> tuple[User, str]:
    """Return ``(user, cookie_token)`` or raise the generic 401."""
    user = await _find_user(session, normalize_email(payload.email))
    if not verify_login_attempt(payload.password, user.password_hash if user else None):
        raise CredentialsError
    assert user is not None  # verify_login_attempt only succeeds for a real row

    ttl = timedelta(days=get_settings().SESSION_TTL_DAYS)
    token, token_hash = new_session_token()
    session.add(
        UserSession(token_hash=token_hash, user_id=user.id, expires_at=utcnow() + ttl)
    )
    await session.commit()
    return user, token


async def get_active_session(session: AsyncSession, token: str) -> UserSession:
    row = await session.get(UserSession, hash_token(token))
    if row is None or not row.active:
        raise UnauthenticatedError
    return row


async def logout(session: AsyncSession, current: UserSession) -> None:
    """Revoke server-side; deleting the cookie alone would leave it replayable."""
    current.revoked_at = utcnow()
    await session.commit()


async def update_profile(
    session: AsyncSession, user: User, payload: ProfilePatchRequest
) -> User:
    """Apply the optional fields of a ProfilePatchRequest; None means 'keep'."""
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.bio is not None:
        user.bio = payload.bio
    if payload.area is not None:
        user.area = payload.area
    await session.commit()
    await session.refresh(user)
    return user


async def current_user(session: AsyncSession, token: str) -> User:
    current = await get_active_session(session, token)
    user = await session.get(User, current.user_id)
    if user is None:  # FK cascade normally prevents this
        raise UnauthenticatedError
    return user


async def _find_user(session: AsyncSession, email: str) -> User | None:
    return (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
