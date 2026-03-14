"""
Hotel AI Receptionist - FastAPI Application
Entry point: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from database.mongodb import connect_db, disconnect_db


def _configure_console_encoding() -> None:
    """Ensure console streams can safely print Unicode logs on Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


_configure_console_encoding()


def _get_log_level() -> int:
    configured = (settings.LOG_LEVEL or "INFO").upper()
    return getattr(logging, configured, logging.INFO)


def _quiet_noisy_loggers() -> None:
    noisy = [
        "pymongo",
        "pymongo.connection",
        "pymongo.topology",
        "pymongo.serverSelection",
        "pymongo.command",
    ]
    for name in noisy:
        logging.getLogger(name).setLevel(logging.WARNING)


logging.basicConfig(
    level=_get_log_level(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("hotel_ai.log", encoding="utf-8"),
    ],
    force=True,
)
logger = logging.getLogger(__name__)
_quiet_noisy_loggers()

# Import routers with error handling
try:
    from voice.twilio_handler import router as voice_router
    logger.info("[OK] Voice router imported")
except Exception as e:
    logger.error(f"[FAIL] Failed to import voice router: {e}", exc_info=True)
    voice_router = None

try:
    from whatsapp.handler import router as whatsapp_router
    logger.info("[OK] WhatsApp router imported")
except Exception as e:
    logger.error(f"[FAIL] Failed to import WhatsApp router: {e}", exc_info=True)
    whatsapp_router = None

try:
    from whatsapp.meta_handler import router as meta_whatsapp_router
    logger.info("[OK] Meta WhatsApp router imported")
except Exception as e:
    logger.error(f"[FAIL] Failed to import Meta WhatsApp router: {e}", exc_info=True)
    meta_whatsapp_router = None

try:
    from routers.api import bookings_router, rooms_router, admin_router
    logger.info("[OK] API routers imported")
except Exception as e:
    logger.error(f"[FAIL] Failed to import API routers: {e}", exc_info=True)
    bookings_router = None
    rooms_router = None
    admin_router = None

try:
    from routers.onboarding import onboarding_router
    logger.info("[OK] Onboarding router imported")
except Exception as e:
    logger.error(f"[FAIL] Failed to import onboarding router: {e}", exc_info=True)
    onboarding_router = None

try:
    from routers.livekit import livekit_router
    logger.info("[OK] LiveKit router imported")
except Exception as e:
    logger.error(f"[FAIL] Failed to import LiveKit router: {e}", exc_info=True)
    livekit_router = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"{settings.HOTEL_NAME} - AI Receptionist starting")
    logger.info(f"   LLM Provider : {settings.LLM_PROVIDER}")
    logger.info(f"   STT Provider : {settings.STT_PROVIDER}")
    logger.info(f"   TTS Provider : {settings.TTS_PROVIDER}")
    logger.info(f"   Environment  : {settings.APP_ENV}")

    await connect_db()

    from ai.llm_provider import get_llm_provider
    get_llm_provider()

    logger.info(f"{settings.HOTEL_NAME} AI Receptionist is LIVE on port {settings.PORT}")
    yield

    await disconnect_db()
    logger.info("Hotel AI Receptionist stopped")


app = FastAPI(
    title=f"{settings.HOTEL_NAME} - AI Receptionist",
    description="""
    Agentic AI Hotel Receptionist System

    - Voice Calls: Real-time AI phone calls via Twilio + STT + TTS
    - WhatsApp: AI-powered messaging with rich confirmations
    - Booking Engine: Full room availability and booking management
    - MongoDB: Persistent guest data and conversation history

    LLM Providers: OpenAI GPT-4o (prod) | Gemini 1.5 Pro (prod) | LM Studio (local dev)
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.mount("/ui", StaticFiles(directory="ui"), name="ui")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc) if settings.DEBUG else "Contact support"},
    )


if voice_router:
    app.include_router(voice_router)
    logger.info("Voice router registered")
else:
    logger.warning("Voice router NOT registered")

if whatsapp_router:
    app.include_router(whatsapp_router)
    logger.info("WhatsApp router registered")
else:
    logger.warning("WhatsApp router NOT registered")

if meta_whatsapp_router:
    app.include_router(meta_whatsapp_router)
    logger.info("Meta WhatsApp router registered")
else:
    logger.warning("Meta WhatsApp router NOT registered")

if bookings_router:
    app.include_router(bookings_router)
    logger.info("Bookings router registered")
else:
    logger.warning("Bookings router NOT registered")

if rooms_router:
    app.include_router(rooms_router)
    logger.info("Rooms router registered")
else:
    logger.warning("Rooms router NOT registered")

if admin_router:
    app.include_router(admin_router)
    logger.info("Admin router registered")
else:
    logger.warning("Admin router NOT registered")

if onboarding_router:
    app.include_router(onboarding_router)
    logger.info("Onboarding router registered")
else:
    logger.warning("Onboarding router NOT registered")

if livekit_router:
    app.include_router(livekit_router)
    logger.info("LiveKit router registered")
else:
    logger.warning("LiveKit router NOT registered")


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": f"{settings.HOTEL_NAME} AI Receptionist",
        "status": "running",
        "version": "1.0.0",
        "env": settings.APP_ENV,
        "llm": settings.LLM_PROVIDER,
        "docs": "/docs",
    }


@app.get("/onboarding", tags=["Onboarding"])
async def onboarding_page():
    return FileResponse("ui/onboarding.html")


@app.get("/health", tags=["Health"])
async def health():
    from database.mongodb import get_db

    try:
        db = get_db()
        await db.command("ping")
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return {
        "status": "healthy",
        "database": db_status,
        "hotel": settings.HOTEL_NAME,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info",
        ws_ping_interval=30,
        ws_ping_timeout=10,
    )
