"""
Pytest Configuration & Fixtures
Provides mocks for LLM provider and MongoDB for testing without external dependencies.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
from typing import Dict, List


# ─────────────────────────────────────────────────────────
# Mock LLM Provider (for testing without API keys)
# ─────────────────────────────────────────────────────────

class MockLLMProvider:
    """Lightweight mock LLM that returns canned responses"""
    
    async def chat_completion(
        self,
        messages: List[Dict],
        tools=None,
        tool_choice="auto",
        temperature=0.7,
        max_tokens=1024,
    ) -> Dict:
        """Return a mock response"""
        # Check what the user is asking
        last_message = messages[-1].get("content", "").lower()
        
        if "availability" in last_message or "room" in last_message:
            return {
                "content": "We have deluxe rooms available for those dates.",
                "tool_calls": [
                    {
                        "id": "mock_tool_1",
                        "function": {
                            "name": "check_room_availability",
                            "arguments": '{"check_in_date": "2026-03-15", "check_out_date": "2026-03-17", "room_type": "deluxe"}'
                        },
                        "type": "function"
                    }
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20}
            }
        elif "book" in last_message or "booking" in last_message:
            return {
                "content": "I'll book that for you. Let me confirm the details.",
                "tool_calls": [
                    {
                        "id": "mock_tool_2",
                        "function": {
                            "name": "create_booking",
                            "arguments": '{"guest_name": "Test Guest", "guest_phone": "+880123456789", "room_type": "deluxe", "check_in_date": "2026-03-15", "check_out_date": "2026-03-17"}'
                        },
                        "type": "function"
                    }
                ],
                "usage": {"prompt_tokens": 60, "completion_tokens": 25}
            }
        
        return {
            "content": "How can I help you with your hotel booking?",
            "tool_calls": None,
            "usage": {"prompt_tokens": 40, "completion_tokens": 15}
        }
    
    async def stream_completion(
        self,
        messages: List[Dict],
        temperature=0.7,
        max_tokens=512,
    ):
        """Mock streaming response"""
        response = "Thank you for your inquiry. "
        for word in response.split():
            yield word + " "
            await asyncio.sleep(0.01)  # Simulate streaming


# ─────────────────────────────────────────────────────────
# Mock MongoDB
# ─────────────────────────────────────────────────────────

class MockAsyncCursor:
    """Mock async MongoDB cursor"""
    
    def __init__(self, documents):
        self.documents = documents
        self.index = 0
    
    async def to_list(self, length=None):
        if length:
            return self.documents[:length]
        return self.documents
    
    def sort(self, field, direction):
        return self
    
    def limit(self, n):
        self.documents = self.documents[:n]
        return self


class MockAsyncCollection:
    """Mock MongoDB collection with async methods"""
    
    def __init__(self, name):
        self.name = name
        self.data = {}
        self.counter = 0
    
    async def find_one(self, query, **kwargs):
        for doc_id, doc in self.data.items():
            match = True
            for key, value in query.items():
                if key not in doc or doc[key] != value:
                    match = False
                    break
            if match:
                return doc
        return None
    
    async def find(self, query, **kwargs):
        results = []
        for doc_id, doc in self.data.items():
            match = True
            for key, value in query.items():
                if key not in doc or doc[key] != value:
                    match = False
                    break
            if match:
                results.append(doc)
        return MockAsyncCursor(results)
    
    async def insert_one(self, document):
        doc_id = self.counter
        self.counter += 1
        self.data[doc_id] = {**document, "_id": str(doc_id)}
        return MagicMock(inserted_id=str(doc_id))
    
    async def insert_many(self, documents):
        ids = []
        for doc in documents:
            doc_id = self.counter
            self.counter += 1
            self.data[doc_id] = {**doc, "_id": str(doc_id)}
            ids.append(str(doc_id))
        return MagicMock(inserted_ids=ids)
    
    async def update_one(self, query, update_doc, upsert=False, **kwargs):
        for doc_id, doc in self.data.items():
            match = True
            for key, value in query.items():
                if key not in doc or doc[key] != value:
                    match = False
                    break
            if match:
                if "$set" in update_doc:
                    doc.update(update_doc["$set"])
                if "$push" in update_doc:
                    for key, value in update_doc["$push"].items():
                        if key not in doc:
                            doc[key] = []
                        if isinstance(doc[key], list):
                            # Support MongoDB's $each syntax used in code/tests.
                            if isinstance(value, dict) and "$each" in value and isinstance(value["$each"], list):
                                doc[key].extend(value["$each"])
                            else:
                                doc[key].append(value)
                if "$addToSet" in update_doc:
                    for key, value in update_doc["$addToSet"].items():
                        if key not in doc:
                            doc[key] = []
                        if isinstance(doc[key], list):
                            if isinstance(value, dict) and "$each" in value and isinstance(value["$each"], list):
                                for item in value["$each"]:
                                    if item not in doc[key]:
                                        doc[key].append(item)
                            else:
                                if value not in doc[key]:
                                    doc[key].append(value)
                return MagicMock(modified_count=1)
        
        if upsert:
            doc_id = self.counter
            self.counter += 1
            new_doc = {**query}
            if "$set" in update_doc:
                new_doc.update(update_doc["$set"])
            if "$setOnInsert" in update_doc:
                new_doc.update(update_doc["$setOnInsert"])
            self.data[doc_id] = {**new_doc, "_id": str(doc_id)}
            return MagicMock(upserted_id=str(doc_id), modified_count=0)
        
        return MagicMock(modified_count=0)
    
    async def delete_many(self, query):
        to_delete = []
        for doc_id, doc in self.data.items():
            match = True
            for key, value in query.items():
                if key not in doc or doc[key] != value:
                    match = False
                    break
            if match:
                to_delete.append(doc_id)
        
        for doc_id in to_delete:
            del self.data[doc_id]
        
        return MagicMock(deleted_count=len(to_delete))
    
    async def create_indexes(self, indexes):
        """Mock index creation"""
        pass


class MockDatabase:
    """Mock MongoDB database"""
    
    def __init__(self):
        self.rooms = MockAsyncCollection("rooms")
        self.bookings = MockAsyncCollection("bookings")
        self.guests = MockAsyncCollection("guests")
        self.conversations = MockAsyncCollection("conversations")
        self.call_sessions = MockAsyncCollection("call_sessions")


# ─────────────────────────────────────────────────────────
# Pytest Fixtures
# ─────────────────────────────────────────────────────────

@pytest.fixture
def mock_llm_provider():
    """Provide mock LLM provider"""
    return MockLLMProvider()


@pytest.fixture
def mock_db():
    """Provide mock MongoDB database"""
    return MockDatabase()


@pytest.fixture
def mock_settings():
    """Provide mock settings"""
    from config import Settings
    return Settings(
        HOTEL_NAME="Test Hotel",
        HOTEL_ADDRESS="123 Test St",
        HOTEL_CHECKIN_TIME="14:00",
        HOTEL_CHECKOUT_TIME="12:00",
        HOTEL_CURRENCY="BDT",
        DEBUG=True,
        APP_ENV="testing",
    )


@pytest.fixture
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def patch_llm_provider(mock_llm_provider):
    """Automatically patch LLM provider in all tests"""
    with patch("ai.llm_provider.get_llm_provider") as mock:
        mock.return_value = mock_llm_provider
        yield mock


@pytest.fixture(autouse=True)
def patch_db(mock_db):
    """Automatically patch database in all tests"""
    with patch("database.mongodb.get_db") as mock_db_get, patch("ai.agent.get_db") as mock_agent_get:
        mock_db_get.return_value = mock_db
        mock_agent_get.return_value = mock_db
        yield mock_db_get


# ─────────────────────────────────────────────────────────
# Asyncio Configuration
# ─────────────────────────────────────────────────────────

pytest_plugins = ("pytest_asyncio",)


def pytest_configure(config):
    """Configure pytest"""
    # asyncio_mode is a scalar option; addinivalue_line is for list-type ini values.
    # Set the option directly to avoid pytest's list assertion.
    if hasattr(config, "option") and hasattr(config.option, "asyncio_mode"):
        config.option.asyncio_mode = "auto"
