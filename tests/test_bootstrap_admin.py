
from uuid import UUID

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from ml_project.bootstrap_admin import BootstrapError, create_initial_admin
from ml_project.models import Base, User, Workspace, WorkspaceMember
from ml_project.security import verify_password


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _create_admin(factory, email="admin@example.com", workspace_name="Kinetic Hire"):
    password = "Strong test passphrase 2026!"

    return create_initial_admin(
        factory,
        email=email,
        full_name="Initial Administrator",
        password=password,
        password_confirmation=password,
        workspace_name=workspace_name,
    )


def test_bootstrap_creates_admin_workspace_and_membership():
    engine, factory = _session_factory()
    password = "Strong test passphrase 2026!"

    user, workspace = create_initial_admin(
        factory,
        email="Admin@Example.com",
        full_name="Initial Administrator",
        password=password,
        password_confirmation=password,
        workspace_name="Kinetic Hire",
    )

    assert isinstance(user.id, UUID)
    assert isinstance(workspace.id, UUID)
    assert user.email == "admin@example.com"
    assert user.is_active is True
    assert user.password_hash.startswith("$argon2id$")
    assert verify_password(password, user.password_hash)
    assert not verify_password("not the password", user.password_hash)

    assert workspace.name == "Kinetic Hire"
    assert workspace.slug == "kinetic-hire"
    assert workspace.created_by_id == user.id

    with factory() as session:
        assert len(session.scalars(select(User)).all()) == 1
        assert len(session.scalars(select(Workspace)).all()) == 1

        membership = session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id == user.id,
            )
        )

        assert membership is not None
        assert membership.role == "ADMIN"

    engine.dispose()


def test_bootstrap_rejects_duplicate_email():
    _engine, factory = _session_factory()
    _create_admin(factory)

    with pytest.raises(BootstrapError, match="email already exists"):
        _create_admin(factory, email="ADMIN@example.com")


def test_bootstrap_rejects_second_user():
    _engine, factory = _session_factory()
    _create_admin(factory)

    with pytest.raises(BootstrapError, match="users already exist"):
        create_initial_admin(
            factory,
            email="second@example.com",
            full_name="Second Administrator",
            password="Strong test passphrase 2026!",
            password_confirmation="Strong test passphrase 2026!",
            workspace_name="Another Workspace",
        )

    with factory() as session:
        assert len(session.scalars(select(User)).all()) == 1
        assert len(session.scalars(select(Workspace)).all()) == 1


def test_existing_inactive_user_blocks_bootstrap():
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

    with pytest.raises(BootstrapError, match="users already exist"):
        _create_admin(factory, email="new-admin@example.com")

    with factory() as session:
        assert len(session.scalars(select(User)).all()) == 1
        assert session.scalars(select(Workspace)).all() == []


def test_existing_workspace_blocks_bootstrap():
    _engine, factory = _session_factory()

    with factory.begin() as session:
        existing_user = User(
            email="existing@example.com",
            password_hash="existing-hash",
            full_name="Existing User",
            is_active=True,
        )
        session.add(existing_user)
        session.flush()

        session.add(
            Workspace(
                name="Existing Workspace",
                slug="existing-workspace",
                created_by_id=existing_user.id,
            )
        )

    with pytest.raises(BootstrapError, match="users already exist"):
        _create_admin(factory)

    with factory() as session:
        assert len(session.scalars(select(User)).all()) == 1
        assert len(session.scalars(select(Workspace)).all()) == 1


def test_bootstrap_rejects_password_confirmation_mismatch():
    _engine, factory = _session_factory()

    with pytest.raises(BootstrapError, match="confirmation does not match"):
        create_initial_admin(
            factory,
            email="admin@example.com",
            full_name="Administrator",
            password="first password",
            password_confirmation="different password",
            workspace_name="Kinetic Hire",
        )

    with factory() as session:
        assert session.scalars(select(User)).all() == []
        assert session.scalars(select(Workspace)).all() == []


def test_bootstrap_rejects_blank_workspace_name():
    _engine, factory = _session_factory()

    with pytest.raises(BootstrapError, match="workspace name"):
        create_initial_admin(
            factory,
            email="admin@example.com",
            full_name="Administrator",
            password="Strong test passphrase 2026!",
            password_confirmation="Strong test passphrase 2026!",
            workspace_name="   ",
        )

    with factory() as session:
        assert session.scalars(select(User)).all() == []
        assert session.scalars(select(Workspace)).all() == []


def test_bootstrap_rolls_back_all_records_on_database_failure():
    engine, factory = _session_factory()

    def fail_user_insert(_mapper, _connection, _target):
        raise IntegrityError(
            "simulated user insert",
            {},
            RuntimeError("forced failure"),
        )

    event.listen(User, "before_insert", fail_user_insert)

    try:
        with pytest.raises(BootstrapError, match="no partial records"):
            _create_admin(factory)
    finally:
        event.remove(User, "before_insert", fail_user_insert)

    with factory() as session:
        assert session.scalars(select(User)).all() == []
        assert session.scalars(select(Workspace)).all() == []
        assert session.scalars(select(WorkspaceMember)).all() == []

    engine.dispose()
