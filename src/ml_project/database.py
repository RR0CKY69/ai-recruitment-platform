"""PostgreSQL-first SQLAlchemy engine, session, and schema initialization helpers."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ml_project.config import get_database_url
from ml_project.models import Base


def create_database_engine(url: str | None = None) -> Engine:
    """Create a connection pool for DATABASE_URL or an explicitly supplied test URL."""
    return create_engine(url or get_database_url(), pool_pre_ping=True)


def create_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    """Create sessions bound to the configured engine or a test engine."""
    return sessionmaker(bind=engine or create_database_engine(), expire_on_commit=False)


def get_session(factory: sessionmaker[Session] | None = None) -> Iterator[Session]:
    """Yield a session and always close it; callers own transaction boundaries."""
    session_factory = factory or create_session_factory()
    with session_factory() as session:
        yield session


def initialize_database(engine: Engine | None = None) -> None:
    """Create missing tables for local bootstrap and isolated tests.

    Use `alembic upgrade head` for versioned production schema changes.
    """
    Base.metadata.create_all(engine or create_database_engine())