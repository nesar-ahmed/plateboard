"""Auth business logic. The only layer that touches users/sessions queries.

Sessions own their transaction: each function commits when its unit of work
is complete (the request-scoped ``DbSession`` only rolls back on error).

Notifications (``/account`` inbox): a welcome on registration and a security
notice on a password change, written in the same transaction.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ValidationFailedError
from app.modules.auth.exceptions import (
    CredentialsError,
    EmailTakenError,
    UnauthenticatedError,
)
from app.modules.auth.models import User, UserSession
from app.modules.auth.schemas import (
    LoginRequest,
    PasswordChangeRequest,
    PreferencesUpdate,
    ProfilePatchRequest,
    RegisterRequest,
)
from app.modules.auth.security import (
    hash_password,
    hash_token,
    new_session_token,
    verify_login_attempt,
    verify_password,
)
from app.modules.notifications import service as notifications
from app.modules.notifications.catalog import (
    AccountPayload,
    NotificationType,
    PasswordChangedPayload,
)
from app.modules.notifications.models import Audience
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
        # The flush assigns the id the welcome points at; the same email
        # racing in from another request fails here or at the commit - a 409.
        await session.flush()
        await notifications.notify(
            session,
            recipient_id=user.id,
            audience=Audience.ACCOUNT,
            kind=NotificationType.ACCOUNT_WELCOME,
            payload=AccountPayload(),
            actor_id=user.id,
        )
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
    """Apply the fields the client sent: omitted means 'keep', null 'clear'."""
    # ``exclude_unset`` is what makes PATCH partial while still letting an
    # explicit null through (same contract as ``dishes.service.update_dish``).
    changes: dict[str, Any] = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(user, field, value)
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


# --- account: preferences, password, sessions ---------------------------------------


class WrongPasswordError(ValidationFailedError):
    """The current password in a password change is wrong: a 422 on that
    field (the caller is signed in - this is form validation, not login)."""

    default_message = "Current password is incorrect"

    def __init__(self) -> None:
        super().__init__(
            details=[
                {
                    "field": "current_password",
                    "type": "wrong_password",
                    "message": "does not match your current password",
                }
            ]
        )


async def update_preferences(
    session: AsyncSession, user: User, payload: PreferencesUpdate
) -> User:
    """Replace both preference lists (PUT semantics)."""
    user.excluded_allergens = list(payload.excluded_allergens)
    user.dietary_preferences = list(payload.dietary_preferences)
    await session.commit()
    await session.refresh(user)
    return user


async def _revoke_other_sessions(
    session: AsyncSession, user_id: Any, keep: UserSession
) -> int:
    result = cast(
        CursorResult[Any],
        await session.execute(
            update(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.token_hash != keep.token_hash,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > utcnow(),
            )
            .values(revoked_at=utcnow())
            .execution_options(synchronize_session=False)
        ),
    )
    return result.rowcount


async def change_password(
    session: AsyncSession,
    user: User,
    current: UserSession,
    payload: PasswordChangeRequest,
) -> int:
    """Verify the current password, store the new hash and sign out every
    *other* session (a changed password should lock out whoever else might
    be signed in). Returns how many sessions were ended."""
    if not verify_password(payload.current_password, user.password_hash):
        raise WrongPasswordError
    user.password_hash = hash_password(payload.new_password)
    ended = await _revoke_other_sessions(session, user.id, current)
    await notifications.notify(
        session,
        recipient_id=user.id,
        audience=Audience.ACCOUNT,
        kind=NotificationType.ACCOUNT_PASSWORD_CHANGED,
        payload=PasswordChangedPayload(signed_out_sessions=ended),
        actor_id=user.id,
    )
    await session.commit()
    return ended


async def list_sessions(session: AsyncSession, user_id: Any) -> list[UserSession]:
    """Active (unrevoked, unexpired) sessions, newest first."""
    stmt = (
        select(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > utcnow(),
        )
        .order_by(UserSession.created_at.desc())
    )
    return list((await session.scalars(stmt)).all())


async def revoke_other_sessions(session: AsyncSession, current: UserSession) -> int:
    ended = await _revoke_other_sessions(session, current.user_id, current)
    await session.commit()
    return ended
