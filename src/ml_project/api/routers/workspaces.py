"""Authenticated workspace discovery endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ml_project.api.dependencies import get_api_session, get_current_user
from ml_project.api.schemas import WorkspaceMembershipResponse
from ml_project.models import User, Workspace, WorkspaceMember

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("", response_model=list[WorkspaceMembershipResponse])
def list_workspaces(
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[WorkspaceMembershipResponse]:
    """Return only workspaces associated with the authenticated user."""
    memberships = session.execute(
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id)
        .order_by(Workspace.name, Workspace.id)
    ).all()
    return [
        WorkspaceMembershipResponse(
            workspace_id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            role=role,
        )
        for workspace, role in memberships
    ]
