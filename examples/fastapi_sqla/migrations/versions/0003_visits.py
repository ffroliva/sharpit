"""create visits table

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-31 12:02:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "visits",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("pet_id", sa.Integer(), sa.ForeignKey("pets.id"), nullable=False),
        sa.Column("visit_date", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("visits")
