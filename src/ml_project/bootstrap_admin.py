
"""One-time CLI bootstrap for the initial administrator and workspace."""

from __future__ import annotations

import argparse
import getpass
import re
import sys

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from ml_project.database import create_session_factory
from ml_project.models import User, Workspace, WorkspaceMember
from ml_project.security import hash_password

_BOOTSTRAP_LOCK_ID = 743912845120
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class BootstrapError(RuntimeError):
    """Raised when safe initial administrator bootstrap cannot proceed."""


def create_initial_admin(
    session_factory: sessionmaker[Session],
    *,
    email: str,
    full_name: str,
    password: str,
    password_confirmation: str,
    workspace_name: str,
) -> tuple[User, Workspace]:
    """Create the first administrator, workspace, and membership atomically."""

    normalized_email = email.strip().casefold()
    normalized_name = full_name.strip()
    normalized_workspace = workspace_name.strip()

    if not _EMAIL_PATTERN.fullmatch(normalized_email):
        raise BootstrapError("Enter a valid email address.")

    if not normalized_name or len(normalized_name) > 200:
        raise BootstrapError("Enter a name between 1 and 200 characters.")

    if not normalized_workspace or len(normalized_workspace) > 200:
        raise BootstrapError("Enter a workspace name between 1 and 200 characters.")

    if not password:
        raise BootstrapError("Password cannot be blank.")

    if password != password_confirmation:
        raise BootstrapError("Password confirmation does not match.")

    workspace_slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        normalized_workspace.casefold(),
    ).strip("-")[:120].strip("-")

    if not workspace_slug:
        raise BootstrapError("Workspace name must produce a valid URL slug.")

    try:
        with session_factory.begin() as session:
            if session.get_bind().dialect.name == "postgresql":
                session.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_id)"),
                    {"lock_id": _BOOTSTRAP_LOCK_ID},
                )

            existing_email = session.scalar(
                select(User.id).where(
                    func.lower(User.email) == normalized_email
                )
            )
            if existing_email is not None:
                raise BootstrapError(
                    "A user account with this email already exists."
                )

            existing_user = session.scalar(select(User.id).limit(1))
            if existing_user is not None:
                raise BootstrapError(
                    "Bootstrap is disabled because users already exist."
                )

            existing_workspace = session.scalar(
                select(Workspace.id).limit(1)
            )
            if existing_workspace is not None:
                raise BootstrapError(
                    "Bootstrap is disabled because a workspace already exists."
                )

            user = User(
                email=normalized_email,
                password_hash=hash_password(password),
                full_name=normalized_name,
                is_active=True,
            )
            session.add(user)
            session.flush()

            workspace = Workspace(
                name=normalized_workspace,
                slug=workspace_slug,
                created_by_id=user.id,
            )
            session.add(workspace)
            session.flush()

            membership = WorkspaceMember(
                workspace_id=workspace.id,
                user_id=user.id,
                role="ADMIN",
            )
            session.add(membership)
            session.flush()

            user_id = user.id
            workspace_id = workspace.id

    except IntegrityError as error:
        raise BootstrapError(
            "Creation failed. The transaction was rolled back; "
            "no partial records were committed."
        ) from error

    with session_factory() as session:
        created_user = session.get(User, user_id)
        created_workspace = session.get(Workspace, workspace_id)

        if created_user is None or created_workspace is None:
            raise BootstrapError(
                "Verification failed after creation. Check the database."
            )

        return created_user, created_workspace


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create the first administrator and workspace."
    )
    parser.parse_args()

    try:
        if not sys.stdin.isatty():
            raise BootstrapError(
                "Run this command in an interactive terminal "
                "so password entry stays hidden."
            )

        email = input("Administrator email: ").strip()
        full_name = input("Administrator full name: ").strip()
        workspace_name = input("Workspace name [Kinetic Hire]: ").strip()
        workspace_name = workspace_name or "Kinetic Hire"

        password = getpass.getpass("Password (input hidden): ")
        password_confirmation = getpass.getpass(
            "Confirm password (input hidden): "
        )

        user, workspace = create_initial_admin(
            create_session_factory(),
            email=email,
            full_name=full_name,
            password=password,
            password_confirmation=password_confirmation,
            workspace_name=workspace_name,
        )

    except (BootstrapError, RuntimeError, OSError, SQLAlchemyError) as error:
        print(f"Administrator bootstrap failed: {error}")
        return 1

    print("\nInitial administrator setup completed.")
    print(f"User UUID: {user.id}")
    print(f"Email: {user.email}")
    print(f"Workspace: {workspace.name}")
    print(f"Workspace slug: {workspace.slug}")
    print("Workspace role: ADMIN")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
