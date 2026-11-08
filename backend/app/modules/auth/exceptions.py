"""Auth-specific errors. They render through the project-wide error envelope."""

from __future__ import annotations

from fastapi import status

from app.core.exceptions import AppError


class CredentialsError(AppError):
    """Generic 401: identical for unknown email and wrong password, so the
    response never reveals whether an account exists."""

    status_code = 401
    code = "invalid_credentials"
    default_message = "Invalid email or password"


class UnauthenticatedError(AppError):
    """No/usable session cookie - protects /api/me and /api/auth/logout."""

    status_code = 401
    code = "unauthenticated"
    default_message = "Not authenticated"


class EmailTakenError(AppError):
    status_code = 409
    code = "email_taken"
    default_message = "An account with this email already exists"


class ForbiddenError(AppError):
    """Authenticated but lacking a required role (e.g. cook endpoints)."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"
    default_message = "This action requires additional privileges"
