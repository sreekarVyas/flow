"""Re-run the category rules on all unconfirmed transactions. No Gmail calls.

    uv run python -m app.categorize
    uv run python -m app.categorize --untagged     # also list payees with no category
"""

import argparse
from collections import Counter

from sqlalchemy import select

from app.categorize.rules import CATEGORIZABLE_KINDS, auto_categorize, load_rules
from app.models import Transaction


def main() -> None:
    from app.db import SessionLocal

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--untagged", action="store_true", help="list expense payees with no category")
    args = ap.parse_args()

    with SessionLocal() as s:
        rules = load_rules(s)
        counts: Counter[str] = Counter()
        untagged: Counter[str] = Counter()
        for t in s.scalars(select(Transaction).order_by(Transaction.ts)):
            if t.confirmed:
                counts["confirmed (kept)"] += 1
                continue
            auto_categorize(t, rules)
            if t.category_id is not None:
                counts["tagged by rule"] += 1
            elif t.kind in CATEGORIZABLE_KINDS:
                counts["untagged"] += 1
                untagged[t.counterparty_name or t.vpa_or_merchant or "?"] += 1
            else:
                counts[f"no category ({t.kind or 'to review'})"] += 1
        s.commit()

    for k, v in counts.most_common():
        print(f"{v:5}  {k}")
    if args.untagged and untagged:
        print("\nuntagged payees:")
        for name, n in untagged.most_common():
            print(f"{n:5}  {name}")


if __name__ == "__main__":
    main()
