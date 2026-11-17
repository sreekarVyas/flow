from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

ACCOUNT_TYPES = ("bank", "credit_card")
DIRECTIONS = ("debit", "credit")
KINDS = ("expense", "transfer", "settlement", "income", "refund")
PARSE_STATUSES = ("txn", "ignored", "unknown")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("institution", "type", "last4", name="uq_accounts_institution_type_last4"),
        CheckConstraint(_in("type", ACCOUNT_TYPES), name="ck_accounts_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20))
    institution: Mapped[str] = mapped_column(String(50))
    last4: Mapped[str] = mapped_column(String(4))


class RawEmail(Base):
    __tablename__ = "raw_emails"
    __table_args__ = (
        CheckConstraint(_in("parse_status", PARSE_STATUSES), name="ck_raw_emails_parse_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    gmail_msg_id: Mapped[str] = mapped_column(String(64), unique=True)
    thread_id: Mapped[str | None] = mapped_column(String(64))
    history_id: Mapped[int | None] = mapped_column(BigInteger)
    sender: Mapped[str] = mapped_column(String(255), index=True)
    subject: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    body_text: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    parse_status: Mapped[str] = mapped_column(String(16), default="unknown", index=True)
    parser_name: Mapped[str | None] = mapped_column(String(64))
    parse_error: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    transaction: Mapped["Transaction | None"] = relationship(back_populates="raw_email")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint(_in("direction", DIRECTIONS), name="ck_transactions_direction"),
        CheckConstraint(f"kind IS NULL OR {_in('kind', KINDS)}", name="ck_transactions_kind"),
        CheckConstraint(
            "category_source IS NULL OR category_source IN ('rule', 'llm', 'manual')",
            name="ck_transactions_category_source",
        ),
        CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    raw_email_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_emails.id", ondelete="SET NULL"), unique=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    direction: Mapped[str] = mapped_column(String(6))
    kind: Mapped[str | None] = mapped_column(String(16))
    counterparty_name: Mapped[str | None] = mapped_column(String(255))
    vpa_or_merchant: Mapped[str | None] = mapped_column(String(255))
    ref_no: Mapped[str | None] = mapped_column(String(64))
    parse_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    # No FK yet: the categories table comes in Phase 2.
    category_id: Mapped[int | None] = mapped_column()
    category_source: Mapped[str | None] = mapped_column(String(8))
    confirmed: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped[Account] = relationship()
    raw_email: Mapped[RawEmail | None] = relationship(back_populates="transaction")


class GmailState(Base):
    __tablename__ = "gmail_state"
    __table_args__ = (CheckConstraint("id = 1", name="ck_gmail_state_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    last_history_id: Mapped[int | None] = mapped_column(BigInteger)
    last_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_poll_result: Mapped[dict | None] = mapped_column(JSONB)
    watch_expiration: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
