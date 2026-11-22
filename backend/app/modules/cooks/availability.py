"""When a kitchen takes orders - pure functions, no database.

A kitchen is in one of four states:

* ``paused``  - the cook switched orders off (``orders_paused``);
* ``anytime`` - no fixed hours: orders are taken whenever (the cook still
  accepts or rejects each one) - every kitchen's state before it sets hours;
* ``open``    - inside one of its weekly windows right now;
* ``closed``  - outside them.

Weekly hours are wall-clock times in the kitchen's own IANA ``timezone``
(``{"day": 0-6, "opens": "HH:MM", "closes": "HH:MM"|"24:00"}``, Monday = 0),
so "11:00-21:00" stays 11:00-21:00 across daylight-saving changes. Everything
computed here is an aware UTC ``datetime``; clients format it for the viewer.
Back-to-back windows merge ("18:00-24:00" + next day "00:00-02:00" is one
evening), so "open until" never stops at an artificial midnight.

``now`` is always a parameter, so tests can pin the clock.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

__all__ = [
    "HORIZON",
    "Availability",
    "Window",
    "compute_availability",
    "is_valid_timezone",
    "upcoming_windows",
]

#: How far ahead the public "next 24 hours" view looks.
HORIZON = timedelta(hours=24)
#: How far ahead "opens at" searches (a week covers any weekly schedule).
LOOKAHEAD = timedelta(days=8)

Status = Literal["open", "closed", "paused", "anytime"]


@dataclasses.dataclass(frozen=True)
class Window:
    starts_at: datetime  # aware, UTC
    ends_at: datetime


@dataclasses.dataclass(frozen=True)
class Availability:
    status: Status
    accepting_orders: bool
    opens_at: datetime | None  # closed: the next opening (within a week)
    closes_at: datetime | None  # open: the end of the current window
    next_24h: list[Window]  # taking-orders windows in [now, now + 24h]
    timezone: str
    as_of: datetime  # the "now" all of the above was computed for


def is_valid_timezone(name: str) -> bool:
    """A real IANA zone name (``Europe/London``), not a path or an abbreviation."""
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def _as_utc(moment: datetime) -> datetime:
    """Naive datetimes are UTC by project convention (``app.shared.base.utcnow``)."""
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def _wall(day: date, hhmm: str, zone: ZoneInfo) -> datetime:
    """``day`` at ``hh:mm`` kitchen time, in UTC; "24:00" is the next midnight."""
    hours, minutes = (int(part) for part in hhmm.split(":"))
    if hours == 24:
        return datetime.combine(day + timedelta(days=1), time(0), tzinfo=zone).astimezone(UTC)
    return datetime.combine(day, time(hours, minutes), tzinfo=zone).astimezone(UTC)


def upcoming_windows(
    hours: Iterable[Mapping[str, Any]], timezone: str, start: datetime, end: datetime
) -> list[Window]:
    """Every (merged) opening window overlapping ``[start, end)``, in order."""
    zone = ZoneInfo(timezone)
    start, end = _as_utc(start), _as_utc(end)
    entries = list(hours)
    windows: list[Window] = []
    # One day of slack on each side: a window can start the local day before.
    day = start.astimezone(zone).date() - timedelta(days=1)
    last = end.astimezone(zone).date() + timedelta(days=1)
    while day <= last:
        for entry in entries:
            if entry["day"] == day.weekday():
                windows.append(Window(_wall(day, entry["opens"], zone), _wall(day, entry["closes"], zone)))
        day += timedelta(days=1)
    windows.sort(key=lambda window: window.starts_at)

    merged: list[Window] = []
    for window in windows:
        if window.ends_at <= window.starts_at:
            continue  # a DST jump swallowed it
        if merged and window.starts_at <= merged[-1].ends_at:
            if window.ends_at > merged[-1].ends_at:
                merged[-1] = Window(merged[-1].starts_at, window.ends_at)
            continue
        merged.append(window)
    return [w for w in merged if w.ends_at > start and w.starts_at < end]


def compute_availability(
    *,
    hours: Iterable[Mapping[str, Any]],
    timezone: str,
    paused: bool,
    now: datetime,
) -> Availability:
    """The kitchen's state at ``now`` plus its windows over the next 24 hours."""
    now = _as_utc(now)
    horizon_end = now + HORIZON
    entries = list(hours)
    if paused:
        return Availability("paused", False, None, None, [], timezone, now)
    if not entries:
        return Availability(
            "anytime", True, None, None, [Window(now, horizon_end)], timezone, now
        )

    windows = upcoming_windows(entries, timezone, now, now + LOOKAHEAD)
    current = next((w for w in windows if w.starts_at <= now < w.ends_at), None)
    next_24h = [
        Window(max(w.starts_at, now), min(w.ends_at, horizon_end))
        for w in windows
        if w.starts_at < horizon_end and w.ends_at > now
    ]
    if current is not None:
        return Availability("open", True, None, current.ends_at, next_24h, timezone, now)
    upcoming = next((w.starts_at for w in windows if w.starts_at > now), None)
    return Availability("closed", False, upcoming, None, next_24h, timezone, now)
