"""richieste di ricarica crediti

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "credit_topup_requests",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("firm_id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(length=32), nullable=True),
        sa.CheckConstraint("credits > 0"),
        sa.ForeignKeyConstraint(["firm_id"], ["law_firms.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_credit_topup_requests_firm_id", "credit_topup_requests", ["firm_id"])


def downgrade() -> None:
    op.drop_index("ix_credit_topup_requests_firm_id", table_name="credit_topup_requests")
    op.drop_table("credit_topup_requests")
