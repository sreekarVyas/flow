"""Turn a stored raw email into (at most) one transaction. Used by poll and reparse."""

from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, RawEmail, Transaction
from app.parsers import classify_email
from app.config import settings
from app.parsers.base import EmailInput, ParsedTxn, infer_kind


def account_name(institution: str, account_type: str, last4: str) -> str:
    suffix = " Card" if account_type == "credit_card" and "card" not in institution.lower() else ""
    return f"{institution}{suffix} ••{last4}"


def get_or_create_account(session: Session, p: ParsedTxn) -> Account:
    acc = session.scalar(
        select(Account).where(
            Account.institution == p.institution,
            Account.type == p.account_type,
            Account.last4 == p.last4,
        )
    )
    if acc is None:
        acc = Account(
            name=account_name(p.institution, p.account_type, p.last4),
            type=p.account_type,
            institution=p.institution,
            last4=p.last4,
        )
        session.add(acc)
        session.flush()
    return acc


def resolve_ts(p: ParsedTxn, received_at: datetime, tz: ZoneInfo) -> datetime:
    """Most alerts give a date but no time. Use the email time when it is the same day."""
    if p.txn_time is not None:
        return datetime.combine(p.txn_date, p.txn_time, tz)
    if received_at.astimezone(tz).date() == p.txn_date:
        return received_at
    return datetime.combine(p.txn_date, time(0), tz)


def apply_classification(session: Session, raw: RawEmail, tz: ZoneInfo) -> str:
    """Classify `raw`, and create, update or remove its transaction. Returns the status."""
    result = classify_email(EmailInput(raw.sender, raw.subject or "", raw.body_text or "", raw.received_at))
    raw.parse_status = result.status
    raw.parser_name = result.parser_name
    raw.parse_error = result.error

    existing = session.scalar(select(Transaction).where(Transaction.raw_email_id == raw.id))

    if result.status == "txn":
        p = result.txn
        assert p is not None
        fields = dict(
            account_id=get_or_create_account(session, p).id,
            ts=resolve_ts(p, raw.received_at, tz),
            amount=p.amount,
            direction=p.direction,
            kind=infer_kind(p, settings.self_names, settings.salary_payers),
            counterparty_name=p.counterparty_name,
            vpa_or_merchant=p.vpa_or_merchant,
            ref_no=p.ref_no,
            parse_confidence=p.confidence,
        )
        if existing is None:
            session.add(Transaction(raw_email_id=raw.id, confirmed=False, **fields))
        else:
            # Keep manual fields (category, confirmed, notes). Refresh parsed fields.
            for k, v in fields.items():
                setattr(existing, k, v)
    elif existing is not None:
        if existing.confirmed or existing.category_source == "manual":
            raw.parse_error = (raw.parse_error or "") + " [kept: transaction was edited by hand]"
        else:
            session.delete(existing)
    return result.status
