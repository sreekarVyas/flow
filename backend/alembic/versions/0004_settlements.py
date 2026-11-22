"""settlements: repayments linked to the shares they settle

Revision ID: 0004_settlements
Revises: 0003_people_splits
Create Date: 2026-11-22

transactions.person_id  — who a settlement (repayment) is from / to.
settlement_links        — part of a settlement applied to one share (split). One repayment can be
                          spread over many shares; one share can be settled by many repayments.
splits.origin           — 'link' when the share was created by linking a repayment to a payment that
                          was not split yet; such a share goes away with its last link.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_settlements"
down_revision: str | None = "0003_people_splits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("person_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_transactions_person_id", "transactions", "people", ["person_id"], ["id"])
    op.create_index("ix_transactions_person_id", "transactions", ["person_id"])

    op.add_column("splits", sa.Column("origin", sa.String(6), server_default="manual", nullable=False))
    op.create_check_constraint("ck_splits_origin", "splits", "origin IN ('manual', 'link')")

    op.create_table(
        "settlement_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "settlement_txn_id", sa.Integer(), sa.ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("split_id", sa.Integer(), sa.ForeignKey("splits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("settlement_txn_id", "split_id", name="uq_settlement_links_txn_split"),
        sa.CheckConstraint("amount > 0", name="ck_settlement_links_amount_positive"),
    )
    op.create_index("ix_settlement_links_settlement_txn_id", "settlement_links", ["settlement_txn_id"])
    op.create_index("ix_settlement_links_split_id", "settlement_links", ["split_id"])


def downgrade() -> None:
    op.drop_index("ix_settlement_links_split_id", table_name="settlement_links")
    op.drop_index("ix_settlement_links_settlement_txn_id", table_name="settlement_links")
    op.drop_table("settlement_links")
    op.drop_constraint("ck_splits_origin", "splits", type_="check")
    op.drop_column("splits", "origin")
    op.drop_index("ix_transactions_person_id", table_name="transactions")
    op.drop_constraint("fk_transactions_person_id", "transactions", type_="foreignkey")
    op.drop_column("transactions", "person_id")
