"""Rule-based categorization.

Order of precedence:
  1. A transaction Siri confirmed is never changed.
  2. A learned `payee` rule (exact, normalized payee name), from a manual tag.
  3. A seed `name_contains` / `vpa_contains` rule. The longest match value wins, so
     "SWIGGY DINERS" beats "SWIGGY". Then the higher priority, then the older rule.

A rule can set `kind` (e.g. a payee Siri marked as a transfer) and/or `category_id`.
Only `expense` and `refund` transactions keep a category.
"""

import re
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Rule, Transaction
from app.parsers.base import infer_kind_from

CATEGORIZABLE_KINDS = ("expense", "refund")


def normalize(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip().upper()


def payee_key(counterparty_name: str | None, vpa_or_merchant: str | None) -> str | None:
    """The payee identity for learned rules. HDFC masks VPAs, so the name comes first."""
    key = normalize(counterparty_name) or normalize(vpa_or_merchant)
    return key[:255] or None


def pick_rule(
    rules: Sequence[Rule], direction: str, counterparty_name: str | None, vpa_or_merchant: str | None
) -> Rule | None:
    payee = payee_key(counterparty_name, vpa_or_merchant)
    name_text = payee or ""
    vpa_text = normalize(vpa_or_merchant)
    usable = [r for r in rules if r.direction in (None, direction)]

    exact = [r for r in usable if r.match_field == "payee" and r.match_value == payee]
    if exact:
        return max(exact, key=lambda r: (r.direction is not None, r.priority, -(r.id or 0)))

    hits = [
        r
        for r in usable
        if (r.match_field == "name_contains" and r.match_value in name_text)
        or (r.match_field == "vpa_contains" and r.match_value in vpa_text)
    ]
    if not hits:
        return None
    return max(hits, key=lambda r: (len(r.match_value), r.priority, -(r.id or 0)))


def load_rules(session: Session) -> list[Rule]:
    return list(session.scalars(select(Rule)))


def auto_categorize(txn: Transaction, rules: Sequence[Rule]) -> Rule | None:
    """Apply the best rule to an unconfirmed transaction. Returns the rule used, if any."""
    if txn.confirmed:
        return None
    rule = pick_rule(rules, txn.direction, txn.counterparty_name, txn.vpa_or_merchant)
    if rule is not None and rule.kind is not None:
        txn.kind = rule.kind
    if rule is not None and rule.category_id is not None and txn.kind in CATEGORIZABLE_KINDS:
        txn.category_id = rule.category_id
        txn.category_source = "rule"
    else:
        txn.category_id = None
        txn.category_source = None
    return rule


def inferred_kind(txn: Transaction) -> str | None:
    """The kind the ingest rules would give this transaction, without any category rule."""
    return infer_kind_from(
        txn.account.type, txn.direction, txn.counterparty_name, txn.vpa_or_merchant,
        settings.self_names, settings.salary_payers,
    )


def learn_rule(session: Session, txn: Transaction) -> Rule | None:
    """After a manual tag on a debit: save (or update) the `payee` rule for its payee.

    The rule stores the category, and the kind only when it differs from the inferred kind.
    If there is nothing to learn, a learned rule for that payee is removed.
    Credits are not learned: money from a person is a settlement one time and a pass-through the next.
    """
    key = payee_key(txn.counterparty_name, txn.vpa_or_merchant)
    if txn.direction != "debit" or key is None:
        return None
    kind = txn.kind if txn.kind != inferred_kind(txn) else None
    if kind == "settlement":
        kind = None  # a payment to a friend is not always a repayment: never automate it
    category_id = txn.category_id if txn.kind in CATEGORIZABLE_KINDS else None

    rule = session.scalar(
        select(Rule).where(Rule.match_field == "payee", Rule.match_value == key, Rule.direction == "debit")
    )
    if kind is None and category_id is None:
        if rule is not None and rule.source == "learned":
            session.delete(rule)
        return None
    if rule is None:
        rule = Rule(match_field="payee", match_value=key, direction="debit", source="learned")
        session.add(rule)
    rule.kind = kind
    rule.category_id = category_id
    session.flush()
    return rule


def similar_unconfirmed(session: Session, txn: Transaction) -> list[Transaction]:
    """Other unconfirmed transactions with the same payee and direction."""
    key = payee_key(txn.counterparty_name, txn.vpa_or_merchant)
    if key is None:
        return []
    candidates = session.scalars(
        select(Transaction).where(
            Transaction.id != txn.id,
            Transaction.confirmed.is_(False),
            Transaction.direction == txn.direction,
        )
    )
    return [t for t in candidates if payee_key(t.counterparty_name, t.vpa_or_merchant) == key]
