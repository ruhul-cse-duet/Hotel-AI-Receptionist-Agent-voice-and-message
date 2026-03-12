"""
Twilio Voice Call Handler
Real-time bidirectional audio streaming via WebSockets (Twilio Media Streams).
Flow: Caller → Twilio → WebSocket → STT → AI Agent → TTS → Twilio → Caller
"""

import asyncio
import base64
import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import Response
from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import VoiceResponse, Connect, Start, Stream

from ai.agent import get_voice_agent
from ai.prompts import GREETING_VOICE
from voice.stt_tts import get_stt, get_tts
from database.mongodb import get_db
from database.tenancy import (
    resolve_hotel_by_twilio_number,
    resolve_hotel_by_id,
    set_current_tenant,
    get_hotel_profile,
)
from database.models import CallSession, Conversation, ConversationChannel, ConversationContext
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["Voice Calls"])

# In-memory session store for active WebSocket calls
active_sessions: dict = {}


# ─────────────────────────────────────────────
# Twilio Webhooks
# ─────────────────────────────────────────────

@router.post("/incoming")
async def incoming_call(request: Request):
    """
    Twilio calls this when someone calls your Twilio number.
    Returns TwiML to initiate Media Stream WebSocket.
    """
    form = await request.form()
    call_sid = form.get("CallSid", "")
    caller_phone = form.get("From", "unknown")
    to_number = form.get("To", "")

    hotel = await resolve_hotel_by_twilio_number(to_number, channel="voice")
    if not hotel or not hotel.get("is_active", True):
        logger.error("No hotel found for voice number: %s", to_number)
        response = VoiceResponse()
        response.say("This number is not configured. Please contact support, sir.")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    set_current_tenant(hotel)

    logger.info(f"📞 Incoming call: {call_sid} from {caller_phone}")

    # Create conversation session
    session_id = str(uuid.uuid4())
    db = get_db()

    # Store call session
    session = CallSession(
        call_sid=call_sid,
        phone=caller_phone,
        session_id=session_id,
    )
    await db.call_sessions.insert_one(session.model_dump(by_alias=True))

    # Create conversation record
    conv = Conversation(
        session_id=session_id,
        phone=caller_phone,
        channel=ConversationChannel.VOICE,
        call_sid=call_sid,
        context=ConversationContext(guest_phone=caller_phone),
    )
    await db.conversations.insert_one(conv.model_dump(by_alias=True))

    # Store session_id keyed by call_sid for WebSocket lookup
    active_sessions[call_sid] = {
        "session_id": session_id,
        "phone": caller_phone,
        "stream_sid": None,
        "hotel_id": hotel.get("hotel_id"),
    }

    # TwiML: Start Media Stream to our WebSocket
    response = VoiceResponse()

    # Play greeting while WebSocket initializes
    profile = get_hotel_profile()
    greeting = GREETING_VOICE.format(
        hotel_name=profile["name"],
        receptionist_name=profile["receptionist_name"],
    )

    start = Start()
    base_host = request.headers.get("host")
    if not base_host:
        base_host = settings.WEBHOOK_BASE_URL.replace("https://", "").replace("http://", "")
    start.stream(url=f"wss://{base_host}/voice/stream", track="inbound_track")
    response.append(start)

    # Initial pause to let WebSocket connect
    response.pause(length=1)

    # Say greeting via Twilio TTS (or we can do it via WS)
    response.say(
        greeting,
        voice="Polly.Joanna",
        language="en-US",
    )

    return Response(content=str(response), media_type="application/xml")


@router.post("/status")
async def call_status(request: Request):
    """Twilio calls this on call status changes (completed, failed, etc.)"""
    form = await request.form()
    call_sid = form.get("CallSid")
    status = form.get("CallStatus")
    duration = form.get("CallDuration", "0")

    logger.info(f"📞 Call {call_sid} → {status} ({duration}s)")

    if status in ["completed", "failed", "busy", "no-answer"]:
        session_data = active_sessions.pop(call_sid, None)
        if session_data:
            hotel_id = session_data.get("hotel_id")
            if hotel_id:
                hotel = await resolve_hotel_by_id(hotel_id)
                if hotel:
                    set_current_tenant(hotel)
            db = get_db()
            await db.conversations.update_one(
                {"session_id": session_data["session_id"]},
                {
                    "$set": {
                        "status": "completed",
                        "duration_sec": float(duration),
                        "ended_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                    }
                }
            )
            await db.call_sessions.delete_one({"call_sid": call_sid})

    return Response(content="", status_code=204)


# ─────────────────────────────────────────────
# WebSocket — Real-time Audio Streaming
# ─────────────────────────────────────────────

@router.websocket("/stream")
async def media_stream(websocket: WebSocket):
    """
    Twilio Media Stream WebSocket.
    Receives inbound audio → STT → AI Agent → TTS → sends audio back to caller.
    """
    await websocket.accept()
    logger.info("🔌 WebSocket connected")

    stt = get_stt()
    tts = get_tts()
    agent = get_voice_agent()

    call_sid: Optional[str] = None
    session_data: Optional[dict] = None
    audio_buffer = bytearray()
    silence_count = 0
    SILENCE_THRESHOLD = 20  # ~2 seconds of silence (100ms chunks)
    MIN_AUDIO_BYTES = 8000  # minimum bytes before processing

    try:
        async for raw_msg in websocket.iter_text():
            msg = json.loads(raw_msg)
            event = msg.get("event")

            # ── Connected ──────────────────────────────────
            if event == "connected":
                logger.info("Twilio Media Stream: connected")

            # ── Start ─────────────────────────────────────
            elif event == "start":
                stream_meta = msg.get("start", {})
                call_sid = stream_meta.get("callSid")
                stream_sid = stream_meta.get("streamSid")
                session_data = active_sessions.get(call_sid)
                if session_data:
                    session_data["stream_sid"] = stream_sid
                    session_data["websocket"] = websocket
                    hotel_id = session_data.get("hotel_id")
                    if hotel_id:
                        hotel = await resolve_hotel_by_id(hotel_id)
                        if hotel:
                            set_current_tenant(hotel)
                logger.info(f"🎙 Stream started: {call_sid}")

            # ── Media (audio chunk) ───────────────────────
            elif event == "media" and session_data:
                payload = msg.get("media", {}).get("payload", "")
                if payload:
                    chunk = base64.b64decode(payload)
                    audio_buffer.extend(chunk)
                    silence_count = 0
                else:
                    silence_count += 1

                # Detect end-of-speech and process
                if silence_count >= SILENCE_THRESHOLD and len(audio_buffer) > MIN_AUDIO_BYTES:
                    speech = bytes(audio_buffer)
                    audio_buffer = bytearray()
                    silence_count = 0

                    # Process in background to not block audio stream
                    asyncio.create_task(
                        _process_speech_turn(
                            websocket=websocket,
                            speech_bytes=speech,
                            session_data=session_data,
                            stt=stt,
                            tts=tts,
                            agent=agent,
                        )
                    )

            # ── Stop ──────────────────────────────────────
            elif event == "stop":
                logger.info(f"🛑 Stream stopped: {call_sid}")
                if session_data:
                    await agent.end_conversation(session_data["session_id"])
                break

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        if call_sid and call_sid in active_sessions:
            active_sessions.pop(call_sid, None)


async def _process_speech_turn(
    websocket: WebSocket,
    speech_bytes: bytes,
    session_data: dict,
    stt,
    tts,
    agent,
):
    """STT → AI Agent → TTS → stream audio back to caller"""
    try:
        # Ensure tenant context is set for this background task
        hotel_id = session_data.get("hotel_id") if session_data else None
        if hotel_id:
            hotel = await resolve_hotel_by_id(hotel_id)
            if hotel:
                set_current_tenant(hotel)

        # 1. Speech to Text
        user_text = await stt.transcribe(speech_bytes, language="en")
        if not user_text or len(user_text.strip()) < 2:
            return

        logger.info(f"👤 Guest said: {user_text}")

        # 2. AI Agent processes the message
        response_text, tool_calls = await agent.process_message(
            session_id=session_data["session_id"],
            user_message=user_text,
            phone=session_data["phone"],
        )

        logger.info(f"🤖 AI responds: {response_text[:100]}")

        # 3. Text to Speech
        audio_bytes = await tts.synthesize(response_text)

        # 4. Send audio back through Twilio Media Stream
        # Twilio expects base64-encoded mulaw 8kHz audio
        # Convert MP3 to mulaw if needed
        mulaw_audio = await _convert_to_mulaw(audio_bytes)

        await _send_audio_to_caller(
            websocket=websocket,
            stream_sid=session_data.get("stream_sid"),
            audio_bytes=mulaw_audio,
        )

    except Exception as e:
        logger.error(f"Speech processing error: {e}", exc_info=True)


async def _convert_to_mulaw(mp3_bytes: bytes) -> bytes:
    """Convert MP3/audio to 8kHz mulaw (required by Twilio Media Streams)"""
    import subprocess
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f_in:
        f_in.write(mp3_bytes)
        in_path = f_in.name

    out_path = in_path.replace(".mp3", ".mulaw")

    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", in_path,
            "-ar", "8000", "-ac", "1",
            "-acodec", "pcm_mulaw",
            "-f", "mulaw", out_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.wait()

        if os.path.exists(out_path):
            with open(out_path, "rb") as f:
                return f.read()
        return mp3_bytes
    finally:
        for p in [in_path, out_path]:
            if os.path.exists(p):
                os.unlink(p)


async def _send_audio_to_caller(websocket: WebSocket, stream_sid: str, audio_bytes: bytes):
    """Send TTS audio back to caller via Twilio Media Stream"""
    if not stream_sid:
        return

    CHUNK_SIZE = 160  # 20ms of 8kHz mulaw
    for i in range(0, len(audio_bytes), CHUNK_SIZE):
        chunk = audio_bytes[i:i + CHUNK_SIZE]
        payload = base64.b64encode(chunk).decode("utf-8")

        msg = {
            "event": "media",
            "streamSid": stream_sid,
            "media": {"payload": payload}
        }
        try:
            await websocket.send_text(json.dumps(msg))
            await asyncio.sleep(0.01)  # ~10ms pacing
        except Exception:
            break


# ─────────────────────────────────────────────
# Outbound Call (AI initiates call to guest)
# ─────────────────────────────────────────────

async def make_outbound_call(
    to_phone: str,
    message: str,
    booking_id: Optional[str] = None,
) -> dict:
    """AI calls a guest — for booking confirmations, reminders etc."""
    try:
        profile = get_hotel_profile()
        account_sid = profile["twilio_account_sid"] or settings.TWILIO_ACCOUNT_SID
        auth_token = profile["twilio_auth_token"] or settings.TWILIO_AUTH_TOKEN
        twilio_client = TwilioClient(account_sid, auth_token)

        twiml = VoiceResponse()
        twiml.say(message, voice="Polly.Joanna", language="en-US")
        twiml.pause(length=2)
        twiml.say(
            f"For assistance, please call us back at {profile['phone']}, sir. Thank you!",
            voice="Polly.Joanna"
        )

        from_number = profile["twilio_voice_number"] or settings.TWILIO_PHONE_NUMBER
        call = twilio_client.calls.create(
            twiml=str(twiml),
            to=to_phone,
            from_=from_number,
            status_callback=f"{settings.WEBHOOK_BASE_URL}/voice/status",
        )
        logger.info(f"📞 Outbound call to {to_phone}: {call.sid}")
        return {"success": True, "call_sid": call.sid}

    except Exception as e:
        logger.error(f"Outbound call failed: {e}")
        return {"success": False, "error": str(e)}
