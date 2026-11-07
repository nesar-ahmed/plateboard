"""Error vocabulary and the single place where errors become HTTP responses.

Domain modules raise subclasses of :class:`AppError` (usually their own
``exceptions.py``); nothing below the service layer knows about HTTP codes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = logging.getLogger(__name__)


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: Any | None = Field(
        default=None, description="Machine-readable context, e.g. the failing fields"
    )


class ErrorEnvelope(BaseModel):
    """Every non-2xx response uses this shape."""

    error: ErrorInfo


class AppError(Exception):
    """Base class for expected, client-visible failures."""

    status_code: ClassVar[int] = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: ClassVar[str] = "internal_error"
    default_message: ClassVar[str] = "Internal server error"

    def __init__(
        self, message: str | None = None, *, details: Any | None = None
    ) -> None:
        super().__init__(message or self.default_message)
        self.message = message or self.default_message
        self.details = details

    def to_envelope(self) -> ErrorEnvelope:
        return ErrorEnvelope(
            error=ErrorInfo(code=self.code, message=self.message, details=self.details)
        )


class NotFoundError(AppError):
    status_code: ClassVar[int] = status.HTTP_404_NOT_FOUND
    code: ClassVar[str] = "not_found"
    default_message: ClassVar[str] = "Resource not found"


class ConflictError(AppError):
    status_code: ClassVar[int] = status.HTTP_409_CONFLICT
    code: ClassVar[str] = "conflict"
    default_message: ClassVar[str] = "Resource conflicts with existing data"


class ValidationFailedError(AppError):
    status_code: ClassVar[int] = status.HTTP_422_UNPROCESSABLE_CONTENT
    code: ClassVar[str] = "validation_failed"
    default_message: ClassVar[str] = "Request could not be processed"


class PermissionDeniedError(AppError):
    status_code: ClassVar[int] = status.HTTP_403_FORBIDDEN
    code: ClassVar[str] = "permission_denied"
    default_message: ClassVar[str] = "Operation not allowed"


_HTTP_CODES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
    status.HTTP_403_FORBIDDEN: "permission_denied",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_413_CONTENT_TOO_LARGE: "payload_too_large",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "validation_failed",
    status.HTTP_429_TOO_MANY_REQUESTS: "too_many_requests",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "internal_error",
}


def _envelope(
    code: str,
    message: str,
    *,
    details: Any | None = None,
    headers: Mapping[str, str] | None = None,
    status_code: int,
) -> JSONResponse:
    body = ErrorEnvelope(error=ErrorInfo(code=code, message=message, details=details))
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
        headers=dict(headers or {}),
    )


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    """Domain errors are expected: log at warning, never leak internals."""
    logger.warning("%s: %s", type(exc).__name__, exc.message)
    return _envelope(
        exc.code, exc.message, details=exc.details, status_code=exc.status_code
    )


async def http_exception_handler(
    _request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Wrap framework-raised HTTP errors (404 on unknown routes, 405, ...) in the same envelope."""
    if isinstance(exc, HTTPException) and exc.headers is not None:
        headers: dict[str, str] | None = dict(exc.headers)
    else:
        headers = None
    code = _HTTP_CODES.get(exc.status_code, "error")
    return _envelope(
        code, str(exc.detail), status_code=exc.status_code, headers=headers
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Report each failing field as ``{field, type, message}``."""
    details = [
        {
            "field": ".".join(str(part) for part in error["loc"][1:])
            or str(error["loc"][0]),
            "type": error["type"],
            "message": error["msg"],
        }
        for error in exc.errors()
    ]
    logger.info(
        "validation error on %s %s: %d issue(s)",
        request.method,
        request.url.path,
        len(details),
    )
    return _envelope(
        "validation_failed",
        "Request validation failed",
        details=details,
        status_code=422,
    )


async def integrity_error_handler(
    request: Request, exc: IntegrityError
) -> JSONResponse:
    """Unique/FK violations are races, not bugs - but never echo SQL back."""
    logger.warning(
        "integrity error on %s %s: %s", request.method, request.url.path, exc.orig
    )
    message = (
        f"Data conflicts with an existing record: {exc.orig}"
        if get_settings().DEBUG
        else "Data conflicts with existing records"
    )
    return _envelope("conflict", message, status_code=409)


async def sqlalchemy_error_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    logger.exception(
        "database failure on %s %s", request.method, request.url.path, exc_info=exc
    )
    return _envelope(
        "database_error", "The request could not be completed", status_code=500
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Wire every handler onto the application (order: most specific first).

    The table is typed as ``(exception class, handler)`` pairs because
    Starlette's stubs only accept handlers that take a bare ``Exception``,
    while ours legitimately narrow the ``exc`` parameter.
    """
    handlers: list[tuple[type[BaseException], object]] = [
        (AppError, app_error_handler),
        (RequestValidationError, validation_error_handler),
        (IntegrityError, integrity_error_handler),
        (SQLAlchemyError, sqlalchemy_error_handler),
        (StarletteHTTPException, http_exception_handler),
    ]
    for exception_type, handler in handlers:
        app.add_exception_handler(exception_type, handler)  # type: ignore[arg-type]
