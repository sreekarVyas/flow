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
    false,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

ACCOUNT_TYPES = ("bank", "credit_card")
DIRECTIONS = ("debit", "credit")
KINDS = ("expense", "transfer", "settlement", "income", "refund")
PARSE_STATUSES = ("txn", "ignored", "unknown")
MATCH_FIELDS = ("payee", "name_contains", "vpa_contains")
RULE_SOURCES = ("seed", "learned")
PAID_BY = ("me", "person")
SPLIT_ORIGINS = ("manual", "link")


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


class Category(Base):
    """Two levels: a parent (parent_id NULL) and its children."""

    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint(
            "parent_id", "name", name="uq_categories_parent_name", postgresql_nulls_not_distinct=True
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), index=True)
    icon: Mapped[str | None] = mapped_column(String(16))
    sort_order: Mapped[int] = mapped_column(server_default="0", default=0)
    archived: Mapped[bool] = mapped_column(server_default=false(), default=False)
    is_seed: Mapped[bool] = mapped_column(server_default=false(), default=False)


class Rule(Base):
    """payee: exact normalized payee name (learned from manual tags).
    name_contains / vpa_contains: substring of the payee name / VPA (seed rules). Longest match wins.
    """

    __tablename__ = "rules"
    __table_args__ = (
        UniqueConstraint(
            "match_field", "match_value", "direction", name="uq_rules_match", postgresql_nulls_not_distinct=True
        ),
        CheckConstraint(_in("match_field", MATCH_FIELDS), name="ck_rules_match_field"),
        CheckConstraint(_in("source", RULE_SOURCES), name="ck_rules_source"),
        CheckConstraint(f"direction IS NULL OR {_in('direction', DIRECTIONS)}", name="ck_rules_direction"),
        CheckConstraint(f"kind IS NULL OR {_in('kind', KINDS)}", name="ck_rules_kind"),
        CheckConstraint("category_id IS NOT NULL OR kind IS NOT NULL", name="ck_rules_has_action"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_field: Mapped[str] = mapped_column(String(16))
    match_value: Mapped[str] = mapped_column(String(255))
    direction: Mapped[str | None] = mapped_column(String(6))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str | None] = mapped_column(String(16))
    priority: Mapped[int] = mapped_column(server_default="0", default=0)
    source: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    category: Mapped[Category | None] = relationship()


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
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    category_source: Mapped[str | None] = mapped_column(String(8))
    confirmed: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped[Account] = relationship()
    raw_email: Mapped[RawEmail | None] = relationship(back_populates="transaction")
    # Settlements only: who the repayment is from (credit) or to (debit).
    person_id: Mapped[int | None] = mapped_column(ForeignKey("people.id"), index=True)

    splits: Mapped[list["Split"]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan", passive_deletes=True, order_by="Split.id"
    )
    person: Mapped["Person | None"] = relationship()
    # Settlements only: the shares this repayment is applied to.
    links_out: Mapped[list["SettlementLink"]] = relationship(
        back_populates="settlement", cascade="all, delete-orphan", passive_deletes=True,
        order_by="SettlementLink.id",
    )

    @property
    def applied(self) -> Decimal:
        return sum((link.amount for link in self.links_out), Decimal("0"))

    @property
    def unapplied(self) -> Decimal:
        """Settlements only: the part of the repayment not linked to any share yet."""
        return self.amount - self.applied if self.kind == "settlement" else Decimal("0")

    @property
    def my_share(self) -> Decimal:
        """Amount minus the shares other people owe me. Splits must be loaded."""
        return self.amount - sum((s.share_amount for s in self.splits if s.paid_by == "me"), Decimal("0"))


class Person(Base):
    __tablename__ = "people"
    __table_args__ = (
        CheckConstraint("name_key = lower(name_key) AND name_key <> ''", name="ck_people_name_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100))
    name_key: Mapped[str] = mapped_column(String(100), unique=True)
    # Names the bank prints for this person (e.g. "A B NAME"), for repayment suggestions.
    match_names: Mapped[list[str]] = mapped_column(ARRAY(String(255)), server_default="{}", default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaymentSource(Base):
    """One payment source as the bank prints it (name + UPI ID), nicknamed as a person."""

    __tablename__ = "payment_sources"
    __table_args__ = (
        UniqueConstraint("name_key", "vpa", name="uq_payment_sources_name_vpa"),
        CheckConstraint("name_key <> '' OR vpa <> ''", name="ck_payment_sources_not_empty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name_key: Mapped[str] = mapped_column(String(255), index=True)
    vpa: Mapped[str] = mapped_column(String(255))
    printed_name: Mapped[str | None] = mapped_column(String(255))
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    person: Mapped[Person] = relationship()


class Split(Base):
    """paid_by = me: the person owes me share_amount. paid_by = person: I owe them."""

    __tablename__ = "splits"
    __table_args__ = (
        UniqueConstraint("transaction_id", "person_id", name="uq_splits_transaction_person"),
        CheckConstraint("share_amount > 0", name="ck_splits_share_positive"),
        CheckConstraint(_in("paid_by", PAID_BY), name="ck_splits_paid_by"),
        CheckConstraint(_in("origin", SPLIT_ORIGINS), name="ck_splits_origin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), index=True)
    share_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    paid_by: Mapped[str] = mapped_column(String(6), server_default="me", default="me")
    origin: Mapped[str] = mapped_column(String(6), server_default="manual", default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    transaction: Mapped[Transaction] = relationship(back_populates="splits")
    person: Mapped[Person] = relationship()
    links: Mapped[list["SettlementLink"]] = relationship(
        back_populates="split", cascade="all, delete-orphan", passive_deletes=True, order_by="SettlementLink.id"
    )

    @property
    def settled(self) -> Decimal:
        """Net repaid on this share. Can exceed the share (an overpayment not yet returned)."""
        return sum((link.signed for link in self.links), Decimal("0"))

    @property
    def outstanding(self) -> Decimal:
        """Still owed on this share. Negative = overpaid (money to return)."""
        return self.share_amount - self.settled


class SettlementLink(Base):
    """`amount` of a settlement transaction applied to one share.

    The direction of the settlement decides the effect. On a share the person owes me (paid_by = me),
    their credit settles it and my debit to them (returning an overpayment) re-opens it.
    """

    __tablename__ = "settlement_links"
    __table_args__ = (
        UniqueConstraint("settlement_txn_id", "split_id", name="uq_settlement_links_txn_split"),
        CheckConstraint("amount > 0", name="ck_settlement_links_amount_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    settlement_txn_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), index=True)
    split_id: Mapped[int] = mapped_column(ForeignKey("splits.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    settlement: Mapped[Transaction] = relationship(back_populates="links_out")
    split: Mapped[Split] = relationship(back_populates="links")

    @property
    def settles(self) -> bool:
        """True when this link reduces what is owed on the share."""
        return (self.split.paid_by == "me") == (self.settlement.direction == "credit")

    @property
    def signed(self) -> Decimal:
        return self.amount if self.settles else -self.amount


class GmailState(Base):
    __tablename__ = "gmail_state"
    __table_args__ = (CheckConstraint("id = 1", name="ck_gmail_state_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    last_history_id: Mapped[int | None] = mapped_column(BigInteger)
    last_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_poll_result: Mapped[dict | None] = mapped_column(JSONB)
    watch_expiration: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
