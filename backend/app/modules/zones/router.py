"""HTTP routes for zones (public, read-only).

* GET /api/zones  - every zone with its grid coordinates, in grid order

Zones are small reference data, so the list is not paginated. Clients use the
``slug`` for ``GET /api/dishes?zone=...`` and for a cook's ``zone`` field.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbSession
from app.modules.zones import service
from app.modules.zones.schemas import ZoneOut

zone_router = APIRouter(prefix="/api/zones", tags=["zones"])


@zone_router.get("", response_model=list[ZoneOut])
async def list_zones(db: DbSession) -> list[ZoneOut]:
    zones = await service.list_zones(db)
    return [ZoneOut.model_validate(zone) for zone in zones]
