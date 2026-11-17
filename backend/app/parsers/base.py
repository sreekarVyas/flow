"""Parser framework.

Each email gets one status:
  txn      a transaction parser matched and extracted all required fields
  ignored  a known non-transaction pattern matched (OTP, login alert, offer, ...)
  unknown  nothing matched; shown in the "needs a parser" list

Transaction parsers always run first, so an ignore rule can never hide a transaction.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from collections.abc import Sequence
from typing import Literal, Protocol

Status = Literal["txn", "ignored", "unknown"]


@dataclass(frozen=True)
class EmailInput:
    sender: str
    subject: str
    body_text: str
    received_at: datetime | None = None  # for alerts that carry no date


@dataclass
class ParsedTxn:
    institution: str  # e.g. "HDFC", "SBI Card"
    account_type: Literal["bank", "credit_card"]
    last4: str
    amount: Decimal
    direction: Literal["debit", "credit"]
    txn_date: date
    txn_time: time | None = None
    counterparty_name: str | None = None
    vpa_or_merchant: str | None = None
    ref_no: str | None = None
    confidence: Decimal = Decimal("1.00")

    def __post_init__(self) -> None:
        if not re.fullmatch(r"\d{4}", self.last4):
            raise ValueError(f"last4 must be 4 digits, got {self.last4!r}")
        if self.amount <= 0:
            raise ValueError(f"amount must be positive, got {self.amount}")


class TxnParser(Protocol):
    name: str
    senders: tuple[str, ...]

    def parse(self, email: EmailInput) -> ParsedTxn | None:
        """Return a ParsedTxn, or None if this email is not this parser's format."""


@dataclass(frozen=True)
class IgnoreRule:
    name: str
    senders: tuple[str, ...]
    subject: re.Pattern[str] | None = None
    body: re.Pattern[str] | None = None

    def matches(self, email: EmailInput) -> bool:
        if email.sender not in self.senders:
            return False
        if self.subject and not self.subject.search(email.subject):
            return False
        if self.body and not self.body.search(email.body_text):
            return False
        return bool(self.subject or self.body)


@dataclass
class ClassifyResult:
    status: Status
    parser_name: str | None = None
    txn: ParsedTxn | None = None
    error: str | None = None


# Money moved. If an email says this, an ignore rule must not swallow it.
_TXN_WORDS = re.compile(r"\b(debited|credited|spent|withdrawn|charged|deducted)\b", re.I)
_AMOUNT = re.compile(r"(?:rs\.?|inr|₹)\s?[\d,]+(?:\.\d{1,2})?", re.I)


def looks_like_txn(email: EmailInput) -> bool:
    text = f"{email.subject}\n{email.body_text}"
    return bool(_TXN_WORDS.search(text) and _AMOUNT.search(text))


def classify(
    email: EmailInput, parsers: list[TxnParser], ignore_rules: list[IgnoreRule]
) -> ClassifyResult:
    errors: list[str] = []
    for p in parsers:
        if email.sender not in p.senders:
            continue
        try:
            txn = p.parse(email)
        except (ValueError, InvalidOperation) as e:
            errors.append(f"{p.name}: {e}")
            continue
        if txn is not None:
            return ClassifyResult("txn", p.name, txn)

    error = "; ".join(errors) or None
    if not looks_like_txn(email):
        for rule in ignore_rules:
            if rule.matches(email):
                return ClassifyResult("ignored", rule.name, error=error)
    return ClassifyResult("unknown", error=error)


# ---------- helpers for parsers ----------


def to_amount(s: str) -> Decimal:
    return Decimal(s.replace(",", "").strip())


def squash(text: str) -> str:
    """Collapse all whitespace to single spaces. Parsers match on this."""
    return re.sub(r"\s+", " ", text).strip()


# ---------- kind inference (CLAUDE.md §8 seed patterns) ----------


def infer_kind(
    p: ParsedTxn, self_names: Sequence[str] = (), salary_payers: Sequence[str] = ()
) -> str | None:
    """`self_names` / `salary_payers` come from settings (.env), so personal data stays out of code."""
    text = " ".join(filter(None, [p.counterparty_name, p.vpa_or_merchant])).upper()
    if p.account_type == "bank":
        if p.direction == "debit":
            # Card bill: via CRED (VPA cred.club@axisb; HDFC masks it to ****club@axisb)
            # or via HDFC NetBanking. Plain "CRED" with ...lity@axisb is a utility bill: an expense.
            if "CRED CLUB" in text or "CLUB@AXISB" in text or "CREDIT CARD BILL" in text:
                return "transfer"
            if any(n.upper() in text for n in self_names):
                return "transfer"  # to my own account
            return "expense"
        if "SALARY" in text or any(n.upper() in text for n in salary_payers):
            return "income"
        return None  # credit: settlement / pass-through / refund -> review
    # credit card
    if p.direction == "debit":
        return "expense"
    return None  # card credit: bill payment or refund -> review
