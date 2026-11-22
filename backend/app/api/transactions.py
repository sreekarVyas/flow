from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, contains_eager, selectinload

from app.categorize.rules import CATEGORIZABLE_KINDS, learn_rule, payee_key, similar_unconfirmed
from app.config import settings
from app.db import get_session
from app.ledger import compute_shares, my_share_expr, others_share_subquery, person_balances, recovered_on
from app.models import Account, Category, GmailState, Person, RawEmail, SettlementLink, Split, Transaction
from app.people import resolve_person
from app.settle import clear_settlement
from app.schemas import (
    RawEmailOut,
    SharedTotals,
    SimilarOut,
    SplitRequest,
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


# Everything TransactionOut shows: shares with their repayments, and a repayment's person and shares.
TXN_LOAD = (
    selectinload(Transaction.account),
    selectinload(Transaction.splits).selectinload(Split.person),
    selectinload(Transaction.splits).selectinload(Split.links).selectinload(SettlementLink.settlement),
    selectinload(Transaction.person),
    selectinload(Transaction.links_out)
    .selectinload(SettlementLink.split)
    .options(selectinload(Split.transaction), selectinload(Split.links).selectinload(SettlementLink.settlement)),
)


def load_txn(session: Session, txn_id: int) -> Transaction:
    """Fresh copy with everything TransactionOut needs (after a write)."""
    return session.scalars(
        select(Transaction).where(Transaction.id == txn_id).options(*TXN_LOAD).execution_options(populate_existing=True)
    ).one()


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
        .options(contains_eager(Transaction.account), *TXN_LOAD[1:])
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
    expense = debit & (Transaction.kind == "expense")
    zero = Decimal("0")
    others = others_share_subquery()
    rows = session.execute(
        select(
            Account.type,
            func.coalesce(func.sum(case((debit, Transaction.amount))), zero),
            func.count(case((debit, 1))),
            func.coalesce(func.sum(case((~debit, Transaction.amount))), zero),
            func.count(case((~debit, 1))),
            func.coalesce(func.sum(case((expense, Transaction.amount))), zero),
            func.coalesce(func.sum(case((Transaction.kind == "transfer", Transaction.amount))), zero),
            func.coalesce(func.sum(case((expense, my_share_expr(others)))), zero),
            func.coalesce(func.sum(case((expense, others.c.others))), zero),
        )
        .join(Transaction.account)
        .outerjoin(others, others.c.transaction_id == Transaction.id)
        .where(Transaction.ts >= start, Transaction.ts < end)
        .group_by(Account.type)
    ).all()
    totals = {
        r[0]: TypeTotals(
            debit_total=r[1], debit_count=r[2], credit_total=r[3], credit_count=r[4],
            expense_total=r[5], transfer_total=r[6], my_share_total=r[7],
        )
        for r in rows
    }
    balances = person_balances(session).values()
    month_expenses = select(Transaction.id).where(
        Transaction.ts >= start, Transaction.ts < end, Transaction.kind == "expense", Transaction.direction == "debit"
    )
    shared = SharedTotals(
        others_share=sum((r[8] for r in rows), zero),
        recovered=recovered_on(session, month_expenses),
        owed_to_me=sum((b.net for b in balances if b.net > 0), zero),
        i_owe=sum((-b.net for b in balances if b.net < 0), zero),
        people_owing=sum(1 for b in balances if b.net > 0),
    )
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
        shared=shared,
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


@router.get("/transactions/{txn_id}", response_model=TransactionOut)
def get_transaction(txn_id: int, session: Session = Depends(get_session)):
    _get_txn(session, txn_id)
    return load_txn(session, txn_id)


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
    """Tag by hand. Sets `confirmed`, learns a payee rule (debits), and can tag similar ones.

    A body with only `notes` saves the note and changes nothing else.
    """
    t = _get_txn(session, txn_id)
    sent = body.model_fields_set

    if "category_id" in sent and body.category_id is not None and body.category_id != t.category_id:
        cat = session.get(Category, body.category_id)
        if cat is None or cat.archived:
            raise HTTPException(status_code=422, detail="unknown or hidden category")

    if "kind" in sent and body.kind != "expense" and t.splits:
        raise HTTPException(
            status_code=409, detail="this expense is split with people; remove the split before changing its kind"
        )

    tagged = bool(sent & {"kind", "category_id"})
    if "kind" in sent and t.kind == "settlement" and body.kind != "settlement":
        clear_settlement(session, t)
    if "kind" in sent:
        t.kind = body.kind
    if "category_id" in sent:
        t.category_id = body.category_id
    if "notes" in sent:
        t.notes = (body.notes or "").strip() or None
    if t.kind not in CATEGORIZABLE_KINDS:
        t.category_id = None
    if t.category_id is None:
        t.category_source = None
    elif tagged:
        t.category_source = "manual"
    if sent - {"notes"} or not sent:  # a note alone does not confirm the tag
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


@router.put("/transactions/{txn_id}/splits", response_model=TransactionOut)
def put_splits(txn_id: int, body: SplitRequest, session: Session = Depends(get_session)):
    """Replace who shares this expense. An empty `people` list removes the split.

    People are found by id, or by name without regard to case (created when new).
    The transaction becomes confirmed: a split means Siri has reviewed it.
    """
    t = _get_txn(session, txn_id)
    if body.people and not (t.kind == "expense" and t.direction == "debit"):
        raise HTTPException(status_code=422, detail="only expenses I paid can be split")

    person_ids: list[int] = []
    for p in body.people:
        if p.person_id is not None:
            if session.get(Person, p.person_id) is None:
                raise HTTPException(status_code=422, detail=f"person {p.person_id} not found")
            person_ids.append(p.person_id)
        elif p.name:
            try:
                person_ids.append(resolve_person(session, p.name)[0].id)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e)) from e
        else:
            raise HTTPException(status_code=422, detail="each person needs a person_id or a name")
    if len(set(person_ids)) != len(person_ids):
        raise HTTPException(status_code=422, detail="the same person is listed twice")

    try:
        shares = compute_shares(t.amount, body.mode, [p.value for p in body.people], body.include_me)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    # Update in place so split ids stay stable (settlement links will point at them).
    current = {s.person_id: s for s in t.splits if s.paid_by == "me"}
    for pid, share in zip(person_ids, shares, strict=True):
        if pid in current:
            kept = current.pop(pid)
            kept.share_amount, kept.origin = share, "manual"
        else:
            t.splits.append(Split(person_id=pid, share_amount=share, paid_by="me"))
    for gone in current.values():
        if gone.links:
            raise HTTPException(
                status_code=409,
                detail=f"{gone.person.display_name} has repayments tagged to this payment; remove those first",
            )
        t.splits.remove(gone)
    if body.people:
        t.confirmed = True

    session.commit()
    return load_txn(session, t.id)
