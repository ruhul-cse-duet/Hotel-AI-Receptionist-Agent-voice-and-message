"""
MongoDB Async Connection via Motor
Collections: rooms, bookings, guests, conversations, call_sessions, hotels (admin)
"""

import logging
from typing import Optional, Set

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import IndexModel, ASCENDING, DESCENDING

from config import settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncIOMotorClient] = None
_admin_db: Optional[AsyncIOMotorDatabase] = None
_indexed_tenant_dbs: Set[str] = set()


async def connect_db():
    global _client, _admin_db
    _client = AsyncIOMotorClient(
        settings.MONGODB_URI,
        serverSelectionTimeoutMS=5000,
        maxPoolSize=50,
        minPoolSize=5,
    )
    _admin_db = _client[settings.MONGODB_DB_NAME]
    await _create_admin_indexes()
    # Default tenant indexes for legacy single-tenant mode
    ensure_tenant_indexes(settings.MONGODB_DB_NAME, _admin_db)
    logger.info(f"✅ MongoDB connected → admin={settings.MONGODB_DB_NAME}")


async def disconnect_db():
    global _client
    if _client:
        _client.close()
        logger.info("MongoDB disconnected")


def get_client() -> AsyncIOMotorClient:
    return _client


def get_admin_db() -> AsyncIOMotorDatabase:
    return _admin_db


def get_db_by_name(db_name: str) -> AsyncIOMotorDatabase:
    if not _client:
        raise RuntimeError("MongoDB client not initialized")
    return _client[db_name]


def get_db() -> AsyncIOMotorDatabase:
    from database.tenancy import get_tenant_db
    return get_tenant_db()


def ensure_tenant_indexes(db_name: str, db: AsyncIOMotorDatabase) -> None:
    if not db_name or db is None:
        return
    if db_name in _indexed_tenant_dbs:
        return
    _indexed_tenant_dbs.add(db_name)
    # run in background to avoid blocking request path
    import asyncio
    asyncio.create_task(_create_tenant_indexes(db))


async def _create_admin_indexes():
    db = _admin_db
    if db is None:
        return

    await db.hotels.create_indexes([
        IndexModel([("hotel_id", ASCENDING)], unique=True),
        IndexModel([("db_name", ASCENDING)], unique=True),
        IndexModel([("twilio_voice_number", ASCENDING)], unique=True, sparse=True),
        IndexModel([("twilio_whatsapp_number", ASCENDING)], unique=True, sparse=True),
        IndexModel([("is_active", ASCENDING)]),
        IndexModel([("created_at", DESCENDING)]),
    ])

    logger.info("✅ Admin indexes created (hotels)")


async def _create_tenant_indexes(db: AsyncIOMotorDatabase):
    if db is None:
        return

    # Rooms
    await db.rooms.create_indexes([
        IndexModel([("room_number", ASCENDING)], unique=True),
        IndexModel([("room_type", ASCENDING)]),
        IndexModel([("is_active", ASCENDING)]),
    ])

    # Bookings
    await db.bookings.create_indexes([
        IndexModel([("booking_id", ASCENDING)], unique=True),
        IndexModel([("guest_phone", ASCENDING)]),
        IndexModel([("room_id", ASCENDING)]),
        IndexModel([("check_in_date", ASCENDING), ("check_out_date", ASCENDING)]),
        IndexModel([("status", ASCENDING)]),
        IndexModel([("created_at", DESCENDING)]),
    ])

    # Guests
    await db.guests.create_indexes([
        IndexModel([("phone", ASCENDING)], unique=True),
        IndexModel([("email", ASCENDING)]),
        IndexModel([("name", ASCENDING)]),
    ])

    # Conversations (call & whatsapp sessions)
    await db.conversations.create_indexes([
        IndexModel([("session_id", ASCENDING)], unique=True),
        IndexModel([("phone", ASCENDING)]),
        IndexModel([("channel", ASCENDING)]),    # voice | whatsapp
        IndexModel([("created_at", DESCENDING)]),
        IndexModel([("status", ASCENDING)]),
    ])

    # Call sessions (real-time call state)
    await db.call_sessions.create_indexes([
        IndexModel([("call_sid", ASCENDING)], unique=True),
        IndexModel([("phone", ASCENDING)]),
        IndexModel([("created_at", DESCENDING)]),
    ])

    logger.info("✅ Tenant indexes created")
