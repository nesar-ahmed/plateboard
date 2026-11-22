"""Dashboard read models: aggregates computed in SQL, assembled per audience.

Each building block is one query (or a handful) scoped by who is asking -
``customer_id`` for the customer dashboard, ``cook_id`` for the cook's, no
scope for the admin's - so the three dashboards share their definitions
("booked value", "open orders", ...) instead of re-deriving them:

* :func:`order_stats` - counts per status and the money totals
* :func:`order_series` - per-day / per-month points over a window, zero-filled
* :func:`dish_ranking` / :func:`cook_ranking` - top N by portions / value
* :func:`menu_stats` - dish counts, price spread, allergen and tag frequency
* :func:`cart_demand` - what sits in carts right now
* :func:`earnings_snapshot` / :func:`cook_earnings` - the cook's money:
  completed orders by completion day, plus the open pipeline

Nothing here writes; every function is safe to call on any request.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import (
    ColumnElement,
    Select,
    and_,
    case,
    distinct,
    func,
    literal,
    select,
    true,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import (
    ROLE_ADMIN,
    ROLE_COOK,
    ROLE_CUSTOMER,
    CookApplicationStatus,
    CookProfile,
    User,
    UserSession,
)
from app.modules.cart import service as cart_service
from app.modules.cart.models import Cart, CartItem
from app.modules.cart.schemas import CartCookOut
from app.modules.dashboards.schemas import (
    QUEUE_LIMIT,
    TOP_N,
    AdminDashboard,
    Amount,
    CartDemand,
    CartSnapshot,
    CookDashboard,
    CookEarnings,
    CookRank,
    CountPoint,
    CustomerDashboard,
    CustomerRank,
    CustomerStats,
    DishRank,
    EarningsGroup,
    EarningsPoint,
    EarningsQuery,
    EarningsRange,
    EarningsSnapshot,
    EarningsSummary,
    KitchenPerformance,
    MenuStats,
    OrderPoint,
    OrderStats,
    PlatformCarts,
    PriceStats,
    ProfileChecklist,
    ProfileStep,
    ProfileStepKey,
    StatusCounts,
    TagCount,
    UserStats,
    Window,
    ZoneStats,
)
from app.modules.dishes.models import Dish
from app.modules.orders import service as order_service
from app.modules.orders.models import (
    OPEN_STATUSES,
    CancelledBy,
    Order,
    OrderItem,
    OrderStatus,
)
from app.modules.orders.schemas import OrderOut, order_out
from app.modules.zones.models import Zone
from app.modules.zones.schemas import ZoneOut
from app.shared.base import utcnow
from app.shared.sql import (
    day_bucket,
    json_array_contains,
    minutes_between,
    month_bucket,
    week_bucket,
)

Unit = Literal["day", "month"]

_NOT_CANCELLED = Order.status != OrderStatus.CANCELLED.value


# --- windows -----------------------------------------------------------------------------


def _month_start(day: date, months_back: int) -> date:
    index = day.year * 12 + (day.month - 1) - months_back
    return date(index // 12, index % 12 + 1, 1)


def make_window(unit: Unit, periods: int, today: date | None = None) -> Window:
    """The last ``periods`` days (or months), today included."""
    end = today or utcnow().date()
    start = (
        end - timedelta(days=periods - 1)
        if unit == "day"
        else _month_start(end, periods - 1)
    )
    return Window(unit=unit, periods=periods, start=start, end=end)


def _labels(window: Window) -> list[str]:
    """Every period label in the window, oldest first (the zero-fill keys)."""
    if window.unit == "day":
        return [
            (window.start + timedelta(days=i)).isoformat()
            for i in range(window.periods)
        ]
    return [
        _month_start(window.end, back).strftime("%Y-%m")
        for back in range(window.periods - 1, -1, -1)
    ]


def _window_start(window: Window) -> datetime:
    return datetime.combine(window.start, datetime.min.time())


def _bucket(unit: Unit, column: Any) -> ColumnElement[str]:
    return day_bucket(column) if unit == "day" else month_bucket(column)


# --- orders ------------------------------------------------------------------------------


def _scoped[S: Select[*tuple[Any, ...]]](
    stmt: S, customer_id: uuid.UUID | None, cook_id: uuid.UUID | None
) -> S:
    if customer_id is not None:
        stmt = stmt.where(Order.customer_id == customer_id)
    if cook_id is not None:
        stmt = stmt.where(Order.cook_id == cook_id)
    return stmt


async def order_stats(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID | None = None,
    cook_id: uuid.UUID | None = None,
) -> OrderStats:
    stmt = _scoped(
        select(Order.status, func.count(), func.coalesce(func.sum(Order.total), 0)),
        customer_id,
        cook_id,
    ).group_by(Order.status)
    counts: dict[str, int] = {}
    values: dict[str, int] = {}
    for status, count, value in (await session.execute(stmt)).all():
        counts[status], values[status] = count, value
    cancelled = OrderStatus.CANCELLED.value
    orders = sum(counts.values())
    kept = orders - counts.get(cancelled, 0)
    booked = sum(value for status, value in values.items() if status != cancelled)
    return OrderStats(
        orders=orders,
        by_status=StatusCounts(**counts),
        open=sum(counts.get(status.value, 0) for status in OPEN_STATUSES),
        booked_value=booked,
        completed_value=values.get(OrderStatus.COMPLETED.value, 0),
        average_order_value=round(booked / kept) if kept else 0,
    )


async def order_series(
    session: AsyncSession,
    window: Window,
    *,
    customer_id: uuid.UUID | None = None,
    cook_id: uuid.UUID | None = None,
) -> list[OrderPoint]:
    """Orders by the period they were *placed* in (a later cancellation moves
    an order from ``orders``/``value`` to ``cancelled``, same period)."""
    bucket = _bucket(window.unit, Order.created_at).label("period")
    kept = case((_NOT_CANCELLED, 1), else_=0)
    stmt = (
        _scoped(
            select(
                bucket,
                func.sum(kept),
                func.sum(1 - kept),
                func.sum(case((_NOT_CANCELLED, Order.total), else_=0)),
            ),
            customer_id,
            cook_id,
        )
        .where(Order.created_at >= _window_start(window))
        .group_by(bucket)
    )
    found = {row[0]: row[1:] for row in (await session.execute(stmt)).all()}
    return [
        OrderPoint(period=label, orders=orders, cancelled=cancelled, value=value)
        for label in _labels(window)
        for orders, cancelled, value in [found.get(label, (0, 0, 0))]
    ]


async def dish_ranking(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID | None = None,
    cook_id: uuid.UUID | None = None,
    where: Sequence[ColumnElement[bool]] = (_NOT_CANCELLED,),
    by: Literal["quantity", "value"] = "quantity",
    limit: int | None = TOP_N,
) -> list[DishRank]:
    """Most-ordered dishes (portions; or ``by="value"``) over the orders
    matching ``where`` (default: not cancelled). Lines of a still-existing
    dish group by the dish - so a renamed dish is one entry under its current
    name; lines of deleted dishes group by the name they were ordered under.
    ``limit=None`` returns every dish."""
    quantity = func.sum(OrderItem.quantity)
    value = func.sum(OrderItem.unit_price * OrderItem.quantity)
    ranked = (quantity, value) if by == "quantity" else (value, quantity)
    stmt = (
        _scoped(
            select(
                OrderItem.dish_id,
                func.coalesce(func.max(Dish.name), func.max(OrderItem.name)),
                quantity,
                func.count(distinct(OrderItem.order_id)),
                value,
            )
            .join(Order, Order.id == OrderItem.order_id)
            .outerjoin(Dish, Dish.id == OrderItem.dish_id)
            .where(*where),
            customer_id,
            cook_id,
        )
        .group_by(
            OrderItem.dish_id,
            case((OrderItem.dish_id.is_(None), OrderItem.name), else_=literal(None)),
        )
        .order_by(*(column.desc() for column in ranked), func.max(OrderItem.name))
        .limit(limit)
    )
    return [
        DishRank(dish_id=dish_id, name=name, quantity=qty, orders=orders, value=value)
        for dish_id, name, qty, orders, value in (await session.execute(stmt)).all()
    ]


async def cook_ranking(
    session: AsyncSession, *, customer_id: uuid.UUID | None = None, limit: int = TOP_N
) -> list[CookRank]:
    """Cooks by booked value (the customer's favourites, or the platform's top)."""
    value = func.sum(Order.total)
    stmt = (
        _scoped(
            select(Order.cook_id, User.display_name, func.count(), value)
            .join(User, User.id == Order.cook_id)
            .where(_NOT_CANCELLED),
            customer_id,
            None,
        )
        .group_by(Order.cook_id, User.display_name)
        .order_by(value.desc(), func.count().desc(), User.display_name)
        .limit(limit)
    )
    return [
        CookRank(cook_id=cook_id, name=name, orders=orders, value=total)
        for cook_id, name, orders, total in (await session.execute(stmt)).all()
    ]


async def _recent_orders(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID | None = None,
    cook_id: uuid.UUID | None = None,
) -> list[OrderOut]:
    _total, views = await order_service.page_orders(
        session, customer_id=customer_id, cook_id=cook_id, limit=TOP_N
    )
    return [order_out(view) for view in views]


# --- menu + carts ------------------------------------------------------------------------


async def _tag_counts(
    session: AsyncSession, column: Any, cook_id: uuid.UUID | None
) -> list[TagCount]:
    elements = func.json_each(column).table_valued("value")
    count = func.count()
    stmt = (
        select(elements.c.value, count)
        .select_from(Dish)
        .join(elements, true())
        .where(Dish.active.is_(True))
        .group_by(elements.c.value)
        .order_by(count.desc(), elements.c.value)
    )
    if cook_id is not None:
        stmt = stmt.where(Dish.cook_id == cook_id)
    return [
        TagCount(name=name, count=n) for name, n in (await session.execute(stmt)).all()
    ]


async def menu_stats(
    session: AsyncSession, *, cook_id: uuid.UUID | None = None
) -> MenuStats:
    active = Dish.active.is_(True)
    stmt = select(
        func.count(),
        func.coalesce(func.sum(case((active, 1), else_=0)), 0),
        func.min(case((active, Dish.price))),
        func.avg(case((active, Dish.price))),
        func.max(case((active, Dish.price))),
    ).select_from(Dish)
    if cook_id is not None:
        stmt = stmt.where(Dish.cook_id == cook_id)
    total, active_count, low, mean, high = (await session.execute(stmt)).one()
    return MenuStats(
        dishes=total,
        active=active_count,
        inactive=total - active_count,
        price=PriceStats(min=low, avg=None if mean is None else round(mean), max=high),
        allergens=await _tag_counts(session, Dish.allergens, cook_id),
        dietary_tags=await _tag_counts(session, Dish.dietary_tags, cook_id),
    )


async def _cart_totals(
    session: AsyncSession, cook_id: uuid.UUID | None
) -> tuple[int, int, int, int, int]:
    """``(carts, guest_carts, account_carts, portions, value)`` over lines of
    active dishes (optionally one cook's)."""
    stmt = (
        select(
            func.count(distinct(Cart.id)),
            func.count(distinct(case((Cart.user_id.is_(None), Cart.id)))),
            func.count(distinct(case((Cart.user_id.is_not(None), Cart.id)))),
            func.coalesce(func.sum(CartItem.quantity), 0),
            func.coalesce(func.sum(CartItem.quantity * Dish.price), 0),
        )
        .select_from(CartItem)
        .join(Cart, Cart.id == CartItem.cart_id)
        .join(Dish, Dish.id == CartItem.dish_id)
        .where(Dish.active.is_(True))
    )
    if cook_id is not None:
        stmt = stmt.where(Dish.cook_id == cook_id)
    carts, guests, accounts, portions, value = (await session.execute(stmt)).one()
    return carts, guests, accounts, portions, value


# --- customer ----------------------------------------------------------------------------


async def customer_dashboard(
    session: AsyncSession, user_id: uuid.UUID, *, months: int
) -> CustomerDashboard:
    window = make_window("month", months)
    cart = await cart_service.get_cart(session, cart_service.CartOwner(user_id=user_id))
    return CustomerDashboard(
        window=window,
        orders=await order_stats(session, customer_id=user_id),
        spending=await order_series(session, window, customer_id=user_id),
        favourite_cooks=await cook_ranking(session, customer_id=user_id),
        favourite_dishes=await dish_ranking(session, customer_id=user_id),
        recent_orders=await _recent_orders(session, customer_id=user_id),
        cart=CartSnapshot(
            cook=CartCookOut(id=cart.cook_id, name=cart.cook_name)
            if cart.cook_id
            else None,
            lines=len(cart.lines),
            item_count=cart.item_count,
            total=cart.total,
            unavailable_count=cart.unavailable_count,
        ),
    )


# --- cook --------------------------------------------------------------------------------


async def customer_stats(session: AsyncSession, cook_id: uuid.UUID) -> CustomerStats:
    """Unique / repeat customers of a kitchen (non-cancelled orders) - also
    behind the public profile's stats strip."""
    per_customer = (
        select(Order.customer_id, func.count().label("orders"))
        .where(Order.cook_id == cook_id, _NOT_CANCELLED)
        .group_by(Order.customer_id)
        .subquery()
    )
    unique, repeat = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(
                    func.sum(case((per_customer.c.orders > 1, 1), else_=0)), 0
                ),
            ).select_from(per_customer)
        )
    ).one()
    return CustomerStats(unique=unique, repeat=repeat)


async def _average_fulfilment(
    session: AsyncSession, cook_id: uuid.UUID
) -> float | None:
    mean = await session.scalar(
        select(func.avg(minutes_between(Order.created_at, Order.completed_at))).where(
            Order.cook_id == cook_id, Order.status == OrderStatus.COMPLETED.value
        )
    )
    return None if mean is None else round(float(mean), 1)


_COMPLETED = Order.status == OrderStatus.COMPLETED.value
_CANCELLED = Order.status == OrderStatus.CANCELLED.value
_BY_COOK = Order.cancelled_by == CancelledBy.COOK.value
_BY_CUSTOMER = Order.cancelled_by == CancelledBy.CUSTOMER.value
#: A request the cook turned down: cancelled by them before accepting it.
_REJECTED = and_(_CANCELLED, _BY_COOK, Order.accepted_at.is_(None))


def _day_start(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time())


def _count_if(condition: ColumnElement[bool]) -> ColumnElement[int]:
    return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)


def _sum_if(condition: ColumnElement[bool], column: Any) -> ColumnElement[int]:
    return func.coalesce(func.sum(case((condition, column), else_=0)), 0)


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


def _minutes(mean: Any) -> float | None:
    return None if mean is None else round(float(mean), 1)


async def _earned_since(
    session: AsyncSession, cook_id: uuid.UUID, starts: Sequence[datetime | None]
) -> list[Amount]:
    """Completed orders (count, totals) completed since each of ``starts``
    (``None`` = ever) - one query, one conditional sum pair per start."""
    columns: list[ColumnElement[int]] = []
    for since in starts:
        recent = true() if since is None else Order.completed_at >= since
        columns += [_count_if(recent), _sum_if(recent, Order.total)]
    row = (
        await session.execute(
            select(*columns).where(Order.cook_id == cook_id, _COMPLETED)
        )
    ).one()
    return [Amount(orders=row[i], value=row[i + 1]) for i in range(0, len(row), 2)]


async def _open_amounts(
    session: AsyncSession, cook_id: uuid.UUID
) -> tuple[Amount, Amount]:
    """``(awaiting_acceptance, in_progress)``: placed vs accepted + ready."""
    placed = Order.status == OrderStatus.PLACED.value
    started = Order.status != OrderStatus.PLACED.value
    row = (
        await session.execute(
            select(
                _count_if(placed),
                _sum_if(placed, Order.total),
                _count_if(started),
                _sum_if(started, Order.total),
            ).where(
                Order.cook_id == cook_id,
                Order.status.in_([status.value for status in OPEN_STATUSES]),
            )
        )
    ).one()
    return Amount(orders=row[0], value=row[1]), Amount(orders=row[2], value=row[3])


async def earnings_snapshot(
    session: AsyncSession, cook_id: uuid.UUID, *, today: date | None = None
) -> EarningsSnapshot:
    """Today / last 7 days / this month / lifetime earnings plus the open
    pipeline - the dashboard's money tiles (UTC days)."""
    day = today or utcnow().date()
    today_, week, month, lifetime = await _earned_since(
        session,
        cook_id,
        [
            _day_start(day),
            _day_start(day - timedelta(days=6)),
            _day_start(day.replace(day=1)),
            None,
        ],
    )
    waiting, cooking = await _open_amounts(session, cook_id)
    return EarningsSnapshot(
        today=today_,
        last_7_days=week,
        this_month=month,
        lifetime=lifetime,
        awaiting_acceptance=waiting,
        in_progress=cooking,
    )


async def kitchen_performance(
    session: AsyncSession, cook_id: uuid.UUID
) -> KitchenPerformance:
    """How the kitchen handles requests (all-time) - the cook dashboard's
    ``performance`` and the public profile's acceptance rate."""
    accepted_ever = Order.accepted_at.is_not(None)
    row = (
        await session.execute(
            select(
                func.count(),
                _count_if(accepted_ever),
                _count_if(_REJECTED),
                _count_if(and_(_CANCELLED, _BY_COOK, accepted_ever)),
                _count_if(and_(_CANCELLED, _BY_CUSTOMER)),
                _count_if(_CANCELLED),
                func.avg(minutes_between(Order.created_at, Order.accepted_at)),
                func.avg(minutes_between(Order.accepted_at, Order.ready_at)),
            ).where(Order.cook_id == cook_id)
        )
    ).one()
    total, accepted, rejected, after, by_customer, cancelled, accept, prep = row
    return KitchenPerformance(
        accepted=accepted,
        rejected=rejected,
        acceptance_rate=_ratio(accepted, accepted + rejected),
        cancelled_after_accepting=after,
        cancelled_by_customer=by_customer,
        cancellation_rate=_ratio(cancelled, total),
        average_accept_minutes=_minutes(accept),
        average_prep_minutes=_minutes(prep),
    )


async def _top_customers(
    session: AsyncSession, cook_id: uuid.UUID
) -> list[CustomerRank]:
    """The kitchen's best customers: most non-cancelled orders, then value."""
    orders = func.count()
    value = func.sum(Order.total)
    stmt = (
        select(
            Order.customer_id,
            User.display_name,
            orders,
            value,
            func.max(Order.created_at),
        )
        .join(User, User.id == Order.customer_id)
        .where(Order.cook_id == cook_id, _NOT_CANCELLED)
        .group_by(Order.customer_id, User.display_name)
        .order_by(orders.desc(), value.desc(), User.display_name)
        .limit(TOP_N)
    )
    return [
        CustomerRank(
            customer_id=customer_id,
            name=name,
            orders=count,
            value=total,
            last_order_at=last,
        )
        for customer_id, name, count, total, last in (await session.execute(stmt)).all()
    ]


async def _queue(session: AsyncSession, cook_id: uuid.UUID) -> list[OrderOut]:
    """Open orders, first come first served (the requests to answer first)."""
    _total, views = await order_service.page_orders(
        session,
        cook_id=cook_id,
        status=OPEN_STATUSES,
        oldest_first=True,
        limit=QUEUE_LIMIT,
    )
    return [order_out(view) for view in views]


async def _checklist(
    session: AsyncSession,
    cook_id: uuid.UUID,
    user: User | None,
    profile: CookProfile | None,
) -> ProfileChecklist:
    """Which set-up steps are done (see :class:`ProfileChecklist`)."""
    active = Dish.active.is_(True)
    public, undescribed = (
        await session.execute(
            select(
                _count_if(active), _count_if(and_(active, Dish.description.is_(None)))
            ).where(Dish.cook_id == cook_id)
        )
    ).one()
    done: dict[ProfileStepKey, bool] = {
        "display_name": bool(user and user.display_name),
        "bio": bool(user and user.bio),
        "specialties": bool(profile and profile.specialties),
        "zone": bool(profile and profile.zone_id),
        "public_dish": public > 0,
        "dish_descriptions": public > 0 and undescribed == 0,
    }
    return ProfileChecklist(
        done=sum(done.values()),
        total=len(done),
        steps=[ProfileStep(key=key, done=value) for key, value in done.items()],
    )


async def cook_dashboard(
    session: AsyncSession, cook_id: uuid.UUID, *, days: int
) -> CookDashboard:
    window = make_window("day", days)
    user = await session.get(User, cook_id)
    profile = await session.get(CookProfile, cook_id)
    carts, _guests, _accounts, portions, value = await _cart_totals(session, cook_id)
    return CookDashboard(
        window=window,
        zone=ZoneOut.model_validate(profile.zone) if profile and profile.zone else None,
        orders=await order_stats(session, cook_id=cook_id),
        revenue=await order_series(session, window, cook_id=cook_id),
        top_dishes=await dish_ranking(session, cook_id=cook_id),
        customers=await customer_stats(session, cook_id),
        average_fulfilment_minutes=await _average_fulfilment(session, cook_id),
        demand=CartDemand(carts=carts, portions=portions, value=value),
        menu=await menu_stats(session, cook_id=cook_id),
        recent_orders=await _recent_orders(session, cook_id=cook_id),
        earnings=await earnings_snapshot(session, cook_id, today=window.end),
        performance=await kitchen_performance(session, cook_id),
        top_customers=await _top_customers(session, cook_id),
        queue=await _queue(session, cook_id),
        checklist=await _checklist(session, cook_id, user, profile),
    )


# --- cook earnings -----------------------------------------------------------------------


def _earnings_bucket(group: EarningsGroup, column: Any) -> ColumnElement[str]:
    return {"day": day_bucket, "week": week_bucket, "month": month_bucket}[group](
        column
    )


def earnings_labels(group: EarningsGroup, start: date, end: date) -> list[str]:
    """Every period label from ``start`` to ``end``, oldest first (the
    zero-fill keys; they match the SQL buckets)."""
    if group == "day":
        return [
            (start + timedelta(days=i)).isoformat()
            for i in range((end - start).days + 1)
        ]
    if group == "week":
        monday = start - timedelta(days=start.weekday())
        weeks = (end - monday).days // 7 + 1
        return [(monday + timedelta(weeks=i)).isoformat() for i in range(weeks)]
    first = start.year * 12 + start.month - 1
    last = end.year * 12 + end.month - 1
    return [f"{index // 12:04d}-{index % 12 + 1:02d}" for index in range(first, last + 1)]


def _completed_between(start: date, end: date) -> ColumnElement[bool]:
    return and_(
        _COMPLETED,
        Order.completed_at >= _day_start(start),
        Order.completed_at < _day_start(end + timedelta(days=1)),
    )


async def _earnings_summary(
    session: AsyncSession, cook_id: uuid.UUID, start: date, end: date
) -> EarningsSummary:
    completed = _completed_between(start, end)
    cancelled = and_(
        _CANCELLED,
        Order.cancelled_at >= _day_start(start),
        Order.cancelled_at < _day_start(end + timedelta(days=1)),
    )
    row = (
        await session.execute(
            select(
                _count_if(completed),
                _sum_if(completed, Order.total),
                _sum_if(completed, Order.item_count),
                _count_if(cancelled),
                _sum_if(cancelled, Order.total),
                _count_if(and_(cancelled, _REJECTED)),
            ).where(Order.cook_id == cook_id)
        )
    ).one()
    orders, earned, portions, cancelled_orders, lost, rejected = row
    return EarningsSummary(
        earned=earned,
        orders=orders,
        portions=portions,
        average_order_value=round(earned / orders) if orders else 0,
        cancelled_orders=cancelled_orders,
        cancelled_value=lost,
        rejected_orders=rejected,
    )


async def cook_earnings(
    session: AsyncSession, cook_id: uuid.UUID, query: EarningsQuery
) -> CookEarnings:
    """The kitchen's money over ``query``'s range: summary vs the previous
    range of equal length, a zero-filled series, earnings per dish, and the
    lifetime / open figures. Completed orders count on their completion day."""
    assert query.start is not None and query.end is not None  # resolved by the schema
    start, end, days = query.start, query.end, query.days
    bucket = _earnings_bucket(query.group, Order.completed_at).label("period")
    stmt = (
        select(bucket, func.count(), func.sum(Order.total))
        .where(Order.cook_id == cook_id, _completed_between(start, end))
        .group_by(bucket)
    )
    found = {period: (n, total) for period, n, total in (await session.execute(stmt)).all()}
    (lifetime,) = await _earned_since(session, cook_id, [None])
    waiting, cooking = await _open_amounts(session, cook_id)
    return CookEarnings(
        range=EarningsRange(start=start, end=end, days=days, group=query.group),
        summary=await _earnings_summary(session, cook_id, start, end),
        previous=await _earnings_summary(
            session,
            cook_id,
            start - timedelta(days=days),
            start - timedelta(days=1),
        ),
        series=[
            EarningsPoint(period=label, orders=n, earned=total)
            for label in earnings_labels(query.group, start, end)
            for n, total in [found.get(label, (0, 0))]
        ],
        dishes=await dish_ranking(
            session,
            cook_id=cook_id,
            where=(_completed_between(start, end),),
            by="value",
            limit=None,
        ),
        lifetime=lifetime,
        awaiting_acceptance=waiting,
        in_progress=cooking,
    )


# --- admin -------------------------------------------------------------------------------


async def _count(session: AsyncSession, stmt: Select[Any]) -> int:
    return (await session.scalar(stmt)) or 0


async def _user_stats(session: AsyncSession, window: Window) -> UserStats:
    users = select(func.count()).select_from(User)

    def with_role(role: str) -> Select[Any]:
        return users.where(json_array_contains(User.roles, role))

    now = utcnow()
    return UserStats(
        total=await _count(session, users),
        customers=await _count(session, with_role(ROLE_CUSTOMER)),
        cooks=await _count(session, with_role(ROLE_COOK)),
        admins=await _count(session, with_role(ROLE_ADMIN)),
        new_in_window=await _count(
            session, users.where(User.created_at >= _window_start(window))
        ),
        active_sessions=await _count(
            session,
            select(func.count())
            .select_from(UserSession)
            .where(UserSession.revoked_at.is_(None), UserSession.expires_at > now),
        ),
        pending_cook_applications=await _count(
            session,
            select(func.count())
            .select_from(CookProfile)
            .where(CookProfile.status == CookApplicationStatus.PENDING.value),
        ),
    )


async def _signups(session: AsyncSession, window: Window) -> list[CountPoint]:
    bucket = day_bucket(User.created_at).label("period")
    stmt = (
        select(bucket, func.count())
        .where(User.created_at >= _window_start(window))
        .group_by(bucket)
    )
    found = {period: count for period, count in (await session.execute(stmt)).all()}
    return [
        CountPoint(period=label, count=found.get(label, 0)) for label in _labels(window)
    ]


def _by_zone(rows: Iterable[Any]) -> dict[uuid.UUID, tuple[Any, ...]]:
    return {row[0]: tuple(row[1:]) for row in rows}


async def _zone_stats(session: AsyncSession) -> list[ZoneStats]:
    """Each figure is its own grouped query (joining them all at once would
    multiply rows), merged per zone."""
    cooks = _by_zone(
        await session.execute(
            select(CookProfile.zone_id, func.count())
            .where(
                CookProfile.zone_id.is_not(None),
                CookProfile.status == CookApplicationStatus.ACCEPTED.value,
            )
            .group_by(CookProfile.zone_id)
        )
    )
    dishes = _by_zone(
        await session.execute(
            select(CookProfile.zone_id, func.count())
            .select_from(Dish)
            .join(CookProfile, CookProfile.user_id == Dish.cook_id)
            .where(Dish.active.is_(True), CookProfile.zone_id.is_not(None))
            .group_by(CookProfile.zone_id)
        )
    )
    orders = _by_zone(
        await session.execute(
            select(CookProfile.zone_id, func.count(), func.sum(Order.total))
            .select_from(Order)
            .join(CookProfile, CookProfile.user_id == Order.cook_id)
            .where(_NOT_CANCELLED, CookProfile.zone_id.is_not(None))
            .group_by(CookProfile.zone_id)
        )
    )
    zones = await session.scalars(select(Zone).order_by(Zone.y, Zone.x))
    return [
        ZoneStats(
            slug=zone.slug,
            name=zone.name,
            x=zone.x,
            y=zone.y,
            cooks=cooks.get(zone.id, (0,))[0],
            active_dishes=dishes.get(zone.id, (0,))[0],
            orders=orders.get(zone.id, (0, 0))[0],
            value=orders.get(zone.id, (0, 0))[1],
        )
        for zone in zones
    ]


async def admin_dashboard(session: AsyncSession, *, days: int) -> AdminDashboard:
    window = make_window("day", days)
    carts, guests, accounts, portions, value = await _cart_totals(session, None)
    return AdminDashboard(
        window=window,
        users=await _user_stats(session, window),
        signups=await _signups(session, window),
        orders=await order_stats(session),
        order_series=await order_series(session, window),
        top_cooks=await cook_ranking(session),
        top_dishes=await dish_ranking(session),
        zones=await _zone_stats(session),
        menu=await menu_stats(session),
        carts=PlatformCarts(
            carts=carts,
            guest_carts=guests,
            account_carts=accounts,
            portions=portions,
            value=value,
        ),
    )
