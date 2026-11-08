"""Zone business logic: lookups by slug and the (seed/test-only) create."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationFailedError
from app.modules.zones.models import Zone
from app.modules.zones.schemas import ZoneCreate


class UnknownZoneError(ValidationFailedError):
    """A request referenced a zone slug that does not exist.

    422 with the same ``details`` shape as schema validation errors, so the
    client can point at the offending field (``zone`` in a query string or a
    request body alike).
    """

    default_message = "Unknown zone"

    def __init__(self, slug: str, *, field: str = "zone") -> None:
        super().__init__(
            details=[
                {
                    "field": field,
                    "type": "unknown_zone",
                    "message": f"no zone with slug {slug!r} (see GET /api/zones)",
                }
            ]
        )


class ZoneConflictError(ConflictError):
    default_message = "A zone with this slug or grid cell already exists"


async def list_zones(session: AsyncSession) -> list[Zone]:
    """Every zone in grid order (row by row, then column)."""
    stmt = select(Zone).order_by(Zone.y, Zone.x)
    return list((await session.scalars(stmt)).all())


async def get_zone_by_slug(session: AsyncSession, slug: str) -> Zone | None:
    return await session.scalar(select(Zone).where(Zone.slug == slug))


async def resolve_zone(
    session: AsyncSession, slug: str, *, field: str = "zone"
) -> Zone:
    """The zone for an (already normalized) slug, or a 422 naming ``field``."""
    zone = await get_zone_by_slug(session, slug)
    if zone is None:
        raise UnknownZoneError(slug, field=field)
    return zone


async def create_zone(session: AsyncSession, payload: ZoneCreate) -> Zone:
    zone = Zone(**payload.model_dump())
    session.add(zone)
    try:
        await session.commit()
    except IntegrityError:  # slug or (x, y) cell already taken
        await session.rollback()
        raise ZoneConflictError from None
    await session.refresh(zone)
    return zone
