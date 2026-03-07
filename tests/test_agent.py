"""
Unit tests for Hotel AI Agent
Tests conversation, message processing, and context management.
Uses mocked LLM and database (see conftest.py).
"""

import pytest
from ai.agent import HotelAgent
from database.models import ConversationChannel, Conversation, ConversationContext


class TestHotelAgentInitialization:
    """Test agent initialization"""
    
    def test_voice_agent_creation(self):
        """Test voice agent initialization"""
        agent = HotelAgent(ConversationChannel.VOICE)
        assert agent.is_voice is True
        assert agent.channel == ConversationChannel.VOICE
    
    def test_whatsapp_agent_creation(self):
        """Test WhatsApp agent initialization"""
        agent = HotelAgent(ConversationChannel.WHATSAPP)
        assert agent.is_voice is False
        assert agent.channel == ConversationChannel.WHATSAPP


class TestHotelAgentMessageProcessing:
    """Test message processing and agentic loop"""
    
    @pytest.mark.asyncio
    async def test_process_simple_message(self, mock_db):
        """Test processing a simple greeting"""
        agent = HotelAgent(ConversationChannel.WHATSAPP)
        
        # Create test session
        session_id = "test-session-123"
        phone = "+880123456789"
        
        # Insert initial conversation
        conv = Conversation(
            session_id=session_id,
            phone=phone,
            channel=ConversationChannel.WHATSAPP,
            context=ConversationContext(guest_phone=phone),
        )
        await mock_db.conversations.insert_one(conv.model_dump(by_alias=True))
        
        # Process message
        response, tool_calls = await agent.process_message(
            session_id=session_id,
            user_message="Hello, do you have rooms available?",
            phone=phone,
        )
        
        # Assertions
        assert isinstance(response, str)
        assert len(response) > 0
        assert isinstance(tool_calls, list)
    
    @pytest.mark.asyncio
    async def test_process_booking_request(self, mock_db):
        """Test processing a booking request"""
        agent = HotelAgent(ConversationChannel.VOICE)
        
        session_id = "test-session-456"
        phone = "+880987654321"
        
        # Create conversation
        conv = Conversation(
            session_id=session_id,
            phone=phone,
            channel=ConversationChannel.VOICE,
            context=ConversationContext(guest_phone=phone),
        )
        await mock_db.conversations.insert_one(conv.model_dump(by_alias=True))
        
        # Process booking request
        response, tool_calls = await agent.process_message(
            session_id=session_id,
            user_message="I want to book a room for March 15 to 17",
            phone=phone,
        )
        
        assert isinstance(response, str)
        assert isinstance(tool_calls, list)
    
    @pytest.mark.asyncio
    async def test_conversation_history_saved(self, mock_db):
        """Test that conversation history is saved to MongoDB"""
        agent = HotelAgent(ConversationChannel.WHATSAPP)
        
        session_id = "test-session-789"
        phone = "+880555555555"
        
        # Create conversation
        conv = Conversation(
            session_id=session_id,
            phone=phone,
            channel=ConversationChannel.WHATSAPP,
            context=ConversationContext(guest_phone=phone),
        )
        await mock_db.conversations.insert_one(conv.model_dump(by_alias=True))
        
        # Send message
        await agent.process_message(
            session_id=session_id,
            user_message="Hello!",
            phone=phone,
        )
        
        # Check if conversation was saved
        saved = await mock_db.conversations.find_one({"session_id": session_id})
        assert saved is not None
        assert "messages" in saved
        assert len(saved["messages"]) > 0


class TestAgentLazyLoading:
    """Test that agent doesn't eagerly load LLM provider"""
    
    def test_agent_lazy_llm_initialization(self):
        """Test that LLM provider is lazily loaded"""
        agent = HotelAgent(ConversationChannel.VOICE)
        
        # Initially _llm should be None
        assert agent._llm is None
        
        # After accessing llm property, it should be loaded
        _ = agent.llm
        assert agent._llm is not None
    
    def test_agent_executor_eager_load(self):
        """Test that executor is loaded at init"""
        agent = HotelAgent(ConversationChannel.VOICE)
        
        # Executor should be loaded immediately
        assert agent.executor is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
