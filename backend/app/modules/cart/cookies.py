"""The guest-cart cookie (``CART_COOKIE_NAME``), set/cleared in one place.

Used by the cart router (first add as a guest) and the auth router (login
claims the guest cart, so the cookie goes away).
"""

from __future__ import annotations

from fastapi import Request, Response

from app.core.config import get_settings
from app.core.cookies import cookie_attrs


def read_guest_token(request: Request) -> str | None:
    return request.cookies.get(get_settings().CART_COOKIE_NAME) or None


def set_guest_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.CART_COOKIE_NAME,
        value=token,
        max_age=settings.CART_TTL_DAYS * 86400,  # integer seconds, like the session
        httponly=True,  # page scripts never see the token
        **cookie_attrs(),
    )


def clear_guest_cookie(response: Response) -> None:
    response.delete_cookie(key=get_settings().CART_COOKIE_NAME, **cookie_attrs())
