"""People: one row per person, matched without regard to case or extra spaces."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Person


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
