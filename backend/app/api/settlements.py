"""Repayments tagged against earlier payments. Both workflows end in app/settle.py."""

from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.transactions import TXN_LOAD, load_txn
from app.categorize.rules import normalize
from app.db import get_session
from app.models import PaymentSource, Person, SettlementLink, Transaction
from app.people import find_person, resolve_person
from app.schemas import (
    RepaymentCandidate,
    RepaymentCandidatesOut,
    RepaymentRequest,
    SettleCandidate,
    SettleCandidatesOut,
    SettlementRequest,
    SourceOut,
    TransactionOut,
)
from app.sources import assign, lookup, source_key
from app.settle import SettleError, link, make_settlement, set_links, unlink

router = APIRouter(prefix="/api")
ZERO = Decimal("0")
LIMIT = 60


def _txn(session: Session, txn_id: int) -> Transaction:
    t = session.get(Transaction, txn_id)
    if t is None:
        raise HTTPException(status_code=404, detail="transaction not found")
    return t


def _person(session: Session, person_id: int | None, name: str | None) -> Person | None:
    if person_id is not None:
        p = session.get(Person, person_id)
        if p is None:
            raise HTTPException(status_code=422, detail=f"person {person_id} not found")
        return p
    if name and name.strip():
        try:
            return resolve_person(session, name)[0]
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
    return None


def suggest_person(session: Session, t: Transaction) -> Person | None:
    """The nickname of this transaction's payment source, or the best guess."""
    return lookup(session, t).person


@router.get("/transactions/{txn_id}/source", response_model=SourceOut)
def get_source(txn_id: int, session: Session = Depends(get_session)):
    info = lookup(session, _txn(session, txn_id))
    return SourceOut(
        printed_name=info.printed_name, vpa=info.vpa, person=info.person, known=info.known, suggestion=info.suggestion
    )


def _payee_filter(q: str | None):
    if not q or not q.strip():
        return None
    like = f"%{q.strip()}%"
    return or_(Transaction.counterparty_name.ilike(like), Transaction.vpa_or_merchant.ilike(like))


# ---------- workflow 1: from the repayment ----------


@router.put("/transactions/{txn_id}/settlement", response_model=TransactionOut)
def put_settlement(txn_id: int, body: SettlementRequest, session: Session = Depends(get_session)):
    """Mark this transaction as a repayment from / to a person, and replace the payments it is tagged to.
    `links: []` keeps it as an untagged repayment that still counts in the person's balance.
    """
    t = _txn(session, txn_id)
    person = _person(session, body.person_id, body.nickname or body.name) or t.person
    if person is None:
        raise HTTPException(status_code=422, detail="give this payment source a nickname")
    expenses = {e.id: e for e in session.scalars(
        select(Transaction).where(Transaction.id.in_([x.transaction_id for x in body.links])).options(*TXN_LOAD)
    )}
    missing = [x.transaction_id for x in body.links if x.transaction_id not in expenses]
    if missing:
        raise HTTPException(status_code=422, detail=f"transaction {missing[0]} not found")
    try:
        if t.person_id is not None and t.person_id != person.id:
            set_links(session, t, [])  # a full replace: the old person's links go first
        make_settlement(t, person)
        set_links(session, t, [(expenses[x.transaction_id], x.amount, x.share) for x in body.links])
    except SettleError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    assign(session, t, person)
    session.commit()
    return load_txn(session, t.id)


@router.get("/transactions/{txn_id}/settle-candidates", response_model=SettleCandidatesOut)
def settle_candidates(
    txn_id: int,
    person_id: int | None = None,
    nickname: str | None = None,
    q: str | None = None,
    session: Session = Depends(get_session),
):
    """Earlier payments this repayment could be tagged to. Already tagged first, then payments where the
    person has an open share (oldest first), then other payments (newest first)."""
    t = _txn(session, txn_id)
    suggested = suggest_person(session, t)
    by_nick = find_person(session, nickname) if nickname else None
    pid = person_id or (by_nick.id if by_nick else None) or (None if nickname else t.person_id) or (
        suggested.id if suggested and not nickname else None
    )
    linked = {lk.split.transaction_id: lk.amount for lk in t.links_out}

    stmt = select(Transaction).where(
        Transaction.kind == "expense", Transaction.direction == "debit", Transaction.id != t.id
    )
    flt = _payee_filter(q)
    if flt is not None:
        stmt = stmt.where(flt)
    else:
        stmt = stmt.where(Transaction.ts <= t.ts + timedelta(days=1))
    rows = list(session.scalars(stmt.options(*TXN_LOAD).order_by(Transaction.ts.desc()).limit(LIMIT)))
    missing = set(linked) - {r.id for r in rows}
    if missing:
        rows += session.scalars(select(Transaction).where(Transaction.id.in_(missing)).options(*TXN_LOAD))

    items = []
    for e in rows:
        share = next((s for s in e.splits if s.person_id == pid and s.paid_by == "me"), None) if pid else None
        items.append(SettleCandidate(transaction=e, share=share, linked_amount=linked.get(e.id, ZERO)))

    def rank(c: SettleCandidate):
        if c.linked_amount > 0:
            return (0, c.transaction.ts.timestamp())
        if c.share is not None and c.share.outstanding > 0:
            return (1, c.transaction.ts.timestamp())
        return (2, -c.transaction.ts.timestamp())

    return SettleCandidatesOut(suggested_person=suggested, items=sorted(items, key=rank))


# ---------- workflow 2: from the original payment ----------


@router.post("/transactions/{txn_id}/repayments", response_model=TransactionOut)
def add_repayment(txn_id: int, body: RepaymentRequest, session: Session = Depends(get_session)):
    """Tag a repayment transaction against this payment (same rows as workflow 1)."""
    expense = _txn(session, txn_id)
    settlement = _txn(session, body.settlement_txn_id)
    person = _person(session, body.person_id, body.nickname or body.name) or settlement.person
    if person is None:
        raise HTTPException(status_code=422, detail="give this payment source a nickname")
    try:
        make_settlement(settlement, person)
        link(session, settlement, expense, body.amount, body.share)
    except SettleError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    assign(session, settlement, person)
    session.commit()
    return load_txn(session, expense.id)


@router.get("/transactions/{txn_id}/repayment-candidates", response_model=RepaymentCandidatesOut)
def repayment_candidates(txn_id: int, q: str | None = None, session: Session = Depends(get_session)):
    """Money that could be a repayment for this payment: credits not yet reviewed or marked as
    repayments with money left to tag, plus returns to the people on it. Likely ones first."""
    e = _txn(session, txn_id)
    people = {s.person_id: s.person for s in e.splits}
    printed = {n for p in people.values() for n in p.match_names} | {p.name_key.upper() for p in people.values()}
    known_sources = {
        (s.name_key, s.vpa)
        for s in session.scalars(select(PaymentSource).where(PaymentSource.person_id.in_(people or [-1])))
    }
    linked = {lk.settlement_txn_id: lk.amount for s in e.splits for lk in s.links}

    stmt = select(Transaction).where(
        Transaction.id != e.id,
        or_(
            (Transaction.direction == "credit") & (Transaction.kind.is_(None) | (Transaction.kind == "settlement")),
            (Transaction.kind == "settlement") & Transaction.person_id.in_(people or [-1]),
        ),
    )
    flt = _payee_filter(q)
    if flt is not None:
        stmt = stmt.where(flt)
    else:
        stmt = stmt.where(Transaction.ts >= e.ts - timedelta(days=7))
    rows = list(session.scalars(stmt.options(*TXN_LOAD).order_by(Transaction.ts.desc()).limit(LIMIT)))
    missing = set(linked) - {r.id for r in rows}
    if missing:
        rows += session.scalars(select(Transaction).where(Transaction.id.in_(missing)).options(*TXN_LOAD))
    rows = [r for r in rows if r.id in linked or r.kind != "settlement" or r.unapplied > 0]

    def rank(t: Transaction):
        if t.id in linked:
            return (0, t.ts.timestamp())
        if t.person_id in people:
            return (1, t.ts.timestamp())
        if source_key(t) in known_sources or normalize(t.counterparty_name) in printed:
            return (2, t.ts.timestamp())
        return (3, -t.ts.timestamp())

    return RepaymentCandidatesOut(
        items=[RepaymentCandidate(transaction=t, linked_amount=linked.get(t.id, ZERO)) for t in sorted(rows, key=rank)]
    )


@router.delete("/settlement-links/{link_id}", status_code=204)
def delete_link(link_id: int, session: Session = Depends(get_session)):
    row = session.get(SettlementLink, link_id)
    if row is None:
        raise HTTPException(status_code=404, detail="link not found")
    unlink(session, row)
    session.commit()
    return Response(status_code=204)
