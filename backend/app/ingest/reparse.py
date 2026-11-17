"""Re-run the classifier on stored emails after a parser change. No Gmail calls.

    uv run python -m app.ingest.reparse                # unknown emails (default)
    uv run python -m app.ingest.reparse --status all
"""

import argparse
from collections import Counter

from sqlalchemy import select

from app.config import settings
from app.ingest.store import apply_classification
from app.models import RawEmail


def main() -> None:
    from app.db import SessionLocal

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", default="unknown", choices=["unknown", "ignored", "txn", "all"])
    args = ap.parse_args()

    with SessionLocal() as s:
        stmt = select(RawEmail).where(RawEmail.parser_name.is_distinct_from("sender_not_allowed"))
        if args.status != "all":
            stmt = stmt.where(RawEmail.parse_status == args.status)
        before: Counter[str] = Counter()
        after: Counter[str] = Counter()
        for raw in s.scalars(stmt).all():
            before[raw.parse_status] += 1
            after[apply_classification(s, raw, settings.tz)] += 1
        s.commit()
    print(f"before: {dict(before)}\nafter:  {dict(after)}")


if __name__ == "__main__":
    main()
