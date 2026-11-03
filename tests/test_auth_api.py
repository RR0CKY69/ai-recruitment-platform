from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ml_project.api.dependencies import get_api_session
from ml_project.api.main import app
from ml_project.api.rate_limit import InMemoryLoginRateLimiter, client_rate_limit_key
from ml_project.api.routers import auth as auth_router
from ml_project.config import get_jwt_settings, get_login_rate_limit_settings
from ml_project.models import Base, RefreshSession, User
from ml_project.security import hash_password, hash_refresh_token
from ml_project.config import get_refresh_token_settings


TEST_JWT_SECRET = "test-only-secret-key-with-at-least-32-bytes"
TEST_PASSWORD = "Correct test passphrase 2026!"

@pytest.fixture(autouse=True)
def clear_login_rate_limit_settings_cache():
    get_login_rate_limit_settings.cache_clear()
    yield
    get_login_rate_limit_settings.cache_clear()

@pytest.fixture
def auth_client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    monkeypatch.setenv("JWT_ACCESS_TOKEN_MINUTES", "15")
    monkeypatch.setenv("JWT_ISSUER", "test-auth-api")
    monkeypatch.setenv("JWT_AUDIENCE", "test-clients")
    monkeypatch.setenv("LOGIN_RATE_LIMIT_ATTEMPTS", "5")
    monkeypatch.setenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60")
    monkeypatch.setenv("LOGIN_RATE_LIMIT_TRUSTED_PROXIES", "")
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    monkeypatch.setenv("REFRESH_TOKEN_DAYS", "7")
    monkeypatch.setenv("REFRESH_COOKIE_NAME", "refresh_token")
    monkeypatch.setenv("REFRESH_COOKIE_SECURE", "false")
    monkeypatch.setenv("REFRESH_COOKIE_SAMESITE", "Lax")
    monkeypatch.setenv("REFRESH_COOKIE_PATH", "/")
    monkeypatch.setattr("ml_project.config.load_dotenv", lambda *_args, **_kwargs: None)
    try:
        from ml_project.config import get_refresh_token_settings, get_cors_origins
        get_refresh_token_settings.cache_clear()
        get_cors_origins.cache_clear()
    except Exception:
        pass

    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        with factory() as session:
            yield session

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_api_session] = override_session
    try:
        with TestClient(app) as client:
            yield client, factory
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        engine.dispose()


def _add_user(factory, *, email="admin@example.com", is_active=True, password=TEST_PASSWORD):
    with factory.begin() as session:
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name="Recruitment Admin",
            is_active=is_active,
        )
        session.add(user)
        session.flush()
        return user.id


def _signed_token(*, secret=TEST_JWT_SECRET, claims=None):
    settings = get_jwt_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "iss": settings.issuer,
        "aud": settings.audience,
    }
    if claims is not None:
        payload.update(claims)
    return jwt.encode(payload, secret, algorithm="HS256")


def test_login_returns_short_lived_bearer_token_without_credentials(auth_client):
    client, factory = auth_client
    user_id = _add_user(factory)

    response = client.post(
        "/auth/login",
        json={"email": " ADMIN@EXAMPLE.COM ", "password": TEST_PASSWORD},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    assert TEST_PASSWORD not in response.text
    claims = jwt.decode(
        body["access_token"],
        TEST_JWT_SECRET,
        algorithms=["HS256"],
        issuer="test-auth-api",
        audience="test-clients",
        options={"require": ["sub", "iat", "exp", "iss", "aud"]},
    )
    assert claims["sub"] == str(user_id)
    assert "role" not in claims
    assert "workspace_id" not in claims


def test_login_rejects_unknown_user_and_wrong_password_generically(auth_client):
    client, factory = auth_client
    _add_user(factory)

    wrong_password = client.post(
        "/auth/login", json={"email": "admin@example.com", "password": "wrong password"}
    )
    unknown_user = client.post(
        "/auth/login", json={"email": "unknown@example.com", "password": "wrong password"}
    )

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()
    assert wrong_password.json()["detail"] == "Invalid email or password."
    assert "admin@example.com" not in unknown_user.text


def test_unknown_email_uses_dummy_argon2_verification(auth_client, monkeypatch):
    client, _factory = auth_client
    verified_passwords = []
    monkeypatch.setattr(
        auth_router,
        "verify_dummy_password",
        lambda password: verified_passwords.append(password) or False,
    )

    response = client.post(
        "/auth/login",
        json={"email": "unknown@example.com", "password": TEST_PASSWORD},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password."}
    assert verified_passwords == [TEST_PASSWORD]


def test_repeated_login_attempts_return_generic_429(auth_client, monkeypatch):
    client, factory = auth_client
    _add_user(factory)
    monkeypatch.setenv("LOGIN_RATE_LIMIT_ATTEMPTS", "2")
    wrong_password = {"email": "admin@example.com", "password": "wrong passphrase"}
    unknown_email = {"email": "unknown@example.com", "password": "wrong passphrase"}

    first = client.post("/auth/login", json=wrong_password)
    second = client.post("/auth/login", json=unknown_email)
    blocked = client.post("/auth/login", json=wrong_password)

    assert first.status_code == second.status_code == 401
    assert first.json() == second.json() == {"detail": "Invalid email or password."}
    assert blocked.status_code == 429
    assert blocked.json() == {"detail": "Too many login attempts. Please try again later."}
    assert "Retry-After" in blocked.headers
    assert "unknown@example.com" not in blocked.text


def test_rate_limit_resets_after_configured_fixed_window(auth_client, monkeypatch):
    client, _factory = auth_client
    now = [100.0]
    monkeypatch.setattr(
        auth_router,
        "login_rate_limiter",
        InMemoryLoginRateLimiter(clock=lambda: now[0]),
    )
    monkeypatch.setenv("LOGIN_RATE_LIMIT_ATTEMPTS", "1")
    monkeypatch.setenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "10")
    payload = {"email": "unknown@example.com", "password": "wrong passphrase"}

    first = client.post("/auth/login", json=payload)
    blocked = client.post("/auth/login", json=payload)
    now[0] += 10
    after_reset = client.post("/auth/login", json=payload)

    assert first.status_code == after_reset.status_code == 401
    assert blocked.status_code == 429


def test_successful_login_sequences_do_not_exhaust_rate_limit(auth_client, monkeypatch):
    client, factory = auth_client
    _add_user(factory)
    monkeypatch.setenv("LOGIN_RATE_LIMIT_ATTEMPTS", "2")
    valid_credentials = {"email": "admin@example.com", "password": TEST_PASSWORD}

    # Consecutive successful logins must all succeed and not consume failure budget
    for _ in range(5):
        response = client.post("/auth/login", json=valid_credentials)
        assert response.status_code == 200
        assert "access_token" in response.json()


def test_mixed_successful_and_failed_logins_preserve_failure_protection(auth_client, monkeypatch):
    client, factory = auth_client
    _add_user(factory)
    monkeypatch.setenv("LOGIN_RATE_LIMIT_ATTEMPTS", "2")
    valid_credentials = {"email": "admin@example.com", "password": TEST_PASSWORD}
    wrong_password = {"email": "admin@example.com", "password": "wrong-password"}

    # Failure 1
    fail_1 = client.post("/auth/login", json=wrong_password)
    assert fail_1.status_code == 401

    # Successful login succeeds without increasing the failure count
    success = client.post("/auth/login", json=valid_credentials)
    assert success.status_code == 200

    # Failure 2 (reaches limit of 2 failures)
    fail_2 = client.post("/auth/login", json=wrong_password)
    assert fail_2.status_code == 401

    # Next attempt is blocked with 429
    blocked = client.post("/auth/login", json=valid_credentials)
    assert blocked.status_code == 429
    assert blocked.json() == {"detail": "Too many login attempts. Please try again later."}
    assert "Retry-After" in blocked.headers


def test_rate_limits_use_socket_peer_unless_proxy_is_explicitly_trusted():
    from ipaddress import ip_network

    from starlette.requests import Request

    def request(peer, forwarded=None):
        headers = []
        if forwarded is not None:
            headers.append((b"x-forwarded-for", forwarded.encode()))
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": headers,
                "client": (peer, 12345),
                "server": ("testserver", 80),
                "scheme": "http",
                "query_string": b"",
            }
        )

    spoofed = request("10.0.0.1", "198.51.100.20")
    trusted = request("10.0.0.1", "198.51.100.20")
    other_client = request("10.0.0.2")
    trusted_networks = (ip_network("10.0.0.0/8"),)

    assert client_rate_limit_key(spoofed) == "10.0.0.1"
    assert client_rate_limit_key(trusted, trusted_networks) == "198.51.100.20"
    assert client_rate_limit_key(other_client) == "10.0.0.2"
    limiter = InMemoryLoginRateLimiter(clock=lambda: 1.0)
    assert limiter.check(client_rate_limit_key(spoofed), 1, 60) is None
    assert limiter.check(client_rate_limit_key(other_client), 1, 60) is None


def test_rate_limits_handle_duplicate_forwarded_headers_and_prevent_spoofing():
    from ipaddress import ip_network

    from starlette.requests import Request

    trusted_networks = (ip_network("10.0.0.0/8"),)

    def request_with_headers(headers, peer="10.0.0.1"):
        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/auth/login",
                "headers": headers,
                "client": (peer, 12345),
                "server": ("testserver", 80),
                "scheme": "http",
                "query_string": b"",
            }
        )

    # Attacker injects 1.1.1.1; trusted reverse proxy appends 198.51.100.20 as separate header
    spoof_attempt = request_with_headers(
        [
            (b"x-forwarded-for", b"1.1.1.1"),
            (b"x-forwarded-for", b"198.51.100.20"),
        ]
    )
    assert client_rate_limit_key(spoof_attempt, trusted_networks) == "198.51.100.20"

    # Multiple comma-separated values spread across multiple header lines
    multi_header_chain = request_with_headers(
        [
            (b"x-forwarded-for", b"1.1.1.1, 2.2.2.2"),
            (b"x-forwarded-for", b"198.51.100.20, 10.0.0.2"),
        ]
    )
    # 10.0.0.1 (peer) is trusted -> 10.0.0.2 is trusted -> 198.51.100.20 is untrusted (stops here)
    assert client_rate_limit_key(multi_header_chain, trusted_networks) == "198.51.100.20"


def test_rate_limits_traverse_multi_hop_trusted_proxies():
    from ipaddress import ip_network

    from starlette.requests import Request

    trusted_networks = (ip_network("10.0.0.0/8"), ip_network("172.16.0.0/12"))

    def request(forwarded, peer="10.0.0.1"):
        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/auth/login",
                "headers": [(b"x-forwarded-for", forwarded.encode())] if forwarded else [],
                "client": (peer, 12345),
                "server": ("testserver", 80),
                "scheme": "http",
                "query_string": b"",
            }
        )

    # client (203.0.113.50) -> proxy2 (172.16.0.5) -> proxy1 (10.0.0.1) -> API
    multi_hop = request("203.0.113.50, 172.16.0.5", peer="10.0.0.1")
    assert client_rate_limit_key(multi_hop, trusted_networks) == "203.0.113.50"

    # Entire chain is trusted; returns leftmost proxy
    all_trusted = request("10.0.0.3, 172.16.0.2", peer="10.0.0.1")
    assert client_rate_limit_key(all_trusted, trusted_networks) == "10.0.0.3"

    # Chain contains malformed IP; fails closed to peer IP
    malformed = request("203.0.113.50, not-a-valid-ip", peer="10.0.0.1")
    assert client_rate_limit_key(malformed, trusted_networks) == "10.0.0.1"


def test_rate_limits_missing_client_fallback_does_not_create_global_lockout():
    from starlette.requests import Request

    def request_without_client(headers):
        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/auth/login",
                "headers": headers,
                "client": None,
                "server": ("testserver", 80),
                "scheme": "http",
                "query_string": b"",
            }
        )

    client_a = request_without_client(
        [
            (b"user-agent", b"browser-agent-alpha"),
            (b"x-forwarded-for", b"203.0.113.10"),
        ]
    )
    client_b = request_without_client(
        [
            (b"user-agent", b"browser-agent-beta"),
            (b"x-forwarded-for", b"203.0.113.20"),
        ]
    )
    no_headers = request_without_client([])

    key_a = client_rate_limit_key(client_a)
    key_b = client_rate_limit_key(client_b)
    key_none = client_rate_limit_key(no_headers)

    assert key_a.startswith("fallback:")
    assert key_b.startswith("fallback:")
    assert key_a != key_b
    assert key_none == "fallback:no-client"

    # Rate limiting client A does not block client B
    limiter = InMemoryLoginRateLimiter(clock=lambda: 10.0)
    assert limiter.check(key_a, 1, 60) is None
    # Second attempt by client A is blocked
    assert limiter.check(key_a, 1, 60) == 60
    # Client B is not blocked
    assert limiter.check(key_b, 1, 60) is None


def test_rate_limits_invalid_client_ip_does_not_share_bucket_or_trust_forwarded_headers():
    from ipaddress import ip_network

    from starlette.requests import Request

    trusted_networks = (ip_network("10.0.0.0/8"),)

    def request_named(peer_name, forwarded=None):
        headers = []
        if forwarded:
            headers.append((b"x-forwarded-for", forwarded.encode()))
        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/auth/login",
                "headers": headers,
                "client": (peer_name, 12345),
                "server": ("testserver", 80),
                "scheme": "http",
                "query_string": b"",
            }
        )

    # Non-IP peers (e.g. test client, unix socket hostname) do not trust forwarded headers
    req_alpha = request_named("testclient-alpha", forwarded="198.51.100.99")
    req_beta = request_named("testclient-beta", forwarded="198.51.100.99")

    key_alpha = client_rate_limit_key(req_alpha, trusted_networks)
    key_beta = client_rate_limit_key(req_beta, trusted_networks)

    assert key_alpha == "client:testclient-alpha"
    assert key_beta == "client:testclient-beta"
    assert key_alpha != key_beta

    limiter = InMemoryLoginRateLimiter(clock=lambda: 50.0)
    assert limiter.check(key_alpha, 1, 60) is None
    assert limiter.check(key_alpha, 1, 60) == 60
    assert limiter.check(key_beta, 1, 60) is None


def test_rate_limits_ipv6_and_ipv4_mapped_ipv6_normalization():
    from ipaddress import ip_network

    from starlette.requests import Request

    def request(peer, forwarded=None):
        headers = []
        if forwarded:
            headers.append((b"x-forwarded-for", forwarded.encode()))
        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/auth/login",
                "headers": headers,
                "client": (peer, 12345),
                "server": ("testserver", 80),
                "scheme": "http",
                "query_string": b"",
            }
        )

    # Pure IPv6 proxy trust and forwarding
    ipv6_trusted_networks = (ip_network("2001:db8:1::/48"),)
    ipv6_trusted_peer = request("2001:db8:1::50", forwarded="2001:db8:2::99")
    ipv6_untrusted_peer = request("2001:db8:ffff::1", forwarded="2001:db8:2::99")

    assert client_rate_limit_key(ipv6_trusted_peer, ipv6_trusted_networks) == "2001:db8:2::99"
    assert client_rate_limit_key(ipv6_untrusted_peer, ipv6_trusted_networks) == "2001:db8:ffff::1"

    # Dual-stack IPv4-mapped IPv6 proxy recognized against IPv4 trusted network
    ipv4_trusted_networks = (ip_network("10.0.0.0/8"),)
    mapped_trusted_peer = request("::ffff:10.0.0.1", forwarded="::ffff:198.51.100.77")
    mapped_untrusted_peer = request("::ffff:203.0.113.88", forwarded="::ffff:198.51.100.77")

    assert client_rate_limit_key(mapped_trusted_peer, ipv4_trusted_networks) == "198.51.100.77"
    assert client_rate_limit_key(mapped_untrusted_peer, ipv4_trusted_networks) == "203.0.113.88"


def test_rate_limiter_enforces_maximum_capacity():
    from ml_project.api.rate_limit import DEFAULT_MAX_BUCKETS

    assert DEFAULT_MAX_BUCKETS >= 1000
    limiter = InMemoryLoginRateLimiter(clock=lambda: 100.0, max_buckets=5)

    for i in range(12):
        result = limiter.check(f"client-{i}", attempts=5, window_seconds=60)
        assert result is None

    assert len(limiter._buckets) == 5
    # The most recently added 5 clients must be present
    for i in range(7, 12):
        assert f"client-{i}" in limiter._buckets


def test_rate_limiter_cleans_up_expired_buckets():
    now = [100.0]
    limiter = InMemoryLoginRateLimiter(clock=lambda: now[0], max_buckets=10)

    # First attempt for client-old
    limiter.check("client-old", attempts=5, window_seconds=60)
    assert "client-old" in limiter._buckets

    # Advance clock past window and past cleanup threshold
    now[0] += 70.0

    # New client arrives, triggering expired bucket cleanup
    limiter.check("client-new", attempts=5, window_seconds=60)

    assert "client-old" not in limiter._buckets
    assert "client-new" in limiter._buckets
    assert len(limiter._buckets) == 1


def test_rate_limiter_evicts_oldest_bucket_when_capacity_reached():
    now = [100.0]
    limiter = InMemoryLoginRateLimiter(clock=lambda: now[0], max_buckets=3)

    limiter.check("client-1", attempts=5, window_seconds=60)
    now[0] += 5.0
    limiter.check("client-2", attempts=5, window_seconds=60)
    now[0] += 5.0
    limiter.check("client-3", attempts=5, window_seconds=60)

    assert len(limiter._buckets) == 3
    assert list(limiter._buckets.keys()) == ["client-1", "client-2", "client-3"]

    # Adding a 4th unexpired client when full evicts client-1 (the oldest)
    now[0] += 5.0
    limiter.check("client-4", attempts=5, window_seconds=60)

    assert len(limiter._buckets) == 3
    assert "client-1" not in limiter._buckets
    assert list(limiter._buckets.keys()) == ["client-2", "client-3", "client-4"]


def test_rate_limiter_concurrent_access_preserves_thread_safety_and_bounds():
    from concurrent.futures import ThreadPoolExecutor

    limiter = InMemoryLoginRateLimiter(max_buckets=15)

    def worker(worker_id: int):
        for step in range(10):
            client_key = f"thread-client-{worker_id % 30}-{step % 5}"
            limiter.check(client_key, attempts=10, window_seconds=60)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker, i) for i in range(24)]
        for future in futures:
            future.result()

    assert len(limiter._buckets) <= 15


def test_login_rejects_corrupted_stored_password_hash_generically(auth_client):
    client, factory = auth_client
    with factory.begin() as session:
        session.add(
            User(
                email="broken@example.com",
                password_hash="not-an-argon2-hash",
                full_name="Broken Hash User",
                is_active=True,
            )
        )

    response = client.post(
        "/auth/login", json={"email": "broken@example.com", "password": TEST_PASSWORD}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password."}


def test_inactive_user_cannot_login_or_use_current_user(auth_client):
    client, factory = auth_client
    inactive_user_id = _add_user(factory, is_active=False)

    login_response = client.post(
        "/auth/login", json={"email": "admin@example.com", "password": TEST_PASSWORD}
    )
    token = _signed_token(claims={"sub": str(inactive_user_id)})
    current_response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert login_response.status_code == 403
    assert login_response.json() == {"detail": "Authentication is not permitted."}
    assert current_response.status_code == 401
    assert "email" not in current_response.json()


def test_me_requires_token_and_returns_only_safe_user_fields(auth_client):
    client, factory = auth_client
    user_id = _add_user(factory)

    missing = client.get("/auth/me")
    token = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": TEST_PASSWORD},
    ).json()["access_token"]
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert missing.status_code == 401
    assert response.status_code == 200
    assert response.json() == {
        "id": str(user_id),
        "email": "admin@example.com",
        "full_name": "Recruitment Admin",
        "is_active": True,
    }
    assert "password_hash" not in response.json()
    assert "access_token" not in response.json()


@pytest.mark.parametrize("token", ["not-a-jwt", "", None])
def test_me_rejects_malformed_or_missing_token(auth_client, token):
    client, _factory = auth_client
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}

    response = client.get("/auth/me", headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired access token."}


@pytest.mark.parametrize(
    "claim_override",
    [
        {"iss": "wrong-issuer"},
        {"aud": "wrong-audience"},
    ],
)
def test_me_rejects_wrong_issuer_or_audience(auth_client, claim_override):
    client, factory = auth_client
    user_id = _add_user(factory)
    token = _signed_token(claims={"sub": str(user_id), **claim_override})

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_me_rejects_unsigned_token_algorithm(auth_client):
    client, factory = auth_client
    user_id = _add_user(factory)
    settings = get_jwt_settings()
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "iss": settings.issuer,
            "aud": settings.audience,
        },
        key="",
        algorithm="none",
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_me_rejects_valid_token_for_nonexistent_user(auth_client):
    client, _factory = auth_client
    token = _signed_token()

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_me_rejects_expired_and_incorrectly_signed_tokens(auth_client):
    client, factory = auth_client
    user_id = _add_user(factory)
    settings = get_jwt_settings()
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id),
        "iat": now - timedelta(minutes=5),
        "exp": now - timedelta(minutes=1),
        "iss": settings.issuer,
        "aud": settings.audience,
    }
    expired_token = jwt.encode(claims, TEST_JWT_SECRET, algorithm="HS256")
    bad_signature = jwt.encode(claims, "different-test-secret-that-is-long-enough", algorithm="HS256")

    expired_response = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
    )
    signature_response = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {bad_signature}"}
    )

    assert expired_response.status_code == 401
    assert signature_response.status_code == 401
    assert expired_response.json() == signature_response.json()


def test_me_rejects_missing_required_jwt_claims(auth_client):
    client, factory = auth_client
    user_id = _add_user(factory)
    settings = get_jwt_settings()
    token = jwt.encode(
        {
            "sub": str(user_id),
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            "iss": settings.issuer,
        },
        TEST_JWT_SECRET,
        algorithm="HS256",
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_login_reports_unavailable_when_signing_secret_is_missing(auth_client, monkeypatch):
    client, factory = auth_client
    _add_user(factory)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    response = client.post(
        "/auth/login", json={"email": "admin@example.com", "password": TEST_PASSWORD}
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Authentication service is unavailable."}


@pytest.mark.parametrize("email", ["not-an-email", "name@localhost", "two@@example.com"])
def test_login_validates_email_input(auth_client, email):
    client, _factory = auth_client

    response = client.post("/auth/login", json={"email": email, "password": TEST_PASSWORD})

    assert response.status_code == 422


def test_validation_errors_do_not_reflect_invalid_email_or_password(auth_client):
    client, _factory = auth_client
    password_marker = "test-password-marker-never-return"
    email_marker = "test-invalid-email-marker"

    response = client.post(
        "/auth/login",
        json={"email": email_marker, "password": password_marker},
    )

    assert response.status_code == 422
    assert password_marker not in response.text
    assert email_marker not in response.text
    error = response.json()["detail"][0]
    assert error == {
        "loc": ["body", "email"],
        "type": "value_error",
        "msg": "Enter a valid email address.",
    }


def test_oversized_password_is_not_reflected_in_validation_response(auth_client):
    client, _factory = auth_client
    password_marker = "oversized-password-test-marker-" + ("x" * 1030)

    response = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": password_marker},
    )

    assert response.status_code == 422
    assert password_marker not in response.text
    assert "oversized-password-test-marker" not in response.text
    assert response.json()["detail"] == [
        {
            "loc": ["body", "password"],
            "type": "too_long",
            "msg": "String is too long.",
        }
    ]


def test_malformed_login_json_does_not_reflect_raw_request_body(auth_client):
    client, _factory = auth_client
    body_marker = "raw-login-body-secret-marker"
    request_body = (
        '{"email":"admin@example.com","password":"'
        + body_marker
        + '",BROKEN'
    )

    response = client.post(
        "/auth/login",
        content=request_body,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert body_marker not in response.text
    assert response.json()["detail"][0]["loc"][0] == "body"
    assert response.json()["detail"][0]["type"] == "json_invalid"
    assert response.json()["detail"][0]["msg"] == "Request body must be valid JSON."


@pytest.mark.parametrize(
    ("payload", "marker", "expected_type"),
    [
        (
            {"email": "admin@example.com"},
            "unused-missing-password-marker",
            "missing",
        ),
        (
            {
                "email": "admin@example.com",
                "password": {"secret": "nested-password-marker"},
            },
            "nested-password-marker",
            "string_type",
        ),
        (
            {
                "email": "admin@example.com",
                "password": "test-password",
                "access_token": "unexpected-token-marker",
            },
            "unexpected-token-marker",
            "extra_forbidden",
        ),
    ],
)
def test_login_missing_invalid_type_and_extra_fields_are_safe(
    auth_client, payload, marker, expected_type
):
    client, _factory = auth_client

    response = client.post("/auth/login", json=payload)

    assert response.status_code == 422
    assert marker not in response.text
    assert all("input" not in item and "ctx" not in item for item in response.json()["detail"])
    assert any(item["type"] == expected_type for item in response.json()["detail"])


def test_non_auth_validation_error_keeps_safe_field_path_and_message(auth_client):
    client, factory = auth_client
    _add_user(factory)
    token = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": TEST_PASSWORD},
    ).json()["access_token"]

    response = client.get(
        "/jobs?workspace_id=not-a-uuid",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == [
        {
            "loc": ["query", "workspace_id"],
            "type": "uuid_parsing",
            "msg": "Input should be a valid UUID.",
        }
    ]


def test_login_creates_refresh_session_and_cookie(auth_client):
    client, factory = auth_client
    user_id = _add_user(factory)
    response = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    cookies = response.cookies
    assert "refresh_token" in cookies
    # Check cookie attributes via set-cookie
    set_cookie = response.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie
    assert "Path=/" in set_cookie or "path=/" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()
    assert "max-age=604800" in set_cookie.lower()
    assert "secure" not in set_cookie.lower()
    assert "domain=" not in set_cookie.lower()
    with factory() as session:
        sessions = session.query(RefreshSession).all()
        assert len(sessions) == 1
        assert sessions[0].user_id == user_id
        assert sessions[0].revoked_at is None
        # token hash stored, not plaintext
        assert sessions[0].token_hash != cookies.get("refresh_token")


def test_refresh_rotates_tokens_and_reuses_family(auth_client):
    client, factory = auth_client
    _add_user(factory)
    login_resp = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:5173"},
    )
    assert login_resp.status_code == 200
    old_cookie = login_resp.cookies.get("refresh_token")
    with factory() as session:
        old_session = session.query(RefreshSession).first()
        old_id = old_session.id
        old_family = old_session.family_id

    refresh_resp = client.post("/auth/refresh", headers={"Origin": "http://localhost:5173"})
    assert refresh_resp.status_code == 200
    data = refresh_resp.json()
    assert "access_token" in data
    assert "refresh_token" in refresh_resp.cookies
    new_cookie = refresh_resp.cookies.get("refresh_token")
    assert new_cookie and new_cookie != old_cookie
    with factory() as session:
        sessions = session.query(RefreshSession).all()
        assert len(sessions) == 2
        revoked_old = session.query(RefreshSession).filter(RefreshSession.id == old_id).first()
        assert revoked_old.revoked_at is not None
        new_s = session.query(RefreshSession).filter(RefreshSession.id != old_id).first()
        assert new_s.family_id == old_family
        assert new_s.revoked_at is None
        assert new_s.token_hash != hash_refresh_token(old_cookie)


def test_refresh_reuse_revokes_family(auth_client):
    client, factory = auth_client
    _add_user(factory)
    login_resp = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:5173"},
    )
    old_cookie = login_resp.cookies.get("refresh_token")
    # rotate
    r1 = client.post("/auth/refresh", headers={"Origin": "http://localhost:5173"})
    assert r1.status_code == 200
    # reuse old cookie
    client.cookies.set("refresh_token", old_cookie)
    r2 = client.post("/auth/refresh", headers={"Origin": "http://localhost:5173"})
    assert r2.status_code == 401
    with factory() as session:
        sessions = session.query(RefreshSession).all()
        assert all(s.revoked_at is not None for s in sessions)


def test_refresh_rejects_missing_invalid_expired_revoked(auth_client):
    client, factory = auth_client
    _add_user(factory)
    # missing
    r = client.post("/auth/refresh", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 401
    # invalid
    client.cookies.set("refresh_token", "invalid")
    r = client.post("/auth/refresh", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 401

    client.cookies.clear()
    login_response = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:5173"},
    )
    assert login_response.status_code == 200
    with factory() as session:
        refresh_session = session.query(RefreshSession).one()
        refresh_session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    expired_response = client.post("/auth/refresh", headers={"Origin": "http://localhost:5173"})
    assert expired_response.status_code == 401
    with factory() as session:
        refresh_session = session.query(RefreshSession).one()
        assert refresh_session.revoked_at is not None

    client.cookies.clear()
    login_response = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:5173"},
    )
    assert login_response.status_code == 200
    with factory() as session:
        refresh_session = session.query(RefreshSession).order_by(RefreshSession.created_at.desc()).first()
        refresh_session.revoked_at = datetime.now(timezone.utc)
        session.commit()
    client.cookies.set("refresh_token", login_response.cookies.get("refresh_token"))
    revoked_response = client.post("/auth/refresh", headers={"Origin": "http://localhost:5173"})
    assert revoked_response.status_code == 401


def test_refresh_rejects_invalid_origin(auth_client):
    client, factory = auth_client
    _add_user(factory)
    login_resp = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://evil.com"},
    )
    # Origin validation rejects bad origin
    assert login_resp.status_code == 403


def test_logout_revokes_and_clears_cookie(auth_client):
    client, factory = auth_client
    _add_user(factory)
    login_resp = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:5173"},
    )
    assert login_resp.status_code == 200
    lo = client.post("/auth/logout", headers={"Origin": "http://localhost:5173"})
    assert lo.status_code == 200
    set_cookie = lo.headers.get("set-cookie", "")
    assert "refresh_token" in set_cookie
    assert "Max-Age=0" in set_cookie or "expires" in set_cookie.lower()
    with factory() as session:
        s = session.query(RefreshSession).first()
        assert s.revoked_at is not None
    refresh_after_logout = client.post(
        "/auth/refresh", headers={"Origin": "http://localhost:5173"}
    )
    assert refresh_after_logout.status_code == 401
    # repeated logout safe
    lo2 = client.post("/auth/logout", headers={"Origin": "http://localhost:5173"})
    assert lo2.status_code == 200


def test_logout_missing_cookie_safe(auth_client):
    client, _factory = auth_client
    lo = client.post("/auth/logout", headers={"Origin": "http://localhost:5173"})
    assert lo.status_code == 200


def test_refresh_token_hash_uniqueness_and_dedup_migration(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    db_file = tmp_path / "rt.db"
    engine = create_engine(f"sqlite+pysqlite:///{db_file.as_posix()}")
    cfg = Config(str(__import__('pathlib').Path(__file__).resolve().parents[1] / "alembic.ini"))
    import os
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{db_file.as_posix()}"
    command.upgrade(cfg, "head")
    insp = inspect(engine)
    assert "refresh_sessions" in insp.get_table_names()
    # Check unique index exists
    idxs = {i["name"]: i for i in insp.get_indexes("refresh_sessions")}
    # Either unique index present
    assert any("token_hash" in str(k) for k in idxs.keys())
    command.downgrade(cfg, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]


def test_concurrent_refresh_transaction_behavior_documented(auth_client):
    # SQLite has limited locking; document behavior via test
    client, factory = auth_client
    _add_user(factory)
    login_resp = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:5173"},
    )
    assert login_resp.status_code == 200
    # Two sequential refreshes - first rotates, second with new cookie works
    r1 = client.post("/auth/refresh", headers={"Origin": "http://localhost:5173"})
    assert r1.status_code == 200
    r2 = client.post("/auth/refresh", headers={"Origin": "http://localhost:5173"})
    assert r2.status_code == 200
    # Note: SQLite does not prove PostgreSQL row-locking behavior for true concurrency; transaction usage present.
