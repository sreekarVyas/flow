"""Settlements: repayments tagged against earlier payments, in both workflows."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ingest.poller import poll_once
from app.models import RawEmail, Rule, SettlementLink, Split, Transaction
from tests.test_ingest import FakeSource, email, parsers  # noqa: F401  (fixture)

D = Decimal


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


def mail(i: str, amount: str, direction: str, day: int, name: str):
    return email(i, f"TEST Rs.{amount} {direction} a/c 1234 on 2026-11-{day:02} {name}",
                 when=datetime(2026, 11, day, 6, tzinfo=UTC))


def load(session, *specs) -> dict[str, Transaction]:
    """specs: (key, amount, direction, day, name). Returns {key: Transaction}."""
    poll_once(session, FakeSource([mail(k, a, d, day, n) for k, a, d, day, n in specs]))
    raw = {r.gmail_msg_id: r.id for r in session.scalars(select(RawEmail))}
    return {k: session.scalar(select(Transaction).where(Transaction.raw_email_id == raw[k])) for k, *_ in specs}


def split(client, t: Transaction, **people) -> dict:
    r = client.put(f"/api/transactions/{t.id}/splits",
                   json={"mode": "exact", "people": [{"name": n, "value": v} for n, v in people.items()]})
    assert r.status_code == 200, r.text
    return r.json()


def settle(client, t: Transaction, name: str, links: list[tuple[Transaction, str]], **share) -> dict:
    body = {"name": name, "links": [{"transaction_id": e.id, "amount": a, **share} for e, a in links]}
    r = client.put(f"/api/transactions/{t.id}/settlement", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def person(client, name: str) -> dict:
    return next(p for p in client.get("/api/people").json() if p["display_name"].lower() == name.lower())


def share_of(client, t: Transaction, name: str) -> dict:
    row = next(r for r in client.get("/api/transactions", params={"month": "2026-11"}).json() if r["id"] == t.id)
    return next(s for s in row["splits"] if s["person"]["display_name"].lower() == name.lower())


def test_full_repayment_cancels_the_share(session, client, parsers):  # noqa: F811
    tx = load(session, ("a", "10000.00", "debit", 5, "WL VUE ANTHROPIC"), ("b", "7000.00", "credit", 9, "FRIEND A"))
    split(client, tx["a"], Friend="7000")
    body = settle(client, tx["b"], "friend", [(tx["a"], "7000")])
    assert body["kind"] == "settlement" and body["person"]["display_name"] == "Friend"
    assert D(body["unapplied"]) == 0 and D(body["links_out"][0]["split"]["outstanding"]) == 0

    s = share_of(client, tx["a"], "Friend")
    assert (D(s["settled"]), D(s["outstanding"])) == (D("7000.00"), D("0.00"))
    assert D(person(client, "Friend")["net"]) == 0
    summary = client.get("/api/summary", params={"month": "2026-11"}).json()["shared"]
    assert (D(summary["recovered"]), D(summary["owed_to_me"])) == (D("7000.00"), 0)
    # A repayment is not income and not spending.
    cats = client.get("/api/categories/summary", params={"month": "2026-11"}).json()
    assert D(cats["total"]) == D("3000.00")


def test_partial_repayment_leaves_the_rest_outstanding(session, client, parsers):  # noqa: F811
    tx = load(session, ("a", "10000.00", "debit", 5, "SHOP"), ("b", "4000.00", "credit", 9, "FRIEND A"))
    split(client, tx["a"], Friend="7000")
    settle(client, tx["b"], "Friend", [(tx["a"], "4000")])
    assert D(share_of(client, tx["a"], "Friend")["outstanding"]) == D("3000.00")
    assert D(person(client, "Friend")["net"]) == D("3000.00")
    detail = client.get(f"/api/people/{person(client, 'Friend')['id']}").json()
    assert D(detail["history"][0]["outstanding"]) == D("3000.00")
    assert [D(r["amount"]) for r in detail["repayments"]] == [D("4000.00")]
    assert client.get(f"/api/transactions/{tx['b'].id}").json()["person"]["display_name"] == "Friend"
    assert client.get("/api/transactions/999999").status_code == 404


def test_both_workflows_give_the_same_rows(session, client, parsers):  # noqa: F811
    tx = load(session,
              ("a", "1000.00", "debit", 5, "SHOP ONE"), ("b", "400.00", "credit", 9, "FRIEND A"),
              ("c", "1000.00", "debit", 5, "SHOP TWO"), ("d", "400.00", "credit", 9, "FRIEND B"))
    split(client, tx["a"], Asha="500")
    split(client, tx["c"], Ravi="500")
    settle(client, tx["b"], "Asha", [(tx["a"], "400")])  # from the repayment
    r = client.post(f"/api/transactions/{tx['c'].id}/repayments",  # from the original payment
                    json={"settlement_txn_id": tx["d"].id, "amount": "400", "name": "RAVI"})
    assert r.status_code == 200, r.text
    assert D(r.json()["splits"][0]["outstanding"]) == D("100.00")

    session.expire_all()
    for repay, expense in ((tx["b"], tx["a"]), (tx["d"], tx["c"])):
        repay = session.get(Transaction, repay.id)
        (lk,) = repay.links_out
        assert (repay.kind, repay.confirmed, lk.amount, lk.split.transaction_id) == ("settlement", True, D("400.00"), expense.id)
        assert lk.split.outstanding == D("100.00") and repay.person.display_name in ("Asha", "Ravi")


def test_tag_to_unsplit_payment_creates_the_share(session, client, parsers):  # noqa: F811
    tx = load(session,
              ("a", "7000.00", "debit", 5, "BOUGHT FOR FRIEND"), ("b", "7000.00", "credit", 9, "FRIEND A"),
              ("c", "10000.00", "debit", 5, "BIG SHOP"), ("d", "3000.00", "credit", 9, "FRIEND A"))
    # Whole payment was for the friend: the repayment cancels it out.
    settle(client, tx["b"], "Friend", [(tx["a"], "7000")])
    row = next(r for r in client.get("/api/transactions", params={"month": "2026-11"}).json() if r["id"] == tx["a"].id)
    assert D(row["my_share"]) == 0
    assert (row["splits"][0]["origin"], D(row["splits"][0]["outstanding"])) == ("link", 0)

    # Part of it: the share follows the link, and goes away with it.
    body = settle(client, tx["d"], "Friend", [(tx["c"], "3000")])
    assert D(share_of(client, tx["c"], "Friend")["share_amount"]) == D("3000.00")
    client.delete(f"/api/settlement-links/{body['links_out'][0]['id']}")
    session.expire_all()
    assert session.get(Transaction, tx["c"].id).splits == []
    assert session.get(Transaction, tx["c"].id).my_share == D("10000.00")
    assert D(person(client, "Friend")["net"]) == D("-3000.00")  # still counts, untagged


def test_explicit_share_on_unsplit_payment(session, client, parsers):  # noqa: F811
    tx = load(session, ("a", "10000.00", "debit", 5, "SHOP"), ("b", "4000.00", "credit", 9, "FRIEND A"))
    body = settle(client, tx["b"], "Friend", [(tx["a"], "4000")], share="7000")
    assert D(body["links_out"][0]["split"]["outstanding"]) == D("3000.00")
    client.delete(f"/api/settlement-links/{body['links_out'][0]['id']}")
    assert D(share_of(client, tx["a"], "Friend")["share_amount"]) == D("7000.00")  # a real share stays


def test_one_repayment_over_two_payments(session, client, parsers):  # noqa: F811
    tx = load(session,
              ("a", "500.00", "debit", 3, "DINNER"), ("b", "700.00", "debit", 4, "MOVIE"),
              ("c", "600.00", "credit", 9, "FRIEND A"))
    client.put(f"/api/transactions/{tx['a'].id}/splits", json={"people": [{"name": "Friend"}]})
    client.put(f"/api/transactions/{tx['b'].id}/splits", json={"people": [{"name": "friend"}]})
    body = settle(client, tx["c"], "Friend", [(tx["a"], "250"), (tx["b"], "350")])
    assert D(body["unapplied"]) == 0 and len(body["links_out"]) == 2
    assert [D(share_of(client, tx[k], "Friend")["outstanding"]) for k in "ab"] == [0, 0]
    assert D(person(client, "Friend")["net"]) == 0


def test_overpayment_then_return_nets_out(session, client, parsers):  # noqa: F811
    tx = load(session,
              ("a", "3000.00", "debit", 3, "TRIP"), ("b", "2500.00", "credit", 9, "FRIEND A"),
              ("c", "1000.00", "debit", 10, "FRIEND A"))
    split(client, tx["a"], Friend="1500")
    settle(client, tx["b"], "Friend", [(tx["a"], "2500")])
    assert D(share_of(client, tx["a"], "Friend")["outstanding"]) == D("-1000.00")  # overpaid
    assert D(person(client, "Friend")["net"]) == D("-1000.00")  # I owe it back

    body = settle(client, tx["c"], "Friend", [(tx["a"], "1000")])  # the money I sent back
    assert body["links_out"][0]["settles"] is False
    s = share_of(client, tx["a"], "Friend")
    assert (D(s["settled"]), D(s["outstanding"])) == (D("1500.00"), 0)
    assert D(person(client, "Friend")["net"]) == 0
    assert D(client.get("/api/summary", params={"month": "2026-11"}).json()["shared"]["recovered"]) == D("1500.00")
    # Both real transactions stay as they were.
    session.expire_all()
    assert [session.get(Transaction, tx[k].id).amount for k in "bc"] == [D("2500.00"), D("1000.00")]


def test_untagged_repayment_counts_in_balance(session, client, parsers):  # noqa: F811
    tx = load(session, ("a", "1000.00", "debit", 3, "SHOP"), ("b", "5000.00", "credit", 9, "FRIEND A"))
    split(client, tx["a"], Friend="600")
    body = settle(client, tx["b"], "Friend", [])
    assert D(body["unapplied"]) == D("5000.00")
    p = person(client, "Friend")
    assert (D(p["received"]), D(p["net"])) == (D("5000.00"), D("-4400.00"))


def test_validation(session, client, parsers):  # noqa: F811
    tx = load(session,
              ("a", "1000.00", "debit", 3, "SHOP"), ("b", "300.00", "credit", 9, "FRIEND A"),
              ("c", "200.00", "debit", 9, "FRIEND A"), ("d", "50.00", "credit", 9, "SALARY CO SALARY"))
    split(client, tx["a"], Friend="500")
    put = lambda t, body: client.put(f"/api/transactions/{t.id}/settlement", json=body)  # noqa: E731

    assert put(tx["b"], {"links": []}).status_code == 422  # no person
    r = put(tx["b"], {"name": "Friend", "links": [{"transaction_id": tx["a"].id, "amount": "301"}]})
    assert r.status_code == 422 and "more than the repayment" in r.json()["detail"]
    assert put(tx["b"], {"name": "Friend", "links": [{"transaction_id": tx["d"].id, "amount": "10"}]}).status_code == 422
    r = put(tx["c"], {"name": "Other", "links": [{"transaction_id": tx["a"].id, "amount": "100"}]})
    assert r.status_code == 422 and "no share" in r.json()["detail"]
    r = put(tx["b"], {"name": "Other", "links": [{"transaction_id": tx["a"].id, "amount": "300", "share": "900"}]})
    assert r.status_code == 422 and "not already shared" in r.json()["detail"]
    assert put(tx["a"], {"name": "Friend", "links": []}).status_code == 422  # a split payment is not a repayment

    settle(client, tx["b"], "Friend", [(tx["a"], "300")])
    # Tagging from the payment side with a different person is refused while the repayment has links.
    r = client.post(f"/api/transactions/{tx['a'].id}/repayments",
                    json={"settlement_txn_id": tx["b"].id, "amount": "100", "name": "Someone Else"})
    assert r.status_code == 422 and "remove this repayment's links" in r.json()["detail"]
    # A full replace with a new person drops the old links.
    moved = put(tx["b"], {"name": "Someone Else", "links": []}).json()
    assert moved["person"]["display_name"] == "Someone Else" and moved["links_out"] == []
    settle(client, tx["b"], "Friend", [(tx["a"], "300")])
    r = client.put(f"/api/transactions/{tx['a'].id}/splits", json={"people": []})
    assert r.status_code == 409 and "repayments" in r.json()["detail"]

    # Turning the repayment into something else removes its links.
    assert client.patch(f"/api/transactions/{tx['b'].id}", json={"kind": "income"}).status_code == 200
    session.expire_all()
    assert session.scalar(select(SettlementLink)) is None
    assert session.get(Transaction, tx["b"].id).person_id is None


def test_suggestions_and_candidates(session, client, parsers):  # noqa: F811
    tx = load(session,
              ("a", "1000.00", "debit", 3, "OLD SHOP"), ("b", "800.00", "debit", 6, "NEW SHOP"),
              ("c", "300.00", "credit", 9, "A B FRIEND"), ("d", "200.00", "credit", 10, "A B FRIEND"))
    split(client, tx["a"], Friend="500")
    settle(client, tx["c"], "Friend", [(tx["a"], "300")])

    # The bank-printed name is remembered, so the next credit from it suggests the person.
    cand = client.get(f"/api/transactions/{tx['d'].id}/settle-candidates").json()
    assert cand["suggested_person"]["display_name"] == "Friend"
    first = cand["items"][0]
    assert first["transaction"]["id"] == tx["a"].id and D(first["share"]["outstanding"]) == D("200.00")

    reps = client.get(f"/api/transactions/{tx['a'].id}/repayment-candidates").json()["items"]
    assert [r["transaction"]["id"] for r in reps[:2]] == [tx["c"].id, tx["d"].id]
    assert D(reps[0]["linked_amount"]) == D("300.00")


def test_settlement_kind_is_never_learned_and_survives_reparse(session, client, parsers):  # noqa: F811
    from app.config import settings
    from app.ingest.store import apply_classification

    tx = load(session, ("a", "1000.00", "debit", 3, "SHOP"), ("b", "200.00", "debit", 9, "FRIEND A"))
    client.patch(f"/api/transactions/{tx['b'].id}", json={"kind": "settlement"})
    assert session.scalar(select(Rule).where(Rule.source == "learned")) is None

    split(client, tx["a"], Friend="500")
    tx2 = load(session, ("c", "500.00", "credit", 10, "FRIEND A"))
    settle(client, tx2["c"], "Friend", [(tx["a"], "500")])
    session.expire_all()
    for raw in session.scalars(select(RawEmail)).all():
        apply_classification(session, raw, settings.tz)
    session.commit()
    c = session.get(Transaction, tx2["c"].id)
    assert (c.kind, c.person.display_name, len(c.links_out)) == ("settlement", "Friend", 1)
    assert session.scalar(select(Split)).outstanding == 0


# ---------- nicknames for payment sources ----------


def with_vpa(session, t: Transaction, vpa: str) -> Transaction:
    t.vpa_or_merchant = vpa
    session.commit()
    return t


def test_same_nickname_on_two_upi_ids_is_one_person(session, client, parsers):  # noqa: F811
    tx = load(session,
              ("a", "1000.00", "debit", 3, "SHOP"),
              ("b", "200.00", "credit", 9, "A B FRIEND"), ("c", "300.00", "credit", 10, "A B FRIEND"),
              ("d", "50.00", "credit", 11, "A B FRIEND"))
    with_vpa(session, tx["b"], "****11@ybl")
    with_vpa(session, tx["c"], "****22@okaxis")
    with_vpa(session, tx["d"], "****11@ybl")

    src = client.get(f"/api/transactions/{tx['b'].id}/source").json()
    assert (src["person"], src["known"], src["suggestion"]) == (None, False, "A B Friend")

    first = client.put(f"/api/transactions/{tx['b'].id}/settlement",
                       json={"nickname": "Prajwala", "links": [{"transaction_id": tx["a"].id, "amount": "200"}]}).json()

    # Another UPI ID with the same printed name: suggested, not assumed.
    src = client.get(f"/api/transactions/{tx['c'].id}/source").json()
    assert (src["person"]["display_name"], src["known"]) == ("Prajwala", False)
    second = client.put(f"/api/transactions/{tx['c'].id}/settlement",
                        json={"nickname": "  PRAJWALA ", "links": [{"transaction_id": tx["a"].id, "amount": "300"}]}).json()
    assert second["person"]["id"] == first["person"]["id"]

    # The first UPI ID is now known: its next payment gets the nickname without asking.
    src = client.get(f"/api/transactions/{tx['d'].id}/source").json()
    assert (src["person"]["display_name"], src["known"]) == ("Prajwala", True)

    p = person(client, "prajwala")
    detail = client.get(f"/api/people/{p['id']}").json()
    assert sorted(s["vpa"] for s in detail["sources"]) == ["****11@YBL", "****22@OKAXIS"]
    assert D(share_of(client, tx["a"], "Prajwala")["share_amount"]) == D("500.00")  # one share, two repayments
    assert len(client.get("/api/people").json()) == 1

    # Forget a wrongly nicknamed UPI ID: past repayments stay.
    client.delete(f"/api/payment-sources/{detail['sources'][0]['id']}")
    assert len(client.get(f"/api/people/{p['id']}").json()["sources"]) == 1
    assert D(person(client, "prajwala")["received"]) == D("500.00")


def test_merge_two_nicknames(session, client, parsers):  # noqa: F811
    tx = load(session,
              ("a", "1000.00", "debit", 3, "SHOP"),
              ("b", "200.00", "credit", 9, "FRIEND ONE"), ("c", "300.00", "credit", 10, "FRIEND TWO"))
    split(client, tx["a"], Praj="400", Prajwala="300")
    settle(client, tx["b"], "Praj", [(tx["a"], "200")])
    settle(client, tx["c"], "Prajwala", [(tx["a"], "300")])
    src, dst = person(client, "Praj"), person(client, "Prajwala")

    r = client.post(f"/api/people/{src['id']}/merge", json={"into_id": dst["id"]})
    assert r.status_code == 200, r.text
    merged = r.json()
    assert (D(merged["owed_to_me"]), D(merged["received"]), D(merged["net"])) == (D("700.00"), D("500.00"), D("200.00"))
    s = share_of(client, tx["a"], "Prajwala")
    assert (D(s["share_amount"]), D(s["settled"]), len(s["links"])) == (D("700.00"), D("500.00"), 2)
    assert [p["display_name"] for p in client.get("/api/people").json()] == ["Prajwala"]
    assert client.get(f"/api/transactions/{tx['b'].id}").json()["person"]["display_name"] == "Prajwala"
    detail = client.get(f"/api/people/{dst['id']}").json()
    assert {x["printed_name"] for x in detail["sources"]} == {"FRIEND ONE", "FRIEND TWO"}
    assert client.post(f"/api/people/{dst['id']}/merge", json={"into_id": dst["id"]}).status_code == 422


def test_tag_from_payment_with_nickname(session, client, parsers):  # noqa: F811
    tx = load(session, ("a", "1000.00", "debit", 3, "SHOP"), ("b", "400.00", "credit", 9, "A B FRIEND"))
    split(client, tx["a"], Prajwala="500")
    r = client.post(f"/api/transactions/{tx['a'].id}/repayments",
                    json={"settlement_txn_id": tx["b"].id, "amount": "400", "nickname": "prajwala"})
    assert r.status_code == 200, r.text
    assert D(r.json()["splits"][0]["outstanding"]) == D("100.00")
    src = client.get(f"/api/transactions/{tx['b'].id}/source").json()
    assert (src["person"]["display_name"], src["known"]) == ("Prajwala", True)
    r = client.post(f"/api/transactions/{tx['a'].id}/repayments", json={"settlement_txn_id": tx["a"].id, "amount": "1"})
    assert r.status_code == 422
