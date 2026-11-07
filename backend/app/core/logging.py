"""Logging setup.

Kept deliberately small: structured JSON logging belongs to the deployment
target, and ``LOG_JSON`` gives a hook without pulling in another dependency.
"""

from __future__ import annotations

import json
import logging
import logging.config
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings

_CONFIGURED = False

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


class _JsonFormatter(logging.Formatter):
    """Minimal structured formatter (no third-party dependency)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(settings: Settings) -> None:
    """Idempotent logging configuration, called from the app lifespan."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    formatter = "json" if settings.LOG_JSON else "plain"
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "plain": {"format": _FORMAT},
                "json": {"()": "app.core.logging._JsonFormatter"},
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stderr",
                    "formatter": formatter,
                    "level": settings.LOG_LEVEL,
                }
            },
            "loggers": {
                # uvicorn already installs its own handlers; let it delegate to
                # the root logger so this configuration wins in every entry
                # point (uvicorn, fastapi dev, pytest, scripts).
                "uvicorn": {
                    "handlers": [],
                    "level": settings.LOG_LEVEL,
                    "propagate": True,
                },
                "uvicorn.error": {
                    "handlers": [],
                    "level": settings.LOG_LEVEL,
                    "propagate": True,
                },
                "uvicorn.access": {
                    "handlers": [],
                    "level": settings.LOG_LEVEL,
                    "propagate": True,
                },
                "sqlalchemy.engine": {
                    "handlers": [],
                    "level": "INFO" if settings.SQL_ECHO else "WARNING",
                    "propagate": True,
                },
            },
            "root": {"handlers": ["default"], "level": settings.LOG_LEVEL},
        }
    )
    _CONFIGURED = True
