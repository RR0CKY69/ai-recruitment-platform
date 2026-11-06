
import hashlib
import hmac

import pytest

from ml_project import config
from ml_project.security import hash_refresh_token

VALID_SECRET = "a" * 32
TEST_TOKEN = "test-refresh-token-value"


@pytest.fixture(autouse=True)
def isolated_refresh_config(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("REFRESH_TOKEN_HASH_SECRET", raising=False)
    config.get_refresh_token_settings.cache_clear()
    yield
    config.get_refresh_token_settings.cache_clear()


def test_development_without_hash_secret_uses_sha256_fallback(monkeypatch):
    monkeypatch.setenv("ENV", "development")
    expected = hashlib.sha256(TEST_TOKEN.encode("utf-8")).hexdigest()
    assert hash_refresh_token(TEST_TOKEN) == expected


def test_production_without_hash_secret_raises(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    with pytest.raises(RuntimeError, match="REFRESH_TOKEN_HASH_SECRET"):
        hash_refresh_token(TEST_TOKEN)


def test_production_with_valid_secret_uses_hmac(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("REFRESH_TOKEN_HASH_SECRET", VALID_SECRET)
    expected = hmac.new(
        VALID_SECRET.encode("utf-8"), TEST_TOKEN.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    assert hash_refresh_token(TEST_TOKEN) == expected


def test_invalid_production_config_cannot_silently_fallback(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("REFRESH_TOKEN_HASH_SECRET", "too-short")
    with pytest.raises(RuntimeError, match="REFRESH_TOKEN_HASH_SECRET"):
        hash_refresh_token(TEST_TOKEN)
