from fastapi.testclient import TestClient

from ml_project.api.main import app


def test_fastapi_application_imports_successfully():
    assert app.title == "AI Recruitment Sourcing API"
    assert app.version == "0.1.0"


def test_health_endpoint_returns_ok():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
import importlib

import pytest

from ml_project import config
from ml_project.api import main as api_main


@pytest.fixture
def reloaded_app(monkeypatch):
    def _reload(env_value):
        monkeypatch.setattr(config, "load_dotenv", lambda *_args, **_kwargs: None)
        if env_value is None:
            monkeypatch.delenv("ENV", raising=False)
        else:
            monkeypatch.setenv("ENV", env_value)
        if env_value == "production":
            monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://example.test")
        else:
            monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        importlib.reload(api_main)
        return api_main.app

    yield _reload
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setattr(config, "load_dotenv", lambda *_args, **_kwargs: None)
    importlib.reload(api_main)


def test_docs_enabled_in_development(reloaded_app):
    app = reloaded_app("development")
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/redoc").status_code == 200
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/health").status_code == 200


def test_docs_disabled_in_production(reloaded_app):
    app = reloaded_app("production")
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/health").status_code == 200
def test_production_invalid_jwt_prevents_startup(reloaded_app, monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    app = reloaded_app("production")
    with pytest.raises(RuntimeError), TestClient(app):
        pass
