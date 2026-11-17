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

## Tests

```sh
cd backend && uv run pytest     # DB tests use the flow_test database; they skip if Postgres is down
cd frontend && npm run build    # type-check + build
```
