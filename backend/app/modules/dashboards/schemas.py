"""Response schemas for the three dashboards (customer, cook, admin).

Conventions shared by every dashboard, so the frontend can reuse its charts:

* Money is integer minor units. "Value" always means the totals of orders
  that were **not cancelled** (``booked``); ``completed_value`` is the part
  that is already completed.
* Summary blocks (``orders``, rankings, menu, carts) are **all-time**; time
  series cover the requested **window** (``window`` says which), one point per
  UTC day or month, oldest first, with empty periods present as zeros - a
  chart can plot the list as-is.
* Rankings are the top :data:`TOP_N`, best first, ties broken by name.
* The cook's **earnings** are completed orders, counted on the UTC day they
  were *completed* (the handover, when the customer pays the cook); open
  orders are not earned yet (``awaiting_acceptance`` / ``in_progress``).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Literal, Self

from pydantic import (
    BaseModel,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.modules.cart.schemas import CartCookOut
from app.modules.orders.schemas import OrderOut
from app.modules.zones.schemas import ZoneOut
from app.shared.base import utcnow
from app.shared.types import UTCDateTime

#: Length of every ranking list.
TOP_N = 5
#: Most open orders the cook dashboard lists in its queue.
QUEUE_LIMIT = 20
#: Default and longest span of ``GET /api/cooks/me/earnings``, in days.
EARNINGS_DEFAULT_DAYS = 30
EARNINGS_MAX_DAYS = 366

# --- shared building blocks ------------------------------------------------------------


class Window(BaseModel):
    """The period the time series cover (UTC calendar days/months, inclusive)."""

    unit: Literal["day", "month"]
    periods: int = Field(description="number of points in each series")
    start: date = Field(description="first day covered")
    end: date = Field(description="last day covered (today, UTC)")


class StatusCounts(BaseModel):
    """Orders per status - one field per status, for donut/stacked charts."""

    placed: int = 0
    accepted: int = 0
    ready: int = 0
    completed: int = 0
    cancelled: int = 0


class OrderStats(BaseModel):
    orders: int = Field(description="every order, cancelled included")
    by_status: StatusCounts
    open: int = Field(description="placed + accepted + ready (still in progress)")
    booked_value: int = Field(description="totals of non-cancelled orders, minor units")
    completed_value: int = Field(description="totals of completed orders, minor units")
    average_order_value: int = Field(
        description="booked_value / non-cancelled orders (0 without any), minor units"
    )


class OrderPoint(BaseModel):
    """One period of an order time series (bar/line charts)."""

    period: str = Field(description="YYYY-MM-DD (day series) or YYYY-MM (month series)")
    orders: int = Field(description="orders placed in the period, cancelled excluded")
    cancelled: int = Field(
        description="orders placed in the period and later cancelled"
    )
    value: int = Field(description="totals of the non-cancelled ones, minor units")


class CountPoint(BaseModel):
    period: str = Field(description="YYYY-MM-DD")
    count: int


class TagCount(BaseModel):
    """How many active dishes carry an allergen / dietary tag."""

    name: str
    count: int


class DishRank(BaseModel):
    dish_id: uuid.UUID | None = Field(description="null if the dish was deleted since")
    name: str = Field(description="current dish name (or the ordered one if deleted)")
    quantity: int = Field(description="portions ordered (non-cancelled orders)")
    orders: int = Field(description="orders containing the dish")
    value: int = Field(description="line totals, minor units")


class CookRank(BaseModel):
    cook_id: uuid.UUID
    name: str | None
    orders: int = Field(description="non-cancelled orders")
    value: int = Field(description="their totals, minor units")


class PriceStats(BaseModel):
    """Over active dishes; all null while there are none."""

    min: int | None
    avg: int | None = Field(description="rounded to a whole minor unit")
    max: int | None


class MenuStats(BaseModel):
    dishes: int = Field(description="every dish, deactivated included")
    active: int
    inactive: int
    price: PriceStats
    allergens: list[TagCount] = Field(
        description="over active dishes, most common first"
    )
    dietary_tags: list[TagCount] = Field(
        description="over active dishes, most common first"
    )


class CartDemand(BaseModel):
    """Dishes waiting in shoppers' carts right now (active dishes only) - a
    demand signal before anything is ordered."""

    carts: int = Field(description="carts holding at least one such dish")
    portions: int
    value: int = Field(description="at current prices, minor units")


# --- customer ----------------------------------------------------------------------------


class CartSnapshot(BaseModel):
    """The caller's cart in one line (the full cart is ``GET /api/cart``)."""

    cook: CartCookOut | None
    lines: int = Field(description="distinct dishes")
    item_count: int = Field(description="portions across available lines")
    total: int = Field(description="minor units, available lines only")
    unavailable_count: int


class CustomerDashboard(BaseModel):
    """``GET /api/me/dashboard`` - the signed-in user as a buyer."""

    window: Window
    orders: OrderStats
    spending: list[OrderPoint] = Field(description="per month, over the window")
    favourite_cooks: list[CookRank]
    favourite_dishes: list[DishRank]
    recent_orders: list[OrderOut] = Field(
        description=f"the latest {TOP_N}, newest first"
    )
    cart: CartSnapshot


# --- cook --------------------------------------------------------------------------------


class CustomerStats(BaseModel):
    unique: int = Field(description="customers with at least one non-cancelled order")
    repeat: int = Field(description="...of which ordered more than once")


class Amount(BaseModel):
    """A number of orders and their totals."""

    orders: int
    value: int = Field(description="minor units")


class EarningsSnapshot(BaseModel):
    """What the kitchen earned (completed orders, by UTC completion day) and
    what is still in the pipeline (open orders - not earned yet)."""

    today: Amount
    last_7_days: Amount = Field(description="today and the 6 days before")
    this_month: Amount = Field(description="since the 1st of the current month")
    lifetime: Amount
    awaiting_acceptance: Amount = Field(description="placed: requests to answer")
    in_progress: Amount = Field(description="accepted + ready: to cook / hand over")


class KitchenPerformance(BaseModel):
    """How the kitchen handles requests (all-time). A *rejection* is a
    ``placed`` order the cook cancelled; once accepted, it is a cancellation."""

    accepted: int = Field(description="requests the cook accepted")
    rejected: int = Field(description="requests the cook turned down")
    acceptance_rate: float | None = Field(
        description="accepted / (accepted + rejected), 0..1 (null before any answer)"
    )
    cancelled_after_accepting: int = Field(description="by the cook")
    cancelled_by_customer: int
    cancellation_rate: float | None = Field(
        description="cancelled / all orders, 0..1 (null without orders)"
    )
    average_accept_minutes: float | None = Field(
        description="placed -> accepted (null without accepted orders)"
    )
    average_prep_minutes: float | None = Field(
        description="accepted -> ready (null without ready orders)"
    )


class CustomerRank(BaseModel):
    """One of the kitchen's best customers."""

    customer_id: uuid.UUID
    name: str | None
    orders: int = Field(description="non-cancelled orders")
    value: int = Field(description="their totals, minor units")
    last_order_at: UTCDateTime = Field(description="latest of those orders")


ProfileStepKey = Literal[
    "display_name", "bio", "specialties", "zone", "public_dish", "dish_descriptions"
]


class ProfileStep(BaseModel):
    key: ProfileStepKey
    done: bool


class ProfileChecklist(BaseModel):
    """Kitchen set-up progress - what makes a cook findable and trusted.

    Steps (UI copy lives in the frontend): ``display_name`` and ``bio``
    (``PATCH /api/me/profile``), ``specialties`` and ``zone`` (``PATCH
    /api/cooks/me``), ``public_dish`` (at least one public dish) and
    ``dish_descriptions`` (every public dish has a description).
    """

    done: int
    total: int
    steps: list[ProfileStep]


class CookDashboard(BaseModel):
    """``GET /api/cooks/me/dashboard`` - the signed-in cook's kitchen."""

    window: Window
    zone: ZoneOut | None
    orders: OrderStats
    revenue: list[OrderPoint] = Field(description="per day, over the window")
    top_dishes: list[DishRank]
    customers: CustomerStats
    average_fulfilment_minutes: float | None = Field(
        description="placed -> completed (the customer's confirmation of receipt), "
        "over completed orders (null without any)"
    )
    demand: CartDemand
    menu: MenuStats
    recent_orders: list[OrderOut] = Field(
        description=f"the latest {TOP_N}, newest first"
    )
    earnings: EarningsSnapshot
    performance: KitchenPerformance
    top_customers: list[CustomerRank]
    queue: list[OrderOut] = Field(
        description=f"open orders (placed, accepted, ready), oldest first - at most "
        f"{QUEUE_LIMIT}; ``orders.by_status`` has the full counts"
    )
    checklist: ProfileChecklist


# --- cook earnings -----------------------------------------------------------------------

EarningsGroup = Literal["day", "week", "month"]


class EarningsQuery(BaseModel):
    """Query string of ``GET /api/cooks/me/earnings``.

    ``start``/``end`` are inclusive UTC dates. ``end`` defaults to today,
    ``start`` to :data:`EARNINGS_DEFAULT_DAYS` days ending at ``end`` - so
    ``?start=2026-11-01`` alone means "since the 1st". The span is at most
    :data:`EARNINGS_MAX_DAYS` days. ``group`` picks the series buckets: days,
    ISO weeks (labelled by their Monday) or months. After validation both
    dates are always set.
    """

    start: date | None = Field(default=None, description="first day (inclusive)")
    end: date | None = Field(
        default=None,
        validate_default=True,  # so a missing end still gets checked against start
        description="last day (inclusive, default today)",
    )
    group: EarningsGroup = "day"

    # Checked on ``end`` (declared after ``start``, so ``info.data`` has it):
    # a bad range is a 422 naming the field, like the menu's price range.
    @field_validator("end")
    @classmethod
    def _end_after_start(cls, value: date | None, info: ValidationInfo) -> date:
        end = value or utcnow().date()
        start = info.data.get("start")
        if start is not None:
            if start > end:
                raise ValueError("end must be on or after start (default end: today)")
            if (end - start).days + 1 > EARNINGS_MAX_DAYS:
                raise ValueError(f"the range is limited to {EARNINGS_MAX_DAYS} days")
        return end

    @model_validator(mode="after")
    def _default_start(self) -> Self:
        if self.start is None and self.end is not None:
            self.start = self.end - timedelta(days=EARNINGS_DEFAULT_DAYS - 1)
        return self

    @property
    def days(self) -> int:
        assert self.start is not None and self.end is not None  # set by the validator
        return (self.end - self.start).days + 1


class EarningsRange(BaseModel):
    start: date
    end: date
    days: int = Field(description="length of the range")
    group: EarningsGroup


class EarningsSummary(BaseModel):
    """One range's figures. ``earned`` counts orders *completed* in the range;
    cancellations count by when they were cancelled."""

    earned: int = Field(description="totals of orders completed in the range")
    orders: int = Field(description="orders completed in the range")
    portions: int
    average_order_value: int = Field(description="earned / orders (0 without any)")
    cancelled_orders: int = Field(description="orders cancelled in the range")
    cancelled_value: int = Field(description="their totals - value lost")
    rejected_orders: int = Field(
        description="of the cancelled: requests the cook turned down"
    )


class EarningsPoint(BaseModel):
    period: str = Field(
        description="YYYY-MM-DD (day; a week is labelled by its Monday) or YYYY-MM"
    )
    orders: int = Field(description="orders completed in the period")
    earned: int


class CookEarnings(BaseModel):
    """``GET /api/cooks/me/earnings`` - the kitchen's money over a date range."""

    range: EarningsRange
    summary: EarningsSummary
    previous: EarningsSummary = Field(
        description="the same number of days right before ``start`` (for trends)"
    )
    series: list[EarningsPoint] = Field(
        description="per day/week/month over the range, zero-filled, oldest first"
    )
    dishes: list[DishRank] = Field(
        description="every dish in orders completed in the range, by value"
    )
    lifetime: Amount
    awaiting_acceptance: Amount
    in_progress: Amount


# --- admin -------------------------------------------------------------------------------


class UserStats(BaseModel):
    total: int
    customers: int = Field(description="accounts holding the customer role")
    cooks: int = Field(description="accounts holding the cook role")
    admins: int
    new_in_window: int = Field(description="accounts created within the window")
    active_sessions: int = Field(description="unexpired, not logged out")
    pending_cook_applications: int = Field(
        description="cook applications waiting for an admin's decision"
    )


class ZoneStats(ZoneOut):
    """One grid cell with its activity (a heat-map tile)."""

    cooks: int
    active_dishes: int
    orders: int = Field(description="non-cancelled orders with cooks in the zone")
    value: int = Field(description="their totals, minor units")


class PlatformCarts(CartDemand):
    guest_carts: int
    account_carts: int


class AdminDashboard(BaseModel):
    """``GET /api/admin/dashboard`` - the whole platform."""

    window: Window
    users: UserStats
    signups: list[CountPoint] = Field(
        description="new accounts per day, over the window"
    )
    orders: OrderStats
    order_series: list[OrderPoint] = Field(description="per day, over the window")
    top_cooks: list[CookRank]
    top_dishes: list[DishRank]
    zones: list[ZoneStats] = Field(description="every zone in grid order")
    menu: MenuStats
    carts: PlatformCarts
