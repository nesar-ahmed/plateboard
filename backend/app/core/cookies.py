"""Attributes shared by every cookie the API sets (session, guest cart).

One definition keeps them consistent: site-wide path, ``SameSite=Lax`` (not
sent on cross-site POSTs, which is the CSRF protection for cookie-authed
writes) and ``Secure`` in production, where the site is served over HTTPS.
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings


def cookie_attrs() -> dict[str, Any]:
    """Kwargs for ``Response.set_cookie`` / ``delete_cookie`` (besides key/value)."""
    return {"path": "/", "samesite": "lax", "secure": get_settings().is_production}
