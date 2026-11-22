"""People (case-insensitive) and expense splits: share maths, API, balances, summaries."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ingest.poller import poll_once
from app.ledger import compute_shares
from app.models import Person, RawEmail, Split, Transaction
from app.people import clean_name, name_key
from tests.test_ingest import FakeSource, email, parsers  # noqa: F401  (fixture)

D = Decimal


# ---------- unit ----------


def test_name_key_ignores_case_and_spaces():
    assert name_key("  John   Smith ") == "john smith" == name_key("JOHN SMITH")
    assert clean_name("  John   Smith ") == "John Smith"


@pytest.mark.parametrize(
    ("amount", "mode", "values", "include_me", "expected"),
    [
        ("1000", "equal", [None, None], True, ["333.33", "333.33"]),  # me: 333.34
        ("1000", "equal", [None, None, None], False, ["333.34", "333.33", "333.33"]),
        ("500", "equal", [None], True, ["250.00"]),
        ("10000", "exact", ["7000"], True, ["7000.00"]),
        ("10000", "percent", ["30", "25.5"], True, ["3000.00", "2550.00"]),
        ("99.99", "percent", ["33.33"], True, ["33.32"]),  # rounds down; the paisa stays with me
    ],
)
def test_compute_shares(amount, mode, values, include_me, expected):
    vals = [D(v) if v else None for v in values]
    assert compute_shares(D(amount), mode, vals, include_me) == [D(e) for e in expected]


@pytest.mark.parametrize(
    ("mode", "values", "message"),
    [
        ("exact", ["600", "500"], "more than the amount"),
        ("exact", [None], "more than zero"),
        ("percent", ["60", "50"], "more than 100"),
        ("equal", [None] * 5, "rounds to zero"),
    ],
)
def test_compute_shares_rejects(mode, values, message):
    amount = D("0.04") if mode == "equal" else D("1000")
    with pytest.raises(ValueError, match=message):
        compute_shares(amount, mode, [D(v) if v else None for v in values])


# ---------- DB ----------

BIG = "TEST Rs.10000.00 debit a/c 1234 on 2026-11-05 WL VUE ANTHROPIC"
SMALL = "TEST Rs.500.00 debit a/c 1234 on 2026-11-06 GOOD FLIPPIN BURGERS"
CREDIT = "TEST Rs.700.00 credit a/c 1234 on 2026-11-07 SOME FRIEND"


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


def txn(session, name: str) -> Transaction:
    return session.scalar(select(Transaction).where(Transaction.counterparty_name == name))


def test_people_are_case_insensitive(session, client):
    r1 = client.post("/api/people", json={"name": "John"})
    r2 = client.post("/api/people", json={"name": "  JOHN "})
    r3 = client.post("/api/people", json={"name": "john"})
    assert (r1.status_code, r2.status_code, r3.status_code) == (201, 200, 200)
    assert r1.json()["id"] == r2.json()["id"] == r3.json()["id"]
    assert r3.json()["display_name"] == "John"  # first spelling is kept
    assert session.scalar(select(Person).where(Person.name_key == "john")) is not None

    other = client.post("/api/people", json={"name": "Jane Doe"}).json()
    assert [p["display_name"] for p in client.get("/api/people", params={"q": "DOE"}).json()] == ["Jane Doe"]
    assert client.patch(f"/api/people/{other['id']}", json={"display_name": "JOHN"}).status_code == 409
    renamed = client.patch(f"/api/people/{other['id']}", json={"display_name": "Jane  D"}).json()
    assert renamed["display_name"] == "Jane D"
    assert client.post("/api/people", json={"name": "   "}).status_code == 422


def test_split_example_and_balances(session, client, parsers):  # noqa: F811
    poll_once(session, FakeSource([email("a", BIG)]))
    big = txn(session, "WL VUE ANTHROPIC")

    r = client.put(f"/api/transactions/{big.id}/splits",
                   json={"mode": "exact", "people": [{"name": "Friend", "value": "7000"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (D(body["my_share"]), body["confirmed"]) == (D("3000.00"), True)
    assert [(s["person"]["display_name"], D(s["share_amount"]), s["paid_by"]) for s in body["splits"]] == [
        ("Friend", D("7000.00"), "me")
    ]

    # Money summary: full amount stays visible; my share is what counts.
    s = client.get("/api/summary", params={"month": "2026-11"}).json()
    assert D(s["bank"]["expense_total"]) == D("10000.00")
    assert D(s["bank"]["my_share_total"]) == D("3000.00")
    assert (D(s["shared"]["others_share"]), D(s["shared"]["owed_to_me"]), s["shared"]["people_owing"]) == (
        D("7000.00"), D("7000.00"), 1,
    )
    cats = client.get("/api/categories/summary", params={"month": "2026-11"}).json()
    assert D(cats["total"]) == D("3000.00")
    assert cats["parents"][0]["name"] == "Subscriptions" and D(cats["parents"][0]["total"]) == D("3000.00")

    friend, = client.get("/api/people").json()
    assert (D(friend["owed_to_me"]), D(friend["net"]), friend["shares"]) == (D("7000.00"), D("7000.00"), 1)
    detail = client.get(f"/api/people/{friend['id']}").json()
    assert detail["history"][0]["transaction"]["counterparty_name"] == "WL VUE ANTHROPIC"

    # A person with shares cannot be deleted; the transaction list carries the split.
    assert client.delete(f"/api/people/{friend['id']}").status_code == 409
    row, = client.get("/api/transactions", params={"month": "2026-11"}).json()
    assert D(row["my_share"]) == D("3000.00") and len(row["splits"]) == 1


def test_resplit_keeps_ids_and_empty_removes(session, client, parsers):  # noqa: F811
    poll_once(session, FakeSource([email("a", SMALL)]))
    t = txn(session, "GOOD FLIPPIN BURGERS")
    url = f"/api/transactions/{t.id}/splits"

    first = client.put(url, json={"people": [{"name": "Asha"}]}).json()
    assert D(first["my_share"]) == D("250.00")
    split_id = first["splits"][0]["id"]

    second = client.put(url, json={"people": [{"name": "ASHA"}, {"name": "Ravi"}]}).json()
    assert [D(s["share_amount"]) for s in second["splits"]] == [D("166.66"), D("166.66")]
    assert D(second["my_share"]) == D("166.68")
    assert second["splits"][0]["id"] == split_id  # same person, same row

    third = client.put(url, json={"people": []}).json()
    assert third["splits"] == [] and D(third["my_share"]) == D("500.00")
    assert session.scalar(select(Split)) is None


def test_split_validation(session, client, parsers):  # noqa: F811
    poll_once(session, FakeSource([email("a", SMALL), email("b", CREDIT, when=datetime(2026, 11, 7, 6, tzinfo=UTC))]))
    t = txn(session, "GOOD FLIPPIN BURGERS")
    url = f"/api/transactions/{t.id}/splits"

    assert client.put(url, json={"mode": "exact", "people": [{"name": "A", "value": "600"}]}).status_code == 422
    assert client.put(url, json={"people": [{"name": "Ann"}, {"name": "ann"}]}).status_code == 422
    assert client.put(url, json={"people": [{"person_id": 999999}]}).status_code == 422
    assert client.put(url, json={"people": [{}]}).status_code == 422

    credit = txn(session, "SOME FRIEND")
    r = client.put(f"/api/transactions/{credit.id}/splits", json={"people": [{"name": "A"}]})
    assert r.status_code == 422 and "only expenses" in r.json()["detail"]

    # Changing the kind of a split expense needs the split removed first.
    client.put(url, json={"people": [{"name": "A"}]})
    assert client.patch(f"/api/transactions/{t.id}", json={"kind": "transfer"}).status_code == 409


def test_reparse_keeps_splits(session, client, parsers):  # noqa: F811
    from app.config import settings
    from app.ingest.store import apply_classification

    poll_once(session, FakeSource([email("a", SMALL)]))
    t = txn(session, "GOOD FLIPPIN BURGERS")
    client.put(f"/api/transactions/{t.id}/splits", json={"people": [{"name": "Asha"}]})

    session.expire_all()
    for raw in session.scalars(select(RawEmail)).all():
        apply_classification(session, raw, settings.tz)
    session.commit()
    t = txn(session, "GOOD FLIPPIN BURGERS")
    assert [s.share_amount for s in t.splits] == [D("250.00")] and t.my_share == D("250.00")
