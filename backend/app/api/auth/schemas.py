"""Request/response schemas for the auth feature."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.shared.types import UTCDateTime

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128  # cap scrypt input; longer is a DoS vector, not a feature


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(
        min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )


class LoginRequest(RegisterRequest):
    """Same shape as registration (login credentials are a valid pair too)."""


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    created_at: UTCDateTime
