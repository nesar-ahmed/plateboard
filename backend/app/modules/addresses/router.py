"""HTTP routes for the signed-in user's address book (login required).

* GET    /api/me/addresses        - my addresses, default first
* POST   /api/me/addresses        - add one (201; the first becomes default)
* PATCH  /api/me/addresses/{id}   - edit / make default (``is_default: true``)
* DELETE /api/me/addresses/{id}   - remove (the default passes to the newest)

Someone else's address id is a 404. Checkout (``POST /api/me/orders``) takes
an ``address_id`` from this list and copies the address into the order.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response

from app.api.deps import DbSession
from app.modules.addresses import service
from app.modules.addresses.schemas import AddressCreate, AddressOut, AddressPatch
from app.modules.auth.dependencies import LoginRequired

address_router = APIRouter(prefix="/api/me/addresses", tags=["addresses"])


@address_router.get("", response_model=list[AddressOut])
async def list_addresses(user: LoginRequired, db: DbSession) -> list[AddressOut]:
    return [
        AddressOut.model_validate(a) for a in await service.list_addresses(db, user.id)
    ]


@address_router.post("", response_model=AddressOut, status_code=201)
async def create_address(
    payload: AddressCreate, user: LoginRequired, db: DbSession
) -> AddressOut:
    return AddressOut.model_validate(await service.create_address(db, user.id, payload))


@address_router.patch("/{address_id}", response_model=AddressOut)
async def update_address(
    address_id: uuid.UUID, payload: AddressPatch, user: LoginRequired, db: DbSession
) -> AddressOut:
    address = await service.get_owned(db, address_id, user.id)
    return AddressOut.model_validate(await service.update_address(db, address, payload))


@address_router.delete("/{address_id}", status_code=204)
async def delete_address(
    address_id: uuid.UUID, user: LoginRequired, db: DbSession
) -> Response:
    address = await service.get_owned(db, address_id, user.id)
    await service.delete_address(db, address)
    return Response(status_code=204)
