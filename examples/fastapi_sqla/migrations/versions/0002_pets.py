"""create pets table

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-31 12:01:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("owners.id"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("species", sa.String(length=50), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("pets")
