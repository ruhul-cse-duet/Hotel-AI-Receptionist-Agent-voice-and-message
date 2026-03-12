"""
Tenant resolution and request-scoped hotel context.
Supports DB-per-hotel using a shared Mongo client.
"""

import logging
from contextvars import ContextVar
from typing import Optional, Dict, Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from config import settings
from database.mongodb import get_admin_db, get_db_by_name, ensure_tenant_indexes

logger = logging.getLogger(__name__)

_current_hotel: ContextVar[Optional[Dict[str, Any]]] = ContextVar("current_hotel", default=None)
_current_db: ContextVar[Optional[AsyncIOMotorDatabase]] = ContextVar("current_db", default=None)


def set_current_tenant(hotel_doc: Dict[str, Any]) -> AsyncIOMotorDatabase:
    """Set request-scoped hotel + tenant db context."""
    if not hotel_doc:
        _current_hotel.set(None)
        _current_db.set(None)
        return None

    db_name = hotel_doc.get("db_name") or settings.MONGODB_DB_NAME
    db = get_db_by_name(db_name)
    ensure_tenant_indexes(db_name, db)
    _current_hotel.set(hotel_doc)
    _current_db.set(db)
    return db


def clear_current_tenant() -> None:
    _current_hotel.set(None)
    _current_db.set(None)


def get_current_hotel() -> Optional[Dict[str, Any]]:
    return _current_hotel.get()


def get_tenant_db() -> AsyncIOMotorDatabase:
    db = _current_db.get()
    if db is None:
        # Fallback to admin DB for legacy single-tenant usage.
        db = get_admin_db()
        if db is not None:
            ensure_tenant_indexes(settings.MONGODB_DB_NAME, db)
        logger.warning("Tenant DB not set; using admin DB as fallback.")
    return db


def _normalize_twilio_number(value: Optional[str]) -> str:
    if not value:
        return ""
    return value.replace("whatsapp:", "").strip()


def _default_hotel_doc() -> Dict[str, Any]:
    return {
        "hotel_id": "default",
        "name": settings.HOTEL_NAME,
        "receptionist_name": settings.RECEPTIONIST_NAME,
        "phone": settings.HOTEL_PHONE,
        "address": settings.HOTEL_ADDRESS,
        "checkin_time": settings.HOTEL_CHECKIN_TIME,
        "checkout_time": settings.HOTEL_CHECKOUT_TIME,
        "currency": settings.HOTEL_CURRENCY,
        "timezone": settings.HOTEL_TIMEZONE,
        "twilio_voice_number": settings.TWILIO_PHONE_NUMBER,
        "twilio_whatsapp_number": settings.TWILIO_WHATSAPP_NUMBER,
        "twilio_account_sid": settings.TWILIO_ACCOUNT_SID,
        "twilio_auth_token": settings.TWILIO_AUTH_TOKEN,
        "db_name": settings.MONGODB_DB_NAME,
        "is_active": True,
    }


async def resolve_hotel_by_twilio_number(to_number: Optional[str], channel: str) -> Optional[Dict[str, Any]]:
    """Resolve hotel config by Twilio 'To' number."""
    db = get_admin_db()
    if db is None:
        return None

    to_number_norm = _normalize_twilio_number(to_number)
    if not to_number_norm:
        return None

    if channel == "whatsapp":
        query = {"twilio_whatsapp_number": {"$in": [to_number_norm, f"whatsapp:{to_number_norm}"]}}
    else:
        query = {"twilio_voice_number": to_number_norm}

    hotel = await db.hotels.find_one(query)
    if hotel:
        return hotel

    # Fallback for single-tenant setups using .env settings without a hotels record.
    if channel == "whatsapp":
        default_wa = _normalize_twilio_number(settings.TWILIO_WHATSAPP_NUMBER)
        if default_wa and default_wa == to_number_norm:
            logger.warning("No hotel record found for WhatsApp number; using default settings fallback.")
            return _default_hotel_doc()
    else:
        default_voice = _normalize_twilio_number(settings.TWILIO_PHONE_NUMBER)
        if default_voice and default_voice == to_number_norm:
            logger.warning("No hotel record found for voice number; using default settings fallback.")
            return _default_hotel_doc()

    return None


async def resolve_hotel_by_id(hotel_id: str) -> Optional[Dict[str, Any]]:
    db = get_admin_db()
    if db is None:
        return None
    return await db.hotels.find_one({"hotel_id": hotel_id})


def get_hotel_profile() -> Dict[str, Any]:
    """Return hotel profile merged with defaults from settings."""
    hotel = get_current_hotel() or {}
    return {
        "hotel_id": hotel.get("hotel_id", "default"),
        "name": hotel.get("name", settings.HOTEL_NAME),
        "receptionist_name": hotel.get("receptionist_name", settings.RECEPTIONIST_NAME),
        "phone": hotel.get("phone", settings.HOTEL_PHONE),
        "address": hotel.get("address", settings.HOTEL_ADDRESS),
        "checkin_time": hotel.get("checkin_time", settings.HOTEL_CHECKIN_TIME),
        "checkout_time": hotel.get("checkout_time", settings.HOTEL_CHECKOUT_TIME),
        "currency": hotel.get("currency", settings.HOTEL_CURRENCY),
        "timezone": hotel.get("timezone", settings.HOTEL_TIMEZONE),
        "twilio_voice_number": hotel.get("twilio_voice_number", settings.TWILIO_PHONE_NUMBER),
        "twilio_whatsapp_number": hotel.get("twilio_whatsapp_number", settings.TWILIO_WHATSAPP_NUMBER),
        "twilio_account_sid": hotel.get("twilio_account_sid", settings.TWILIO_ACCOUNT_SID),
        "twilio_auth_token": hotel.get("twilio_auth_token", settings.TWILIO_AUTH_TOKEN),
        "db_name": hotel.get("db_name", settings.MONGODB_DB_NAME),
        "is_active": hotel.get("is_active", True),
    }
