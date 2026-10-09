"""Tests for backend.app.core.security — password hashing and JWT tokens."""
from __future__ import annotations

import os

import jwt
import pytest

from backend.app.core.config import get_settings
from backend.app.core.security import (
    create_access_token,
    decode_access_token,
    extract_token_from_header,
    hash_password,
    verify_password,
)

# P0 hardening: jwt_secret must be >= 32 chars and is sourced from the env var
# (config.yaml jwt_secret is intentionally empty). The JWT tests must inject a
# strong secret so create_access_token no longer raises RuntimeError, and clear
# the lru-cached Settings so the value is picked up.
_STRONG_JWT_SECRET = "test-secret-min-32-chars-aaaaaaaaaaaaaaaa"


class TestPasswordHashing:
    def test_hash_returns_hex_and_salt(self):
        pw_hash, salt = hash_password("mypassword")
        assert len(pw_hash) == 64  # SHA-256 hex
        assert len(salt) == 64     # 32 bytes hex

    def test_hash_is_deterministic_with_same_salt(self):
        salt = "ab" * 32
        h1, _ = hash_password("test", salt)
        h2, _ = hash_password("test", salt)
        assert h1 == h2

    def test_different_passwords_different_hashes(self):
        h1, s1 = hash_password("password1")
        h2, s2 = hash_password("password2")
        assert h1 != h2

    def test_verify_correct_password(self):
        pw_hash, salt = hash_password("correct_pw")
        assert verify_password("correct_pw", pw_hash, salt) is True

    def test_verify_wrong_password(self):
        pw_hash, salt = hash_password("correct_pw")
        assert verify_password("wrong_pw", pw_hash, salt) is False

    def test_verify_empty_password(self):
        pw_hash, salt = hash_password("")
        assert verify_password("", pw_hash, salt) is True
        assert verify_password("x", pw_hash, salt) is False


class TestJWTToken:
    @pytest.fixture(autouse=True)
    def _jwt_secret(self):
        os.environ["STOCKPILOT_SECURITY_JWT_SECRET"] = _STRONG_JWT_SECRET
        get_settings.cache_clear()
        yield

    def test_create_and_decode_token(self):
        token = create_access_token(user_id=1, username="alice", role="user")
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "1"
        assert payload["username"] == "alice"
        assert payload["role"] == "user"

    def test_decode_invalid_token(self):
        result = decode_access_token("invalid.token.here")
        assert result is None

    def test_decode_none_token(self):
        result = decode_access_token("")
        assert result is None

    def test_token_has_expiry(self):
        token = create_access_token(user_id=42, username="bob")
        payload = decode_access_token(token)
        assert payload is not None
        assert "exp" in payload
        assert "iat" in payload


class TestExtractToken:
    def test_extract_bearer_token(self):
        result = extract_token_from_header("Bearer abc123")
        assert result == "abc123"

    def test_extract_no_header(self):
        assert extract_token_from_header(None) is None

    def test_extract_empty_header(self):
        assert extract_token_from_header("") is None

    def test_extract_non_bearer(self):
        assert extract_token_from_header("Basic abc123") is None
