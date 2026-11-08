"""Text normalization shared by search (Python side *and* SQL side).

:func:`fold_text` is the single definition of "the same text for search
purposes": Unicode compatibility-decomposed, accents (combining marks)
stripped, then case-folded - so ``SVÍČKOVÁ``, ``Svíčková`` and ``svickova``
are all ``svickova``, and ``Straße`` is ``strasse``.

SQLite's own ``lower()``/``LIKE`` only fold ASCII A-Z, so the database engine
registers this very function as the SQL function ``fold()`` on every
connection (:mod:`app.core.db`); both sides of a comparison therefore always
agree.
"""

from __future__ import annotations

import unicodedata

__all__ = ["FOLD_SQL_FUNCTION", "fold_text", "search_terms"]

#: Name of the SQL function the engine registers (see app.core.db).
FOLD_SQL_FUNCTION = "fold"


def fold_text(value: str | None) -> str | None:
    """Accent- and case-insensitive form of ``value`` (``None`` stays ``None``)."""
    if value is None:
        return None
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def search_terms(query: str | None) -> list[str]:
    """Folded, de-duplicated words of a search box query, in typed order."""
    folded = fold_text(query) or ""
    return list(dict.fromkeys(folded.split()))
