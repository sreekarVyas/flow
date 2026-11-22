from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Kind = Literal["expense", "transfer", "settlement", "income", "refund"]

# Decimal fields serialize to JSON strings ("336.00"), so no float rounding.


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    type: str
    institution: str
    last4: str


class PersonRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    display_name: str


class TxnBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ts: datetime
    amount: Decimal
    direction: str
    counterparty_name: str | None
    vpa_or_merchant: str | None


class LinkFromSettlement(BaseModel):
    """On a share: one repayment applied to it."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    amount: Decimal
    settles: bool  # False = money returned to them (re-opens the share)
    settlement: TxnBrief


class SplitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    person: PersonRef
    share_amount: Decimal
    paid_by: str
    origin: str
    settled: Decimal
    outstanding: Decimal  # negative = overpaid
    links: list[LinkFromSettlement] = []


class SplitBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    share_amount: Decimal
    outstanding: Decimal
    transaction: TxnBrief


class LinkToShare(BaseModel):
    """On a repayment: one share it is applied to."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    amount: Decimal
    settles: bool
    split: SplitBrief


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ts: datetime
    amount: Decimal
    direction: str
    kind: str | None
    counterparty_name: str | None
    vpa_or_merchant: str | None
    ref_no: str | None
    parse_confidence: Decimal | None
    category_id: int | None
    category_source: str | None
    confirmed: bool
    notes: str | None
    account: AccountOut
    splits: list[SplitOut] = []
    my_share: Decimal  # amount minus other people's shares
    person: PersonRef | None = None  # settlements: who it is from / to
    links_out: list[LinkToShare] = []  # settlements: the shares it pays
    unapplied: Decimal  # settlements: part not tagged to any payment


class SettlementLinkIn(BaseModel):
    transaction_id: int  # the earlier payment
    amount: Decimal = Field(gt=0)
    share: Decimal | None = Field(default=None, gt=0)  # only when that person has no share on it yet


class SettlementRequest(BaseModel):
    """Mark a transaction as a repayment from / to a person and tag it to earlier payments."""

    person_id: int | None = None
    name: str | None = Field(default=None, max_length=100)
    nickname: str | None = Field(default=None, max_length=100)  # for the payment source; same as name
    links: list[SettlementLinkIn] = Field(default=[], max_length=50)


class RepaymentRequest(BaseModel):
    """From the original payment: tag a repayment transaction against it."""

    settlement_txn_id: int
    amount: Decimal = Field(gt=0)
    person_id: int | None = None  # needed when the repayment has no person yet
    name: str | None = Field(default=None, max_length=100)
    nickname: str | None = Field(default=None, max_length=100)  # for the repayment's payment source
    share: Decimal | None = Field(default=None, gt=0)


class SourceOut(BaseModel):
    """The other side of a transaction as the bank prints it, and its nickname."""

    printed_name: str | None
    vpa: str | None
    person: PersonRef | None  # known nickname, or the best guess
    known: bool  # this exact name + UPI ID already has this nickname
    suggestion: str  # prefill for the nickname field


class PaymentSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    printed_name: str | None
    vpa: str


class MergeRequest(BaseModel):
    into_id: int


class SettleCandidate(BaseModel):
    transaction: "TransactionOut"
    share: SplitBrief | None  # the person's share on it, if any
    linked_amount: Decimal  # already tagged from this repayment


class SettleCandidatesOut(BaseModel):
    suggested_person: PersonRef | None
    items: list[SettleCandidate]


class RepaymentCandidate(BaseModel):
    transaction: "TransactionOut"
    linked_amount: Decimal  # already tagged to this payment


class RepaymentCandidatesOut(BaseModel):
    items: list[RepaymentCandidate]


class SplitPerson(BaseModel):
    """Name an existing person by id, or by name (found without regard to case, created if new)."""

    person_id: int | None = None
    name: str | None = Field(default=None, max_length=100)
    value: Decimal | None = Field(default=None, gt=0)  # rupees (exact) or percent; unused for equal


class SplitRequest(BaseModel):
    mode: Literal["equal", "exact", "percent"] = "equal"
    include_me: bool = True  # equal mode: do I take a share too?
    people: list[SplitPerson] = Field(default=[], max_length=20)


class PersonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class PersonUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


class PersonOut(BaseModel):
    id: int
    display_name: str
    owed_to_me: Decimal  # their shares of my expenses
    i_owe: Decimal
    received: Decimal
    paid: Decimal
    net: Decimal  # + they owe me, - I owe them
    shares: int


class PersonShare(BaseModel):
    split_id: int
    share_amount: Decimal
    settled: Decimal
    outstanding: Decimal  # negative = overpaid
    paid_by: str
    transaction: TransactionOut


class PersonDetail(PersonOut):
    match_names: list[str]
    history: list[PersonShare]
    repayments: list[TransactionOut]  # settlements from / to them, newest first
    sources: list[PaymentSourceOut]  # UPI IDs nicknamed as this person


class TransactionPatch(BaseModel):
    """Only the fields sent are changed. An empty body confirms the transaction as it is."""

    kind: Kind | None = None
    category_id: int | None = None
    notes: str | None = Field(default=None, max_length=280)  # a short comment
    apply_to_similar: bool = False


class SimilarOut(BaseModel):
    payee: str | None
    count: int
    learns_rule: bool  # a manual tag saves a rule for future payments (debits only)


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    parent_id: int | None
    icon: str | None
    sort_order: int
    archived: bool
    children: list["CategoryOut"] = []


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    parent_id: int | None = None
    icon: str | None = Field(default=None, max_length=16)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    icon: str | None = Field(default=None, max_length=16)
    archived: bool | None = None


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    match_field: str
    match_value: str
    direction: str | None
    category_id: int | None
    kind: str | None
    source: str
    created_at: datetime


class TransactionPatchOut(BaseModel):
    transaction: TransactionOut
    updated_similar: int
    rule: RuleOut | None


class CategorySpend(BaseModel):
    id: int
    name: str
    icon: str | None
    total: Decimal  # my share of expense debits - refund credits
    count: int


class ParentSpend(CategorySpend):
    own_total: Decimal  # tagged with the parent itself, not a child
    children: list[CategorySpend]


class CategorySummaryOut(BaseModel):
    month: str
    total: Decimal  # my spend: my share of all expense debits - refund credits
    untagged_total: Decimal
    untagged_count: int
    parents: list[ParentSpend]


class TypeTotals(BaseModel):
    debit_total: Decimal = Decimal("0")
    debit_count: int = 0
    credit_total: Decimal = Decimal("0")
    credit_count: int = 0
    expense_total: Decimal = Decimal("0")  # debits with kind = expense, full amounts
    my_share_total: Decimal = Decimal("0")  # the same debits, my share only
    transfer_total: Decimal = Decimal("0")


class SharedTotals(BaseModel):
    others_share: Decimal = Decimal("0")  # this month: what others owe on my expenses
    recovered: Decimal = Decimal("0")  # this month's shared expenses: net repaid so far
    owed_to_me: Decimal = Decimal("0")  # all time: sum of positive person balances
    i_owe: Decimal = Decimal("0")  # all time: sum of negative person balances, as a positive number
    people_owing: int = 0


class SummaryOut(BaseModel):
    month: str
    bank: TypeTotals
    credit_card: TypeTotals
    shared: SharedTotals
    unknown_emails: int
    last_poll_at: datetime | None
    last_poll_result: dict | None


class RawEmailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sender: str
    subject: str
    received_at: datetime
    parse_status: str
    parser_name: str | None
    parse_error: str | None
