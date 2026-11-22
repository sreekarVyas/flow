"""People: one row per person, matched without regard to case or extra spaces."""

import re

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import PaymentSource, Person, Split, Transaction


def clean_name(name: str) -> str:
    """The display form: trimmed, single spaces, case kept as typed."""
    return re.sub(r"\s+", " ", name).strip()


def name_key(name: str) -> str:
    """The identity: "John", "JOHN" and "  john " all give "john"."""
    return clean_name(name).lower()


def find_person(session: Session, name: str) -> Person | None:
    key = name_key(name)
    return session.scalar(select(Person).where(Person.name_key == key)) if key else None


def resolve_person(session: Session, name: str) -> tuple[Person, bool]:
    """Return (person, created). Creates the person on first use; never makes a duplicate."""
    shown = clean_name(name)
    if not shown:
        raise ValueError("name is empty")
    if len(shown) > 100:
        raise ValueError("name is longer than 100 characters")
    existing = find_person(session, shown)
    if existing is not None:
        return existing, False
    person = Person(display_name=shown, name_key=name_key(shown), match_names=[])
    session.add(person)
    session.flush()
    return person, True


def merge_people(session: Session, src: Person, dst: Person) -> Person:
    """Fold `src` into `dst`: shares, repayments, payment sources and printed names move over.

    When both have a share on the same payment, the shares are added together, and repayment
    links on them are combined. Original transactions are not changed.
    """
    if src.id == dst.id:
        return dst
    for split in list(session.scalars(select(Split).where(Split.person_id == src.id))):
        twin = session.scalar(
            select(Split).where(
                Split.transaction_id == split.transaction_id, Split.person_id == dst.id, Split.paid_by == split.paid_by
            )
        )
        if twin is None:
            split.person_id = dst.id
            continue
        twin.share_amount += split.share_amount
        if split.origin == "manual":
            twin.origin = "manual"
        for link in list(split.links):
            same = next((x for x in twin.links if x.settlement_txn_id == link.settlement_txn_id), None)
            if same is not None:
                same.amount += link.amount
                session.delete(link)
            else:
                link.split = twin
        session.flush()
        session.delete(split)
    session.execute(update(Transaction).where(Transaction.person_id == src.id).values(person_id=dst.id))
    session.execute(update(PaymentSource).where(PaymentSource.person_id == src.id).values(person_id=dst.id))
    dst.match_names = list(dict.fromkeys([*dst.match_names, *src.match_names]))[-20:]
    session.flush()
    session.delete(src)
    session.flush()
    return dst
