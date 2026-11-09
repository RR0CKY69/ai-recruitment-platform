"""Authenticated workspace discovery endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ml_project.api.dependencies import (
    get_api_session,
    get_current_user,
    require_workspace_admin,
    require_workspace_membership,
)
from ml_project.api.schemas import (
    AddWorkspaceMemberRequest,
    UpdateWorkspaceMemberRoleRequest,
    UpdateWorkspaceRequest,
    WorkspaceDetailResponse,
    WorkspaceMemberResponse,
    WorkspaceMembershipResponse,
)
from ml_project.api.workspace_slugs import generate_workspace_slug
from ml_project.audit import record_audit_event
from ml_project.models import User, Workspace, WorkspaceMember

router = APIRouter(prefix="/workspaces", tags=["workspaces"])
def _lock_workspace_for_admin(
    session: Session,
    user: User,
    workspace_id: UUID,
) -> tuple[Workspace, WorkspaceMember]:
    """Lock a workspace and revalidate the acting user's ADMIN role."""
    require_workspace_admin(session, user, workspace_id)

    workspace = session.scalar(
        select(Workspace)
        .where(Workspace.id == workspace_id)
        .with_for_update()
    )

    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")

    session.expire_all()
    membership = require_workspace_admin(session, user, workspace_id)

    return workspace, membership


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


@router.get("/{workspace_id}", response_model=WorkspaceDetailResponse)
def get_workspace(
    workspace_id: UUID,
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> WorkspaceDetailResponse:
    """Return workspace details to an authenticated workspace member."""
    membership = require_workspace_membership(session, user, workspace_id)
    workspace = session.get(Workspace, workspace_id)

    if workspace is None:
        raise HTTPException(
            status_code=404,
            detail="Workspace not found.",
        )

    return WorkspaceDetailResponse(
        workspace_id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        role=membership.role,
    )


@router.get(
    "/{workspace_id}/members",
    response_model=list[WorkspaceMemberResponse],
)
def list_workspace_members(
    workspace_id: UUID,
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[WorkspaceMemberResponse]:
    """List members visible to authenticated workspace members."""
    require_workspace_membership(session, user, workspace_id)

    members = session.execute(
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .order_by(User.full_name, User.email, User.id)
    ).all()

    return [
        WorkspaceMemberResponse(
            membership_id=membership.id,
            user_id=member.id,
            full_name=member.full_name,
            email=member.email,
            role=membership.role,
            created_at=membership.created_at,
        )
        for membership, member in members
    ]

@router.post(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberResponse,
    status_code=201,
)
def add_workspace_member(
    workspace_id: UUID,
    payload: AddWorkspaceMemberRequest,
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> WorkspaceMemberResponse:
    """Add an existing active user to a workspace."""
    _workspace, _membership = _lock_workspace_for_admin(
        session, user, workspace_id
    )

    member_user = session.execute(
        select(User).where(func.lower(User.email) == payload.email)
    ).scalar_one_or_none()

    if member_user is None or not member_user.is_active:
        raise HTTPException(
            status_code=404,
            detail="Active registered user not found.",
        )

    existing_membership = session.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == member_user.id,
        )
    ).scalar_one_or_none()

    if existing_membership is not None:
        raise HTTPException(
            status_code=409,
            detail="User is already a member of this workspace.",
        )

    membership = WorkspaceMember(
        workspace_id=workspace_id,
        user_id=member_user.id,
        role=payload.role,
    )
    session.add(membership)

    record_audit_event(
        session,
        workspace_id=workspace_id,
        actor_id=user.id,
        action="workspace.member.added",
        entity_type="workspace_member",
        entity_id=member_user.id,
        details={
            "email": member_user.email,
            "role": payload.role,
        },
    )

    try:
        session.commit()
        session.refresh(membership)
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="User is already a member of this workspace.",
        )

    return WorkspaceMemberResponse(
        membership_id=membership.id,
        user_id=member_user.id,
        full_name=member_user.full_name,
        email=member_user.email,
        role=membership.role,
        created_at=membership.created_at,
    )


@router.patch(
    "/{workspace_id}",
    response_model=WorkspaceDetailResponse,
)
def update_workspace(
    workspace_id: UUID,
    payload: UpdateWorkspaceRequest,
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> WorkspaceDetailResponse:
    """Update workspace settings. Only ADMIN members are permitted."""
    workspace, membership = _lock_workspace_for_admin(
        session, user, workspace_id
    )

    old_name = workspace.name
    old_slug = workspace.slug
    new_name = payload.name

    if old_name != new_name:
        new_slug = generate_workspace_slug(new_name)

        workspace.name = new_name
        workspace.slug = new_slug

        record_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=user.id,
            action="workspace.updated",
            entity_type="workspace",
            entity_id=workspace_id,
            details={
                "old_name": old_name,
                "new_name": new_name,
                "old_slug": old_slug,
                "new_slug": new_slug,
            },
        )

        session.commit()
        session.refresh(workspace)

    return WorkspaceDetailResponse(
        workspace_id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        role=membership.role,
    )


@router.patch(
    "/{workspace_id}/members/{user_id}",
    response_model=WorkspaceMemberResponse,
)
def update_workspace_member_role(
    workspace_id: UUID,
    user_id: UUID,
    payload: UpdateWorkspaceMemberRoleRequest,
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> WorkspaceMemberResponse:
    """Change a workspace member's role while protecting the last ADMIN."""
    _workspace, _membership = _lock_workspace_for_admin(
        session, user, workspace_id
    )

    membership = session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )

    if membership is None:
        raise HTTPException(
            status_code=404,
            detail="Workspace member not found.",
        )

    target_user = session.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    old_role = membership.role
    new_role = payload.role

    if old_role == new_role:
        return WorkspaceMemberResponse(
            membership_id=membership.id,
            user_id=target_user.id,
            full_name=target_user.full_name,
            email=target_user.email,
            role=membership.role,
            created_at=membership.created_at,
        )

    if old_role == "ADMIN" and new_role == "RECRUITER":
        admin_count = session.scalar(
            select(func.count()).select_from(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.role == "ADMIN",
            )
        )

        if admin_count <= 1:
            raise HTTPException(
                status_code=409,
                detail="The last workspace administrator cannot be demoted.",
            )

    membership.role = new_role

    record_audit_event(
        session,
        workspace_id=workspace_id,
        actor_id=user.id,
        action="workspace.member.role_updated",
        entity_type="workspace_member",
        entity_id=membership.id,
        details={
            "user_id": str(user_id),
            "old_role": old_role,
            "new_role": new_role,
        },
    )

    session.commit()
    session.refresh(membership)

    return WorkspaceMemberResponse(
        membership_id=membership.id,
        user_id=target_user.id,
        full_name=target_user.full_name,
        email=target_user.email,
        role=membership.role,
        created_at=membership.created_at,
    )

@router.delete(
    "/{workspace_id}/members/{user_id}",
    status_code=200,
)
def remove_workspace_member(
    workspace_id: UUID,
    user_id: UUID,
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    """Remove a workspace member while protecting the last ADMIN."""
    _workspace, _membership = _lock_workspace_for_admin(
        session, user, workspace_id
    )

    membership = session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )

    if membership is None:
        raise HTTPException(
            status_code=404,
            detail="Workspace member not found.",
        )

    if membership.role == "ADMIN":
        admin_count = session.scalar(
            select(func.count()).select_from(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.role == "ADMIN",
            )
        )

        if admin_count <= 1:
            raise HTTPException(
                status_code=409,
                detail="The last workspace administrator cannot be removed.",
            )

    membership_id = membership.id
    member_role = membership.role
    target_user = session.get(User, user_id)
    member_email = target_user.email if target_user else None

    record_audit_event(
        session,
        workspace_id=workspace_id,
        actor_id=user.id,
        action="workspace.member.removed",
        entity_type="workspace_member",
        entity_id=membership_id,
        details={
            "user_id": str(user_id),
            "email": member_email,
            "role": member_role,
        },
    )

    session.delete(membership)

    try:
        session.commit()
    except Exception:
        session.rollback()
        raise

    return {"message": "Workspace member removed."}
