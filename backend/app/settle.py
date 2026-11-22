"""Settlements: tag a repayment against earlier payments.

Both workflows (from the repayment, and from the original payment) call `link` / `unlink`, so they
always produce the same rows. Original transaction amounts are never changed.

Linking a repayment from Asha to a payment:
  - Asha already has a share on it  → the link settles (part of) that share. A full link cancels it out;
    a partial one leaves the rest outstanding; more than the share shows as an overpayment.
  - Asha has no share on it yet      → a share for Asha is created from the link (origin = 'link'),
    unless an explicit `share` is given. Such a share follows its links and goes away with the last one.
A debit to Asha marked as a settlement (returning an overpayment) re-opens her share by its amount.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.categorize.rules import normalize
from app.models import Person, SettlementLink, Split, Transaction

ZERO = Decimal("0")


class SettleError(ValueError):
    """A request that breaks a settlement rule. The message is shown to Siri."""


def remember_name(person: Person, txn: Transaction) -> None:
    """Keep the bank-printed name, so the next repayment from it can be suggested."""
    printed = normalize(txn.counterparty_name)
    if printed and printed not in person.match_names:
        person.match_names = [*person.match_names, printed][-10:]


def make_settlement(txn: Transaction, person: Person | None) -> None:
    if txn.splits:
        raise SettleError("this payment is split with people, so it cannot also be a repayment")
    txn.kind = "settlement"
    txn.category_id = None
    txn.category_source = None
    txn.confirmed = True
    if person is not None and txn.person_id != person.id:
        if txn.links_out:
            raise SettleError("remove this repayment's links before changing who it is from")
        txn.person_id = person.id
        txn.person = person
    if person is not None:
        remember_name(person, txn)


def clear_settlement(session: Session, txn: Transaction) -> None:
    """Called when a settlement becomes some other kind."""
    for link in list(txn.links_out):
        unlink(session, link)
    txn.person_id = None
    txn.person = None


def _sync_auto_share(session: Session, split: Split) -> None:
    """A share created by linking follows its links; with no links left it goes away."""
    if split.origin != "link":
        return
    total = sum((link.signed for link in split.links), ZERO)
    if total <= 0:
        split.transaction.splits.remove(split)
        session.delete(split)
    else:
        split.share_amount = total


def _check_total(settlement: Transaction) -> None:
    if settlement.applied > settlement.amount:
        raise SettleError(
            f"links add up to ₹{settlement.applied}, more than the repayment of ₹{settlement.amount}"
        )


def link(
    session: Session,
    settlement: Transaction,
    expense: Transaction,
    amount: Decimal,
    share: Decimal | None = None,
    check_total: bool = True,
) -> SettlementLink:
    if settlement.kind != "settlement" or settlement.person is None:
        raise SettleError("choose who this repayment is from first")
    if expense.id == settlement.id:
        raise SettleError("a repayment cannot settle itself")
    if not (expense.kind == "expense" and expense.direction == "debit"):
        raise SettleError("a repayment can only be tagged to an expense you paid")
    if amount <= 0:
        raise SettleError("the amount must be more than zero")
    person = settlement.person

    split = next((s for s in expense.splits if s.person_id == person.id and s.paid_by == "me"), None)
    if split is None:
        if settlement.direction != "credit":
            raise SettleError(f"{person.display_name} has no share on that payment to return money against")
        room = expense.my_share
        wanted = share if share is not None else amount
        if wanted > room:
            raise SettleError(f"₹{wanted} is more than the ₹{room} of that payment not already shared")
        split = Split(
            person_id=person.id, person=person, share_amount=wanted, paid_by="me",
            origin="manual" if share is not None and share != amount else "link",
        )
        expense.splits.append(split)
        session.flush()

    existing = next((x for x in split.links if x.settlement_txn_id == settlement.id), None)
    if existing is None:
        existing = SettlementLink(settlement=settlement, split=split, amount=amount)
        session.add(existing)
    else:
        existing.amount = amount

    if check_total:
        _check_total(settlement)
    _sync_auto_share(session, split)
    expense.confirmed = True
    session.flush()
    return existing


def unlink(session: Session, link_row: SettlementLink) -> None:
    split, settlement = link_row.split, link_row.settlement
    session.delete(link_row)
    session.flush()
    session.expire(split, ["links"])
    session.expire(settlement, ["links_out"])
    _sync_auto_share(session, split)
    session.flush()


def set_links(session: Session, settlement: Transaction, wanted: list[tuple[Transaction, Decimal, Decimal | None]]) -> None:
    """Replace the links of a settlement with `wanted` = [(expense, amount, share), ...]."""
    keep = {e.id for e, _, _ in wanted}
    if len(keep) != len(wanted):
        raise SettleError("the same payment is listed twice")
    for old in list(settlement.links_out):
        if old.split.transaction_id not in keep:
            unlink(session, old)
    for expense, amount, share in wanted:
        link(session, settlement, expense, amount, share, check_total=False)
    _check_total(settlement)
