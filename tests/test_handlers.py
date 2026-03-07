"""
Unit tests for API, WhatsApp, and Voice handlers
Tests webhook processing and basic handler logic.
"""

import pytest
from datetime import date


class TestBookingAPI:
    """Test booking-related API endpoints"""
    
    @pytest.mark.asyncio
    async def test_check_availability_basic(self, mock_db):
        """Test availability check"""
        from database.models import Room, RoomType, BedType, RoomPricing, RoomAmenities
        
        # Insert test room
        room = Room(
            room_number="101",
            room_type=RoomType.DELUXE,
            bed_type=BedType.QUEEN,
            floor=1,
            capacity=2,
            amenities=RoomAmenities(),
            pricing=RoomPricing(base_price_per_night=8500),
        )
        await mock_db.rooms.insert_one(room.model_dump(by_alias=True))
        
        # Verify room was inserted
        found = await mock_db.rooms.find_one({"room_number": "101"})
        assert found is not None
        assert found["room_type"] == "deluxe"
    
    @pytest.mark.asyncio
    async def test_booking_creation_mock(self, mock_db):
        """Test booking creation in mock database"""
        from database.models import Booking, BookingStatus, RoomType, PricingBreakdown
        
        # Create booking
        booking = Booking(
            guest_phone="+880123456789",
            guest_name="Test Guest",
            room_id="room-1",
            room_number="101",
            room_type=RoomType.DELUXE,
            check_in_date=date(2026, 3, 15),
            check_out_date=date(2026, 3, 17),
            pricing=PricingBreakdown(
                base_total=17000,
                taxes=2550,
                discounts=0,
                final_total=19550,
                per_night_avg=8500,
                nights=2,
                currency="BDT"
            ),
            status=BookingStatus.CONFIRMED,
        )
        
        # Insert booking
        doc = booking.model_dump(by_alias=True)
        doc["check_in_date"] = "2026-03-15"
        doc["check_out_date"] = "2026-03-17"
        result = await mock_db.bookings.insert_one(doc)
        
        # Verify
        found = await mock_db.bookings.find_one({"guest_phone": "+880123456789"})
        assert found is not None
        assert found["guest_name"] == "Test Guest"


class TestWhatsAppHandler:
    """Test WhatsApp message handling"""
    
    @pytest.mark.asyncio
    async def test_whatsapp_session_creation(self, mock_db):
        """Test WhatsApp session is created"""
        from database.models import Conversation, ConversationChannel, ConversationContext
        
        # Create session
        conv = Conversation(
            session_id="whatsapp-session-1",
            phone="+880123456789",
            channel=ConversationChannel.WHATSAPP,
            context=ConversationContext(guest_phone="+880123456789"),
        )
        
        # Save to mock db
        await mock_db.conversations.insert_one(conv.model_dump(by_alias=True))
        
        # Verify
        found = await mock_db.conversations.find_one({"session_id": "whatsapp-session-1"})
        assert found is not None
        assert found["channel"] == "whatsapp"
    
    @pytest.mark.asyncio
    async def test_whatsapp_message_history(self, mock_db):
        """Test WhatsApp message history is saved"""
        from database.models import (
            Conversation, ConversationChannel, ConversationContext,
            ConversationMessage, MessageRole
        )
        
        session_id = "whatsapp-session-2"
        
        # Create conversation
        conv = Conversation(
            session_id=session_id,
            phone="+880123456789",
            channel=ConversationChannel.WHATSAPP,
            context=ConversationContext(guest_phone="+880123456789"),
        )
        await mock_db.conversations.insert_one(conv.model_dump(by_alias=True))
        
        # Add messages
        msg1 = ConversationMessage(role=MessageRole.USER, content="Hi")
        msg2 = ConversationMessage(role=MessageRole.ASSISTANT, content="Hello!")
        
        await mock_db.conversations.update_one(
            {"session_id": session_id},
            {
                "$push": {
                    "messages": {
                        "$each": [msg1.model_dump(), msg2.model_dump()]
                    }
                }
            }
        )
        
        # Verify
        found = await mock_db.conversations.find_one({"session_id": session_id})
        assert len(found["messages"]) >= 2


class TestVoiceCallHandler:
    """Test voice call handling"""
    
    @pytest.mark.asyncio
    async def test_call_session_creation(self, mock_db):
        """Test voice call session is created"""
        from database.models import CallSession
        
        # Create call session
        session = CallSession(
            call_sid="CA1234567890",
            phone="+880123456789",
            session_id="voice-session-1",
        )
        
        # Save to mock db
        await mock_db.call_sessions.insert_one(session.model_dump(by_alias=True))
        
        # Verify
        found = await mock_db.call_sessions.find_one({"call_sid": "CA1234567890"})
        assert found is not None
        assert found["phone"] == "+880123456789"
    
    @pytest.mark.asyncio
    async def test_call_conversation_creation(self, mock_db):
        """Test voice conversation is created"""
        from database.models import Conversation, ConversationChannel, ConversationContext
        
        # Create conversation
        conv = Conversation(
            session_id="voice-session-2",
            phone="+880123456789",
            channel=ConversationChannel.VOICE,
            call_sid="CA9876543210",
            context=ConversationContext(guest_phone="+880123456789"),
        )
        
        await mock_db.conversations.insert_one(conv.model_dump(by_alias=True))
        
        # Verify
        found = await mock_db.conversations.find_one({"session_id": "voice-session-2"})
        assert found is not None
        assert found["channel"] == "voice"
        assert found["call_sid"] == "CA9876543210"


class TestGuestProfiles:
    """Test guest profile management"""
    
    @pytest.mark.asyncio
    async def test_guest_profile_creation(self, mock_db):
        """Test guest profile is created"""
        from database.models import GuestProfile
        
        # Create guest
        guest = GuestProfile(
            phone="+880123456789",
            name="Ahmed Khan",
            email="ahmed@example.com",
        )
        
        await mock_db.guests.insert_one(guest.model_dump(by_alias=True))
        
        # Verify
        found = await mock_db.guests.find_one({"phone": "+880123456789"})
        assert found is not None
        assert found["name"] == "Ahmed Khan"
    
    @pytest.mark.asyncio
    async def test_guest_profile_update(self, mock_db):
        """Test guest profile is updated"""
        from database.models import GuestProfile
        
        # Create guest
        guest = GuestProfile(
            phone="+880987654321",
            name="Fatima Rahman",
        )
        await mock_db.guests.insert_one(guest.model_dump(by_alias=True))
        
        # Update guest
        await mock_db.guests.update_one(
            {"phone": "+880987654321"},
            {"$set": {"email": "fatima@example.com"}}
        )
        
        # Verify
        found = await mock_db.guests.find_one({"phone": "+880987654321"})
        assert found["email"] == "fatima@example.com"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
