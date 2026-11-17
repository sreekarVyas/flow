from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

# Decimal fields serialize to JSON strings ("336.00"), so no float rounding.


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    type: str
    institution: str
    last4: str


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
    confirmed: bool
    account: AccountOut


class TypeTotals(BaseModel):
    debit_total: Decimal = Decimal("0")
    debit_count: int = 0
    credit_total: Decimal = Decimal("0")
    credit_count: int = 0
    expense_total: Decimal = Decimal("0")  # debits with kind = expense (not my share yet)
    transfer_total: Decimal = Decimal("0")


class SummaryOut(BaseModel):
    month: str
    bank: TypeTotals
    credit_card: TypeTotals
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
