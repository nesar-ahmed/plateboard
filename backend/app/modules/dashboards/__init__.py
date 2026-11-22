"""Dashboard feature: read-only summaries for customers, cooks and admins.

* ``customer_dashboard_router`` - ``GET /api/me/dashboard``
* ``cook_dashboard_router``     - ``GET /api/cooks/me/dashboard``
* ``admin_dashboard_router``    - ``GET /api/admin/dashboard``
* ``cook_earnings_router``      - ``GET /api/cooks/me/earnings``

All aggregation happens in SQL (``service.py``); the definitions (booked value,
open orders, rankings, zero-filled series) are shared by all three.
"""

from app.modules.dashboards.router import (
    admin_dashboard_router,
    cook_dashboard_router,
    cook_earnings_router,
    customer_dashboard_router,
)

__all__ = [
    "admin_dashboard_router",
    "cook_dashboard_router",
    "cook_earnings_router",
    "customer_dashboard_router",
]
