"""payment_sources: a nickname for each payment source (bank-printed name + UPI ID)

Revision ID: 0005_payment_sources
Revises: 0004_settlements
Create Date: 2026-11-22

A source is one (name, UPI ID) pair as the bank prints it. Its nickname is a person, so two UPI IDs
nicknamed "Prajwala" (case does not matter) are one person.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_payment_sources"
down_revision: str | None = "0004_settlements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name_key", sa.String(255), nullable=False),  # upper case, single spaces; '' if none
        sa.Column("vpa", sa.String(255), nullable=False),  # upper case as printed (masked); '' if none
        sa.Column("printed_name", sa.String(255), nullable=True),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("people.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name_key", "vpa", name="uq_payment_sources_name_vpa"),
        sa.CheckConstraint("name_key <> '' OR vpa <> ''", name="ck_payment_sources_not_empty"),
    )
    op.create_index("ix_payment_sources_person_id", "payment_sources", ["person_id"])
    op.create_index("ix_payment_sources_name_key", "payment_sources", ["name_key"])


def downgrade() -> None:
    op.drop_index("ix_payment_sources_name_key", table_name="payment_sources")
    op.drop_index("ix_payment_sources_person_id", table_name="payment_sources")
    op.drop_table("payment_sources")
