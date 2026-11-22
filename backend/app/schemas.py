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


class SplitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    person: PersonRef
    share_amount: Decimal
    paid_by: str


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
    paid_by: str
    transaction: TransactionOut


class PersonDetail(PersonOut):
    match_names: list[str]
    history: list[PersonShare]


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
