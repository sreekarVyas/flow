"""FastAPI app. Run: uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import categories, sync, transactions
from app.config import settings
from app.ingest.runner import poll_forever

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(poll_forever()) if settings.poll_enabled else None
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Flow", lifespan=lifespan)
app.include_router(transactions.router)
app.include_router(sync.router)
app.include_router(categories.router)
