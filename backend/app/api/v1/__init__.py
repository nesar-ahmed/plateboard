"""API version 1 - the surface under development.

Every v1 endpoint lives in this package and is aggregated in
:mod:`app.api.v1.router`. Future breaking changes go into ``app/api/v2/``
instead of mutating these routes.
"""

from app.api.v1.router import v1_router

__all__ = ["v1_router"]
