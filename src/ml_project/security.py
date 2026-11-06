"""Password hashing helpers for future authentication services."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from ml_project.config import JWTSettings, get_jwt_settings, get_refresh_token_settings

_PASSWORD_HASHER = PasswordHasher()
_DUMMY_PASSWORD = secrets.token_urlsafe(32)
_DUMMY_PASSWORD_HASH = _PASSWORD_HASHER.hash(_DUMMY_PASSWORD)
del _DUMMY_PASSWORD
JWT_ALGORITHM = "HS256"
JWT_REQUIRED_CLAIMS = ["sub", "iat", "exp", "iss", "aud"]


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id defaults from argon2-cffi."""
    if not password:
        raise ValueError("Password cannot be empty.")
    return _PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against an Argon2 hash without exposing mismatch details."""
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def verify_dummy_password(password: str) -> bool:
    """Perform one Argon2 verification for unknown users without exposing its hash."""
    return verify_password(password, _DUMMY_PASSWORD_HASH)


def generate_refresh_token() -> str:
    """Generate a cryptographically secure refresh token (plaintext) for transmission in HttpOnly cookie."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """Hash a refresh token for storage using HMAC-SHA256 when a secret is configured."""
    if not token:
        raise ValueError("Refresh token cannot be empty.")
    settings = get_refresh_token_settings()
    if settings.hash_secret:
        digest = hmac.new(settings.hash_secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()
        return digest
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(subject: UUID, settings: JWTSettings | None = None) -> str:
    """Issue a short-lived HS256 token without embedding roles or workspace access."""
    token_settings = settings or get_jwt_settings()
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=token_settings.access_token_minutes)
    claims = {
        "sub": str(subject),
        "iat": issued_at,
        "exp": expires_at,
        "iss": token_settings.issuer,
        "aud": token_settings.audience,
    }
    return jwt.encode(claims, token_settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, settings: JWTSettings | None = None) -> UUID:
    """Validate token algorithm, signature, issuer, audience, required claims, and UUID subject."""
    token_settings = settings or get_jwt_settings()
    claims = jwt.decode(
        token,
        token_settings.secret_key,
        algorithms=[JWT_ALGORITHM],
        issuer=token_settings.issuer,
        audience=token_settings.audience,
        options={"require": JWT_REQUIRED_CLAIMS},
    )
    subject = claims.get("sub")
    if not isinstance(subject, str):
        raise jwt.InvalidTokenError("Invalid subject claim.")
    try:
        return UUID(subject)
    except ValueError as error:
        raise jwt.InvalidTokenError("Invalid subject claim.") from error
