"""Thin wrapper over the Gmail API. Read-only scope."""

import base64
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parseaddr
from pathlib import Path

from bs4 import BeautifulSoup
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.config import settings

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# The client library retries 429 and 403 rateLimitExceeded with exponential backoff
# (about 2, 4, 8 ... 128 s). Gmail's per-user limit is counted per minute.
RETRIES = 7


class GmailAuthError(RuntimeError):
    """No usable token. Run `uv run python -m app.gmail.auth`."""


@dataclass
class FetchedEmail:
    gmail_msg_id: str
    thread_id: str | None
    history_id: int | None
    sender: str  # lower-case address only, no display name
    subject: str
    received_at: datetime  # UTC
    body_text: str | None
    body_html: str | None


def save_token(creds: Credentials, path: Path | None = None) -> None:
    path = path or settings.gmail_token
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(creds.to_json())


def load_credentials() -> Credentials:
    path = settings.gmail_token
    if not path.exists():
        raise GmailAuthError(f"No Gmail token at {path}. Run: uv run python -m app.gmail.auth")
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds.valid:
        return creds
    if not creds.refresh_token:
        raise GmailAuthError("Gmail token has no refresh token. Run: uv run python -m app.gmail.auth")
    try:
        creds.refresh(Request())
    except RefreshError as e:
        raise GmailAuthError(
            f"Gmail token refresh failed ({e}). If the OAuth app is in Testing mode, "
            "publish it to production, then run: uv run python -m app.gmail.auth"
        ) from e
    save_token(creds)
    return creds


# ---------- MIME helpers (pure, unit-tested) ----------


def _decode_part(part: dict) -> str | None:
    data = part.get("body", {}).get("data")
    if not data:
        return None
    raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    charset = "utf-8"
    for h in part.get("headers", []):
        if h["name"].lower() == "content-type":
            m = re.search(r'charset="?([\w-]+)"?', h["value"], re.I)
            if m:
                charset = m.group(1)
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _walk(part: dict) -> tuple[str | None, str | None]:
    """Return the first text/plain and the first text/html body in a payload tree."""
    mime = part.get("mimeType", "")
    if mime == "text/plain":
        return _decode_part(part), None
    if mime == "text/html":
        return None, _decode_part(part)
    plain = html = None
    for sub in part.get("parts", []) or []:
        p, h = _walk(sub)
        plain = plain or p
        html = html or h
    return plain, html


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    lines = (line.strip() for line in soup.get_text("\n").splitlines())
    return "\n".join(line for line in lines if line)


def best_text(plain: str | None, html: str | None) -> str | None:
    # Bank alerts are HTML-first. The plain part is often missing or a stub.
    if html:
        return html_to_text(html)
    if plain:
        lines = (line.strip() for line in plain.splitlines())
        return "\n".join(line for line in lines if line)
    return None


def parse_message(msg: dict) -> FetchedEmail:
    payload = msg.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    plain, html = _walk(payload)
    return FetchedEmail(
        gmail_msg_id=msg["id"],
        thread_id=msg.get("threadId"),
        history_id=int(msg["historyId"]) if msg.get("historyId") else None,
        sender=parseaddr(headers.get("from", ""))[1].lower(),
        subject=headers.get("subject", ""),
        received_at=datetime.fromtimestamp(int(msg["internalDate"]) / 1000, tz=UTC),
        body_text=best_text(plain, html),
        body_html=html,
    )


# ---------- API client ----------


class GmailClient:
    def __init__(self, creds: Credentials | None = None):
        self._svc = build("gmail", "v1", credentials=creds or load_credentials(), cache_discovery=False)

    def profile(self) -> dict:
        return self._svc.users().getProfile(userId="me").execute(num_retries=RETRIES)

    def list_message_ids(self, query: str) -> list[str]:
        """All message ids for a search query, newest first."""
        ids: list[str] = []
        token = None
        while True:
            resp = (
                self._svc.users()
                .messages()
                .list(userId="me", q=query, maxResults=500, pageToken=token)
                .execute(num_retries=RETRIES)
            )
            ids.extend(m["id"] for m in resp.get("messages", []))
            token = resp.get("nextPageToken")
            if not token:
                return ids

    def get_message(self, msg_id: str) -> FetchedEmail:
        msg = self._svc.users().messages().get(userId="me", id=msg_id, format="full").execute(num_retries=RETRIES)
        return parse_message(msg)
