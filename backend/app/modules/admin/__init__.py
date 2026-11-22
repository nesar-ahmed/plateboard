"""Admin back office (role: admin): platform-wide user and order lists.

* ``admin_router`` - ``GET /api/admin/users``, ``GET /api/admin/orders`` and
  cook verification (``POST|DELETE /api/admin/cooks/{id}/verification``)

The admin role is granted only by operator scripts (``scripts/seed.py``),
never through the API. The admin dashboard lives in ``app.modules.dashboards``.
"""

from app.modules.admin.router import admin_router

__all__ = ["admin_router"]
