"""HTTP routes for authentication.

Mounted un-versioned under ``/api`` (same philosophy as ``/api/health``):

* POST /api/auth/register  - create an account
* POST /api/auth/login     - create a session, set the HTTP-only cookie, and
                             move a guest cart (if any) to the account
* POST /api/auth/logout    - revoke the session, clear the cookie
* GET  /api/me             - the authenticated user
* PATCH /api/me/profile    - display name / bio / area
* GET|PUT /api/me/preferences - food profile (excluded allergens, diets)
* POST /api/me/password    - change password (signs out other sessions)
* GET  /api/me/sessions    - active sessions; POST .../revoke-others ends them
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app.api.deps import DbSession
from app.core.config import get_settings
from app.core.cookies import cookie_attrs as _cookie_attrs
from app.modules.auth import service
from app.modules.auth.dependencies import CurrentSession, LoginRequired
from app.modules.auth.schemas import (
    LoginRequest,
    PasswordChangedOut,
    PasswordChangeRequest,
    PreferencesOut,
    PreferencesUpdate,
    ProfilePatchRequest,
    RegisterRequest,
    SessionOut,
    SessionsRevokedOut,
    UserOut,
)
from app.modules.cart.cookies import clear_guest_cookie, read_guest_token
from app.modules.cart.service import claim_guest_cart

auth_router = APIRouter(prefix="/api", tags=["auth"])


@auth_router.post("/auth/register", response_model=UserOut, status_code=201)
async def register(payload: RegisterRequest, db: DbSession) -> UserOut:
    user = await service.register(db, payload)
    return UserOut.model_validate(user)


@auth_router.post("/auth/login")
async def login(
    payload: LoginRequest, request: Request, response: Response, db: DbSession
) -> UserOut:
    """Log in; a guest cart from this browser becomes the account's cart (see
    ``claim_guest_cart`` for how it combines with an existing one)."""
    user, token = await service.login(db, payload)
    guest_token = read_guest_token(request)
    if guest_token:
        await claim_guest_cart(db, user.id, guest_token)
        clear_guest_cookie(response)
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
async def me(user: LoginRequired) -> UserOut:
    return UserOut.model_validate(user)


@auth_router.patch("/me/profile", response_model=UserOut)
async def patch_profile(
    payload: ProfilePatchRequest, user: LoginRequired, db: DbSession
) -> UserOut:
    """Edit display name / bio / free-text area. Omitted fields are kept, an
    explicit ``null`` clears one. Length limits live in ProfilePatchRequest;
    an empty body, blank string or oversized field is a 422."""
    updated = await service.update_profile(db, user, payload)
    return UserOut.model_validate(updated)


@auth_router.get("/me/preferences", response_model=PreferencesOut)
async def get_preferences(user: LoginRequired) -> PreferencesOut:
    return PreferencesOut.model_validate(user, from_attributes=True)


@auth_router.put("/me/preferences", response_model=PreferencesOut)
async def put_preferences(
    payload: PreferencesUpdate, user: LoginRequired, db: DbSession
) -> PreferencesOut:
    """Replace the food profile. Unknown allergens are a 422; diets follow
    the dish-tag rules (trimmed, lowercase, unique, max 10)."""
    updated = await service.update_preferences(db, user, payload)
    return PreferencesOut.model_validate(updated, from_attributes=True)


@auth_router.post("/me/password", response_model=PasswordChangedOut)
async def change_password(
    payload: PasswordChangeRequest,
    user: LoginRequired,
    current: CurrentSession,
    db: DbSession,
) -> PasswordChangedOut:
    """Wrong current password -> 422 (``wrong_password`` on
    ``current_password``). This session stays signed in; all others end."""
    ended = await service.change_password(db, user, current, payload)
    return PasswordChangedOut(signed_out_sessions=ended)


@auth_router.get("/me/sessions", response_model=list[SessionOut])
async def list_sessions(current: CurrentSession, db: DbSession) -> list[SessionOut]:
    rows = await service.list_sessions(db, current.user_id)
    return [
        SessionOut(
            id=row.token_hash[:12],
            created_at=row.created_at,
            expires_at=row.expires_at,
            current=row.token_hash == current.token_hash,
        )
        for row in rows
    ]


@auth_router.post("/me/sessions/revoke-others", response_model=SessionsRevokedOut)
async def revoke_other_sessions(
    current: CurrentSession, db: DbSession
) -> SessionsRevokedOut:
    """Sign out everywhere else; this session stays."""
    return SessionsRevokedOut(
        signed_out_sessions=await service.revoke_other_sessions(db, current)
    )
