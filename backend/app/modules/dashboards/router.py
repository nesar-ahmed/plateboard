"""HTTP routes for the three dashboards - one read-only summary per audience.

* GET /api/me/dashboard         - customer view of the signed-in user
  (login only; every account can buy, cooks and admins included)
* GET /api/cooks/me/dashboard   - the signed-in cook's kitchen (cook only)
* GET /api/admin/dashboard      - the whole platform (admin only)
* GET /api/cooks/me/earnings    - the cook's money over a date range (cook
  only): completed orders by completion day, vs the previous range

Each answers one document with all-time summaries plus time series over a
window (``?months=`` for the customer's monthly spending, ``?days=`` for the
daily series of cooks and admins). Shapes: ``app.modules.dashboards.schemas``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.modules.auth.dependencies import AdminRequired, CookRequired, LoginRequired
from app.modules.dashboards import service
from app.modules.dashboards.schemas import (
    AdminDashboard,
    CookDashboard,
    CookEarnings,
    CustomerDashboard,
    EarningsQuery,
)

customer_dashboard_router = APIRouter(prefix="/api/me/dashboard", tags=["dashboards"])
cook_dashboard_router = APIRouter(prefix="/api/cooks/me/dashboard", tags=["dashboards"])
admin_dashboard_router = APIRouter(prefix="/api/admin/dashboard", tags=["dashboards"])
cook_earnings_router = APIRouter(prefix="/api/cooks/me/earnings", tags=["dashboards"])

Months = Annotated[int, Query(ge=1, le=24, description="monthly series length")]
Days = Annotated[int, Query(ge=1, le=365, description="daily series length")]


@customer_dashboard_router.get("", response_model=CustomerDashboard)
async def customer_dashboard(
    user: LoginRequired, db: DbSession, months: Months = 6
) -> CustomerDashboard:
    """Orders by status, monthly spending, favourite cooks and dishes, the
    latest orders and the current cart."""
    return await service.customer_dashboard(db, user.id, months=months)


@cook_dashboard_router.get("", response_model=CookDashboard)
async def cook_dashboard(
    user: CookRequired, db: DbSession, days: Days = 30
) -> CookDashboard:
    """The kitchen at a glance: money tiles (today / 7 days / this month /
    lifetime + open pipeline), the open-order queue (oldest first), orders by
    status, daily revenue, best sellers, top customers, request handling
    (acceptance rate, timings), cart demand, the menu breakdown, the set-up
    checklist and the latest orders."""
    return await service.cook_dashboard(db, user.id, days=days)


@cook_earnings_router.get("", response_model=CookEarnings)
async def cook_earnings(
    user: CookRequired,
    db: DbSession,
    query: Annotated[EarningsQuery, Query()],
) -> CookEarnings:
    """Earnings over ``start``..``end`` (inclusive UTC dates; default the
    last 30 days, at most 366): the summary and the same-length range before
    it, a zero-filled series per ``group`` (day / week / month), earnings per
    dish, lifetime earnings and the open pipeline. An order is *earned* on
    the day it is completed."""
    return await service.cook_earnings(db, user.id, query)


@admin_dashboard_router.get("", response_model=AdminDashboard)
async def admin_dashboard(
    _admin: AdminRequired, db: DbSession, days: Days = 30
) -> AdminDashboard:
    """Users and signups, platform orders and daily volume, top cooks and
    dishes, the zone grid's activity, the menu breakdown and open carts."""
    return await service.admin_dashboard(db, days=days)
