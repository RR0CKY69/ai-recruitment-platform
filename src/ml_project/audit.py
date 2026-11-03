"""Small audit logging helpers for workspace-scoped mutations."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from ml_project.models import AuditLog


def record_audit_event(
    session: Session,
    *,
    workspace_id: UUID,
    actor_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    event = AuditLog(
        workspace_id=workspace_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details or {},
    )
    session.add(event)
    return event
