"""Account endpoints behind the user panel (``/account`` in the frontend).

Acceptance rules under test:

* food preferences: login required; empty by default; PUT replaces both
  lists; allergens must be known (422) and are de-duplicated; diets are
  trimmed, lowercased, unique tags;
* password change: the current password must match (422 ``wrong_password``
  on ``current_password``), the new one must differ and be 8+ characters;
  afterwards the old password fails, the new one works, *other* sessions are
  signed out and this one stays;
* sessions: list the active ones (this one flagged ``current``, never the
  token), and "sign out everywhere else" keeps only this one.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command

from tests.conftest import DEFAULT_PASSWORD, make_alembic_config

PREFS = "/api/me/preferences"
EMAIL = "user@example.com"
NEW_PASSWORD = "a-brand-new-passphrase"


def assert_error(
    response, status: int, code: str, detail_type: str | None = None
) -> dict:
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code, error
    if detail_type is not None:
        assert detail_type in {d["type"] for d in error["details"]}, error
    return error


async def second_device(
    make_client, email: str = EMAIL, password: str = DEFAULT_PASSWORD
):
    """Log the same account in from another 'browser' (own cookie jar)."""
    other = make_client()
    response = await other.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return other


# --- preferences ----------------------------------------------------------------------


async def test_preferences_require_login(client) -> None:
    assert_error(await client.get(PREFS), 401, "unauthenticated")
    assert_error(await client.put(PREFS, json={}), 401, "unauthenticated")


async def test_preferences_default_empty_and_put_replaces(accounts) -> None:
    await accounts.customer()
    client = accounts.client
    assert (await client.get(PREFS)).json() == {
        "excluded_allergens": [],
        "dietary_preferences": [],
    }

    saved = await client.put(
        PREFS,
        json={
            "excluded_allergens": ["peanuts", "milk", "peanuts"],
            "dietary_preferences": [" Vegan ", "gluten free"],
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json() == {
        "excluded_allergens": ["peanuts", "milk"],
        "dietary_preferences": ["vegan", "gluten free"],
    }
    # PUT is a full replacement: omitted lists become empty.
    cleared = await client.put(PREFS, json={"excluded_allergens": ["sesame"]})
    assert cleared.json() == {
        "excluded_allergens": ["sesame"],
        "dietary_preferences": [],
    }
    assert (await client.get(PREFS)).json() == cleared.json()


@pytest.mark.parametrize(
    "body",
    [
        {"excluded_allergens": ["chocolate"]},
        {"dietary_preferences": ["vegan", "VEGAN"]},
        {"dietary_preferences": ["   "]},
        {"dietary_preferences": ["x" * 31]},
    ],
)
async def test_preferences_validation(accounts, body) -> None:
    await accounts.customer()
    assert_error(await accounts.client.put(PREFS, json=body), 422, "validation_failed")


def test_existing_accounts_get_empty_preferences(environment, tmp_path: Path) -> None:
    """0009 adds NOT NULL columns: rows created before it must read as []."""
    config = make_alembic_config()
    command.downgrade(config, "0008")
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
            ("b" * 32, "before-0009@example.com", "x"),
        )
        conn.commit()
    finally:
        conn.close()
    command.upgrade(config, "head")
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT excluded_allergens, dietary_preferences FROM users"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("[]", "[]")


# --- password ---------------------------------------------------------------------------


async def test_password_change_rules(accounts) -> None:
    await accounts.customer()
    client = accounts.client
    wrong = await client.post(
        "/api/me/password",
        json={"current_password": "not-my-password", "new_password": NEW_PASSWORD},
    )
    assert_error(wrong, 422, "validation_failed", "wrong_password")
    same = await client.post(
        "/api/me/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": DEFAULT_PASSWORD},
    )
    assert_error(same, 422, "validation_failed")
    short = await client.post(
        "/api/me/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "short"},
    )
    assert_error(short, 422, "validation_failed")


async def test_password_change_signs_out_other_sessions_only(
    accounts, make_client
) -> None:
    await accounts.customer()
    client = accounts.client
    other = await second_device(make_client)
    changed = await client.post(
        "/api/me/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json() == {"signed_out_sessions": 1}

    assert (await client.get("/api/me")).status_code == 200  # this one stays
    assert_error(await other.get("/api/me"), 401, "unauthenticated")  # that one ended

    client.cookies.clear()
    assert (await accounts.login(EMAIL, DEFAULT_PASSWORD)).status_code == 401
    assert (await accounts.login(EMAIL, NEW_PASSWORD)).status_code == 200


# --- sessions -----------------------------------------------------------------------------


async def test_sessions_list_and_sign_out_elsewhere(accounts, make_client) -> None:
    await accounts.customer()
    client = accounts.client
    other = await second_device(make_client)
    sessions = (await client.get("/api/me/sessions")).json()
    assert len(sessions) == 2
    assert sorted(s["current"] for s in sessions) == [False, True]
    assert all(len(s["id"]) == 12 for s in sessions)  # a fingerprint, not the token
    assert client.cookies["plateboard_session"] not in {s["id"] for s in sessions}

    ended = await client.post("/api/me/sessions/revoke-others")
    assert ended.json() == {"signed_out_sessions": 1}
    assert [s["current"] for s in (await client.get("/api/me/sessions")).json()] == [
        True
    ]
    assert_error(await other.get("/api/me"), 401, "unauthenticated")

    assert_error(await make_client().get("/api/me/sessions"), 401, "unauthenticated")
