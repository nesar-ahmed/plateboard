"""Central import point for every ORM model.

Alembic's ``env.py`` imports this module so that all mappers are configured
before metadata is used. The v1 API is starting from a clean slate, so no
models exist yet - when the first ``app/api/v1/<feature>/models.py`` lands,
import it here and generate a revision:

    uv run alembic revision --autogenerate -m "add <feature>"
"""

from app.shared.base import Base

__all__ = ["Base"]
