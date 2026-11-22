"""Address-book business logic.

Rules:

* an address belongs to one account; anyone else's id is a 404 (like dishes);
* at most :data:`MAX_ADDRESSES` per account (409 ``address_limit``);
* exactly one default while the account has addresses: the first address
  becomes the default, ``is_default: true`` moves the default, and deleting
  the default promotes the most recently added remaining address;
* :func:`delivery_snapshot` is what an order stores - a copy, never a link.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.addresses.models import MAX_ADDRESSES, Address
from app.modules.addresses.schemas import AddressCreate, AddressPatch
from app.modules.zones.schemas import ZoneOut
from app.modules.zones.service import resolve_zone


class AddressNotFoundError(NotFoundError):
    default_message = "Address not found"


class AddressLimitError(ConflictError):
    code = "address_limit"
    default_message = f"An account can keep at most {MAX_ADDRESSES} addresses"


class UnknownAddressError(ValidationFailedError):
    """A request body referenced an address the caller does not have."""

    default_message = "Unknown address"

    def __init__(self, *, field: str = "address_id") -> None:
        super().__init__(
            details=[
                {
                    "field": field,
                    "type": "unknown_address",
                    "message": "no such address in your address book",
                }
            ]
        )


async def list_addresses(session: AsyncSession, user_id: uuid.UUID) -> list[Address]:
    """Default first, then newest first."""
    stmt = (
        select(Address)
        .where(Address.user_id == user_id)
        .order_by(Address.is_default.desc(), Address.created_at.desc(), Address.id)
    )
    return list((await session.scalars(stmt)).all())


async def get_owned(
    session: AsyncSession, address_id: uuid.UUID, user_id: uuid.UUID
) -> Address:
    address = await session.scalar(
        select(Address).where(Address.id == address_id, Address.user_id == user_id)
    )
    if address is None:
        raise AddressNotFoundError
    return address


async def _clear_default(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Unset the current default *in the database first*, so setting the new
    one never trips the one-default-per-user unique index."""
    await session.execute(
        update(Address)
        .where(Address.user_id == user_id, Address.is_default.is_(True))
        .values(is_default=False)
        .execution_options(synchronize_session="fetch")
    )


async def create_address(
    session: AsyncSession, user_id: uuid.UUID, payload: AddressCreate
) -> Address:
    count = await session.scalar(
        select(func.count()).select_from(Address).where(Address.user_id == user_id)
    )
    if (count or 0) >= MAX_ADDRESSES:
        raise AddressLimitError
    zone = await resolve_zone(session, payload.zone) if payload.zone else None
    make_default = payload.is_default or not count
    if make_default:
        await _clear_default(session, user_id)
    address = Address(
        user_id=user_id,
        zone=zone,
        is_default=make_default,
        **payload.model_dump(exclude={"zone", "is_default"}),
    )
    session.add(address)
    await session.commit()
    await session.refresh(address)
    return address


async def update_address(
    session: AsyncSession, address: Address, payload: AddressPatch
) -> Address:
    changes: dict[str, Any] = payload.model_dump(exclude_unset=True)
    if "zone" in changes:
        slug = changes.pop("zone")
        address.zone = await resolve_zone(session, slug) if slug else None
    if changes.pop("is_default", None) and not address.is_default:
        await _clear_default(session, address.user_id)
        address.is_default = True
    for field, value in changes.items():
        setattr(address, field, value)
    await session.commit()
    await session.refresh(address)
    return address


async def delete_address(session: AsyncSession, address: Address) -> None:
    user_id, was_default = address.user_id, address.is_default
    await session.delete(address)
    await session.flush()
    if was_default:
        successor = await session.scalar(
            select(Address)
            .where(Address.user_id == user_id)
            .order_by(Address.created_at.desc(), Address.id)
            .limit(1)
        )
        if successor is not None:
            successor.is_default = True
    await session.commit()


def delivery_snapshot(address: Address) -> dict[str, Any]:
    """The JSON an order keeps (see ``DeliveryAddressOut``)."""
    return {
        "label": address.label,
        "recipient": address.recipient,
        "phone": address.phone,
        "line1": address.line1,
        "line2": address.line2,
        "city": address.city,
        "postal_code": address.postal_code,
        "instructions": address.instructions,
        "zone": ZoneOut.model_validate(address.zone).model_dump()
        if address.zone
        else None,
    }
