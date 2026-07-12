"""API security primitives (ADR-018 serving).

Password hashing (stdlib PBKDF2 - no extra dependency) and HS256 JWTs. Kept tiny
and dependency-light; the user/role aggregate it authenticates is the D4
UserRepository.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

_ALGO = "sha256"
_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(_ALGO, password.encode(), salt, _ITERATIONS)
    return f"pbkdf2_{_ALGO}${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        _, iterations, salt_hex, expected = encoded.split("$")
        digest = hashlib.pbkdf2_hmac(_ALGO, password.encode(), bytes.fromhex(salt_hex),
                                     int(iterations))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(digest.hex(), expected)


def create_access_token(
    subject: str, roles: tuple[str, ...], secret: str, algorithm: str, ttl_minutes: int
) -> str:
    now = datetime.now(tz=UTC)
    claims = {
        "sub": subject,
        "roles": list(roles),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
    }
    return jwt.encode(claims, secret, algorithm=algorithm)


def decode_access_token(token: str, secret: str, algorithm: str) -> dict | None:
    try:
        return jwt.decode(token, secret, algorithms=[algorithm])
    except JWTError:
        return None
