"""Add workspace-scoped unique legacy identifiers.

Revision ID: 2b4d7f0a91c3
Revises: 0073db67417d
Create Date: 2026-10-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2b4d7f0a91c3"
down_revision: str | None = "0073db67417d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _restore_candidate_email_index_if_sqlite(bind=None) -> None:
    bind = bind or op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    index_exists = bind.exec_driver_sql(
        "SELECT 1 FROM sqlite_master WHERE type = 'index' "
        "AND name = 'uq_candidates_workspace_email_ci'"
    ).scalar_one_or_none()
    if index_exists is None:
        op.create_index(
            "uq_candidates_workspace_email_ci",
            "candidates",
            ["workspace_id", sa.text("lower(email)")],
            unique=True,
            postgresql_where=sa.text("email IS NOT NULL"),
            sqlite_where=sa.text("email IS NOT NULL"),
        )


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.create_unique_constraint(
            "uq_jobs_workspace_legacy_job_id", ["workspace_id", "legacy_job_id"]
        )
    with op.batch_alter_table("candidates") as batch_op:
        batch_op.create_unique_constraint(
            "uq_candidates_workspace_legacy_candidate_id",
            ["workspace_id", "legacy_candidate_id"],
        )
    _restore_candidate_email_index_if_sqlite()


def downgrade() -> None:
    with op.batch_alter_table("candidates") as batch_op:
        batch_op.drop_constraint("uq_candidates_workspace_legacy_candidate_id", type_="unique")
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_constraint("uq_jobs_workspace_legacy_job_id", type_="unique")
    _restore_candidate_email_index_if_sqlite()
