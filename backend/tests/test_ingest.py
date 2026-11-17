"""Poll, reparse and API against a real Postgres test DB, with a fake Gmail source."""

import re
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import app.parsers as registry
from app.gmail.client import FetchedEmail
from app.ingest.poller import poll_once
from app.models import Account, RawEmail, Transaction
from app.parsers.base import EmailInput, ParsedTxn

BANK = "alerts@hdfcbank.bank.in"


class FakeFormatParser:
    """A made-up format for tests only. Real parsers come from real samples."""

    name = "test_format"
    senders = (BANK,)
    pat = re.compile(r"TEST Rs\.([\d.]+) (debit|credit) a/c (\d{4}) on (\d{4}-\d{2}-\d{2}) (.+)")

    def parse(self, email: EmailInput) -> ParsedTxn | None:
        m = self.pat.search(email.body_text)
        if not m:
            return None
        return ParsedTxn("HDFC", "bank", m[3], Decimal(m[1]), m[2], date.fromisoformat(m[4]),
                         counterparty_name=m[5])


def email(i: str, body: str, sender: str = BANK, when: datetime | None = None) -> FetchedEmail:
    return FetchedEmail(i, "t" + i, 1, sender, f"subject {i}", when or datetime(2026, 11, 5, 6, tzinfo=UTC), body, None)


class FakeSource:
    def __init__(self, emails: list[FetchedEmail]):
        self.emails = {e.gmail_msg_id: e for e in emails}
        self.queries: list[str] = []
        self.gets = 0

    def profile(self) -> dict:
        return {"historyId": "12345", "emailAddress": "me@example.com"}

    def list_message_ids(self, query: str) -> list[str]:
        self.queries.append(query)
        return list(reversed(self.emails))  # newest first, like Gmail

    def get_message(self, msg_id: str) -> FetchedEmail:
        self.gets += 1
        return self.emails[msg_id]


@pytest.fixture
def parsers(monkeypatch):
    monkeypatch.setattr(registry, "TXN_PARSERS", [FakeFormatParser()])


EMAILS = [
    email("a", "TEST Rs.336.00 debit a/c 1234 on 2026-11-05 GOOD FLIPPIN BURGERS"),
    email("b", "TEST Rs.37019.00 debit a/c 1234 on 2026-11-06 CRED CLUB"),
    email("c", "TEST Rs.120.00 debit a/c 1234 on 2026-10-31 TEA", when=datetime(2026, 11, 1, 3, tzinfo=UTC)),
    email("d", "some new alert format nobody parses yet"),
    email("e", "phishing body", sender="hdfc-alerts@evil.example"),
]


def test_poll_is_idempotent_and_filters(session, parsers):
    src = FakeSource(EMAILS)
    r1 = poll_once(session, src)
    assert (r1["fetched"], r1["txn"], r1["ignored"], r1["unknown"]) == (5, 3, 1, 1)
    assert "from:(alerts@hdfcbank.bank.in OR onlinesbicard@sbicard.com) after:" in src.queries[0]

    r2 = poll_once(session, src)
    assert r2["fetched"] == 0 and src.gets == 5
    assert session.scalar(select(func.count()).select_from(Transaction)) == 3
    assert session.scalar(select(func.count()).select_from(Account)) == 1

    foreign = session.scalar(select(RawEmail).where(RawEmail.gmail_msg_id == "e"))
    assert foreign.body_text is None and foreign.parser_name == "sender_not_allowed"

    cred = session.scalar(select(Transaction).where(Transaction.counterparty_name == "CRED CLUB"))
    assert cred.kind == "transfer"


def test_reparse_picks_up_new_parser(session, monkeypatch):
    from app.config import settings
    from app.ingest.store import apply_classification

    poll_once(session, FakeSource(EMAILS[:2]))
    assert session.scalar(select(func.count()).select_from(Transaction)) == 0

    monkeypatch.setattr(registry, "TXN_PARSERS", [FakeFormatParser()])
    for raw in session.scalars(select(RawEmail)).all():
        apply_classification(session, raw, settings.tz)
    session.commit()
    assert session.scalar(select(func.count()).select_from(Transaction)) == 2

    # Parser removed again -> unconfirmed transactions go away.
    monkeypatch.setattr(registry, "TXN_PARSERS", [])
    for raw in session.scalars(select(RawEmail)).all():
        apply_classification(session, raw, settings.tz)
    session.commit()
    assert session.scalar(select(func.count()).select_from(Transaction)) == 0


def test_api_month_filter_and_summary(session, parsers):
    from app.main import app

    poll_once(session, FakeSource(EMAILS))
    client = TestClient(app)

    rows = client.get("/api/transactions", params={"month": "2026-11"}).json()
    assert [r["counterparty_name"] for r in rows] == ["CRED CLUB", "GOOD FLIPPIN BURGERS"]  # Oct 31 excluded
    assert rows[0]["amount"] == "37019.00" and rows[0]["account"]["name"] == "HDFC ••1234"

    assert client.get("/api/transactions", params={"month": "2026-11", "account_type": "credit_card"}).json() == []
    assert client.get("/api/transactions", params={"month": "2026-13"}).status_code == 422

    s = client.get("/api/summary", params={"month": "2026-11"}).json()
    assert s["bank"]["debit_count"] == 2
    assert Decimal(s["bank"]["debit_total"]) == Decimal("37355.00")
    assert Decimal(s["bank"]["expense_total"]) == Decimal("336.00")
    assert Decimal(s["bank"]["transfer_total"]) == Decimal("37019.00")
    assert s["unknown_emails"] == 1 and s["last_poll_result"]["fetched"] == 5

    unknown = client.get("/api/raw-emails", params={"status": "unknown"}).json()
    assert [u["subject"] for u in unknown] == ["subject d"]


def test_migration_matches_models(migrated_db):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.models import Base

    with migrated_db.connect() as c:
        diff = compare_metadata(MigrationContext.configure(c), Base.metadata)
    assert diff == []
