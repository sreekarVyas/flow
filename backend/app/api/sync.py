from fastapi import APIRouter, HTTPException

from app.gmail.client import GmailAuthError
from app.ingest.runner import run_poll

router = APIRouter(prefix="/api")


@router.post("/sync")
async def sync() -> dict:
    try:
        return await run_poll()
    except GmailAuthError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
