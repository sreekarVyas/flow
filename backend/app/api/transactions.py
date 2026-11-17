from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, contains_eager

from app.config import settings
from app.db import get_session
from app.models import Account, GmailState, RawEmail, Transaction
from app.schemas import RawEmailOut, SummaryOut, TransactionOut, TypeTotals

router = APIRouter(prefix="/api")

Month = Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", examples=["2026-11"])]


def month_bounds(month: str) -> tuple[datetime, datetime]:
    """[start, end) of a calendar month in the app time zone (IST)."""
    y, m = map(int, month.split("-"))
    start = datetime(y, m, 1, tzinfo=settings.tz)
    end = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=settings.tz)
    return start, end


@router.get("/health")
def health(session: Session = Depends(get_session)) -> dict:
    session.execute(select(1))
    return {"ok": True}


@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    month: Month,
    account_type: Literal["bank", "credit_card"] | None = None,
    session: Session = Depends(get_session),
):
    start, end = month_bounds(month)
    stmt = (
        select(Transaction)
        .join(Transaction.account)
        .options(contains_eager(Transaction.account))
        .where(Transaction.ts >= start, Transaction.ts < end)
        .order_by(Transaction.ts.desc(), Transaction.id.desc())
    )
    if account_type:
        stmt = stmt.where(Account.type == account_type)
    return session.scalars(stmt).all()


@router.get("/summary", response_model=SummaryOut)
def summary(month: Month, session: Session = Depends(get_session)):
    start, end = month_bounds(month)
    debit = Transaction.direction == "debit"
    zero = Decimal("0")
    rows = session.execute(
        select(
            Account.type,
            func.coalesce(func.sum(case((debit, Transaction.amount))), zero),
            func.count(case((debit, 1))),
            func.coalesce(func.sum(case((~debit, Transaction.amount))), zero),
            func.count(case((~debit, 1))),
            func.coalesce(func.sum(case((debit & (Transaction.kind == "expense"), Transaction.amount))), zero),
            func.coalesce(func.sum(case((Transaction.kind == "transfer", Transaction.amount))), zero),
        )
        .join(Transaction.account)
        .where(Transaction.ts >= start, Transaction.ts < end)
        .group_by(Account.type)
    ).all()
    totals = {
        r[0]: TypeTotals(
            debit_total=r[1], debit_count=r[2], credit_total=r[3], credit_count=r[4],
            expense_total=r[5], transfer_total=r[6],
        )
        for r in rows
    }
    unknown = session.scalar(
        select(func.count()).where(
            RawEmail.parse_status == "unknown", RawEmail.received_at >= start, RawEmail.received_at < end
        )
    )
    state = session.get(GmailState, 1)
    return SummaryOut(
        month=month,
        bank=totals.get("bank", TypeTotals()),
        credit_card=totals.get("credit_card", TypeTotals()),
        unknown_emails=unknown or 0,
        last_poll_at=state.last_poll_at if state else None,
        last_poll_result=state.last_poll_result if state else None,
    )


@router.get("/raw-emails", response_model=list[RawEmailOut])
def list_raw_emails(
    status: Literal["txn", "ignored", "unknown"] = "unknown",
    month: Month | None = None,
    session: Session = Depends(get_session),
):
    stmt = select(RawEmail).where(RawEmail.parse_status == status).order_by(RawEmail.received_at.desc())
    if month:
        start, end = month_bounds(month)
        stmt = stmt.where(RawEmail.received_at >= start, RawEmail.received_at < end)
    return session.scalars(stmt.limit(500)).all()
