from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, contains_eager

from app.categorize.rules import CATEGORIZABLE_KINDS, learn_rule, payee_key, similar_unconfirmed
from app.config import settings
from app.db import get_session
from app.models import Account, Category, GmailState, RawEmail, Transaction
from app.schemas import (
    RawEmailOut,
    SimilarOut,
    SummaryOut,
    TransactionOut,
    TransactionPatch,
    TransactionPatchOut,
    TypeTotals,
)

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


def _get_txn(session: Session, txn_id: int) -> Transaction:
    t = session.get(Transaction, txn_id)
    if t is None:
        raise HTTPException(status_code=404, detail="transaction not found")
    return t


@router.get("/transactions/{txn_id}/similar", response_model=SimilarOut)
def similar(txn_id: int, session: Session = Depends(get_session)):
    t = _get_txn(session, txn_id)
    payee = payee_key(t.counterparty_name, t.vpa_or_merchant)
    return SimilarOut(
        payee=payee,
        count=len(similar_unconfirmed(session, t)),
        learns_rule=payee is not None and t.direction == "debit",
    )


@router.patch("/transactions/{txn_id}", response_model=TransactionPatchOut)
def patch_transaction(txn_id: int, body: TransactionPatch, session: Session = Depends(get_session)):
    """Tag by hand. Sets `confirmed`, learns a payee rule (debits), and can tag similar ones."""
    t = _get_txn(session, txn_id)
    sent = body.model_fields_set

    if "category_id" in sent and body.category_id is not None and body.category_id != t.category_id:
        cat = session.get(Category, body.category_id)
        if cat is None or cat.archived:
            raise HTTPException(status_code=422, detail="unknown or hidden category")

    tagged = bool(sent & {"kind", "category_id"})
    if "kind" in sent:
        t.kind = body.kind
    if "category_id" in sent:
        t.category_id = body.category_id
    if "notes" in sent:
        t.notes = body.notes or None
    if t.kind not in CATEGORIZABLE_KINDS:
        t.category_id = None
    if t.category_id is None:
        t.category_source = None
    elif tagged:
        t.category_source = "manual"
    t.confirmed = True

    rule = learn_rule(session, t) if tagged else None

    updated = 0
    if body.apply_to_similar:
        for o in similar_unconfirmed(session, t):
            o.kind = t.kind
            o.category_id = t.category_id
            o.category_source = "manual" if t.category_id is not None else None
            o.confirmed = True
            updated += 1

    session.commit()
    return TransactionPatchOut(transaction=t, updated_similar=updated, rule=rule)
