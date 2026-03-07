"""
WhatsApp Handler — Twilio WhatsApp Business API
Handles inbound/outbound WhatsApp messages with AI agent.
Supports text, voice notes, and sending booking confirmations.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import Response
from twilio.rest import Client as TwilioClient
from twilio.twiml.messaging_response import MessagingResponse

from ai.agent import get_whatsapp_agent
from ai.prompts import GREETING_WHATSAPP, BOOKING_CONFIRMATION_WHATSAPP
from database.mongodb import get_db
from database.models import Conversation, ConversationChannel, ConversationContext
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])


# ─────────────────────────────────────────────
# Inbound WhatsApp Message Webhook
# ─────────────────────────────────────────────

@router.post("/incoming")
async def incoming_whatsapp(
    request: Request,
    From: str = Form(...),            # whatsapp:+8801XXXXXXXXX
    Body: str = Form(default=""),
    NumMedia: str = Form(default="0"),
    MediaUrl0: Optional[str] = Form(default=None),
    MediaContentType0: Optional[str] = Form(default=None),
    ProfileName: Optional[str] = Form(default=None),
):
    """
    Twilio calls this webhook on every incoming WhatsApp message.
    """
    # Normalize phone number
    phone = From.replace("whatsapp:", "")
    message_body = Body.strip()

    logger.info(f"📱 WhatsApp from {phone} ({ProfileName}): {message_body[:100]}")

    db = get_db()
    agent = get_whatsapp_agent()

    # Handle voice note (audio media)
    if int(NumMedia) > 0 and MediaContentType0 and "audio" in MediaContentType0:
        message_body = await _transcribe_voice_note(MediaUrl0)
        if not message_body:
            await _send_whatsapp(
                phone,
                "Sorry, I couldn't understand that voice note. Please type your message. 😊"
            )
            return Response(content="", status_code=204)

    if not message_body:
        await _send_whatsapp(phone, "Hello! 👋 How can I help you today?")
        return Response(content="", status_code=204)

    # Get or create WhatsApp session (1 session per phone number, reused)
    session = await _get_or_create_whatsapp_session(db, phone, ProfileName)
    session_id = session["session_id"]

    # Handle special commands
    if message_body.lower() in ["hi", "hello", "hey", "start", "menu"]:
        greeting = GREETING_WHATSAPP.format(hotel_name=settings.HOTEL_NAME)
        await _send_whatsapp(phone, greeting)

        # Save greeting to conversation
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
            }
        )
        return Response(content="", status_code=204)

    # Process with AI Agent
    try:
        response_text, tool_calls = await agent.process_message(
            session_id=session_id,
            user_message=message_body,
            phone=phone,
        )

        # Check if a booking was just created → send rich confirmation
        for tc in tool_calls:
            if tc["name"] == "create_booking":
                import json
                result = json.loads(tc["result"])
                if result.get("success"):
                    await _send_booking_confirmation_whatsapp(phone, result)
                    return Response(content="", status_code=204)

        # Send regular AI response
        await _send_whatsapp(phone, response_text)

    except Exception as e:
        logger.error(f"WhatsApp processing error: {e}", exc_info=True)
        await _send_whatsapp(
            phone,
            "I'm sorry, I'm experiencing a technical issue. Please try again or call us directly. 🙏"
        )

    return Response(content="", status_code=204)


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
        f"This is a friendly reminder that your stay at *{settings.HOTEL_NAME}* "
        f"begins *tomorrow, {booking_data['check_in_date']}* at {settings.HOTEL_CHECKIN_TIME}.\n\n"
        f"📋 Booking ID: *{booking_data['booking_id']}*\n"
        f"🏨 Room: {booking_data['room_type'].title()}\n\n"
        f"Please bring a valid government ID for check-in.\n"
        f"We look forward to welcoming you! 🎉"
    )
    return await _send_whatsapp(phone, msg)


async def send_checkout_reminder(phone: str, booking_data: dict) -> bool:
    """Send check-out reminder on departure day"""
    msg = (
        f"☀️ *Good Morning, {booking_data['guest_name']}!*\n\n"
        f"This is a reminder that check-out time is *{settings.HOTEL_CHECKOUT_TIME}* today.\n\n"
        f"For late check-out requests, please contact the front desk.\n"
        f"We hope you enjoyed your stay at *{settings.HOTEL_NAME}*! 🌟\n\n"
        f"Please rate your experience by replying with a number 1-5. ⭐"
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
    try:
        # Format phone for Twilio WhatsApp
        to = f"whatsapp:{phone}" if not phone.startswith("whatsapp:") else phone
        from_wa = settings.TWILIO_WHATSAPP_NUMBER
        if not from_wa.startswith("whatsapp:"):
            from_wa = f"whatsapp:{from_wa}"

        client = TwilioClient(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        msg = client.messages.create(
            body=message,
            from_=from_wa,
            to=to,
        )
        logger.info(f"📤 WhatsApp sent to {phone}: {msg.sid}")
        return True
    except Exception as e:
        logger.error(f"WhatsApp send error: {e}")
        return False


async def _send_booking_confirmation_whatsapp(phone: str, booking: dict) -> bool:
    """Send rich booking confirmation message"""
    children_str = f" + {booking.get('children', 0)} children" if booking.get("children", 0) > 0 else ""

    msg = BOOKING_CONFIRMATION_WHATSAPP.format(
        booking_id=booking.get("booking_id", ""),
        guest_name=booking.get("guest_name", ""),
        room_type=booking.get("room_type", "").title(),
        room_number=booking.get("room_number", ""),
        check_in_date=booking.get("check_in_date", ""),
        check_out_date=booking.get("check_out_date", ""),
        checkin_time=settings.HOTEL_CHECKIN_TIME,
        checkout_time=settings.HOTEL_CHECKOUT_TIME,
        adults=booking.get("adults", 1),
        children_str=children_str,
        currency=booking.get("currency", settings.HOTEL_CURRENCY),
        total_amount=float(booking.get("total_amount", 0)),
        hotel_address=settings.HOTEL_ADDRESS,
    )
    return await _send_whatsapp(phone, msg)


async def _transcribe_voice_note(media_url: str) -> str:
    """Download and transcribe a WhatsApp voice note"""
    try:
        import httpx
        from voice.stt_tts import get_stt

        async with httpx.AsyncClient() as client:
            response = await client.get(
                media_url,
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                follow_redirects=True,
            )
            audio_bytes = response.content

        stt = get_stt()
        text = await stt.transcribe(audio_bytes)
        logger.info(f"🎤 Voice note transcribed: {text}")
        return text
    except Exception as e:
        logger.error(f"Voice note transcription error: {e}")
        return ""
