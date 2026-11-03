"""FastAPI dependencies for database sessions and authenticated users."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ml_project.database import get_session
from ml_project.models import User, WorkspaceMember
from ml_project.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_api_session() -> Iterator[Session]:
    """Provide a request-scoped session; this dependency does not commit writes."""
    yield from get_session()


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_api_session)],
) -> User:
    """Validate the bearer token and reload the active user from the database."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        user_id = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise unauthorized from None
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is unavailable.",
        ) from None

    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


def require_workspace_membership(
    session: Session, user: User, workspace_id: UUID
) -> WorkspaceMember:
    """Authorize access only when the authenticated user belongs to the workspace."""
    membership = session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if membership is None or membership.role not in {"ADMIN", "RECRUITER"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace membership is required for this operation.",
        )
    return membership
