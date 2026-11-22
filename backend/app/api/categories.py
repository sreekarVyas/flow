from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.transactions import Month, month_bounds
from app.db import get_session
from app.ledger import my_share_expr, others_share_subquery
from app.models import Account, Category, Rule, Transaction
from app.schemas import (
    CategoryCreate,
    CategoryOut,
    CategorySpend,
    CategorySummaryOut,
    CategoryUpdate,
    ParentSpend,
    RuleOut,
)

router = APIRouter(prefix="/api")


def _tree(cats: list[Category]) -> list[CategoryOut]:
    order = sorted(cats, key=lambda c: (c.sort_order, c.name.lower()))
    parents = {c.id: CategoryOut.model_validate(c) for c in order if c.parent_id is None}
    for c in order:
        if c.parent_id is not None and c.parent_id in parents:
            parents[c.parent_id].children.append(CategoryOut.model_validate(c))
    return list(parents.values())


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(session: Session = Depends(get_session)):
    """Parents with their children. Hidden (archived) ones are included and flagged."""
    return _tree(list(session.scalars(select(Category))))


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryCreate, session: Session = Depends(get_session)):
    if body.parent_id is not None:
        parent = session.get(Category, body.parent_id)
        if parent is None or parent.parent_id is not None:
            raise HTTPException(status_code=422, detail="parent must be a top-level category")
    last = session.scalar(
        select(func.max(Category.sort_order)).where(Category.parent_id.is_not_distinct_from(body.parent_id))
    )
    cat = Category(
        name=body.name.strip(), parent_id=body.parent_id, icon=body.icon,
        sort_order=(last if last is not None else -1) + 1,
    )
    session.add(cat)
    try:
        session.commit()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="a category with this name exists there") from e
    return CategoryOut.model_validate(cat)


@router.patch("/categories/{cat_id}", response_model=CategoryOut)
def update_category(cat_id: int, body: CategoryUpdate, session: Session = Depends(get_session)):
    cat = session.get(Category, cat_id)
    if cat is None:
        raise HTTPException(status_code=404, detail="category not found")
    sent = body.model_fields_set
    if "name" in sent and body.name:
        cat.name = body.name.strip()
    if "icon" in sent:
        cat.icon = body.icon or None
    if "archived" in sent and body.archived is not None:
        cat.archived = body.archived
    try:
        session.commit()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="a category with this name exists there") from e
    return CategoryOut.model_validate(cat)


@router.get("/categories/summary", response_model=CategorySummaryOut)
def category_summary(
    month: Month,
    account_type: Literal["bank", "credit_card"] | None = None,
    session: Session = Depends(get_session),
):
    """My spend per category: my share of expense debits, minus refund credits."""
    start, end = month_bounds(month)
    others = others_share_subquery()
    signed = case(
        ((Transaction.kind == "expense") & (Transaction.direction == "debit"), my_share_expr(others)),
        ((Transaction.kind == "refund") & (Transaction.direction == "credit"), -Transaction.amount),
        else_=Decimal("0"),
    )
    stmt = (
        select(Transaction.category_id, func.coalesce(func.sum(signed), Decimal("0")), func.count())
        .join(Transaction.account)
        .outerjoin(others, others.c.transaction_id == Transaction.id)
        .where(Transaction.ts >= start, Transaction.ts < end, Transaction.kind.in_(("expense", "refund")))
        .group_by(Transaction.category_id)
    )
    if account_type:
        stmt = stmt.where(Account.type == account_type)
    by_cat: dict[int | None, tuple[Decimal, int]] = {r[0]: (r[1], r[2]) for r in session.execute(stmt)}

    cats = {c.id: c for c in session.scalars(select(Category))}
    parents: dict[int, ParentSpend] = {}

    def parent_of(c: Category) -> ParentSpend:
        p = cats[c.parent_id] if c.parent_id is not None else c
        if p.id not in parents:
            parents[p.id] = ParentSpend(
                id=p.id, name=p.name, icon=p.icon, total=Decimal("0"), count=0,
                own_total=Decimal("0"), children=[],
            )
        return parents[p.id]

    for cat_id, (total, count) in by_cat.items():
        if cat_id is None:
            continue
        c = cats[cat_id]
        ps = parent_of(c)
        ps.total += total
        ps.count += count
        if c.parent_id is None:
            ps.own_total += total
        else:
            ps.children.append(CategorySpend(id=c.id, name=c.name, icon=c.icon, total=total, count=count))

    for ps in parents.values():
        ps.children.sort(key=lambda x: x.total, reverse=True)
    untagged_total, untagged_count = by_cat.get(None, (Decimal("0"), 0))
    return CategorySummaryOut(
        month=month,
        total=sum((t for t, _ in by_cat.values()), Decimal("0")),
        untagged_total=untagged_total,
        untagged_count=untagged_count,
        parents=sorted(parents.values(), key=lambda p: p.total, reverse=True),
    )


@router.get("/rules", response_model=list[RuleOut])
def list_rules(session: Session = Depends(get_session)):
    """Learned rules first (newest first), then seed rules A–Z."""
    rules = session.scalars(select(Rule)).all()
    return sorted(
        rules,
        key=lambda r: (r.source != "learned", -r.created_at.timestamp() if r.source == "learned" else 0, r.match_value),
    )


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, session: Session = Depends(get_session)):
    rule = session.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="rule not found")
    session.delete(rule)
    session.commit()
    return Response(status_code=204)
