"""Poll Gmail for alert emails, store them, classify them.

Run once by hand:  uv run python -m app.ingest.poller [--since 2026-11-01]
"""

import argparse
import logging
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.gmail.client import FetchedEmail
from app.ingest.store import apply_classification
from app.models import GmailState, RawEmail

log = logging.getLogger(__name__)

# Re-read this much before the last poll, to cover clock skew and late delivery.
POLL_OVERLAP = timedelta(days=2)


class MailSource(Protocol):
    def profile(self) -> dict: ...
    def list_message_ids(self, query: str) -> list[str]: ...
    def get_message(self, msg_id: str) -> FetchedEmail: ...


def build_query(senders: list[str], after: datetime) -> str:
    # Epoch seconds are exact; date strings in Gmail search use the account's time zone.
    return f"from:({' OR '.join(senders)}) after:{int(after.timestamp())}"


def query_start(state: GmailState | None, since: date | None) -> datetime:
    """`since` wins. Else the first poll starts at the backfill date, later polls near the last poll.

    One day of margin is cheap and safe: the API filters rows by transaction date, not email date.
    """
    start = since or (settings.backfill_start if state is None or state.last_poll_at is None else None)
    if start is not None:
        return datetime.combine(start - timedelta(days=1), time(0), settings.tz)
    assert state is not None and state.last_poll_at is not None
    return state.last_poll_at - POLL_OVERLAP


def get_state(session: Session) -> GmailState:
    state = session.get(GmailState, 1)
    if state is None:
        state = GmailState(id=1)
        session.add(state)
        session.flush()
    return state


def poll_once(session: Session, source: MailSource, since: date | None = None) -> dict:
    state = get_state(session)
    senders = [s.lower() for s in settings.alert_senders]
    query = build_query(senders, query_start(state, since))

    ids = source.list_message_ids(query)
    known = set(
        session.scalars(select(RawEmail.gmail_msg_id).where(RawEmail.gmail_msg_id.in_(ids)))
    ) if ids else set()
    new_ids = [i for i in ids if i not in known]

    counts: Counter[str] = Counter()
    for msg_id in reversed(new_ids):  # oldest first
        fe = source.get_message(msg_id)
        allowed = fe.sender in senders
        raw = RawEmail(
            gmail_msg_id=fe.gmail_msg_id,
            thread_id=fe.thread_id,
            history_id=fe.history_id,
            sender=fe.sender,
            subject=fe.subject,
            received_at=fe.received_at,
            # `from:` also matches display names. Do not keep bodies of other senders.
            body_text=fe.body_text if allowed else None,
            body_html=fe.body_html if allowed else None,
            parse_status="unknown",
        )
        session.add(raw)
        session.flush()
        if allowed:
            status = apply_classification(session, raw, settings.tz)
        else:
            raw.parse_status, raw.parser_name = "ignored", "sender_not_allowed"
            status = "ignored"
        counts[status] += 1
        session.commit()  # commit per email, so a crash keeps earlier progress

    result = {
        "query": query,
        "listed": len(ids),
        "fetched": len(new_ids),
        "txn": counts["txn"],
        "ignored": counts["ignored"],
        "unknown": counts["unknown"],
    }
    state = get_state(session)
    state.last_history_id = int(source.profile()["historyId"])
    state.last_poll_at = datetime.now(UTC)
    state.last_poll_result = result
    session.commit()
    log.info("poll: %s", result)
    return result


def main() -> None:
    from app.db import SessionLocal
    from app.gmail.client import GmailClient

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", type=date.fromisoformat, help="re-list mail from this date (YYYY-MM-DD)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as session:
        print(poll_once(session, GmailClient(), since=args.since))


if __name__ == "__main__":
    main()
