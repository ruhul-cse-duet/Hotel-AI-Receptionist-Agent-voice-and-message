# PROJECT STRUCTURE GUIDE

## Overview

This document explains the reorganized Python project structure for the Hotel AI Receptionist system.

## Directory Layout

```
hotel-ai-receptionist/
│
├── main.py                          # FastAPI application entry point
├── config.py                        # Pydantic Settings (centralized config)
├── requirements.txt                 # Python dependencies
├── .env.example                     # Environment variables template
├── .env                             # (local only) Actual env vars
├── hotel_ai.log                     # Application logs
├── README.md                        # This file
├── PROJECT_STRUCTURE.md             # (this file) Detailed structure guide
│
├── database/
│   ├── __init__.py                  # Database package marker
│   ├── mongodb.py                   # Motor async MongoDB connection, indexes
│   └── models.py                    # Pydantic models for all data schemas
│
├── ai/
│   ├── __init__.py                  # AI package marker
│   ├── llm_provider.py              # LLM abstraction (OpenAI/Gemini/LM Studio)
│   ├── agent.py                     # Conversation agent & agentic loop
│   ├── tools.py                     # Booking tools (availability, create_booking)
│   └── prompts.py                   # System prompts & templates
│
├── voice/
│   ├── __init__.py                  # Voice package marker
│   ├── twilio_handler.py            # Phone call webhooks & TwiML generation
│   ├── stt_tts.py                   # Speech-to-Text & Text-to-Speech providers
│   └── prompts.py                   # Voice-specific system prompts
│
├── whatsapp/
│   ├── __init__.py                  # WhatsApp package marker
│   ├── handler.py                   # WhatsApp message handlers
│   └── prompts.py                   # WhatsApp-specific prompts
│
├── routers/
│   ├── __init__.py                  # Routers package marker
│   └── api.py                       # FastAPI route definitions (/bookings, /rooms, /admin)
│
├── utils/
│   ├── __init__.py                  # Utils package marker
│   ├── logger.py                    # Logging configuration
│   └── seed_rooms.py                # Database seed script for sample rooms
│
└── tests/                           # (optional) Unit tests
    ├── test_agent.py
    ├── test_llm_provider.py
    └── test_handlers.py
```

## File Descriptions

### Root Level

**main.py**
- FastAPI application initialization
- Lifespan events (startup/shutdown)
- Route mounting for all modules
- CORS middleware setup

**config.py**
- Pydantic BaseSettings for configuration
- Environment variable definitions
- Enums for LLM/STT/TTS providers
- Settings validation

**requirements.txt**
- All Python package dependencies
- Pinned versions for reproducibility

**.env.example**
- Template with all required environment variables
- Instructions for setup

## Module Details

### database/

**mongodb.py**
- MongoDB async connection via Motor
- Database initialization and connection pooling
- Index creation for all collections
- Connection lifecycle management

**models.py**
- Pydantic BaseModels for data validation
- Enums: RoomType, BookingStatus, ConversationChannel, etc.
- Schemas: Room, Booking, Conversation, CallSession, etc.
- API request/response models

### ai/

**llm_provider.py**
- BaseLLMProvider abstract class
- OpenAIProvider - GPT-4o integration
- GeminiProvider - Gemini 1.5 Pro integration
- LMStudioProvider - Local LLM support
- Factory pattern for provider selection

**agent.py**
- HotelAgent main class
- Conversation state management
- Agentic loop (LLM → Tools → LLM)
- Multi-turn conversation handling
- Session persistence

**tools.py**
- Tool definitions (booking tools, availability checker)
- Tool executor for safe function calling
- Integration with booking logic

**prompts.py**
- System prompts for various scenarios
- Booking confirmation templates
- Error handling prompts

### voice/

**twilio_handler.py**
- Incoming call handler (TwiML generation)
- WebSocket handler for media streams
- Real-time audio processing
- Call status callbacks

**stt_tts.py**
- Abstract base for STT/TTS providers
- OpenAI Whisper integration
- ElevenLabs TTS integration
- Google Cloud alternatives

**prompts.py**
- Voice call system prompts
- Brevity reminders for voice
- Voice-specific conversation templates

### whatsapp/

**handler.py**
- Incoming WhatsApp message webhook
- Session management (per phone number)
- Voice note transcription
- Booking confirmation formatting

**prompts.py**
- WhatsApp greeting templates
- Rich message formatting (bold, emojis)
- Booking confirmation messages

### routers/

**api.py**
- /bookings routes (list, create, get, update, cancel)
- /rooms routes (list, create, update)
- /admin routes (dashboard, statistics)
- Query parameters & filtering

### utils/

**logger.py**
- Logging configuration
- File and stream handlers
- Log level based on APP_ENV

**seed_rooms.py**
- Database seeding script
- Sample room creation with pricing & amenities
- Usage: `python -m utils.seed_rooms`

## Import Pattern

```python
# From database
from database.mongodb import get_db, connect_db, disconnect_db
from database.models import Room, Booking, Conversation, ConversationChannel

# From AI
from ai.llm_provider import get_llm_provider
from ai.agent import get_voice_agent, get_whatsapp_agent
from ai.tools import get_tool_executor

# From voice
from voice.stt_tts import get_stt, get_tts
from voice.twilio_handler import router as voice_router

# From WhatsApp
from whatsapp.handler import router as whatsapp_router

# From API routers
from routers.api import bookings_router, rooms_router, admin_router

# Config
from config import settings, LLMProvider
```

## Data Flow Examples

### Voice Call Flow
```
1. Guest calls Twilio number
   ↓
2. twilio_handler.py: incoming_call() generates TwiML
   ↓
3. WebSocket established for media stream
   ↓
4. voice/stt_tts.py: get_stt().transcribe(audio)
   ↓
5. ai/agent.py: get_voice_agent().process_message()
   ↓
6. ai/llm_provider.py: get_llm_provider().chat_completion()
   ↓
7. ai/tools.py: execute booking tool if needed
   ↓
8. voice/stt_tts.py: get_tts().synthesize(response)
   ↓
9. Send audio back through Twilio
   ↓
10. database/mongodb.py: Save conversation to DB
```

### WhatsApp Flow
```
1. Guest sends WhatsApp message
   ↓
2. whatsapp/handler.py: incoming_whatsapp()
   ↓
3. Session management via database/mongodb.py
   ↓
4. ai/agent.py: get_whatsapp_agent().process_message()
   ↓
5. LLM processing (same as voice)
   ↓
6. whatsapp/handler.py: _send_whatsapp()
   ↓
7. Save to conversations collection
```

### Booking Flow
```
1. AI agent collects info (name, dates, room type, etc.)
   ↓
2. ai/tools.py: execute_tool("create_booking", {...})
   ↓
3. routers/api.py: POST /bookings logic
   ↓
4. Check availability in database
   ↓
5. Create booking in MongoDB
   ↓
6. Send confirmation via WhatsApp
```

## Configuration & Environment

See `.env.example` for all environment variables:
- LLM provider selection
- API keys (OpenAI, Gemini, Deepgram, ElevenLabs, Twilio)
- Database connection
- Webhook URLs
- Feature flags

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Seed database
python -m utils.seed_rooms

# Start server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Package Organization Benefits

1. **Separation of Concerns** — Each module handles one responsibility
2. **Scalability** — Easy to add new providers or features
3. **Testability** — Clear interfaces for unit testing
4. **Maintainability** — Logical file organization
5. **Reusability** — Import models/tools from any module
6. **Async-first** — All I/O operations are async

## Future Expansion

- Add more LLM providers
- Add more STT/TTS providers
- Add analytics module
- Add testing suite
- Add admin dashboard frontend
- Add payment integration
- Add calendar/availability engine
