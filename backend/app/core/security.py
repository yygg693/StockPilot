"""Security module - password hashing and JWT token management.

Uses hashlib.pbkdf2_hmac for password hashing (no external dependency).
Uses PyJWT for token generation/verification.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt

from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger

logger = get_logger("security")

# Password hashing parameters
_PBKDF2_ITERATIONS = 100_000
_HASH_ALGORITHM = "sha256"
_SALT_BYTES = 32


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Hash a password using PBKDF2-HMAC-SHA256.

    Returns (password_hash, salt) both as hex strings.
    """
    if salt is None:
        salt = secrets.token_hex(_SALT_BYTES)
    pw_hash = hashlib.pbkdf2_hmac(
        _HASH_ALGORITHM,
        password.encode("utf-8"),
        bytes.fromhex(salt),
        _PBKDF2_ITERATIONS,
    )
    return pw_hash.hex(), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """Verify a password against stored hash and salt."""
    pw_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(pw_hash, stored_hash)


def create_access_token(user_id: int, username: str, role: str = "user") -> str:
    """Create a JWT access token."""
    settings = get_settings()
    if len(settings.security.jwt_secret) < 32:
        raise RuntimeError(
            "JWT secret must be at least 32 chars. Set STOCKPILOT_SECURITY_JWT_SECRET env var "
            "(config.yaml jwt_secret is empty by design, not a fallback)."
        )
    expire = datetime.now(UTC) + timedelta(hours=settings.security.jwt_expire_hours)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    token = jwt.encode(payload, settings.security.jwt_secret, algorithm="HS256")
    return token


def decode_access_token(token: str) -> dict | None:
    """Decode and validate a JWT token. Returns payload or None."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.security.jwt_secret, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("jwt.expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("jwt.invalid", error=str(e))
        return None


def extract_token_from_header(authorization: str | None) -> str | None:
    """Extract Bearer token from Authorization header."""
    if not authorization:
        return None
    if not authorization.startswith("Bearer "):
        return None
    return authorization[7:]
