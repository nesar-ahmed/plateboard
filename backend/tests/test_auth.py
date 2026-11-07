"""Auth acceptance tests.

Every case the spec demands:

* wrong password -> 401, duplicate email -> 409, logout invalidates the session
* generic login errors (never reveal whether an email exists)
* stored passwords are salted hashes, not plain text
* emails are unique/compared case-insensitively, cookie is HTTP-only
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.api.auth.models import User
from app.api.auth.security import verify_password
from app.core.db import get_sessionmaker

PASSWORD = "super-secret-passphrase"


async def _register(client, email: str = "user@example.com", password: str = PASSWORD):
    return await client.post(
        "/api/auth/register", json={"email": email, "password": password}
    )


async def _login(client, email: str = "user@example.com", password: str = PASSWORD):
    return await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )


async def _fetch_user(email: str) -> User | None:
    """Read the user row straight from the (temp) database."""
    async with get_sessionmaker()() as session:
        return (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()


def _token_from_login(response) -> str:
    """Extract the raw session token from a login response's Set-Cookie."""
    cookie = response.headers["set-cookie"]
    pair = cookie.split(";")[0]
    assert pair.startswith("plateboard_session=")
    return pair.split("=", 1)[1]


async def _replay(client, token: str):
    """Call /api/me with a manually supplied session cookie (bypasses the jar)."""
    return await client.get(
        "/api/me", headers={"cookie": f"plateboard_session={token}"}
    )


# --- register ---------------------------------------------------------------


async def test_register_creates_account_and_lowercases_email(client) -> None:
    response = await _register(client, "MixedCase@Example.COM")
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "mixedcase@example.com"
    assert "password" not in body and "password_hash" not in body


async def test_duplicate_email_returns_409(client) -> None:
    assert (await _register(client)).status_code == 201
    again = await _register(client)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "email_taken"


async def test_duplicate_email_is_case_insensitive(client) -> None:
    assert (await _register(client, "user@example.com")).status_code == 201
    dup = await _register(client, "USER@EXAMPLE.com")
    assert dup.status_code == 409


async def test_short_password_is_rejected(client) -> None:
    response = await _register(client, password="tiny1")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


# --- login ------------------------------------------------------------------


async def test_login_sets_httponly_session_cookie(client) -> None:
    await _register(client)
    response = await _login(client)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "secure" not in cookie  # non-production test environment


async def test_wrong_password_returns_401(client) -> None:
    await _register(client)
    response = await _login(client, password="wrong-but-long-enough")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_unknown_email_returns_401(client) -> None:
    response = await _login(client, email="ghost@example.com")
    assert response.status_code == 401


async def test_login_errors_are_generic_and_identical(client) -> None:
    """Wrong password and unknown email must be indistinguishable."""
    await _register(client)
    wrong_password = await _login(client, password="wrong-but-long-enough")
    unknown_email = await _login(client, email="ghost@example.com")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    body = wrong_password.json()["error"]
    assert "exists" not in body["message"].lower()
    assert "no account" not in body["message"].lower()
    assert "ghost@example.com" not in body["message"]


async def test_login_is_case_insensitive_on_email(client) -> None:
    await _register(client, "user@example.com")
    response = await _login(client, email="USER@Example.com")
    assert response.status_code == 200


# --- /api/me ------------------------------------------------------------------


async def test_me_without_session_returns_401(client) -> None:
    response = await client.get("/api/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_me_returns_the_logged_in_user(client) -> None:
    await _register(client)
    assert (await _login(client)).status_code == 200
    response = await client.get("/api/me")
    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"


# --- logout ----------------------------------------------------------------


async def test_logout_requires_a_session(client) -> None:
    response = await client.post("/api/auth/logout")
    assert response.status_code == 401


async def test_logout_invalidates_the_session(client) -> None:
    """Server-side revocation: replaying the *raw stolen token* must fail too,
    not just rely on the cookie being cleared from the client jar."""
    await _register(client)
    token = _token_from_login(await _login(client))

    assert (await client.post("/api/auth/logout")).status_code == 204

    # httpx applied the deletion to the jar, so the plain call gets no cookie...
    assert (await client.get("/api/me")).status_code == 401
    # ...and an explicit replay of the captured token is refused server-side.
    assert (await _replay(client, token)).status_code == 401


async def test_other_sessions_survive_one_logout(client) -> None:
    await _register(client)
    first = _token_from_login(await _login(client))
    # Cookie jar now holds the second token; logout revokes only that one.
    second = _token_from_login(await _login(client))
    await client.post("/api/auth/logout")
    assert (await _replay(client, first)).status_code == 200
    assert second != first


# --- password storage ---------------------------------------------------------


async def test_stored_password_is_not_plain_text(client) -> None:
    await _register(client)
    user = await _fetch_user("user@example.com")
    assert user is not None
    assert user.password_hash != PASSWORD
    assert PASSWORD not in user.password_hash
    assert user.password_hash.startswith("scrypt$")  # algo$params$salt$digest
    assert verify_password(PASSWORD, user.password_hash)
    assert not verify_password("wrong-but-long-enough", user.password_hash)


async def test_same_password_different_salts(client) -> None:
    await _register(client, "a@example.com")
    await _register(client, "b@example.com")
    a = await _fetch_user("a@example.com")
    b = await _fetch_user("b@example.com")
    assert a and b
    assert a.password_hash != b.password_hash, "per-user salt required"
    assert verify_password(PASSWORD, a.password_hash)
    assert verify_password(PASSWORD, b.password_hash)


# --- security module unit checks ------------------------------------------------


@pytest.mark.parametrize(
    "stored", ["not-a-scrypt-string", "scrypt$14$8$1$deadbeef$zzzz", ""]
)
def test_verify_password_rejects_garbage(stored: str) -> None:
    assert verify_password("whatever1234", stored) is False
