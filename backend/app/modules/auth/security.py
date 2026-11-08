"""Password hashing and session tokens - standard library only.

Passwords use ``hashlib.scrypt`` with a fresh random salt per user, encoded
self-describingly so parameters can be upgraded later without ambiguity::

    scrypt$N_log2$r$p$salt_hex$hash_hex

Session tokens are random 256-bit values; only their SHA-256 is stored.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

# Cost parameters: n=2**14 (16 MiB working memory), r=8, p=1 - in line with
# what production frameworks use, and quick enough for tests.
_PARAM_N = 2**14
_PARAM_R = 8
_PARAM_P = 1
_DKLEN = 32
_MAXMEM = 64 * 1024 * 1024
_ALGO = "scrypt"


def hash_password(plain: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        plain.encode("utf-8"),
        salt=salt,
        n=_PARAM_N,
        r=_PARAM_R,
        p=_PARAM_P,
        dklen=_DKLEN,
        maxmem=_MAXMEM,
    )
    return f"{_ALGO}${_PARAM_N.bit_length() - 1}${_PARAM_R}${_PARAM_P}${salt.hex()}${digest.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    try:
        algo, log_n, r, p, salt_hex, digest_hex = stored.split("$")
        if algo != _ALGO:
            return False
        digest = hashlib.scrypt(
            plain.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=2 ** int(log_n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(digest_hex)),
            maxmem=_MAXMEM,
        )
    except (ValueError, TypeError):  # malformed stored value
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


# Constant used when the account does not exist: burning the same CPU time as
# a real verification keeps login timing from leaking account existence.
_DUMMY_HASH = hash_password(secrets.token_hex(32))


def verify_login_attempt(password: str, stored_hash: str | None) -> bool:
    """Verify against the real hash, or the dummy one for unknown accounts."""
    return (
        verify_password(password, stored_hash)
        if stored_hash
        else _burn_then_false(password)
    )


def _burn_then_false(password: str) -> bool:
    verify_password(password, _DUMMY_HASH)
    return False


def new_session_token() -> tuple[str, str]:
    """Return ``(cookie_token, token_hash)`` - only the hash is persisted."""
    token = secrets.token_urlsafe(32)
    return token, hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
