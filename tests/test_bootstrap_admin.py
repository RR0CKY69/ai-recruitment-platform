from uuid import UUID

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from ml_project.bootstrap_admin import BootstrapError, create_initial_admin
from ml_project.models import Base, User, Workspace
from ml_project.security import verify_password


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def test_bootstrap_creates_active_user_with_argon2_hash_and_no_workspace():
    engine, factory = _session_factory()
    password = "Strong test passphrase 2026!"

    user = create_initial_admin(
        factory,
        email="Admin@Example.com",
        full_name="Initial Administrator",
        password=password,
        password_confirmation=password,
    )

    assert isinstance(user.id, UUID)
    assert user.email == "admin@example.com"
    assert user.is_active is True
    assert user.password_hash.startswith("$argon2id$")
    assert verify_password(password, user.password_hash)
    assert not verify_password("not the password", user.password_hash)
    with factory() as session:
        assert session.scalars(select(Workspace)).all() == []
        assert len(session.scalars(select(User)).all()) == 1
    engine.dispose()


def test_bootstrap_rejects_duplicate_email_and_second_bootstrap_user():
    _engine, factory = _session_factory()
    password = "Strong test passphrase 2026!"
    create_initial_admin(
        factory,
        email="admin@example.com",
        full_name="Initial Administrator",
        password=password,
        password_confirmation=password,
    )

    with pytest.raises(BootstrapError, match="email already exists"):
        create_initial_admin(
            factory,
            email="ADMIN@example.com",
            full_name="Duplicate",
            password=password,
            password_confirmation=password,
        )

    with pytest.raises(BootstrapError, match="one-time"):
        create_initial_admin(
            factory,
            email="second@example.com",
            full_name="Second Administrator",
            password=password,
            password_confirmation=password,
        )

    with factory() as session:
        assert len(session.scalars(select(User)).all()) == 1


def test_existing_inactive_user_also_blocks_initial_bootstrap():
    _engine, factory = _session_factory()
    with factory.begin() as session:
        session.add(
            User(
                email="inactive@example.com",
                password_hash="existing-hash",
                full_name="Inactive Account",
                is_active=False,
            )
        )

    with pytest.raises(BootstrapError, match="one-time"):
        create_initial_admin(
            factory,
            email="new-admin@example.com",
            full_name="New Administrator",
            password="Strong test passphrase 2026!",
            password_confirmation="Strong test passphrase 2026!",
        )

    with factory() as session:
        assert len(session.scalars(select(User)).all()) == 1


def test_bootstrap_password_confirmation_must_match():
    _engine, factory = _session_factory()

    with pytest.raises(BootstrapError, match="confirmation does not match"):
        create_initial_admin(
            factory,
            email="admin@example.com",
            full_name="Administrator",
            password="first password",
            password_confirmation="different password",
        )

    with factory() as session:
        assert session.scalars(select(User)).all() == []


def test_bootstrap_rolls_back_user_insert_on_database_failure():
    engine, factory = _session_factory()

    def fail_user_insert(_mapper, _connection, _target):
        raise IntegrityError("simulated user insert", {}, RuntimeError("forced failure"))

    event.listen(User, "before_insert", fail_user_insert)
    try:
        with pytest.raises(BootstrapError, match="no changes were committed"):
            create_initial_admin(
                factory,
                email="admin@example.com",
                full_name="Administrator",
                password="Strong test passphrase 2026!",
                password_confirmation="Strong test passphrase 2026!",
            )
    finally:
        event.remove(User, "before_insert", fail_user_insert)

    with factory() as session:
        assert session.scalars(select(User)).all() == []
    engine.dispose()