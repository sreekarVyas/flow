# Flow — personal expense tracker

Phase 1 slice: poll Gmail for HDFC / SBI Card alert emails, store them, parse transactions,
show November 2026 in a web UI. Local only. See `CLAUDE.md` for the full design.

| Part | Stack |
|---|---|
| DB | Postgres 17 (Docker Compose, `127.0.0.1:5432`) |
| Backend | FastAPI, SQLAlchemy 2.0, Alembic, psycopg 3, uv (`backend/`) |
| Frontend | React 19, Vite 7, TypeScript, Tailwind CSS v4, TanStack Query (`frontend/`) |

## 1. One-time tooling

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh                                   # uv (Python deps)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash   # nvm
nvm install 22                                                                    # Node 22 LTS
```

## 2. One-time Google Cloud setup (about 15 min)

1. Go to <https://console.cloud.google.com> → create a project (for example `flow`).
2. **APIs & Services → Library →** search "Gmail API" → **Enable**.
3. **Google Auth Platform → Get started**:
   - Branding: app name `Flow`, your support email, your developer contact email.
   - Audience: **External**. Finish the wizard.
4. **Data Access → Add or remove scopes →** tick `.../auth/gmail.readonly` → **Update → Save**.
5. **Audience → Publish app → Confirm.** Status must be **In production**.
   In "Testing", refresh tokens expire after 7 days.
6. **Clients → Create client →** type **Desktop app**, name `flow-local` → **Create** → **Download JSON**.
7. Save the file as `backend/secrets/client_secret.json` (the folder is git-ignored).

At consent, Google shows "Google hasn't verified this app". Click **Advanced → Go to Flow (unsafe)**.
This is expected for a personal app.

## 3. Run

```sh
docker compose up -d                       # Postgres (also creates flow_test)

cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.gmail.auth            # browser consent, once
uv run python -m app.ingest.poller         # first poll: mail since 31 Oct
uv run python -m app.ingest.survey         # see unparsed email formats
uv run python -m app.categorize            # tag stored transactions with the category rules
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

cd ../frontend
npm install
npm run dev                                # http://127.0.0.1:5173
```

The API polls Gmail every 10 min (`POLL_INTERVAL_SECONDS`). The UI has a **Sync now** button.

## Parser workflow

1. Mail lands in `raw_emails` with `parse_status` = `txn`, `ignored` or `unknown`.
2. `uv run python -m app.ingest.survey` groups `unknown` emails by sender + subject and prints masked samples.
3. Add a parser (`app/parsers/<bank>.py`) or an ignore rule, register it in `app/parsers/__init__.py`,
   and add a masked fixture + test in `backend/tests/`.
4. `uv run python -m app.ingest.reparse` re-classifies stored emails. No Gmail calls.

Transaction parsers always run before ignore rules. An ignore rule never matches an email that
says "debited / credited / spent …" with an amount, so a transaction cannot be silently dropped.

## Categories & rules

- Migration `0002` seeds a two-level category list (19 parents) and built-in name rules.
- New transactions get a category from the rules at ingest (`category_source = rule`, not confirmed).
  Only `expense` and `refund` transactions carry a category.
- Rule order: a learned **payee** rule (exact name), then the longest **name contains** / **UPI ID contains** match.
  Name rules look at the payee name only, because the masked VPA carries PSP names such as `rxairtel`.
- Tag by hand in the UI (tap a row). This confirms the transaction and saves a payee rule (debits only).
  "Also tag N other payments" applies the same tag to unconfirmed payments to that payee.
- Confirmed transactions keep their kind and category on reparse and on `app.categorize`.
- `uv run python -m app.categorize --untagged` lists the payees no rule matches.
- Edit categories and delete rules on the **Categories & rules** screen (link at the bottom of the list).

## People & splits

- **My spend = my share.** A split expense counts only my share in "My spend" and in the category totals;
  the full amount stays visible on the row and in the bank / card tiles. Money from friends never counts as spending.
- People are matched without regard to case or extra spaces: "John", "JOHN" and " john " are one person
  (`people.name_key`). The first spelling is kept as the display name; rename it on the People screen.
- Split a payment in its sheet: Equal (optionally without me), Exact ₹ or %. Rounding remainders stay with me.
  `PUT /api/transactions/{id}/splits` replaces the split; an empty list removes it.
- Balances are calculated from splits and repayments, never stored (`app/ledger.py`).

## Repayments (settlements)

- Mark money from a friend as **Settlement**, choose the person, and tag it to earlier payments.
  One repayment can be spread over several payments (₹600 → ₹250 + ₹350); one share can be settled by several repayments.
  - Full amount of their share → the share is **cancelled out** (settled).
  - Less → the rest stays **owed**. More → shown as **overpaid**; tag the money you sent back to the same
    payment and it nets out (₹2,500 in, ₹1,000 back → ₹1,500 applied).
  - A payment that was not split: tagging a repayment creates that person's share from it
    (the whole payment when the amounts match). Set "their share" to record a bigger share than was repaid.
- The same can be done from the original payment ("Paid back" → Tag a repayment). Both write the same rows
  (`app/settle.py`). Untagged repayment money still counts in the person's balance.
- Original transaction amounts never change. A repayment is never income or spending.
- **Nicknames for payment sources.** A settlement shows who paid (bank-printed name + UPI ID) and a
  **Nickname** field. The nickname is the person: two UPI IDs with the same nickname (any case) are one
  person; different nicknames are different people. A UPI ID nicknamed once is filled in automatically
  next time; a new UPI ID with a known printed name gets the nickname as a marked guess.
  Splits use the same nicknames. Fix mistakes on the person page: "Forget" a UPI ID, or rename a
  nickname to an existing one to **merge** the two (shares, repayments and UPI IDs move over).

## Tests

```sh
cd backend && uv run pytest     # DB tests use the flow_test database; they skip if Postgres is down
cd frontend && npm run build    # type-check + build
```
