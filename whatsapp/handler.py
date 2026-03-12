"""
WhatsApp Handler — Twilio WhatsApp Business API
Handles inbound/outbound WhatsApp messages with AI agent.
Supports text, voice notes, and sending booking confirmations.
"""

import asyncio
import logging
import time
import uuid
from collections import OrderedDict
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import Response
from twilio.rest import Client as TwilioClient
from twilio.twiml.messaging_response import MessagingResponse

from ai.agent import get_whatsapp_agent
from ai.prompts import GREETING_WHATSAPP, BOOKING_CONFIRMATION_WHATSAPP
from database.mongodb import get_db
from database.tenancy import (
    resolve_hotel_by_twilio_number,
    set_current_tenant,
    get_hotel_profile,
)
from database.models import Conversation, ConversationChannel, ConversationContext
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])
TWILIO_WHATSAPP_BODY_LIMIT = 1600
WHATSAPP_SAFE_CHUNK_SIZE = 1500

# Inbound webhook dedupe (Twilio will retry webhooks on timeouts)
_recent_inbound_message_sids: "OrderedDict[str, float]" = OrderedDict()
_INBOUND_DEDUP_TTL_SECONDS = 10 * 60
_INBOUND_DEDUP_MAX = 5000

# If Twilio tells us the account exceeded daily messaging quota, avoid spamming retries.
_twilio_quota_exceeded_until_ts: Optional[float] = None


def _seen_inbound_recently(message_sid: Optional[str]) -> bool:
    if not message_sid:
        return False
    now = time.time()
    cutoff = now - _INBOUND_DEDUP_TTL_SECONDS
    # prune oldest
    while _recent_inbound_message_sids:
        _, ts = next(iter(_recent_inbound_message_sids.items()))
        if ts >= cutoff:
            break
        _recent_inbound_message_sids.popitem(last=False)
    if message_sid in _recent_inbound_message_sids:
        return True
    _recent_inbound_message_sids[message_sid] = now
    if len(_recent_inbound_message_sids) > _INBOUND_DEDUP_MAX:
        _recent_inbound_message_sids.popitem(last=False)
    return False


def _twilio_quota_exceeded() -> bool:
    global _twilio_quota_exceeded_until_ts
    if _twilio_quota_exceeded_until_ts is None:
        return False
    if time.time() >= _twilio_quota_exceeded_until_ts:
        _twilio_quota_exceeded_until_ts = None
        return False
    return True


def _mark_twilio_quota_exceeded(cooldown_seconds: int = 24 * 60 * 60) -> None:
    global _twilio_quota_exceeded_until_ts
    _twilio_quota_exceeded_until_ts = time.time() + max(60, cooldown_seconds)


async def _fire_and_forget(coro):
    try:
        await coro
    except Exception as e:
        logger.error("WhatsApp background task failed: %s", e, exc_info=True)


# ─────────────────────────────────────────────
# Inbound WhatsApp Message Webhook
# ─────────────────────────────────────────────

@router.post("/incoming")
async def incoming_whatsapp(
    request: Request,
    From: str = Form(...),            # whatsapp:+8801XXXXXXXXX
    Body: str = Form(default=""),
    MessageSid: Optional[str] = Form(default=None),
    NumMedia: str = Form(default="0"),
    MediaUrl0: Optional[str] = Form(default=None),
    MediaContentType0: Optional[str] = Form(default=None),
    ProfileName: Optional[str] = Form(default=None),
    To: Optional[str] = Form(default=None),
):
    """
    Twilio calls this webhook on every incoming WhatsApp message.
    """
    to_number = To or ""

    hotel = await resolve_hotel_by_twilio_number(to_number, channel="whatsapp")
    if not hotel or not hotel.get("is_active", True):
        logger.error("No hotel found for WhatsApp number: %s", to_number)
        return Response(content="", status_code=204)

    set_current_tenant(hotel)
    if _seen_inbound_recently(MessageSid):
        return Response(content="", status_code=204)

    # Normalize phone number
    phone = From.replace("whatsapp:", "")
    message_body = Body.strip()
    logger.info(f"📱 WhatsApp from {phone} ({ProfileName}) sid={MessageSid}: {message_body[:100]}")

    # Always ACK fast to avoid Twilio webhook retries; process in background.
    asyncio.create_task(
        _fire_and_forget(
            _handle_incoming_whatsapp(
                phone=phone,
                message_body=message_body,
                num_media=NumMedia,
                media_url0=MediaUrl0,
                media_type0=MediaContentType0,
                profile_name=ProfileName,
                hotel=hotel,
            )
        )
    )
    return Response(content="", status_code=204)


async def _handle_incoming_whatsapp(
    phone: str,
    message_body: str,
    num_media: str,
    media_url0: Optional[str],
    media_type0: Optional[str],
    profile_name: Optional[str],
    hotel: Optional[dict],
) -> None:
    if hotel:
        set_current_tenant(hotel)
    db = get_db()
    agent = get_whatsapp_agent()

    # Handle voice note (audio media)
    if int(num_media or "0") > 0 and media_type0 and "audio" in media_type0:
        if not media_url0:
            await _send_whatsapp(phone, "Sorry, I couldn't access that voice note. Please type your message, sir.")
            return
        message_body = await _transcribe_voice_note(media_url0, media_type0)
        if not message_body:
            await _send_whatsapp(phone, "Sorry, I couldn't understand that voice note. Please type your message, sir.")
            return

    if not (message_body or "").strip():
        profile = get_hotel_profile()
        await _send_whatsapp(
            phone,
            f"Hello! This is {profile['receptionist_name']} at {profile['name']}. How can I help you today, sir?",
        )
        return

    # Get or create WhatsApp session (1 session per phone number, reused)
    session = await _get_or_create_whatsapp_session(db, phone, profile_name)
    session_id = session["session_id"]

    # Handle special commands
    if message_body.lower() in ["hi", "hello", "hey", "start", "menu"]:
        profile = get_hotel_profile()
        greeting = GREETING_WHATSAPP.format(
            hotel_name=profile["name"],
            receptionist_name=profile["receptionist_name"],
        )
        sent = await _send_whatsapp(phone, greeting)

        if sent:
            await db.conversations.update_one(
                {"session_id": session_id},
                {
                    "$push": {
                        "messages": {
                            "$each": [
                                {"role": "user", "content": message_body, "timestamp": datetime.utcnow()},
                                {"role": "assistant", "content": greeting, "timestamp": datetime.utcnow()},
                            ]
                        }
                    },
                    "$set": {"updated_at": datetime.utcnow()},
                },
            )
        return

    # Process with AI Agent
    try:
        response_text, tool_calls = await agent.process_message(
            session_id=session_id,
            user_message=message_body,
            phone=phone,
        )

        # Booking created → send rich confirmation (single WhatsApp message)
        for tc in tool_calls:
            if tc["name"] == "create_booking":
                import json

                result = json.loads(tc["result"])
                if result.get("success"):
                    await _send_booking_confirmation_whatsapp(phone, result)
                    return

        await _send_whatsapp(phone, response_text)

    except Exception as e:
        logger.error("WhatsApp processing error: %s", e, exc_info=True)
        await _send_whatsapp(
            phone,
            "I'm sorry, I'm experiencing a technical issue. Please try again or call us directly, sir.",
        )


# ─────────────────────────────────────────────
# Outbound WhatsApp Messages
# ─────────────────────────────────────────────

async def send_booking_confirmation(phone: str, booking_data: dict) -> bool:
    """Send WhatsApp booking confirmation to guest"""
    return await _send_booking_confirmation_whatsapp(phone, booking_data)


async def send_whatsapp_message(phone: str, message: str) -> bool:
    """Send any WhatsApp message to a phone number"""
    return await _send_whatsapp(phone, message)


async def send_check_in_reminder(phone: str, booking_data: dict) -> bool:
    """Send check-in reminder 1 day before"""
    msg = (
        f"🌟 *Check-in Reminder!*\n\n"
        f"Dear {booking_data['guest_name']},\n\n"
        f"This is a friendly reminder that your stay at *{get_hotel_profile()['name']}* "
        f"begins *tomorrow, {booking_data['check_in_date']}* at {get_hotel_profile()['checkin_time']}.\n\n"
        f"📋 Booking ID: *{booking_data['booking_id']}*\n"
        f"🏨 Room: {booking_data['room_type'].title()}\n\n"
        f"Please bring a valid government ID for check-in, sir.\n"
        f"We look forward to welcoming you, sir! 🎉"
    )
    return await _send_whatsapp(phone, msg)


async def send_checkout_reminder(phone: str, booking_data: dict) -> bool:
    """Send check-out reminder on departure day"""
    msg = (
        f"☀️ *Good Morning, {booking_data['guest_name']}!*\n\n"
        f"This is a reminder that check-out time is *{get_hotel_profile()['checkout_time']}* today.\n\n"
        f"For late check-out requests, please contact the front desk, sir.\n"
        f"We hope you enjoyed your stay at *{get_hotel_profile()['name']}*, sir! 🌟\n\n"
        f"Please rate your experience by replying with a number 1-5, sir. ⭐"
    )
    return await _send_whatsapp(phone, msg)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

async def _get_or_create_whatsapp_session(db, phone: str, name: Optional[str]) -> dict:
    """Get active WhatsApp session or create new one"""
    # Look for recent active conversation (last 24 hours)
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(hours=24)

    existing = await db.conversations.find_one({
        "phone": phone,
        "channel": "whatsapp",
        "status": "active",
        "updated_at": {"$gte": cutoff},
    }, sort=[("updated_at", -1)])

    if existing:
        return existing

    # Create new session
    session_id = str(uuid.uuid4())
    conv = Conversation(
        session_id=session_id,
        phone=phone,
        channel=ConversationChannel.WHATSAPP,
        context=ConversationContext(
            guest_phone=phone,
            guest_name=name,
        ),
    )
    doc = conv.model_dump(by_alias=True)
    await db.conversations.insert_one(doc)
    logger.info(f"📱 New WhatsApp session: {session_id} for {phone}")
    return doc


async def _send_whatsapp(phone: str, message: str) -> bool:
    """Send WhatsApp message via Twilio"""
    profile = get_hotel_profile()
    account_sid = profile["twilio_account_sid"] or settings.TWILIO_ACCOUNT_SID
    auth_token = profile["twilio_auth_token"] or settings.TWILIO_AUTH_TOKEN
    wa_number = profile["twilio_whatsapp_number"] or settings.TWILIO_WHATSAPP_NUMBER

    if not account_sid or not auth_token or not wa_number:
        logger.warning("WhatsApp send skipped: Twilio WhatsApp settings missing")
        return False

    if _twilio_quota_exceeded():
        logger.warning("WhatsApp send skipped: Twilio daily quota previously exceeded")
        return False

    try:
        # Format phone for Twilio WhatsApp
        to = f"whatsapp:{phone}" if not phone.startswith("whatsapp:") else phone
        from_wa = wa_number
        if not from_wa.startswith("whatsapp:"):
            from_wa = f"whatsapp:{from_wa}"

        client = TwilioClient(account_sid, auth_token)
        parts = _chunk_whatsapp_message(message, WHATSAPP_SAFE_CHUNK_SIZE)

        max_parts = max(1, int(getattr(settings, "WHATSAPP_MAX_PARTS", 1)))
        if len(parts) > max_parts:
            truncated = "\n".join(parts[:max_parts]).strip()
            suffix = "\n\n…"
            available = max(1, WHATSAPP_SAFE_CHUNK_SIZE - len(suffix))
            truncated = (truncated[:available] + suffix) if len(truncated) > available else (truncated + suffix)
            parts = [truncated]

        for idx, part in enumerate(parts, start=1):
            msg = await asyncio.to_thread(
                client.messages.create,
                body=part,
                from_=from_wa,
                to=to,
            )
            logger.info(
                "📤 WhatsApp sent to %s%s: %s",
                phone,
                "" if len(parts) == 1 else f" (part {idx}/{len(parts)})",
                msg.sid,
            )
        return True
    except Exception as e:
        twilio_code = getattr(e, "code", None)
        twilio_msg = getattr(e, "msg", None) or str(e)
        twilio_more = getattr(e, "more_info", None)

        # Twilio error 63038: exceeded daily messages limit for the account.
        if twilio_code == 63038:
            _mark_twilio_quota_exceeded()

        logger.error(
            "WhatsApp send error | code=%s | message=%s | more_info=%s | raw=%r",
            twilio_code,
            twilio_msg,
            twilio_more,
            e,
        )
        return False


def _chunk_whatsapp_message(message: str, chunk_size: int) -> list[str]:
    """Split long text into WhatsApp-safe chunks preserving paragraph boundaries."""
    if not message:
        return [""]

    msg = message.strip()
    if len(msg) <= TWILIO_WHATSAPP_BODY_LIMIT:
        return [msg]

    chunks: list[str] = []
    paragraphs = msg.split("\n")
    current = ""

    for para in paragraphs:
        candidate = para.strip()
        if not candidate:
            if current and len(current) + 1 <= chunk_size:
                current += "\n"
            continue

        addition = candidate if not current else f"{current}\n{candidate}"
        if len(addition) <= chunk_size:
            current = addition
            continue

        if current:
            chunks.append(current)
            current = ""

        while len(candidate) > chunk_size:
            chunks.append(candidate[:chunk_size])
            candidate = candidate[chunk_size:]

        current = candidate

    if current:
        chunks.append(current)

    return chunks or [msg[:chunk_size]]


async def _send_booking_confirmation_whatsapp(phone: str, booking: dict) -> bool:
    """Send rich booking confirmation message"""
    children_str = f" + {booking.get('children', 0)} children" if booking.get("children", 0) > 0 else ""
    profile = get_hotel_profile()

    msg = BOOKING_CONFIRMATION_WHATSAPP.format(
        booking_id=booking.get("booking_id", ""),
        guest_name=booking.get("guest_name", ""),
        room_type=booking.get("room_type", "").title(),
        room_number=booking.get("room_number", ""),
        check_in_date=booking.get("check_in_date", ""),
        check_out_date=booking.get("check_out_date", ""),
        checkin_time=profile["checkin_time"],
        checkout_time=profile["checkout_time"],
        adults=booking.get("adults", 1),
        children_str=children_str,
        currency=booking.get("currency", profile["currency"]),
        total_amount=float(booking.get("total_amount", 0)),
        hotel_address=profile["address"],
    )
    return await _send_whatsapp(phone, msg)


async def _transcribe_voice_note(media_url: str, media_type: Optional[str]) -> str:
    """Download and transcribe a WhatsApp voice note"""
    try:
        import httpx
        from voice.stt_tts import get_stt

        profile = get_hotel_profile()
        account_sid = profile["twilio_account_sid"] or settings.TWILIO_ACCOUNT_SID
        auth_token = profile["twilio_auth_token"] or settings.TWILIO_AUTH_TOKEN

        async with httpx.AsyncClient() as client:
            response = await client.get(
                media_url,
                auth=(account_sid, auth_token),
                follow_redirects=True,
            )
            audio_bytes = response.content
            response_media_type = response.headers.get("content-type")

        audio_bytes = await _convert_audio_to_wav(
            audio_bytes=audio_bytes,
            media_type=media_type or response_media_type,
        )

        stt = get_stt()
        text = await stt.transcribe(audio_bytes)
        logger.info(f"🎤 Voice note transcribed: {text}")
        return text
    except Exception as e:
        logger.error(f"Voice note transcription error: {e}")
        return ""


def _media_type_to_extension(media_type: Optional[str]) -> Optional[str]:
    if not media_type:
        return None
    base = media_type.split(";")[0].strip().lower()
    mapping = {
        "audio/ogg": ".ogg",
        "audio/opus": ".opus",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/amr": ".amr",
        "audio/3gpp": ".3gp",
        "audio/mp4": ".m4a",
        "audio/aac": ".aac",
    }
    return mapping.get(base)


async def _convert_audio_to_wav(audio_bytes: bytes, media_type: Optional[str]) -> bytes:
    ext = _media_type_to_extension(media_type)
    if not ext or ext in (".wav", ".wave"):
        return audio_bytes

    import os
    import tempfile
    import asyncio

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f_in:
        f_in.write(audio_bytes)
        in_path = f_in.name

    out_path = in_path + ".wav"
    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", in_path,
            "-ar", "16000", "-ac", "1",
            out_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.wait()

        if os.path.exists(out_path):
            with open(out_path, "rb") as f_out:
                return f_out.read()
        return audio_bytes
    except Exception:
        return audio_bytes
    finally:
        for p in (in_path, out_path):
            if os.path.exists(p):
                os.unlink(p)
