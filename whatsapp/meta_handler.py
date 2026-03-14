"""
Meta WhatsApp Cloud API webhook handler.
Receives inbound messages and sends AI replies via Graph API.
"""

import asyncio
import json
import logging
import time
import os
import tempfile
from collections import OrderedDict
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response

from ai.agent import get_whatsapp_agent
from ai.prompts import GREETING_WHATSAPP, BOOKING_CONFIRMATION_WHATSAPP
from config import settings
from database.mongodb import get_db
from database.tenancy import (
    resolve_hotel_by_meta_phone_number_id,
    set_current_tenant,
    get_hotel_profile,
)
from whatsapp.handler import _get_or_create_whatsapp_session
from voice.stt_tts import get_stt, get_tts

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WhatsApp Meta"])

_recent_meta_message_ids: "OrderedDict[str, float]" = OrderedDict()
_META_DEDUP_TTL_SECONDS = 10 * 60
_META_DEDUP_MAX = 5000


def _seen_meta_message_recently(message_id: Optional[str]) -> bool:
    if not message_id:
        return False
    now = time.time()
    cutoff = now - _META_DEDUP_TTL_SECONDS
    while _recent_meta_message_ids:
        _, ts = next(iter(_recent_meta_message_ids.items()))
        if ts >= cutoff:
            break
        _recent_meta_message_ids.popitem(last=False)
    if message_id in _recent_meta_message_ids:
        return True
    _recent_meta_message_ids[message_id] = now
    if len(_recent_meta_message_ids) > _META_DEDUP_MAX:
        _recent_meta_message_ids.popitem(last=False)
    return False


def _get_meta_base_url() -> str:
    version = (settings.META_GRAPH_API_VERSION or "v20.0").strip()
    return f"https://graph.facebook.com/{version}"


def _get_meta_access_token() -> str:
    return (settings.META_WA_ACCESS_TOKEN or "").strip()


def _normalize_wa_phone(value: Optional[str]) -> str:
    if not value:
        return ""
    if value.startswith("+"):
        return value
    if value.isdigit():
        return f"+{value}"
    return value


def _chunk_message(message: str, chunk_size: int = 1500) -> list[str]:
    if not message:
        return [""]
    msg = message.strip()
    if len(msg) <= chunk_size:
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


def _guess_audio_suffix(mime_type: Optional[str]) -> str:
    if not mime_type:
        return ".ogg"
    mt = mime_type.lower()
    if "ogg" in mt:
        return ".ogg"
    if "opus" in mt:
        return ".opus"
    if "mpeg" in mt or "mp3" in mt:
        return ".mp3"
    if "wav" in mt:
        return ".wav"
    if "m4a" in mt or "mp4" in mt:
        return ".m4a"
    return ".ogg"


async def _download_meta_media(media_id: str) -> tuple[Optional[bytes], Optional[str]]:
    """Download WhatsApp media bytes and return (bytes, mime_type)."""
    token = _get_meta_access_token()
    if not token:
        logger.warning("Meta media download skipped: access token missing")
        return None, None
    if not media_id:
        return None, None

    base = _get_meta_base_url()
    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            meta_url = f"{base}/{media_id}"
            meta_resp = await client.get(meta_url, headers=headers)
            if meta_resp.status_code >= 400:
                logger.error("Meta media metadata failed: %s %s", meta_resp.status_code, meta_resp.text)
                return None, None
            meta = meta_resp.json()
            media_url = meta.get("url")
            mime_type = meta.get("mime_type")
            if not media_url:
                logger.error("Meta media metadata missing url for id=%s", media_id)
                return None, None
            media_resp = await client.get(media_url, headers=headers)
            if media_resp.status_code >= 400:
                logger.error("Meta media download failed: %s %s", media_resp.status_code, media_resp.text)
                return None, None
            return media_resp.content, mime_type
    except Exception as e:
        logger.error("Meta media download error: %s", e, exc_info=True)
        return None, None


async def _transcribe_audio_bytes(audio_bytes: bytes, mime_type: Optional[str]) -> str:
    if not audio_bytes:
        return ""

    # Prefer OpenAI Whisper if configured.
    if settings.STT_PROVIDER == "openai_whisper":
        if not settings.OPENAI_API_KEY:
            logger.warning("OpenAI Whisper skipped: OPENAI_API_KEY missing")
            return ""
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            suffix = _guess_audio_suffix(mime_type)
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(audio_bytes)
                tmp_path = f.name
            try:
                with open(tmp_path, "rb") as audio_file:
                    transcript = await client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        response_format="text",
                    )
                text = (transcript or "").strip()
                logger.info("Whisper transcript length: %s", len(text))
                return text
            finally:
                os.unlink(tmp_path)
        except Exception as e:
            logger.error("OpenAI Whisper transcription failed: %s", e, exc_info=True)
            return ""

    # Fallback to configured STT (may use local whisper)
    try:
        stt = get_stt()
        text = (await stt.transcribe(audio_bytes)) or ""
        logger.info("STT transcript length: %s", len(text))
        return text
    except Exception as e:
        logger.error("STT transcription failed: %s", e, exc_info=True)
        return ""


async def _synthesize_tts_mp3(text: str) -> Optional[bytes]:
    if not text:
        return None
    try:
        tts = get_tts()
        audio = await tts.synthesize(text)
        return audio
    except Exception as e:
        logger.error("TTS synthesis failed: %s", e, exc_info=True)
        if settings.TTS_PROVIDER == "elevenlabs" and settings.OPENAI_API_KEY:
            logger.warning("Falling back to OpenAI TTS")
            try:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
                response = await client.audio.speech.create(
                    model="tts-1",
                    voice=settings.OPENAI_TTS_VOICE,
                    input=text,
                    response_format="mp3",
                )
                return response.content
            except Exception as e2:
                logger.error("OpenAI TTS fallback failed: %s", e2, exc_info=True)
        return None


async def _upload_meta_media(audio_bytes: bytes, mime_type: str = "audio/mpeg") -> Optional[str]:
    token = _get_meta_access_token()
    if not token:
        logger.warning("Meta media upload skipped: access token missing")
        return None
    pnid = settings.META_WA_PHONE_NUMBER_ID
    if not pnid:
        logger.warning("Meta media upload skipped: phone_number_id missing")
        return None

    url = f"{_get_meta_base_url()}/{pnid}/media"
    headers = {"Authorization": f"Bearer {token}"}
    files = {
        "file": ("reply.mp3", audio_bytes, mime_type),
    }
    data = {"messaging_product": "whatsapp"}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, files=files, data=data)
            if resp.status_code >= 400:
                logger.error("Meta media upload failed: %s %s", resp.status_code, resp.text)
                return None
            payload = resp.json()
            return payload.get("id")
    except Exception as e:
        logger.error("Meta media upload error: %s", e, exc_info=True)
        return None


async def _send_meta_audio(phone: str, media_id: str, phone_number_id: Optional[str]) -> bool:
    token = _get_meta_access_token()
    if not token or not media_id:
        return False

    pnid = phone_number_id or settings.META_WA_PHONE_NUMBER_ID
    if not pnid:
        logger.warning("Meta audio send skipped: phone_number_id missing")
        return False

    url = f"{_get_meta_base_url()}/{pnid}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": phone.replace("+", ""),
        "type": "audio",
        "audio": {"id": media_id},
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, headers=headers, json=payload)
            logger.info("Meta WhatsApp audio send status: %s", resp.status_code)
            if resp.status_code >= 400:
                logger.error("Meta WhatsApp audio send failed: %s %s", resp.status_code, resp.text)
                return False
        return True
    except Exception as e:
        logger.error("Meta WhatsApp audio send error: %s", e, exc_info=True)
        return False


@router.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode") or params.get("hub_mode")
    token = params.get("hub.verify_token") or params.get("hub_verify_token")
    challenge = params.get("hub.challenge") or params.get("hub_challenge")

    if mode == "subscribe" and token and token == settings.META_WA_VERIFY_TOKEN:
        return PlainTextResponse(challenge or "")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def inbound_webhook(request: Request):
    payload = await request.json()
    await _handle_webhook_payload(payload)
    return Response(content="ok", media_type="text/plain")


async def _handle_webhook_payload(payload: dict) -> None:
    try:
        entries = payload.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {}) or {}
                metadata = value.get("metadata", {}) or {}
                phone_number_id = metadata.get("phone_number_id") or settings.META_WA_PHONE_NUMBER_ID

                # Resolve tenant by phone_number_id
                hotel = await resolve_hotel_by_meta_phone_number_id(phone_number_id)
                if not hotel or not hotel.get("is_active", True):
                    logger.error("No hotel found for Meta phone_number_id: %s", phone_number_id)
                    continue

                set_current_tenant(hotel)

                messages = value.get("messages", []) or []
                contacts = value.get("contacts", []) or []
                profile_name = None
                if contacts and isinstance(contacts[0], dict):
                    profile_name = (contacts[0].get("profile") or {}).get("name")

                for msg in messages:
                    msg_id = msg.get("id")
                    if _seen_meta_message_recently(msg_id):
                        continue

                    from_id = msg.get("from") or ""
                    phone = _normalize_wa_phone(from_id)
                    msg_type = msg.get("type", "text")
                    text_body = ""
                    if msg_type == "text":
                        text_body = (msg.get("text") or {}).get("body", "")
                    elif msg_type == "audio":
                        audio = msg.get("audio") or {}
                        media_id = audio.get("id")
                        audio_bytes, mime_type = await _download_meta_media(media_id)
                        if audio_bytes is not None:
                            logger.info("Meta audio bytes=%s mime=%s", len(audio_bytes), mime_type)
                        text_body = await _transcribe_audio_bytes(audio_bytes or b"", mime_type)
                        if not text_body:
                            logger.warning("Audio transcription empty")
                    logger.info(
                        "Meta inbound message | phone_number_id=%s | from=%s | type=%s | text=%s",
                        phone_number_id,
                        phone,
                        msg_type,
                        (text_body or "")[:120],
                    )

                    await _process_incoming_message(
                        phone=phone,
                        message_body=text_body,
                        msg_type=msg_type,
                        profile_name=profile_name,
                        phone_number_id=phone_number_id,
                    )
    except Exception as e:
        logger.error("Meta webhook processing error: %s", e, exc_info=True)


async def _process_incoming_message(
    phone: str,
    message_body: str,
    msg_type: str,
    profile_name: Optional[str],
    phone_number_id: str,
) -> None:
    db = get_db()
    agent = get_whatsapp_agent()

    if msg_type != "text" and not message_body:
        await _send_meta_whatsapp(
            phone,
            "Sorry sir, I couldn't understand the voice note. Please try again or type your message.",
            phone_number_id,
        )
        return

    if not (message_body or "").strip():
        profile = get_hotel_profile()
        await _send_meta_whatsapp(
            phone,
            f"Hello! This is {profile['receptionist_name']} at {profile['name']}. How can I help you today, sir?",
            phone_number_id,
        )
        return

    session = await _get_or_create_whatsapp_session(db, phone, profile_name)
    session_id = session["session_id"]

    if message_body.lower() in ["hi", "hello", "hey", "start", "menu"]:
        profile = get_hotel_profile()
        greeting = GREETING_WHATSAPP.format(
            hotel_name=profile["name"],
            receptionist_name=profile["receptionist_name"],
        )
        sent = await _send_meta_whatsapp(phone, greeting, phone_number_id)
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

    try:
        response_text, tool_calls = await agent.process_message(
            session_id=session_id,
            user_message=message_body,
            phone=phone,
        )

        for tc in tool_calls:
            if tc["name"] == "create_booking":
                result = json.loads(tc["result"])
                if result.get("success"):
                    await _send_booking_confirmation_meta(phone, result, phone_number_id)
                    return

        if msg_type == "audio":
            audio_bytes = await _synthesize_tts_mp3(response_text)
            if audio_bytes:
                media_id = await _upload_meta_media(audio_bytes, mime_type="audio/mpeg")
                if media_id:
                    await _send_meta_audio(phone, media_id, phone_number_id)
                    return
        await _send_meta_whatsapp(phone, response_text, phone_number_id)
    except Exception as e:
        logger.error("Meta WhatsApp processing error: %s", e, exc_info=True)
        await _send_meta_whatsapp(
            phone,
            "I'm sorry, I'm experiencing a technical issue. Please try again or call us directly, sir.",
            phone_number_id,
        )


async def _send_meta_whatsapp(phone: str, message: str, phone_number_id: Optional[str]) -> bool:
    token = _get_meta_access_token()
    if not token:
        logger.warning("Meta WhatsApp send skipped: access token missing")
        return False

    pnid = phone_number_id or settings.META_WA_PHONE_NUMBER_ID
    if not pnid:
        logger.warning("Meta WhatsApp send skipped: phone_number_id missing")
        return False

    url = f"{_get_meta_base_url()}/{pnid}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    parts = _chunk_message(message, 1500)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            for part in parts:
                payload = {
                    "messaging_product": "whatsapp",
                    "to": phone.replace("+", ""),
                    "type": "text",
                    "text": {"body": part},
                }
                resp = await client.post(url, headers=headers, json=payload)
                logger.info("Meta WhatsApp send status: %s", resp.status_code)
                if resp.status_code >= 400:
                    logger.error("Meta WhatsApp send failed: %s %s", resp.status_code, resp.text)
                    return False
        return True
    except Exception as e:
        logger.error("Meta WhatsApp send error: %s", e, exc_info=True)
        return False


async def _send_booking_confirmation_meta(phone: str, booking: dict, phone_number_id: str) -> bool:
    children_str = f" + {booking.get('children', 0)} children" if booking.get("children", 0) > 0 else ""
    profile = get_hotel_profile()

    msg = BOOKING_CONFIRMATION_WHATSAPP.format(
        booking_id=booking.get("booking_id", ""),
        guest_name=booking.get("guest_name", ""),
        room_type=booking.get("room_type", "").title(),
        check_in_date=booking.get("check_in_date", ""),
        check_out_date=booking.get("check_out_date", ""),
        adults=booking.get("adults", 1),
        children=children_str,
        total_price=booking.get("total_price", ""),
        currency=profile.get("currency", "BDT"),
        hotel_name=profile.get("name", ""),
        receptionist_name=profile.get("receptionist_name", ""),
    )
    return await _send_meta_whatsapp(phone, msg, phone_number_id)
