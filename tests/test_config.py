
import pytest

from ml_project import config


@pytest.fixture(autouse=True)
def _isolate_config(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.delenv("ENV", raising=False)


def test_invalid_env_rejected(monkeypatch):
    monkeypatch.setenv("ENV", "staging")
    with pytest.raises(RuntimeError, match="ENV must be"):
        config.get_environment()


def test_missing_jwt_secret_rejected(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        config.get_jwt_settings()


def test_short_jwt_secret_rejected(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("JWT_SECRET_KEY", "short-secret")
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        config.get_jwt_settings()


def test_known_weak_jwt_secret_rejected(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("JWT_SECRET_KEY", "secret")
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        config.get_jwt_settings()


def test_placeholder_jwt_secret_rejected(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("JWT_SECRET_KEY", "replace_with_a_long_random_secret_value_here")
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        config.get_jwt_settings()


def test_valid_jwt_secret_accepted(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("JWT_SECRET_KEY", "a" * 32)
    settings = config.get_jwt_settings()
    assert len(settings.secret_key.encode("utf-8")) >= 32
