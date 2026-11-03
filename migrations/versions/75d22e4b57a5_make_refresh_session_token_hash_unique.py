"""make refresh session token_hash unique

Revision ID: 75d22e4b57a5
Revises: ebf570f17769
Create Date: 2026-11-01 18:17:20.958997
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = '75d22e4b57a5'
down_revision: Union[str, None] = 'ebf570f17769'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM refresh_sessions
        WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (PARTITION BY token_hash ORDER BY created_at) as rn
                FROM refresh_sessions
            ) t WHERE t.rn > 1
        )
        """
    )
    try:
        op.drop_index("ix_refresh_sessions_token_hash", table_name="refresh_sessions")
    except Exception:
        pass
    op.create_index("uq_refresh_sessions_token_hash", "refresh_sessions", ["token_hash"], unique=True)


def downgrade() -> None:
    try:
        op.drop_index("uq_refresh_sessions_token_hash", table_name="refresh_sessions")
    except Exception:
        pass
    op.create_index("ix_refresh_sessions_token_hash", "refresh_sessions", ["token_hash"])
