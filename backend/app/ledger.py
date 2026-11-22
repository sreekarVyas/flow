"""Derived money figures: shares, my spend, and per-person balances.

Nothing here is stored. Every figure comes from transactions + splits (and, later, settlement links),
so the list, the people screen and the summary always agree.

Rule (Siri, 22 Nov 2026): my spend = my share of each expense, in the expense's month and category.
"""

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Literal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from app.models import Split, Transaction

PAISA = Decimal("0.01")
ZERO = Decimal("0")
SplitMode = Literal["equal", "exact", "percent"]


def _paise(x: Decimal) -> Decimal:
    return x.quantize(PAISA, rounding=ROUND_DOWN)


def compute_shares(
    amount: Decimal, mode: SplitMode, values: list[Decimal | None], include_me: bool = True
) -> list[Decimal]:
    """Turn a split request into one share per person (in order). Rounding remainders go to me.

    equal   — amount / (people + me), or / people when include_me is False (then the remainder
              goes to the first person, since I keep nothing).
    exact   — values are rupee amounts.
    percent — values are percentages of the amount.
    """
    n = len(values)
    if n == 0:
        return []
    if mode == "equal":
        parts = n + (1 if include_me else 0)
        per = _paise(amount / parts)
        shares = [per] * n
        if not include_me:
            shares[0] += amount - per * n
    elif mode == "exact":
        if any(v is None or v <= 0 for v in values):
            raise ValueError("every share must be more than zero")
        shares = [_paise(v) for v in values]  # type: ignore[arg-type]
    elif mode == "percent":
        if any(v is None or v <= 0 for v in values):
            raise ValueError("every percentage must be more than zero")
        if sum(values) > 100:  # type: ignore[arg-type]
            raise ValueError("percentages add up to more than 100")
        shares = [_paise(amount * v / 100) for v in values]  # type: ignore[operator]
    else:
        raise ValueError(f"unknown split mode {mode!r}")
    if any(s <= 0 for s in shares):
        raise ValueError("a share rounds to zero; the amount is too small to split this way")
    if sum(shares) > amount:
        raise ValueError(f"shares add up to {sum(shares)}, more than the amount {amount}")
    return shares


def others_share_subquery() -> Subquery:
    """Per transaction: the total that other people owe me on it."""
    return (
        select(Split.transaction_id, func.sum(Split.share_amount).label("others"))
        .where(Split.paid_by == "me")
        .group_by(Split.transaction_id)
        .subquery()
    )


def my_share_expr(others: Subquery) -> ColumnElement[Decimal]:
    """Use with `.outerjoin(others, others.c.transaction_id == Transaction.id)`."""
    return Transaction.amount - func.coalesce(others.c.others, ZERO)


@dataclass
class Balance:
    """Positive `net` = the person owes me."""

    owed_to_me: Decimal = ZERO  # their shares of expenses I paid
    i_owe: Decimal = ZERO  # my shares of expenses they paid (friend-paid, later)
    received: Decimal = ZERO  # repayments from them (settlements, later)
    paid: Decimal = ZERO  # repayments to them (settlements, later)
    shares: int = 0

    @property
    def net(self) -> Decimal:
        return self.owed_to_me - self.i_owe - self.received + self.paid


def person_balances(session: Session, person_ids: list[int] | None = None) -> dict[int, Balance]:
    stmt = select(
        Split.person_id,
        func.coalesce(func.sum(case((Split.paid_by == "me", Split.share_amount))), ZERO),
        func.coalesce(func.sum(case((Split.paid_by == "person", Split.share_amount))), ZERO),
        func.count(),
    ).group_by(Split.person_id)
    if person_ids is not None:
        stmt = stmt.where(Split.person_id.in_(person_ids))
    return {
        pid: Balance(owed_to_me=me, i_owe=them, shares=n) for pid, me, them, n in session.execute(stmt)
    }
