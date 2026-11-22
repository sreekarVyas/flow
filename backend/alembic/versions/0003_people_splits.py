"""people + splits

Revision ID: 0003_people_splits
Revises: 0002_categories_rules
Create Date: 2026-11-22

people.name_key is lower case with single spaces, so "John", "JOHN" and " john " are one person.
splits.paid_by: 'me' = the person owes me the share; 'person' = I owe the person (used by friend-paid expenses later).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_people_splits"
down_revision: str | None = "0002_categories_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "people",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("name_key", sa.String(100), nullable=False, unique=True),
        sa.Column(
            "match_names", postgresql.ARRAY(sa.String(255)), server_default="{}", nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("name_key = lower(name_key) AND name_key <> ''", name="ck_people_name_key"),
    )

    op.create_table(
        "splits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "transaction_id", sa.Integer(), sa.ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("people.id"), nullable=False),
        sa.Column("share_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("paid_by", sa.String(6), server_default="me", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("transaction_id", "person_id", name="uq_splits_transaction_person"),
        sa.CheckConstraint("share_amount > 0", name="ck_splits_share_positive"),
        sa.CheckConstraint("paid_by IN ('me', 'person')", name="ck_splits_paid_by"),
    )
    op.create_index("ix_splits_transaction_id", "splits", ["transaction_id"])
    op.create_index("ix_splits_person_id", "splits", ["person_id"])


def downgrade() -> None:
    op.drop_index("ix_splits_person_id", table_name="splits")
    op.drop_index("ix_splits_transaction_id", table_name="splits")
    op.drop_table("splits")
    op.drop_table("people")
