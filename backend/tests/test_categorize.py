"""Categorization: rule picking (unit) and the tag / learn / summary flow (real test DB)."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.categorize.rules import auto_categorize, load_rules, payee_key, pick_rule
from app.ingest.poller import poll_once
from app.models import Category, Rule, Transaction
from tests.test_ingest import FakeSource, email, parsers  # noqa: F401  (fixture)


def rule(id: int, field: str, value: str, category_id: int | None = 1, **kw) -> Rule:
    return Rule(id=id, match_field=field, match_value=value, category_id=category_id,
                direction=kw.get("direction"), kind=kw.get("kind"), priority=kw.get("priority", 0))


# ---------- unit ----------


def test_payee_key_normalizes():
    assert payee_key("  Ravi   kumar ", "x@ybl") == "RAVI KUMAR"
    assert payee_key(None, "RAZ*Swiggy") == "RAZ*SWIGGY"
    assert payee_key("", "  ") is None


def test_longest_contains_match_wins():
    rules = [rule(1, "name_contains", "SWIGGY", 10), rule(2, "name_contains", "SWIGGY DINERS", 20)]
    assert pick_rule(rules, "debit", "Swiggy Diners", "x@icici").category_id == 20
    assert pick_rule(rules, "debit", "RAZ*SWIGGY", "RAZ*SWIGGY").category_id == 10
    assert pick_rule(rules, "debit", "Zepto", None) is None


def test_name_contains_ignores_vpa_but_vpa_contains_uses_it():
    rules = [rule(1, "name_contains", "AIRTEL", 10), rule(2, "vpa_contains", "LITY@AXISB", 20)]
    # PSP names in the VPA (rxairtel) must not match a name rule.
    assert pick_rule(rules, "debit", "WOW MOMO FOODS", "****.rzp@rxairtel") is None
    assert pick_rule(rules, "debit", "CRED", "********lity@axisb").category_id == 20


def test_learned_payee_rule_beats_seed_and_respects_direction():
    rules = [
        rule(1, "name_contains", "RAGHAVENDRA", 10),
        rule(2, "payee", "SRI RAGHAVENDRA VILAS", 30, direction="debit"),
    ]
    assert pick_rule(rules, "debit", "Sri Raghavendra  vilas", "y@ybl").category_id == 30
    assert pick_rule(rules, "credit", "Sri Raghavendra vilas", "y@ybl").category_id == 10


def test_auto_categorize_only_categorizes_expense_and_keeps_confirmed():
    rules = [rule(1, "name_contains", "CRED CLUB", 10), rule(2, "payee", "MY SBI", None, kind="transfer")]
    t = Transaction(direction="debit", kind="transfer", counterparty_name="CRED CLUB", confirmed=False)
    auto_categorize(t, rules)
    assert t.category_id is None  # a transfer has no category

    t = Transaction(direction="debit", kind="expense", counterparty_name="My SBI", confirmed=False)
    auto_categorize(t, rules)
    assert (t.kind, t.category_id) == ("transfer", None)

    t = Transaction(direction="debit", kind="expense", counterparty_name="CRED CLUB", confirmed=True,
                    category_id=99, category_source="manual")
    auto_categorize(t, rules)
    assert t.category_id == 99


# ---------- DB ----------


def cat_id(session, path: str) -> int:
    parent, _, child = path.partition("/")
    p = session.scalar(select(Category).where(Category.name == parent, Category.parent_id.is_(None)))
    if not child:
        return p.id
    return session.scalar(select(Category.id).where(Category.name == child, Category.parent_id == p.id))


def test_seed_categories_and_rules(session):
    top = session.scalars(select(Category).where(Category.parent_id.is_(None))).all()
    assert len(top) == 19 and all(c.is_seed for c in top)
    assert cat_id(session, "Food & drinks/Tea & coffee") is not None
    names = {r.match_value for r in load_rules(session)}
    assert {"SWIGGY", "SWIGGY DINERS", "BOOK MY SHOW", "LITY@AXISB"} <= names


BURGER = "TEST Rs.336.00 debit a/c 1234 on 2026-11-05 GOOD FLIPPIN BURGERS"
CRED = "TEST Rs.37019.00 debit a/c 1234 on 2026-11-06 CRED CLUB"


def tea(i: str, amount: str = "20.00", day: int = 7) -> object:
    return email(i, f"TEST Rs.{amount} debit a/c 1234 on 2026-11-{day:02} RAVI KUMAR",
                 when=datetime(2026, 11, day, 6, tzinfo=UTC))


def by_name(session, name: str) -> list[Transaction]:
    return list(session.scalars(select(Transaction).where(Transaction.counterparty_name == name).order_by(Transaction.id)))


def test_ingest_auto_tags_expenses_only(session, parsers):  # noqa: F811
    poll_once(session, FakeSource([email("a", BURGER), email("b", CRED), tea("c")]))
    burger, = by_name(session, "GOOD FLIPPIN BURGERS")
    assert burger.category_id == cat_id(session, "Food & drinks/Eating out")
    assert (burger.category_source, burger.confirmed) == ("rule", False)
    cred, = by_name(session, "CRED CLUB")
    assert cred.kind == "transfer" and cred.category_id is None
    assert by_name(session, "RAVI KUMAR")[0].category_id is None  # no seed rule for a person


def test_manual_tag_learns_rule_and_applies_to_similar(session, parsers):  # noqa: F811
    from app.main import app

    poll_once(session, FakeSource([tea("a", day=3), tea("b", day=4), tea("c", day=5)]))
    first, second, third = by_name(session, "RAVI KUMAR")
    client = TestClient(app)

    # Confirm one by hand first: "apply to similar" must not touch it.
    other = cat_id(session, "Food & drinks/Snacks & sweets")
    assert client.patch(f"/api/transactions/{third.id}", json={"category_id": other}).status_code == 200

    assert client.get(f"/api/transactions/{first.id}/similar").json() == {
        "payee": "RAVI KUMAR", "count": 1, "learns_rule": True,
    }
    teacoffee = cat_id(session, "Food & drinks/Tea & coffee")
    r = client.patch(f"/api/transactions/{first.id}", json={"category_id": teacoffee, "apply_to_similar": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated_similar"] == 1
    assert body["transaction"]["category_source"] == "manual" and body["transaction"]["confirmed"] is True
    assert body["rule"]["match_value"] == "RAVI KUMAR" and body["rule"]["kind"] is None

    session.expire_all()
    assert [t.category_id for t in by_name(session, "RAVI KUMAR")] == [teacoffee, teacoffee, other]

    # The next payment to the same payee is auto-tagged by the learned rule.
    poll_once(session, FakeSource([tea("d", day=9)]))
    new = by_name(session, "RAVI KUMAR")[-1]
    assert (new.category_id, new.category_source, new.confirmed) == (teacoffee, "rule", False)

    # ✓ on an auto tag: confirms it, keeps the rule source.
    body = client.patch(f"/api/transactions/{new.id}", json={}).json()
    assert body["transaction"]["confirmed"] is True and body["transaction"]["category_source"] == "rule"
    assert body["rule"] is None


def test_manual_kind_change_is_learned_and_clears_category(session, parsers):  # noqa: F811
    from app.main import app

    poll_once(session, FakeSource([email("a", BURGER)]))
    burger, = by_name(session, "GOOD FLIPPIN BURGERS")
    client = TestClient(app)
    body = client.patch(f"/api/transactions/{burger.id}", json={"kind": "transfer"}).json()
    assert body["transaction"]["kind"] == "transfer" and body["transaction"]["category_id"] is None
    assert body["rule"]["kind"] == "transfer"

    # Back to expense with no category: nothing left to learn, so the rule goes away.
    body = client.patch(f"/api/transactions/{burger.id}", json={"kind": "expense", "category_id": None}).json()
    assert body["rule"] is None
    assert session.scalar(select(Rule).where(Rule.source == "learned")) is None


def test_patch_rejects_unknown_and_hidden_categories(session, parsers):  # noqa: F811
    from app.main import app

    poll_once(session, FakeSource([email("a", BURGER)]))
    burger, = by_name(session, "GOOD FLIPPIN BURGERS")
    client = TestClient(app)
    assert client.patch(f"/api/transactions/{burger.id}", json={"category_id": 999999}).status_code == 422
    assert client.patch("/api/transactions/999999", json={}).status_code == 404

    hidden = client.post("/api/categories", json={"name": "Test hidden", "icon": "🧪"}).json()
    client.patch(f"/api/categories/{hidden['id']}", json={"archived": True})
    assert client.patch(f"/api/transactions/{burger.id}", json={"category_id": hidden["id"]}).status_code == 422


def test_reparse_keeps_manual_kind_and_category(session, parsers):  # noqa: F811
    from app.config import settings
    from app.ingest.store import apply_classification
    from app.main import app
    from app.models import RawEmail

    poll_once(session, FakeSource([email("a", BURGER)]))
    burger, = by_name(session, "GOOD FLIPPIN BURGERS")
    snacks = cat_id(session, "Food & drinks/Snacks & sweets")
    TestClient(app).patch(f"/api/transactions/{burger.id}", json={"kind": "refund", "category_id": snacks})

    session.expire_all()
    for raw in session.scalars(select(RawEmail)).all():
        apply_classification(session, raw, settings.tz)
    session.commit()
    burger, = by_name(session, "GOOD FLIPPIN BURGERS")
    assert (burger.kind, burger.category_id, burger.category_source) == ("refund", snacks, "manual")


def test_note_alone_does_not_confirm_and_survives_reparse(session, parsers):  # noqa: F811
    from app.config import settings
    from app.ingest.store import apply_classification
    from app.main import app
    from app.models import RawEmail

    poll_once(session, FakeSource([email("a", BURGER)]))
    burger, = by_name(session, "GOOD FLIPPIN BURGERS")
    client = TestClient(app)
    body = client.patch(f"/api/transactions/{burger.id}", json={"notes": "  Dinner with friends "}).json()
    t = body["transaction"]
    assert t["notes"] == "Dinner with friends"
    assert (t["confirmed"], t["category_source"], body["rule"]) == (False, "rule", None)
    assert client.patch(f"/api/transactions/{burger.id}", json={"notes": "x" * 281}).status_code == 422

    session.expire_all()
    for raw in session.scalars(select(RawEmail)).all():
        apply_classification(session, raw, settings.tz)
    session.commit()
    assert by_name(session, "GOOD FLIPPIN BURGERS")[0].notes == "Dinner with friends"

    body = client.patch(f"/api/transactions/{burger.id}", json={"notes": ""}).json()
    assert body["transaction"]["notes"] is None


def test_categories_crud(session):
    from app.main import app

    client = TestClient(app)
    tree = client.get("/api/categories").json()
    assert tree[0]["name"] == "Food & drinks" and tree[0]["children"][0]["name"] == "Eating out"

    food = tree[0]["id"]
    made = client.post("/api/categories", json={"name": " Biryani ", "parent_id": food, "icon": "🍛"})
    assert made.status_code == 201 and made.json()["name"] == "Biryani"
    assert client.post("/api/categories", json={"name": "Biryani", "parent_id": food}).status_code == 409
    child = tree[0]["children"][0]["id"]
    assert client.post("/api/categories", json={"name": "Too deep", "parent_id": child}).status_code == 422

    renamed = client.patch(f"/api/categories/{made.json()['id']}", json={"name": "Biryani & rice"}).json()
    assert renamed["name"] == "Biryani & rice"


def test_rules_list_and_delete(session, parsers):  # noqa: F811
    from app.main import app

    client = TestClient(app)
    poll_once(session, FakeSource([tea("a")]))
    t, = by_name(session, "RAVI KUMAR")
    client.patch(f"/api/transactions/{t.id}", json={"category_id": cat_id(session, "Food & drinks/Tea & coffee")})
    rules = client.get("/api/rules").json()
    assert rules[0]["source"] == "learned" and rules[0]["match_value"] == "RAVI KUMAR"
    assert client.delete(f"/api/rules/{rules[0]['id']}").status_code == 204
    assert client.delete(f"/api/rules/{rules[0]['id']}").status_code == 404


def test_category_summary(session, parsers):  # noqa: F811
    from app.main import app

    poll_once(session, FakeSource([
        email("a", BURGER),
        email("b", CRED),
        tea("c", "30.00"),
        email("d", "TEST Rs.100.00 credit a/c 1234 on 2026-11-08 GOOD FLIPPIN BURGERS",
              when=datetime(2026, 11, 8, 6, tzinfo=UTC)),
    ]))
    client = TestClient(app)
    refund = [t for t in by_name(session, "GOOD FLIPPIN BURGERS") if t.direction == "credit"][0]
    eating_out = cat_id(session, "Food & drinks/Eating out")
    client.patch(f"/api/transactions/{refund.id}", json={"kind": "refund", "category_id": eating_out})

    s = client.get("/api/categories/summary", params={"month": "2026-11"}).json()
    assert Decimal(s["total"]) == Decimal("266.00")  # 336 + 30 - 100; the CRED transfer is not spend
    assert (Decimal(s["untagged_total"]), s["untagged_count"]) == (Decimal("30.00"), 1)
    food, = s["parents"]
    assert food["name"] == "Food & drinks" and Decimal(food["total"]) == Decimal("236.00")
    assert [(c["name"], Decimal(c["total"]), c["count"]) for c in food["children"]] == [
        ("Eating out", Decimal("236.00"), 2)
    ]
    card = client.get("/api/categories/summary", params={"month": "2026-11", "account_type": "credit_card"}).json()
    assert card["parents"] == [] and Decimal(card["total"]) == 0


@pytest.mark.parametrize("month", ["2026-13", "x"])
def test_summary_rejects_bad_month(month, session):
    from app.main import app

    assert TestClient(app).get("/api/categories/summary", params={"month": month}).status_code == 422
