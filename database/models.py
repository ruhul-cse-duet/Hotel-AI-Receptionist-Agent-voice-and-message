"""
Pydantic Models — MongoDB Schema Definitions
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field
import uuid


# ─────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────

class RoomType(str, Enum):
    STANDARD = "standard"
    DELUXE = "deluxe"
    SUITE = "suite"
    EXECUTIVE = "executive"
    PRESIDENTIAL = "presidential"


class BedType(str, Enum):
    SINGLE = "single"
    DOUBLE = "double"
    QUEEN = "queen"
    KING = "king"
    TWIN = "twin"


class BookingStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class ConversationChannel(str, Enum):
    VOICE = "voice"
    WHATSAPP = "whatsapp"


class ConversationStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


# -------------------------------
# HOTEL (TENANT) MODELS
# -------------------------------

class HotelConfig(BaseModel):
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")
    hotel_id: str = Field(default_factory=lambda: f"hotel_{uuid.uuid4().hex[:8]}")
    name: str
    website_url: Optional[str] = None
    owner_email: Optional[str] = None
    owner_password_hash: Optional[str] = None
    receptionist_name: str = "Aisha"
    phone: str = ""
    address: str = ""
    checkin_time: str = "14:00"
    checkout_time: str = "12:00"
    currency: str = "BDT"
    timezone: str = "Asia/Dhaka"
    db_name: str
    twilio_voice_number: Optional[str] = None
    twilio_whatsapp_number: Optional[str] = None
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    meta_whatsapp_phone_number_id: Optional[str] = None
    meta_waba_id: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True


# ─────────────────────────────────────────────
# ROOM MODELS
# ─────────────────────────────────────────────

class RoomPricing(BaseModel):
    base_price_per_night: float          # BDT
    weekend_surcharge_pct: float = 0.0   # % extra on weekends
    peak_season_surcharge_pct: float = 0.0
    discount_weekly_pct: float = 0.0     # % off for 7+ nights
    discount_monthly_pct: float = 0.0    # % off for 30+ nights
    tax_pct: float = 15.0                # VAT/tax


class RoomAmenities(BaseModel):
    wifi: bool = True
    ac: bool = True
    tv: bool = True
    minibar: bool = False
    balcony: bool = False
    sea_view: bool = False
    jacuzzi: bool = False
    kitchen: bool = False
    workspace: bool = False
    breakfast_included: bool = False


class Room(BaseModel):
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")
    room_number: str                     # "101", "202A"
    room_type: RoomType
    bed_type: BedType
    floor: int
    capacity: int                        # max guests
    size_sqft: Optional[int] = None
    description: str = ""
    amenities: RoomAmenities = RoomAmenities()
    pricing: RoomPricing
    images: List[str] = []               # URLs
    is_active: bool = True
    is_maintenance: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True


# ─────────────────────────────────────────────
# GUEST MODELS
# ─────────────────────────────────────────────

class GuestProfile(BaseModel):
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")
    phone: str                           # E.164 format: +8801XXXXXXXXX
    name: Optional[str] = None
    email: Optional[str] = None
    nationality: Optional[str] = None
    id_number: Optional[str] = None      # Passport / NID
    preferences: Dict[str, Any] = {}     # room_type, floor, etc.
    total_stays: int = 0
    vip_tier: str = "standard"           # standard | silver | gold | platinum
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_interaction: Optional[datetime] = None

    class Config:
        populate_by_name = True


# ─────────────────────────────────────────────
# BOOKING MODELS
# ─────────────────────────────────────────────

class BookingGuest(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    adults: int = 1
    children: int = 0


class PricingBreakdown(BaseModel):
    base_total: float
    taxes: float
    discounts: float
    final_total: float
    per_night_avg: float
    nights: int
    currency: str = "BDT"


class Booking(BaseModel):
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")
    booking_id: str = Field(default_factory=lambda: f"HTL{uuid.uuid4().hex[:8].upper()}")
    guest_phone: str
    guest_name: str
    guest_email: Optional[str] = None
    room_id: str
    room_number: str
    room_type: RoomType
    check_in_date: date
    check_out_date: date
    adults: int = 1
    children: int = 0
    special_requests: Optional[str] = None
    pricing: PricingBreakdown
    status: BookingStatus = BookingStatus.PENDING
    payment_status: str = "pending"      # pending | partial | paid
    source: str = "ai_receptionist"      # ai_receptionist | whatsapp | web | walk_in
    booking_notes: List[str] = []
    confirmation_sent: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    checked_in_at: Optional[datetime] = None
    checked_out_at: Optional[datetime] = None

    class Config:
        populate_by_name = True


# ─────────────────────────────────────────────
# CONVERSATION MODELS
# ─────────────────────────────────────────────

class ConversationMessage(BaseModel):
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    tool_calls: Optional[List[Dict]] = None
    tool_results: Optional[List[Dict]] = None
    audio_duration_sec: Optional[float] = None  # for voice messages


class ConversationContext(BaseModel):
    """Running context extracted during conversation"""
    guest_name: Optional[str] = None
    guest_phone: Optional[str] = None
    check_in_date: Optional[str] = None
    check_out_date: Optional[str] = None
    room_type: Optional[str] = None
    adults: int = 1
    children: int = 0
    special_requests: Optional[str] = None
    intent: Optional[str] = None          # booking | inquiry | cancellation | complaint
    booking_id: Optional[str] = None
    conversation_stage: str = "greeting"  # greeting | collecting_info | confirming | booked | support


class Conversation(BaseModel):
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    phone: str
    channel: ConversationChannel
    call_sid: Optional[str] = None        # Twilio call SID (voice only)
    messages: List[ConversationMessage] = []
    context: ConversationContext = ConversationContext()
    status: ConversationStatus = ConversationStatus.ACTIVE
    booking_ids: List[str] = []           # bookings made in this conversation
    duration_sec: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None

    class Config:
        populate_by_name = True


# ─────────────────────────────────────────────
# CALL SESSION (real-time call state)
# ─────────────────────────────────────────────

class CallSession(BaseModel):
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), alias="_id")
    call_sid: str
    phone: str
    session_id: str                       # links to Conversation
    websocket_connected: bool = False
    audio_buffer: List[str] = []          # base64 audio chunks (temp)
    partial_transcript: str = ""
    is_speaking: bool = False
    silence_counter: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True


# ─────────────────────────────────────────────
# API Request/Response Models
# ─────────────────────────────────────────────

class AvailabilityRequest(BaseModel):
    check_in_date: date
    check_out_date: date
    room_type: Optional[RoomType] = None
    adults: int = 1
    children: int = 0


class AvailabilityResponse(BaseModel):
    available_rooms: List[Dict]
    check_in_date: date
    check_out_date: date
    nights: int
    currency: str = "BDT"


class BookingCreateRequest(BaseModel):
    guest_name: str
    guest_phone: str
    guest_email: Optional[str] = None
    room_id: str
    check_in_date: date
    check_out_date: date
    adults: int = 1
    children: int = 0
    special_requests: Optional[str] = None


class BookingResponse(BaseModel):
    success: bool
    booking: Optional[Dict] = None
    message: str = ""
    error: Optional[str] = None


class HotelCreateRequest(BaseModel):
    name: str
    db_name: str
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
    is_active: Optional[bool] = True


class HotelUpdateRequest(BaseModel):
    name: Optional[str] = None
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
    is_active: Optional[bool] = None
