from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.transactions import TXN_LOAD
from app.db import get_session
from app.ledger import Balance, person_balances
from app.models import PaymentSource, Person, SettlementLink, Split, Transaction
from app.people import clean_name, merge_people, name_key, resolve_person
from app.schemas import MergeRequest, PersonCreate, PersonDetail, PersonOut, PersonShare, PersonUpdate

router = APIRouter(prefix="/api")


def _out(p: Person, b: Balance | None) -> PersonOut:
    b = b or Balance()
    return PersonOut(
        id=p.id, display_name=p.display_name, owed_to_me=b.owed_to_me, i_owe=b.i_owe,
        received=b.received, paid=b.paid, net=b.net, shares=b.shares,
    )


def _get(session: Session, person_id: int) -> Person:
    p = session.get(Person, person_id)
    if p is None:
        raise HTTPException(status_code=404, detail="person not found")
    return p


@router.get("/people", response_model=list[PersonOut])
def list_people(q: str | None = None, session: Session = Depends(get_session)):
    """Everyone, biggest balance first. `q` matches the start of any word, without regard to case."""
    stmt = select(Person)
    key = name_key(q or "")
    if key:
        stmt = stmt.where(
            (Person.name_key.startswith(key, autoescape=True))
            | (Person.name_key.contains(f" {key}", autoescape=True))
        )
    people = session.scalars(stmt).all()
    balances = person_balances(session, [p.id for p in people])
    out = [_out(p, balances.get(p.id)) for p in people]
    return sorted(out, key=lambda o: (-abs(o.net), o.display_name.lower()))


@router.post("/people", response_model=PersonOut, status_code=201)
def create_person(body: PersonCreate, response: Response, session: Session = Depends(get_session)):
    """Returns the existing person (200) when the name matches one without regard to case."""
    try:
        person, created = resolve_person(session, body.name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    session.commit()
    if not created:
        response.status_code = 200
    return _out(person, person_balances(session, [person.id]).get(person.id))


@router.patch("/people/{person_id}", response_model=PersonOut)
def rename_person(person_id: int, body: PersonUpdate, session: Session = Depends(get_session)):
    p = _get(session, person_id)
    shown = clean_name(body.display_name)
    if not shown:
        raise HTTPException(status_code=422, detail="name is empty")
    p.display_name, p.name_key = shown, name_key(shown)
    try:
        session.commit()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail=f"someone named {shown!r} already exists") from e
    return _out(p, person_balances(session, [p.id]).get(p.id))


@router.delete("/people/{person_id}", status_code=204)
def delete_person(person_id: int, session: Session = Depends(get_session)):
    """Only a person with no shares can be deleted (for typos)."""
    p = _get(session, person_id)
    if session.scalar(select(func.count()).select_from(Split).where(Split.person_id == p.id)):
        raise HTTPException(status_code=409, detail="this person has shares on expenses; remove those first")
    session.delete(p)
    session.commit()
    return Response(status_code=204)


@router.get("/people/{person_id}", response_model=PersonDetail)
def person_detail(person_id: int, session: Session = Depends(get_session)):
    p = _get(session, person_id)
    splits = session.scalars(
        select(Split)
        .join(Split.transaction)
        .where(Split.person_id == p.id)
        .options(selectinload(Split.transaction).options(*TXN_LOAD), selectinload(Split.links).selectinload(SettlementLink.settlement))
        .order_by(Transaction.ts.desc())
    ).all()
    base = _out(p, person_balances(session, [p.id]).get(p.id))
    return PersonDetail(
        **base.model_dump(),
        match_names=p.match_names,
        history=[
            PersonShare(
                split_id=s.id, share_amount=s.share_amount, settled=s.settled, outstanding=s.outstanding,
                paid_by=s.paid_by, transaction=s.transaction,
            )
            for s in splits
        ],
        sources=list(session.scalars(
            select(PaymentSource).where(PaymentSource.person_id == p.id).order_by(PaymentSource.created_at)
        )),
        repayments=list(session.scalars(
            select(Transaction)
            .where(Transaction.kind == "settlement", Transaction.person_id == p.id)
            .options(*TXN_LOAD)
            .order_by(Transaction.ts.desc())
        )),
    )


@router.post("/people/{person_id}/merge", response_model=PersonOut)
def merge(person_id: int, body: MergeRequest, session: Session = Depends(get_session)):
    """Same person under two nicknames: move everything of this one into `into_id` and delete it."""
    src, dst = _get(session, person_id), _get(session, body.into_id)
    if src.id == dst.id:
        raise HTTPException(status_code=422, detail="a person cannot be merged into themselves")
    merge_people(session, src, dst)
    session.commit()
    return _out(dst, person_balances(session, [dst.id]).get(dst.id))


@router.delete("/payment-sources/{source_id}", status_code=204)
def forget_source(source_id: int, session: Session = Depends(get_session)):
    """Forget a UPI ID's nickname (it was given to the wrong person). Past repayments stay as they are."""
    src = session.get(PaymentSource, source_id)
    if src is None:
        raise HTTPException(status_code=404, detail="payment source not found")
    session.delete(src)
    session.commit()
    return Response(status_code=204)
