"""
Public onboarding endpoints for hotel self-setup and website scraping.
"""

import hashlib
import html
import logging
import re
import secrets
from html.parser import HTMLParser
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import settings
from database.models import HotelConfig
from database.mongodb import get_admin_db

logger = logging.getLogger(__name__)

onboarding_router = APIRouter(prefix="/api/onboarding", tags=["Onboarding"])


class ScrapeRequest(BaseModel):
    url: str = Field(..., min_length=8)


class OnboardingRequest(BaseModel):
    name: str
    db_name: Optional[str] = None
    receptionist_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    checkin_time: Optional[str] = None
    checkout_time: Optional[str] = None
    currency: Optional[str] = None
    timezone: Optional[str] = None
    twilio_voice_number: Optional[str] = None
    twilio_whatsapp_number: Optional[str] = None
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    website_url: Optional[str] = None
    owner_email: Optional[str] = None
    owner_password: Optional[str] = None


class _MetaTitleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title: str = ""
        self._in_title = False
        self.meta: dict[str, str] = {}
        self.text_chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = {k.lower(): v for k, v in attrs if k}
        if tag.lower() == "title":
            self._in_title = True
        if tag.lower() == "meta":
            key = attrs_dict.get("property") or attrs_dict.get("name")
            if key:
                content = attrs_dict.get("content", "")
                self.meta[key.lower()] = content

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()
        if data and data.strip():
            self.text_chunks.append(data.strip())


def _slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "hotel"


async def _ensure_unique_db_name(base: str) -> str:
    db = get_admin_db()
    if db is None:
        return base
    candidate = base
    for _ in range(10):
        exists = await db.hotels.find_one({"db_name": candidate}, {"_id": 1})
        if not exists:
            return candidate
        candidate = f"{base}-{secrets.token_hex(2)}"
    return f"{base}-{secrets.token_hex(3)}"


def _hash_password(raw: str) -> str:
    salt = secrets.token_hex(8)
    digest = hashlib.sha256(f"{salt}:{raw}".encode("utf-8")).hexdigest()
    return f"{salt}${digest}"


def _extract_phone(text: str) -> Optional[str]:
    pattern = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")
    matches = pattern.findall(text)
    if not matches:
        return None
    cleaned = re.sub(r"[^\d+]", "", matches[0])
    return cleaned if len(cleaned) >= 9 else None


def _extract_address(text: str) -> Optional[str]:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    for line in lines:
        if "address" in line.lower() and len(line) < 140:
            return line
    return None


@onboarding_router.post("/scrape")
async def scrape_hotel_website(req: ScrapeRequest):
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(req.url)
            resp.raise_for_status()
            html_text = resp.text
    except Exception as e:
        raise HTTPException(400, f"Failed to fetch website: {e}")

    parser = _MetaTitleParser()
    parser.feed(html_text)
    raw_text = html.unescape(" ".join(parser.text_chunks))

    name = parser.meta.get("og:site_name") or parser.title
    phone = (
        parser.meta.get("tel")
        or parser.meta.get("telephone")
        or _extract_phone(raw_text)
    )
    address = (
        parser.meta.get("address")
        or parser.meta.get("og:street-address")
        or parser.meta.get("street-address")
        or _extract_address(raw_text)
    )

    return {
        "name": name or "",
        "phone": phone or "",
        "address": address or "",
        "website_url": req.url,
    }


@onboarding_router.post("/create")
async def create_hotel_onboarding(req: OnboardingRequest):
    db = get_admin_db()
    if db is None:
        raise HTTPException(500, "Database not available")

    db_name = req.db_name or _slugify(req.name)
    db_name = await _ensure_unique_db_name(db_name)

    hotel = HotelConfig(
        name=req.name,
        db_name=db_name,
        receptionist_name=req.receptionist_name or settings.RECEPTIONIST_NAME,
        phone=req.phone or settings.HOTEL_PHONE,
        address=req.address or settings.HOTEL_ADDRESS,
        checkin_time=req.checkin_time or settings.HOTEL_CHECKIN_TIME,
        checkout_time=req.checkout_time or settings.HOTEL_CHECKOUT_TIME,
        currency=req.currency or settings.HOTEL_CURRENCY,
        timezone=req.timezone or settings.HOTEL_TIMEZONE,
        twilio_voice_number=req.twilio_voice_number,
        twilio_whatsapp_number=req.twilio_whatsapp_number,
        twilio_account_sid=req.twilio_account_sid,
        twilio_auth_token=req.twilio_auth_token,
        website_url=req.website_url,
        owner_email=req.owner_email,
        owner_password_hash=_hash_password(req.owner_password) if req.owner_password else None,
        is_active=True,
    )

    doc = hotel.model_dump(by_alias=True)
    await db.hotels.insert_one(doc)
    doc.pop("_id", None)
    return {"success": True, "hotel": doc}
