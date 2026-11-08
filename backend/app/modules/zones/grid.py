"""Grid geometry for zones - the single definition of "distance".

Zones sit on an integer grid, so the distance between two zones is the
**Manhattan (city-block) distance**: the number of grid steps along rows and
columns, ``|x1 - x2| + |y1 - y2|``. It is an integer, symmetric, zero only for
the same cell, and obeys the triangle inequality.

The metric exists twice on purpose - :func:`grid_distance` for Python values
and :func:`grid_distance_sql` for SQL, so the public menu can filter and
paginate in the database. ``tests/test_zones.py`` proves the two agree; change
them together.
"""

from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy import ColumnElement, SQLColumnExpression, func

#: Largest allowed grid coordinate (the CHECKs in the DB only require >= 0).
GRID_MAX = 999
#: Farthest two cells can be apart on the grid: corner to opposite corner.
MAX_GRID_DISTANCE = 2 * GRID_MAX


class GridPosition(Protocol):
    """Anything with integer grid coordinates - a ``Zone`` row, for one."""

    @property
    def x(self) -> int: ...

    @property
    def y(self) -> int: ...


def grid_distance(a: GridPosition, b: GridPosition) -> int:
    """Manhattan distance in grid steps between two positions."""
    return abs(a.x - b.x) + abs(a.y - b.y)


def grid_distance_sql(
    x: SQLColumnExpression[Any], y: SQLColumnExpression[Any], origin: GridPosition
) -> ColumnElement[Any]:
    """SQL twin of :func:`grid_distance` from column ``(x, y)`` to ``origin``."""
    return func.abs(x - origin.x) + func.abs(y - origin.y)
