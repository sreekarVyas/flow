"""Payment sources and their nicknames.

A source is what the bank prints for the other side of a transaction: a name and a (masked) UPI ID.
Siri gives a source a nickname; the nickname is a person (people.name_key, case-insensitive).
Two UPI IDs with the same nickname are one person; different nicknames are different people.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.categorize.rules import normalize
from app.models import PaymentSource, Person, Transaction


def source_key(t: Transaction) -> tuple[str, str] | None:
    name, vpa = normalize(t.counterparty_name)[:255], normalize(t.vpa_or_merchant)[:255]
    if vpa == name:
        vpa = ""  # card merchants: the "UPI ID" is the merchant name again
    return (name, vpa) if (name or vpa) else None


def _title(name: str) -> str:
    return " ".join(w.capitalize() if len(w) > 1 else w for w in name.split())


@dataclass
class SourceInfo:
    printed_name: str | None
    vpa: str | None
    person: Person | None  # the nickname, if known or suggested
    known: bool  # True when this exact source already has the nickname
    suggestion: str  # text to prefill the nickname field


def lookup(session: Session, t: Transaction) -> SourceInfo:
    key = source_key(t)
    printed = t.counterparty_name or t.vpa_or_merchant
    vpa = t.vpa_or_merchant if key and key[1] else None
    person, known = t.person, False
    if key:
        exact = session.scalar(
            select(PaymentSource).where(PaymentSource.name_key == key[0], PaymentSource.vpa == key[1])
        )
        if exact is not None and (person is None or exact.person_id == person.id):
            known, person = True, exact.person
        if person is None and key[0]:
            # Same printed name, another UPI ID: probably the same person. Suggest, do not assume.
            same_name = session.scalar(select(PaymentSource).where(PaymentSource.name_key == key[0]).limit(1))
            person = same_name.person if same_name else None
        if person is None and key[0]:
            person = session.scalar(
                select(Person).where(
                    (Person.name_key == key[0].lower()) | Person.match_names.contains([key[0]])
                ).limit(1)
            )
    suggestion = person.display_name if person else _title(printed or "")
    return SourceInfo(printed_name=printed, vpa=vpa, person=person, known=known, suggestion=suggestion)


def assign(session: Session, t: Transaction, person: Person) -> PaymentSource | None:
    """Give this transaction's source the nickname `person` (creates or moves the source)."""
    key = source_key(t)
    if key is None:
        return None
    src = session.scalar(select(PaymentSource).where(PaymentSource.name_key == key[0], PaymentSource.vpa == key[1]))
    if src is None:
        src = PaymentSource(name_key=key[0], vpa=key[1], printed_name=t.counterparty_name, person_id=person.id)
        session.add(src)
    else:
        src.person_id = person.id
    session.flush()
    return src
