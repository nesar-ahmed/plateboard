"""SQL expression helpers shared by feature services.

JSON list columns (``Dish.dietary_tags``, ``Dish.allergens``, ...) hold
arrays of plain strings. These helpers test membership *inside the database*,
so filters compose with pagination and ``COUNT(*)`` instead of being applied
in Python after the fact.

They use SQLite's JSON1 table-valued ``json_each`` (built into every SQLite
the project supports). A PostgreSQL port would swap the bodies for ``jsonb``
containment (``@>`` / ``?|``) - callers would not change.

The ``folded_*`` helpers implement text search: both sides go through the
``fold()`` SQL function (accent/case folding, see ``app.shared.text``) and the
term is matched as a literal substring (``%``/``_`` escaped).

The ``*_bucket`` helpers label a timestamp with its calendar day / ISO week /
month, as text (``2026-11-08`` / ``2026-11-02`` - the week's Monday /
``2026-11``), for ``GROUP BY`` in dashboard time series. Stored timestamps are
naive UTC, so buckets are UTC days. (PostgreSQL: ``to_char(column,
'YYYY-MM-DD')``, ``date_trunc('week', column)``.) ``minutes_between`` is the matching
duration helper (PostgreSQL: ``extract(epoch from end - start) / 60``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, SQLColumnExpression, exists, func, literal, select

from app.shared.text import FOLD_SQL_FUNCTION

__all__ = [
    "day_bucket",
    "folded",
    "folded_contains",
    "json_array_any_folded_contains",
    "json_array_contains",
    "json_array_contains_any",
    "minutes_between",
    "month_bucket",
    "week_bucket",
]


def _elements(column: SQLColumnExpression[Any]) -> Any:
    """``json_each(column)`` as a FROM item with a ``value`` column; it
    correlates to the enclosing query's row automatically."""
    return func.json_each(column).table_valued("value")


def json_array_contains(
    column: SQLColumnExpression[Any], value: str
) -> ColumnElement[bool]:
    """``value`` is one of the array's elements (exact, case-sensitive match)."""
    elements = _elements(column)
    return exists(
        select(literal(1)).select_from(elements).where(elements.c.value == value)
    )


def json_array_contains_any(
    column: SQLColumnExpression[Any], values: Sequence[str]
) -> ColumnElement[bool]:
    """At least one of ``values`` is in the array (negate it to exclude)."""
    elements = _elements(column)
    return exists(
        select(literal(1)).select_from(elements).where(elements.c.value.in_(list(values)))
    )


def folded(column: SQLColumnExpression[Any]) -> ColumnElement[Any]:
    """``fold(column)`` - the SQL side of ``app.shared.text.fold_text``."""
    return getattr(func, FOLD_SQL_FUNCTION)(column)


def folded_contains(column: SQLColumnExpression[Any], term: str) -> ColumnElement[bool]:
    """``fold(column)`` contains the *already folded* ``term`` literally.

    NULL columns (e.g. no description) simply do not match.
    """
    return folded(column).contains(term, autoescape=True)


def json_array_any_folded_contains(
    column: SQLColumnExpression[Any], term: str
) -> ColumnElement[bool]:
    """Some element of the JSON string array contains the folded ``term``."""
    elements = _elements(column)
    return exists(
        select(literal(1))
        .select_from(elements)
        .where(folded(elements.c.value).contains(term, autoescape=True))
    )


def day_bucket(column: SQLColumnExpression[Any]) -> ColumnElement[str]:
    """``YYYY-MM-DD`` of a (naive UTC) timestamp column."""
    return func.strftime("%Y-%m-%d", column)


def week_bucket(column: SQLColumnExpression[Any]) -> ColumnElement[str]:
    """``YYYY-MM-DD`` of the Monday starting the (ISO) week of the timestamp.

    SQLite's ``weekday 1`` moves *forward* to the next Monday (or stays on
    one), so step back six days first: any day lands on its own week's Monday.
    """
    return func.date(column, "-6 days", "weekday 1")


def month_bucket(column: SQLColumnExpression[Any]) -> ColumnElement[str]:
    """``YYYY-MM`` of a (naive UTC) timestamp column."""
    return func.strftime("%Y-%m", column)


def minutes_between(
    start: SQLColumnExpression[Any], end: SQLColumnExpression[Any]
) -> ColumnElement[float]:
    """``end - start`` in (fractional) minutes; NULL if either is NULL."""
    return (func.julianday(end) - func.julianday(start)) * 1440.0
