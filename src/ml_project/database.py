"""PostgreSQL-first SQLAlchemy engine, session, and schema initialization helpers."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ml_project.config import get_database_url
from ml_project.models import Base


def create_database_engine(url: str | None = None) -> Engine:
    """Create a database engine."""
    if url is None:
        return get_default_engine()

    return create_engine(url, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_default_engine() -> Engine:
    """Return the shared default database engine."""
    return create_engine(
        get_database_url(),
        pool_pre_ping=True,
    )


@lru_cache(maxsize=1)
def get_default_session_factory() -> sessionmaker[Session]:
    """Return the shared default session factory."""
    return sessionmaker(
        bind=get_default_engine(),
        expire_on_commit=False,
    )


def create_session_factory(
    engine: Engine | None = None,
) -> sessionmaker[Session]:
    """Create a session factory for an explicit engine or reuse the default."""
    if engine is None:
        return get_default_session_factory()

    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )


def get_session(
    factory: sessionmaker[Session] | None = None,
) -> Iterator[Session]:
    """Yield a request-scoped session and always close it."""
    session_factory = factory or get_default_session_factory()

    with session_factory() as session:
        yield session


def initialize_database(engine: Engine | None = None) -> None:
    """Create missing tables for local bootstrap and isolated tests.

    Use `alembic upgrade head` for versioned production schema changes.
    """
    Base.metadata.create_all(engine or get_default_engine())