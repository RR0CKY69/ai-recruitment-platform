"""add index on refresh session token_hash

Revision ID: ebf570f17769
Revises: 3c5e7a1b2d4f
Create Date: 2026-11-01 18:11:40.529985
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = 'ebf570f17769'
down_revision: Union[str, None] = '3c5e7a1b2d4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_refresh_sessions_token_hash", "refresh_sessions", ["token_hash"])


def downgrade() -> None:
    op.drop_index("ix_refresh_sessions_token_hash", table_name="refresh_sessions")
