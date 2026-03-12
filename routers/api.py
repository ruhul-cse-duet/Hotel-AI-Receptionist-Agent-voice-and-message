"""
REST API Routers
- /bookings  — CRUD for hotel bookings
- /rooms     — Room management
- /admin     — Admin dashboard data
"""

import logging
from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Depends, Header
from fastapi.responses import JSONResponse

from database.mongodb import get_db, get_admin_db
from database.models import (
    Room, Booking, BookingStatus, RoomType,
    BookingCreateRequest, AvailabilityRequest,
    HotelConfig, HotelCreateRequest, HotelUpdateRequest
)
from ai.tools import get_tool_executor
from config import settings
from database.tenancy import resolve_hotel_by_id, set_current_tenant, get_hotel_profile

logger = logging.getLogger(__name__)

bookings_router = APIRouter(prefix="/bookings", tags=["Bookings"])
rooms_router = APIRouter(prefix="/rooms", tags=["Rooms"])
admin_router = APIRouter(prefix="/admin", tags=["Admin"])


async def require_admin_key(x_admin_key: str = Header(default="", alias="X-Admin-Key")):
    if not settings.ADMIN_SECRET_KEY:
        raise HTTPException(500, "ADMIN_SECRET_KEY not configured")
    if x_admin_key != settings.ADMIN_SECRET_KEY:
        raise HTTPException(401, "Invalid admin key")
    return True


async def require_hotel_context(x_hotel_id: str = Header(default="", alias="X-Hotel-Id")):
    if not x_hotel_id:
        raise HTTPException(400, "X-Hotel-Id header required")
    hotel = await resolve_hotel_by_id(x_hotel_id)
    if not hotel or not hotel.get("is_active", True):
        raise HTTPException(404, "Hotel not found or inactive")
    set_current_tenant(hotel)
    return hotel


# ──────────────────────────────────────────────────────────────────────────────
# PLATFORM ADMIN (HOTELS)
# ──────────────────────────────────────────────────────────────────────────────

@admin_router.get("/hotels", dependencies=[Depends(require_admin_key)])
async def list_hotels(
    page: int = Query(1, ge=1),
    limit: int = Query(50, le=200),
):
    db = get_admin_db()
    skip = (page - 1) * limit
    docs = await db.hotels.find({}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    total = await db.hotels.count_documents({})
    for doc in docs:
        doc.pop("_id", None)
    return {"hotels": docs, "total": total, "page": page, "pages": (total + limit - 1) // limit}


@admin_router.post("/hotels", dependencies=[Depends(require_admin_key)])
async def create_hotel(req: HotelCreateRequest):
    db = get_admin_db()
    hotel = HotelConfig(
        name=req.name,
        db_name=req.db_name,
        receptionist_name=req.receptionist_name or "Aisha",
        phone=req.phone or "",
        address=req.address or "",
        checkin_time=req.checkin_time or "14:00",
        checkout_time=req.checkout_time or "12:00",
        currency=req.currency or "BDT",
        timezone=req.timezone or "Asia/Dhaka",
        twilio_voice_number=req.twilio_voice_number,
        twilio_whatsapp_number=req.twilio_whatsapp_number,
        twilio_account_sid=req.twilio_account_sid,
        twilio_auth_token=req.twilio_auth_token,
        is_active=True if req.is_active is None else req.is_active,
    )
    doc = hotel.model_dump(by_alias=True)
    await db.hotels.insert_one(doc)
    doc.pop("_id", None)
    return {"success": True, "hotel": doc}


@admin_router.get("/hotels/{hotel_id}", dependencies=[Depends(require_admin_key)])
async def get_hotel(hotel_id: str):
    db = get_admin_db()
    doc = await db.hotels.find_one({"hotel_id": hotel_id})
    if not doc:
        raise HTTPException(404, "Hotel not found")
    doc.pop("_id", None)
    return doc


@admin_router.patch("/hotels/{hotel_id}", dependencies=[Depends(require_admin_key)])
async def update_hotel(hotel_id: str, req: HotelUpdateRequest):
    db = get_admin_db()
    update = {k: v for k, v in req.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(400, "No fields to update")
    update["updated_at"] = datetime.utcnow()
    result = await db.hotels.update_one({"hotel_id": hotel_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(404, "Hotel not found")
    doc = await db.hotels.find_one({"hotel_id": hotel_id})
    doc.pop("_id", None)
    return {"success": True, "hotel": doc}


@admin_router.delete("/hotels/{hotel_id}", dependencies=[Depends(require_admin_key)])
async def delete_hotel(hotel_id: str):
    db = get_admin_db()
    result = await db.hotels.delete_one({"hotel_id": hotel_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Hotel not found")
    return {"success": True, "hotel_id": hotel_id}

# ─────────────────────────────────────────────
# BOOKINGS API
# ─────────────────────────────────────────────

@bookings_router.get("/")
async def list_bookings(
    status: Optional[str] = Query(None),
    check_in_date: Optional[date] = Query(None),
    guest_phone: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, le=100),
    _hotel=Depends(require_hotel_context),
):
    db = get_db()
    query = {}
    if status:
        query["status"] = status
    if check_in_date:
        query["check_in_date"] = str(check_in_date)
    if guest_phone:
        query["guest_phone"] = guest_phone

    skip = (page - 1) * limit
    total = await db.bookings.count_documents(query)
    docs = await db.bookings.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

    # Clean up MongoDB ObjectId
    for doc in docs:
        doc.pop("_id", None)

    return {
        "bookings": docs,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit,
    }


@bookings_router.get("/{booking_id}")
async def get_booking(booking_id: str, _hotel=Depends(require_hotel_context)):
    db = get_db()
    doc = await db.bookings.find_one({"booking_id": booking_id.upper()})
    if not doc:
        raise HTTPException(status_code=404, detail="Booking not found")
    doc.pop("_id", None)
    return doc


@bookings_router.post("/")
async def create_booking_api(req: BookingCreateRequest, _hotel=Depends(require_hotel_context)):
    executor = get_tool_executor()
    
    # Get room details to determine room_type
    db = get_db()
    room = await db.rooms.find_one({"_id": req.room_id})
    if not room:
        raise HTTPException(status_code=404, detail=f"Room {req.room_id} not found")
    
    room_type = room.get("room_type", "standard")
    
    result = await executor.create_booking(
        guest_name=req.guest_name,
        guest_phone=req.guest_phone,
        guest_email=req.guest_email,
        room_type=room_type,
        check_in_date=str(req.check_in_date),
        check_out_date=str(req.check_out_date),
        adults=req.adults,
        children=req.children,
        special_requests=req.special_requests,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Booking failed"))
    return result


@bookings_router.patch("/{booking_id}/status")
async def update_booking_status(booking_id: str, status: str, _hotel=Depends(require_hotel_context)):
    valid = [s.value for s in BookingStatus]
    if status not in valid:
        raise HTTPException(400, f"Invalid status. Valid: {valid}")

    db = get_db()
    result = await db.bookings.update_one(
        {"booking_id": booking_id.upper()},
        {"$set": {"status": status, "updated_at": datetime.utcnow()}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Booking not found")
    return {"success": True, "booking_id": booking_id, "status": status}


@bookings_router.delete("/{booking_id}")
async def cancel_booking_api(booking_id: str, reason: Optional[str] = Query(None), _hotel=Depends(require_hotel_context)):
    executor = get_tool_executor()
    result = await executor.cancel_booking(booking_id, reason)
    if result.get("error"):
        raise HTTPException(400, result["error"])
    return result


# ─────────────────────────────────────────────
# ROOMS API
# ─────────────────────────────────────────────

@rooms_router.get("/")
async def list_rooms(
    room_type: Optional[str] = None,
    is_active: bool = True,
    _hotel=Depends(require_hotel_context),
):
    db = get_db()
    query: dict = {"is_active": is_active}
    if room_type:
        query["room_type"] = room_type

    docs = await db.rooms.find(query).sort("room_number", 1).to_list(200)
    for doc in docs:
        doc.pop("_id", None)
    return {"rooms": docs, "total": len(docs)}


@rooms_router.post("/")
async def create_room(room: Room, _hotel=Depends(require_hotel_context)):
    db = get_db()
    existing = await db.rooms.find_one({"room_number": room.room_number})
    if existing:
        raise HTTPException(400, f"Room {room.room_number} already exists")

    doc = room.model_dump(by_alias=True)
    await db.rooms.insert_one(doc)
    doc.pop("_id", None)
    return {"success": True, "room": doc}


@rooms_router.get("/availability")
async def check_availability(
    check_in_date: date = Query(...),
    check_out_date: date = Query(...),
    room_type: Optional[str] = Query(None),
    adults: int = Query(1),
    children: int = Query(0),
    _hotel=Depends(require_hotel_context),
):
    executor = get_tool_executor()
    result = await executor.check_room_availability(
        check_in_date=str(check_in_date),
        check_out_date=str(check_out_date),
        room_type=room_type,
        adults=adults,
        children=children,
    )
    return result


# ─────────────────────────────────────────────
# ADMIN DASHBOARD
# ─────────────────────────────────────────────

@admin_router.get("/dashboard")
async def dashboard_stats(_hotel=Depends(require_hotel_context)):
    """Dashboard overview stats"""
    db = get_db()
    today = str(date.today())

    total_bookings = await db.bookings.count_documents({})
    confirmed = await db.bookings.count_documents({"status": "confirmed"})
    checked_in = await db.bookings.count_documents({"status": "checked_in"})
    today_checkins = await db.bookings.count_documents({
        "check_in_date": today,
        "status": {"$in": ["confirmed", "checked_in"]}
    })
    today_checkouts = await db.bookings.count_documents({
        "check_out_date": today,
        "status": "checked_in"
    })

    # Revenue this month
    from datetime import date
    first_day = date.today().replace(day=1)
    revenue_pipeline = [
        {"$match": {
            "status": {"$in": ["confirmed", "checked_in", "checked_out"]},
            "created_at": {"$gte": datetime(first_day.year, first_day.month, 1)}
        }},
        {"$group": {"_id": None, "total": {"$sum": "$pricing.final_total"}}}
    ]
    rev_result = await db.bookings.aggregate(revenue_pipeline).to_list(1)
    monthly_revenue = rev_result[0]["total"] if rev_result else 0

    total_rooms = await db.rooms.count_documents({"is_active": True})
    occupied_rooms = await db.bookings.count_documents({
        "status": "checked_in",
        "check_in_date": {"$lte": today},
        "check_out_date": {"$gt": today},
    })
    occupancy_rate = round((occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0, 1)

    # Recent conversations
    recent_conv = await db.conversations.count_documents({
        "created_at": {"$gte": datetime(date.today().year, date.today().month, date.today().day)}
    })

    return {
        "bookings": {
            "total": total_bookings,
            "confirmed": confirmed,
            "checked_in": checked_in,
            "today_checkins": today_checkins,
            "today_checkouts": today_checkouts,
        },
        "revenue": {
            "monthly": round(monthly_revenue, 2),
            "currency": get_hotel_profile()["currency"],
        },
        "occupancy": {
            "total_rooms": total_rooms,
            "occupied": occupied_rooms,
            "rate_pct": occupancy_rate,
        },
        "ai": {
            "conversations_today": recent_conv,
        }
    }


@admin_router.get("/conversations")
async def list_conversations(
    channel: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    _hotel=Depends(require_hotel_context),
):
    db = get_db()
    query = {}
    if channel:
        query["channel"] = channel
    if status:
        query["status"] = status

    skip = (page - 1) * limit
    docs = await db.conversations.find(
        query,
        {"messages": 0}  # exclude messages for list view
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

    total = await db.conversations.count_documents(query)

    for doc in docs:
        doc.pop("_id", None)

    return {"conversations": docs, "total": total}


@admin_router.post("/seed-rooms")
async def seed_rooms(_hotel=Depends(require_hotel_context)):
    """Seed sample rooms for testing"""
    db = get_db()
    count = await db.rooms.count_documents({})
    if count > 0:
        return {"message": f"Already have {count} rooms. Skipping."}

    rooms = [
        # Standard Rooms (Floor 1-3)
        *[{
            "_id": f"room_std_{i:03d}",
            "room_number": f"{floor}{i:02d}",
            "room_type": "standard",
            "bed_type": "queen",
            "floor": floor,
            "capacity": 2,
            "size_sqft": 350,
            "description": "Comfortable standard room with city view, queen bed, and all modern amenities.",
            "amenities": {"wifi": True, "ac": True, "tv": True, "minibar": False, "balcony": False, "breakfast_included": False},
            "pricing": {"base_price_per_night": 5000, "tax_pct": 15, "discount_weekly_pct": 10},
            "is_active": True,
            "is_maintenance": False,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        } for floor in range(1, 4) for i in range(1, 6)],
        # Deluxe Rooms (Floor 4-6)
        *[{
            "_id": f"room_dlx_{i:03d}",
            "room_number": f"{floor}{i:02d}",
            "room_type": "deluxe",
            "bed_type": "king",
            "floor": floor,
            "capacity": 3,
            "size_sqft": 500,
            "description": "Spacious deluxe room with panoramic views, king bed, and premium amenities.",
            "amenities": {"wifi": True, "ac": True, "tv": True, "minibar": True, "balcony": True, "breakfast_included": True},
            "pricing": {"base_price_per_night": 9000, "tax_pct": 15, "discount_weekly_pct": 12},
            "is_active": True,
            "is_maintenance": False,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        } for floor in range(4, 7) for i in range(1, 4)],
        # Suites (Floor 7-8)
        *[{
            "_id": f"room_suite_{i:03d}",
            "room_number": f"{floor}0{i}",
            "room_type": "suite",
            "bed_type": "king",
            "floor": floor,
            "capacity": 4,
            "size_sqft": 900,
            "description": "Luxurious suite with separate living area, king bed, and stunning city skyline views.",
            "amenities": {"wifi": True, "ac": True, "tv": True, "minibar": True, "balcony": True, "jacuzzi": True, "breakfast_included": True},
            "pricing": {"base_price_per_night": 18000, "tax_pct": 15, "discount_weekly_pct": 15},
            "is_active": True,
            "is_maintenance": False,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        } for floor in range(7, 9) for i in range(1, 3)],
        # Presidential Suite (Floor 10)
        {
            "_id": "room_presidential_001",
            "room_number": "1001",
            "room_type": "presidential",
            "bed_type": "king",
            "floor": 10,
            "capacity": 6,
            "size_sqft": 2500,
            "description": "The ultimate luxury experience with private butler, multiple rooms, private pool, and VIP services.",
            "amenities": {"wifi": True, "ac": True, "tv": True, "minibar": True, "balcony": True, "jacuzzi": True, "kitchen": True, "breakfast_included": True},
            "pricing": {"base_price_per_night": 75000, "tax_pct": 15, "discount_weekly_pct": 5},
            "is_active": True,
            "is_maintenance": False,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
    ]

    await db.rooms.insert_many(rooms)
    return {"success": True, "rooms_created": len(rooms)}
