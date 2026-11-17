"""init: accounts, raw_emails, transactions, gmail_state

Revision ID: 0001_init
Revises:
Create Date: 2026-11-17
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_init"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("institution", sa.String(50), nullable=False),
        sa.Column("last4", sa.String(4), nullable=False),
        sa.UniqueConstraint("institution", "type", "last4", name="uq_accounts_institution_type_last4"),
        sa.CheckConstraint("type IN ('bank', 'credit_card')", name="ck_accounts_type"),
    )

    op.create_table(
        "raw_emails",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("gmail_msg_id", sa.String(64), nullable=False, unique=True),
        sa.Column("thread_id", sa.String(64), nullable=True),
        sa.Column("history_id", sa.BigInteger(), nullable=True),
        sa.Column("sender", sa.String(255), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("parse_status", sa.String(16), nullable=False),
        sa.Column("parser_name", sa.String(64), nullable=True),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "parse_status IN ('txn', 'ignored', 'unknown')", name="ck_raw_emails_parse_status"
        ),
    )
    op.create_index("ix_raw_emails_sender", "raw_emails", ["sender"])
    op.create_index("ix_raw_emails_received_at", "raw_emails", ["received_at"])
    op.create_index("ix_raw_emails_parse_status", "raw_emails", ["parse_status"])

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column(
            "raw_email_id",
            sa.Integer(),
            sa.ForeignKey("raw_emails.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
        ),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("direction", sa.String(6), nullable=False),
        sa.Column("kind", sa.String(16), nullable=True),
        sa.Column("counterparty_name", sa.String(255), nullable=True),
        sa.Column("vpa_or_merchant", sa.String(255), nullable=True),
        sa.Column("ref_no", sa.String(64), nullable=True),
        sa.Column("parse_confidence", sa.Numeric(3, 2), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("category_source", sa.String(8), nullable=True),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("direction IN ('debit', 'credit')", name="ck_transactions_direction"),
        sa.CheckConstraint(
            "kind IS NULL OR kind IN ('expense', 'transfer', 'settlement', 'income', 'refund')",
            name="ck_transactions_kind",
        ),
        sa.CheckConstraint(
            "category_source IS NULL OR category_source IN ('rule', 'llm', 'manual')",
            name="ck_transactions_category_source",
        ),
        sa.CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
    )
    op.create_index("ix_transactions_account_id", "transactions", ["account_id"])
    op.create_index("ix_transactions_ts", "transactions", ["ts"])

    op.create_table(
        "gmail_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_history_id", sa.BigInteger(), nullable=True),
        sa.Column("last_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_poll_result", postgresql.JSONB(), nullable=True),
        sa.Column("watch_expiration", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_gmail_state_singleton"),
    )


def downgrade() -> None:
    op.drop_table("gmail_state")
    op.drop_index("ix_transactions_ts", table_name="transactions")
    op.drop_index("ix_transactions_account_id", table_name="transactions")
    op.drop_table("transactions")
    op.drop_index("ix_raw_emails_parse_status", table_name="raw_emails")
    op.drop_index("ix_raw_emails_received_at", table_name="raw_emails")
    op.drop_index("ix_raw_emails_sender", table_name="raw_emails")
    op.drop_table("raw_emails")
    op.drop_table("accounts")
