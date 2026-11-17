"""Show what kinds of alert emails are stored, to write parsers from real samples.

    uv run python -m app.ingest.survey                 # unknown emails (default)
    uv run python -m app.ingest.survey --status all    # every email
    uv run python -m app.ingest.survey --samples 2 --chars 1500

Long digit runs (account, card and reference numbers) are masked except the last 4 digits.
"""

import argparse
import re
from collections import Counter, defaultdict

from sqlalchemy import func, select

from app.models import RawEmail


def mask_digits(text: str) -> str:
    return re.sub(r"\d{6,}", lambda m: "X" * (len(m.group()) - 4) + m.group()[-4:], text)


def subject_shape(subject: str) -> str:
    return re.sub(r"\d", "#", subject).strip()


def main() -> None:
    from app.db import SessionLocal

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", default="unknown", choices=["unknown", "ignored", "txn", "all"])
    ap.add_argument("--samples", type=int, default=1, help="sample bodies per group")
    ap.add_argument("--chars", type=int, default=1200, help="max chars per sample body")
    args = ap.parse_args()

    with SessionLocal() as s:
        totals = dict(s.execute(select(RawEmail.parse_status, func.count()).group_by(RawEmail.parse_status)).all())
        print(f"Stored emails by status: {totals}\n")

        stmt = select(RawEmail).order_by(RawEmail.received_at)
        if args.status != "all":
            stmt = stmt.where(RawEmail.parse_status == args.status)
        groups: dict[tuple[str, str], list[RawEmail]] = defaultdict(list)
        for raw in s.scalars(stmt):
            groups[(raw.sender, subject_shape(raw.subject))].append(raw)

        sizes = Counter({k: len(v) for k, v in groups.items()})
        for (sender, shape), n in sizes.most_common():
            rows = groups[(sender, shape)]
            print("=" * 100)
            print(f"[{n:>3}] {sender} | {shape} | status={rows[0].parse_status} parser={rows[0].parser_name}")
            for raw in rows[: args.samples]:
                print(f"--- gmail_msg_id={raw.gmail_msg_id} received={raw.received_at:%Y-%m-%d %H:%M %Z}")
                print(mask_digits((raw.body_text or "<no body>")[: args.chars]))
        print("=" * 100)
        print(f"{len(groups)} groups, {sum(sizes.values())} emails")


if __name__ == "__main__":
    main()
