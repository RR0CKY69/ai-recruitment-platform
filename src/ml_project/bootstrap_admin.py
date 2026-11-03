"""One-time CLI bootstrap for the initial active administrator account."""

from __future__ import annotations

import argparse
import getpass
import re
import sys

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from ml_project.database import create_session_factory
from ml_project.models import User
from ml_project.security import hash_password

_BOOTSTRAP_LOCK_ID = 743912845120
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class BootstrapError(RuntimeError):
    """Raised when safe one-time administrator bootstrap cannot proceed."""


def create_initial_admin(
    session_factory: sessionmaker[Session],
    *,
    email: str,
    full_name: str,
    password: str,
    password_confirmation: str,
) -> User:
    """Create the first active user in one transaction; never creates a workspace."""
    normalized_email = email.strip().casefold()
    normalized_name = full_name.strip()
    if not _EMAIL_PATTERN.fullmatch(normalized_email):
        raise BootstrapError("Enter a valid email address.")
    if not normalized_name:
        raise BootstrapError("Administrator name cannot be blank.")
    if not password:
        raise BootstrapError("Password cannot be blank.")
    if password != password_confirmation:
        raise BootstrapError("Password confirmation does not match.")

    try:
        with session_factory.begin() as session:
            if session.get_bind().dialect.name == "postgresql":
                session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": _BOOTSTRAP_LOCK_ID})

            existing_email = session.scalar(
                select(User.id).where(func.lower(User.email) == normalized_email)
            )
            if existing_email is not None:
                raise BootstrapError("A user account with this email already exists.")

            existing_user = session.scalar(select(User.id).limit(1))
            if existing_user is not None:
                raise BootstrapError(
                    "Initial administrator bootstrap is one-time and is disabled because users already exist."
                )

            user = User(
                email=normalized_email,
                password_hash=hash_password(password),
                full_name=normalized_name,
                is_active=True,
            )
            session.add(user)
            session.flush()
            created_user_id = user.id
    except IntegrityError as error:
        raise BootstrapError(
            "User creation failed; the transaction was rolled back and no changes were committed."
        ) from error

    with session_factory() as session:
        created_user = session.get(User, created_user_id)
        if created_user is None:
            raise BootstrapError("User creation did not persist; transaction was rolled back.")
        return created_user


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create the first active administrator account using hidden password prompts."
    )
    parser.parse_args()

    try:
        if not sys.stdin.isatty():
            raise BootstrapError(
                "Run this command in an interactive terminal so password entry stays hidden."
            )
        email = input("Administrator email: ").strip()
        full_name = input("Administrator full name: ").strip()
        password = getpass.getpass("Password (input hidden): ")
        password_confirmation = getpass.getpass("Confirm password (input hidden): ")
        user = create_initial_admin(
            create_session_factory(),
            email=email,
            full_name=full_name,
            password=password,
            password_confirmation=password_confirmation,
        )
    except (BootstrapError, RuntimeError, OSError, SQLAlchemyError) as error:
        print(f"Administrator bootstrap failed: {error}")
        return 1

    print("Initial administrator account created.")
    print(f"User UUID: {user.id}")
    print(f"Email: {user.email}")
    print("No workspace was created. Add this user to a workspace with the ADMIN role when ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())