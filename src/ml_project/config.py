
"""Environment-based application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_network
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_JWT_ISSUER = "ml-project-api"
DEFAULT_JWT_AUDIENCE = "ml-project-clients"
DEFAULT_JWT_ACCESS_TOKEN_MINUTES = 15
MAX_JWT_ACCESS_TOKEN_MINUTES = 60

DEFAULT_LOGIN_RATE_LIMIT_ATTEMPTS = 5
DEFAULT_LOGIN_RATE_LIMIT_WINDOW_SECONDS = 60

DEFAULT_CORS_ALLOWED_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)

DEFAULT_MAX_RESUME_SIZE_BYTES = 10 * 1024 * 1024

DEFAULT_REFRESH_TOKEN_DAYS = 7
MAX_REFRESH_TOKEN_DAYS = 30
DEFAULT_REFRESH_COOKIE_NAME = "refresh_token"
DEFAULT_REFRESH_COOKIE_PATH = "/"
DEFAULT_REFRESH_COOKIE_SAMESITE = "Lax"  # Lax, Strict, or None
DEFAULT_REFRESH_COOKIE_SECURE = False  # overridden in production


_KNOWN_WEAK_JWT_SECRETS = {
    "changeme",
    "change_me",
    "password",
    "secret",
    "jwt_secret",
    "test",
    "test_secret",
    "development",
    "production",
}


@dataclass(frozen=True)
class JWTSettings:
    """Validated signing configuration for short-lived API access tokens."""

    secret_key: str
    issuer: str
    audience: str
    access_token_minutes: int


@dataclass(frozen=True)
class LoginRateLimitSettings:
    """Per-client login limits and explicitly trusted proxy networks."""

    attempts: int
    window_seconds: int
    trusted_proxy_networks: tuple[IPv4Network | IPv6Network, ...]


@dataclass(frozen=True)
class RefreshTokenSettings:
    """Refresh token and cookie configuration."""

    token_days: int
    cookie_name: str
    cookie_secure: bool
    cookie_samesite: str  # Lax, Strict, or None
    cookie_path: str
    cookie_domain: str | None
    hash_secret: str | None


DEFAULT_ENVIRONMENT = "development"
VALID_ENVIRONMENTS = {"development", "production"}


def get_environment() -> str:
    """Return the runtime environment from ENV, defaulting to development."""
    load_dotenv(PROJECT_ROOT / ".env")
    value = os.getenv("ENV", DEFAULT_ENVIRONMENT).strip().lower()

    if value not in VALID_ENVIRONMENTS:
        raise RuntimeError("ENV must be either 'development' or 'production'.")

    return value


def get_app_environment() -> str:
    """Compatibility alias for get_environment."""
    return get_environment()


def get_database_url() -> str:
    """Return the configured database URL."""
    load_dotenv(PROJECT_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env and configure PostgreSQL."
        )

    return database_url


@lru_cache(maxsize=1)
def get_login_rate_limit_settings() -> LoginRateLimitSettings:
    """Load bounded login limits and trusted proxy configuration."""
    load_dotenv(PROJECT_ROOT / ".env")

    try:
        attempts = int(
            os.getenv(
                "LOGIN_RATE_LIMIT_ATTEMPTS",
                str(DEFAULT_LOGIN_RATE_LIMIT_ATTEMPTS),
            )
        )
        window_seconds = int(
            os.getenv(
                "LOGIN_RATE_LIMIT_WINDOW_SECONDS",
                str(DEFAULT_LOGIN_RATE_LIMIT_WINDOW_SECONDS),
            )
        )
    except ValueError as error:
        raise RuntimeError(
            "Login rate-limit settings must be valid whole numbers."
        ) from error

    if not 1 <= attempts <= 1000 or not 1 <= window_seconds <= 86400:
        raise RuntimeError(
            "Login rate-limit settings are outside the supported range."
        )

    raw_networks = os.getenv(
        "LOGIN_RATE_LIMIT_TRUSTED_PROXIES", ""
    ).strip()

    try:
        trusted_networks = tuple(
            ip_network(value.strip(), strict=False)
            for value in raw_networks.split(",")
            if value.strip()
        )
    except ValueError as error:
        raise RuntimeError(
            "LOGIN_RATE_LIMIT_TRUSTED_PROXIES must contain valid IP networks."
        ) from error

    return LoginRateLimitSettings(
        attempts=attempts,
        window_seconds=window_seconds,
        trusted_proxy_networks=trusted_networks,
    )


def get_jwt_settings() -> JWTSettings:
    """Load JWT settings and reject missing or weak signing secrets."""
    load_dotenv(PROJECT_ROOT / ".env")

    secret_key = os.getenv("JWT_SECRET_KEY", "")
    normalized_secret = secret_key.casefold()

    if (
        len(secret_key.encode("utf-8")) < 32
        or normalized_secret.startswith(
            ("replace_", "change_me", "your_")
        )
        or normalized_secret in _KNOWN_WEAK_JWT_SECRETS
    ):
        raise RuntimeError(
            "JWT_SECRET_KEY must be configured with at least 32 UTF-8 bytes."
        )

    raw_lifetime = os.getenv(
        "JWT_ACCESS_TOKEN_MINUTES",
        str(DEFAULT_JWT_ACCESS_TOKEN_MINUTES),
    )

    try:
        access_token_minutes = int(raw_lifetime)
    except ValueError as error:
        raise RuntimeError(
            "JWT_ACCESS_TOKEN_MINUTES must be a whole number from 1 to 60."
        ) from error

    if not 1 <= access_token_minutes <= MAX_JWT_ACCESS_TOKEN_MINUTES:
        raise RuntimeError(
            "JWT_ACCESS_TOKEN_MINUTES must be a whole number from 1 to 60."
        )

    issuer = os.getenv("JWT_ISSUER", DEFAULT_JWT_ISSUER).strip()
    audience = os.getenv("JWT_AUDIENCE", DEFAULT_JWT_AUDIENCE).strip()

    if not issuer or not audience:
        raise RuntimeError("JWT_ISSUER and JWT_AUDIENCE must not be blank.")

    return JWTSettings(
        secret_key=secret_key,
        issuer=issuer,
        audience=audience,
        access_token_minutes=access_token_minutes,
    )


def get_cors_origins() -> tuple[str, ...]:
    """Return explicitly configured CORS origins; wildcard is never allowed."""
    load_dotenv(PROJECT_ROOT / ".env")

    raw = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
    environment = get_environment()

    if raw:
        origins = tuple(
            origin.strip()
            for origin in raw.split(",")
            if origin.strip()
        )
    elif environment == "development":
        origins = DEFAULT_CORS_ALLOWED_ORIGINS
    else:
        raise RuntimeError(
            "CORS_ALLOWED_ORIGINS must be configured in production."
        )

    if "*" in origins:
        raise RuntimeError(
            "CORS_ALLOWED_ORIGINS must not contain wildcard origins."
        )

    for origin in origins:
        parsed = urlparse(origin)

        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError(
                "CORS_ALLOWED_ORIGINS must contain valid http/https origins."
            )

    return origins


def get_max_resume_size_bytes() -> int:
    """Return the maximum allowed resume upload size in bytes."""
    load_dotenv(PROJECT_ROOT / ".env")
    raw = os.getenv("MAX_RESUME_SIZE_BYTES", str(DEFAULT_MAX_RESUME_SIZE_BYTES)).strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError("MAX_RESUME_SIZE_BYTES must be a whole number.") from error
    if value <= 0:
        raise RuntimeError("MAX_RESUME_SIZE_BYTES must be positive.")
    return value


@lru_cache(maxsize=1)
def get_refresh_token_settings() -> RefreshTokenSettings:
    """Load refresh token and cookie settings; enforce secure production defaults."""
    load_dotenv(PROJECT_ROOT / ".env")
    environment = get_environment()

    try:
        token_days = int(
            os.getenv(
                "REFRESH_TOKEN_DAYS",
                str(DEFAULT_REFRESH_TOKEN_DAYS),
            )
        )
    except ValueError as error:
        raise RuntimeError(
            "REFRESH_TOKEN_DAYS must be a whole number."
        ) from error

    if not 1 <= token_days <= MAX_REFRESH_TOKEN_DAYS:
        raise RuntimeError(
            "REFRESH_TOKEN_DAYS must be between 1 and 30 days."
        )

    cookie_name = os.getenv(
        "REFRESH_COOKIE_NAME",
        DEFAULT_REFRESH_COOKIE_NAME,
    ).strip()

    if not cookie_name:
        raise RuntimeError("REFRESH_COOKIE_NAME must not be blank.")

    cookie_path = (
        os.getenv(
            "REFRESH_COOKIE_PATH",
            DEFAULT_REFRESH_COOKIE_PATH,
        ).strip()
        or DEFAULT_REFRESH_COOKIE_PATH
    )

    cookie_domain = os.getenv(
        "REFRESH_COOKIE_DOMAIN",
        "",
    ).strip() or None

    cookie_samesite = os.getenv(
        "REFRESH_COOKIE_SAMESITE",
        DEFAULT_REFRESH_COOKIE_SAMESITE,
    ).strip().capitalize()

    if cookie_samesite not in {"Lax", "Strict", "None"}:
        raise RuntimeError(
            "REFRESH_COOKIE_SAMESITE must be Lax, Strict, or None."
        )

    raw_secure = os.getenv("REFRESH_COOKIE_SECURE")

    if raw_secure is None:
        cookie_secure = environment == "production"
    else:
        cookie_secure = raw_secure.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    if environment == "production" and not cookie_secure:
        raise RuntimeError(
            "REFRESH_COOKIE_SECURE must be true in production."
        )

    hash_secret = os.getenv(
        "REFRESH_TOKEN_HASH_SECRET",
        "",
    ).strip() or None

    if environment == "production":
        if hash_secret is None:
            raise RuntimeError(
                "REFRESH_TOKEN_HASH_SECRET must be configured with at least 32 UTF-8 bytes in production."
            )

        if len(hash_secret.encode("utf-8")) < 32:
            raise RuntimeError(
                "REFRESH_TOKEN_HASH_SECRET must be configured with at least 32 UTF-8 bytes in production."
            )

        normalized_secret = hash_secret.casefold()

        if (
            normalized_secret in _KNOWN_WEAK_JWT_SECRETS
            or normalized_secret.startswith(
                ("replace_", "change_me", "your_")
            )
        ):
            raise RuntimeError(
                "REFRESH_TOKEN_HASH_SECRET must be configured with at least 32 UTF-8 bytes in production."
            )

    elif hash_secret is not None and len(hash_secret.encode("utf-8")) < 32:
        raise RuntimeError(
            "REFRESH_TOKEN_HASH_SECRET must be at least 32 UTF-8 bytes when configured."
        )

    return RefreshTokenSettings(
        token_days=token_days,
        cookie_name=cookie_name,
        cookie_secure=cookie_secure,
        cookie_samesite=cookie_samesite,
        cookie_path=cookie_path,
        cookie_domain=cookie_domain,
        hash_secret=hash_secret,
    )
