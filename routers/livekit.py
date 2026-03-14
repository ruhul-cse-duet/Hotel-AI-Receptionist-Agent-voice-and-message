"""
LiveKit call link endpoints.
Generates room tokens and serves the call page.
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from config import settings

logger = logging.getLogger(__name__)

livekit_router = APIRouter(tags=["LiveKit"])


def _get_call_base_url() -> str:
    base = (settings.CALL_BASE_URL or "").strip()
    if not base:
        base = (settings.WEBHOOK_BASE_URL or "").strip()
    return base.rstrip("/")


@livekit_router.get("/call/{room_id}")
async def call_page(room_id: str):
    if not room_id:
        raise HTTPException(status_code=400, detail="Missing room id")
    return FileResponse("ui/call.html")


@livekit_router.get("/livekit/token")
async def livekit_token(
    room: str = Query(..., min_length=3),
    identity: Optional[str] = Query(default=None),
):
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET or not settings.LIVEKIT_URL:
        raise HTTPException(status_code=500, detail="LiveKit is not configured")

    try:
        from livekit import api
    except Exception as e:
        logger.error("LiveKit SDK import failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="LiveKit SDK missing. Install livekit-api.")

    identity = identity or f"guest_{uuid.uuid4().hex[:8]}"

    token = (
        api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_grants(api.VideoGrants(room_join=True, room=room))
        .to_jwt()
    )

    return JSONResponse(
        {
            "token": token,
            "url": settings.LIVEKIT_URL,
            "room": room,
            "identity": identity,
            "call_url": f"{_get_call_base_url()}/call/{room}",
        }
    )
