"""Run polls from the web app: one at a time, off the event loop."""

import asyncio
import logging
from datetime import date

from app.config import settings
from app.db import SessionLocal
from app.gmail.client import GmailAuthError, GmailClient
from app.ingest.poller import poll_once

log = logging.getLogger(__name__)
_lock = asyncio.Lock()


def _poll_sync(since: date | None) -> dict:
    with SessionLocal() as session:
        return poll_once(session, GmailClient(), since=since)


async def run_poll(since: date | None = None) -> dict:
    async with _lock:
        return await asyncio.to_thread(_poll_sync, since)


async def poll_forever() -> None:
    while True:
        try:
            await run_poll()
        except GmailAuthError as e:
            log.warning("poll skipped: %s", e)
        except Exception:
            log.exception("poll failed")
        await asyncio.sleep(settings.poll_interval_seconds)
