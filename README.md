# 🏨 Hotel AI Receptionist System

An intelligent, AI-powered hotel receptionist that handles **real phone calls** and **WhatsApp messages** — books rooms, checks availability, and sends confirmations. Built with Python/FastAPI, MongoDB, Twilio, and OpenAI/Gemini/LM Studio.

---

## 🏗️ Full System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    HOTEL AI RECEPTIONIST                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  📞 PHONE CALL FLOW                                             │
│  ─────────────────                                              │
│  Guest dials hotel number                                       │
│       ↓                                                         │
│  Twilio Voice (STT: speech → text)                              │
│       ↓                                                         │
│  POST /api/voice/incoming  ──→  twilio_handler                  │
│       ↓                                                         │
│  agent.py (conversation manager)  ──→  llm_provider              │
│           (OpenAI/Gemini/LM Studio)                             │
│       ↓                                                         │
│  TwiML Response (TTS: text → speech)                            │
│       ↓                                                         │
│  Guest hears natural AI response                                │
│       ↓ (booking confirmed)                                     │
│  MongoDB: save booking  +  WhatsApp confirmation sent           │
│                                                                 │
│  💬 WHATSAPP FLOW                                               │
│  ────────────────                                               │
│  Guest sends WhatsApp message                                   │
│       ↓                                                         │
│  Twilio WhatsApp API                                            │
│       ↓                                                         │
│  POST /api/whatsapp/incoming  ──→  handler.py                   │
│       ↓                                                         │
│  agent.py  ──→  llm_provider                                    │
│       ↓                                                         │
│  AI text response sent back via WhatsApp                        │
│       ↓ (booking confirmed)                                     │
│  MongoDB: save booking  +  WhatsApp booking confirmation        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     DATA LAYER (MongoDB)                        │
│                                                                 │
│  rooms         bookings        conversations                    │
│  ─────         ────────        ─────────────                    │
│  room_number   booking_id      session_id                       │
│  room_type     guest{name,     channel                          │
│  floor         phone, email}   caller_number                    │
│  price         room_ref        messages[]                       │
│  max_guests    check_in_date   state                            │
│  amenities     check_out_date  collected_data                   │
│  is_active     status          booking_id                       │
│                total_amount                                     │
│                booked_via                                       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     AI PROVIDER LAYER                           │
│                                                                 │
│  Production:        LLM_PROVIDER=openai   → GPT-4o              │
│  Alternative:       LLM_PROVIDER=gemini   → Gemini 1.5 Pro      │
│  Local Testing:     LLM_PROVIDER=lm_studio → LM Studio (any LLM)│
│                                                                 │
│  All providers use the same interface:                          │
│  get_llm_provider().chat(messages) → str                        │
│  get_llm_provider().extract_booking() → dict                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
hotel-ai-receptionist/
├── main.py                      # FastAPI app entry point
├── config.py                    # Central configuration (pydantic)
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment variables template
├── hotel_ai.log                 # Application logs
│
├── database/
│   ├── mongodb.py               # MongoDB async connection
│   └── models.py                # Pydantic models (Room, Booking, etc.)
│
├── ai/
│   ├── llm_provider.py          # 🤖 Unified LLM: OpenAI/Gemini/LM Studio
│   ├── tools.py                 # Tool executors (booking, availability)
│   └── agent.py                 # Conversation state machine
│
├── voice/
│   ├── twilio_handler.py        # 📞 Phone call TwiML handler
│   ├── stt_tts.py               # Speech-to-Text & Text-to-Speech
│   └── prompts.py               # Voice system prompts
│
├── whatsapp/
│   ├── handler.py               # 💬 WhatsApp message handler
│   └── prompts.py               # WhatsApp system prompts
│
├── routers/
│   └── api.py                   # FastAPI routes (/bookings, /rooms, /admin)
│
└── utils/
    ├── logger.py                # Logging setup
    └── seed_rooms.py            # Database seed script
```

---

## 🚀 Quick Start

### 1. Prerequisites
- **Python 3.11+**
- MongoDB (local or Atlas)
- Twilio account (for calls + WhatsApp)
- OpenAI API key / Gemini API key / LM Studio (local)
- ngrok (for local webhook testing)
- ffmpeg (for audio processing)

**Install ffmpeg:**
```bash
# Windows (using chocolatey)
choco install ffmpeg

# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

### 2. Setup

```bash
# Clone the repository
git clone <repo>
cd hotel-ai-receptionist

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create environment file
cp .env.example .env
# Edit .env with your credentials
```

### 3. Database Setup

**Option A: MongoDB Atlas (Cloud)**
1. Create account at mongodb.com
2. Create cluster
3. Get connection string
4. Add to `.env`: `MONGODB_URI=mongodb+srv://...`

**Option B: Local MongoDB**
```bash
# Windows
mongod

# macOS
brew services start mongodb-community

# Ubuntu/Debian
sudo systemctl start mongod
```

### 4. Seed Room Data
```bash
python -m utils.seed_rooms
```

### 5. Start the Server

**Production (OpenAI/Gemini):**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**Local Development (LM Studio):**
```bash
# 1. Open LM Studio → Download a model (e.g. Llama 3.1 8B, Qwen 2.5)
# 2. Go to "Local Server" tab → Load model → Start Server
# 3. Set in .env: LLM_PROVIDER=lm_studio
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 6. Expose via ngrok (for Twilio webhooks)
```bash
ngrok http 8000
# Copy the HTTPS URL → update WEBHOOK_BASE_URL in .env
```

---

## ⚙️ Twilio Setup

### Phone Calls
1. Buy a Twilio phone number
2. Go to **Phone Numbers → Manage → Active Numbers**
3. Set Voice webhook: `https://your-ngrok.io/api/voice/incoming` (HTTP POST)
4. Set Status callback: `https://your-ngrok.io/api/voice/status`

### WhatsApp (Sandbox for testing)
1. Go to **Messaging → Try it out → Send a WhatsApp message**
2. Follow sandbox join instructions
3. Set webhook URL: `https://your-ngrok.io/api/whatsapp/incoming`

### WhatsApp (Production)
1. Apply for WhatsApp Business API via Twilio
2. Create approved message templates
3. Update `TWILIO_WHATSAPP_NUMBER` in `.env`

---

## 🤖 AI Provider Switching

| Provider | Use Case | Config |
|----------|----------|--------|
| **OpenAI GPT-4o** | Production, best quality | `AI_PROVIDER=openai` |
| **Google Gemini 1.5 Pro** | Production alternative, cost-effective | `AI_PROVIDER=gemini` |
| **LM Studio** | Local dev, no API costs | `AI_PROVIDER=lmstudio` |

### Recommended LM Studio Models
- **Llama 3.1 8B** — fast, good quality
- **Qwen 2.5 14B** — excellent for conversations
- **Mistral 7B** — lightweight and capable
- **Phi-3 Mini** — ultra-fast on CPU

---

## 📡 API Reference

### Voice Call Webhooks (Twilio → Server)
```
POST /api/voice/incoming       # Incoming call handler
POST /api/voice/handle-input   # DTMF/speech input handler
POST /api/voice/status         # Call status callbacks
```

### WhatsApp Webhooks (Twilio → Server)
```
POST /api/whatsapp/incoming    # Incoming WhatsApp message
POST /api/whatsapp/status      # Message status callbacks
POST /api/whatsapp/send        # Send manual message (admin)
```

### Admin REST API
```
GET  /admin/dashboard               # Stats overview
GET  /rooms                         # List all rooms
POST /rooms                         # Create room
PUT  /rooms/{room_id}               # Update room
GET  /bookings                      # List bookings with filters
GET  /bookings/{booking_id}         # Get booking details
POST /bookings                      # Create manual booking
DELETE /bookings/{booking_id}       # Cancel booking
GET  /bookings/availability?check_in_date=&check_out_date=&room_type=
```

### Response Format
```python
# Success
{
    "status": "success",
    "data": { ... }
}

# Error
{
    "status": "error",
    "message": "Error description",
    "code": "ERROR_CODE"
}
```

---

## 💬 Sample Conversations

### Phone Call
```
AI:   "Thank you for calling Grand Palace Hotel. This is Aisha,
       your AI receptionist. How may I assist you today?"

Guest: "I want to book a room for two nights."

AI:   "I'd be happy to help you with that.
       When would you like to check in?"

Guest: "This Friday, March 13th."

AI:   "And when will you be checking out?"

Guest: "Sunday, March 15th."

AI:   "How many guests will be staying?"

Guest: "Two guests."

AI:   "We have deluxe rooms available at BDT 8,500 per night.
       That would be 17,000 taka for two nights. May I have
       your name to complete the booking?"

Guest: "My name is Rahman."

AI:   "Thank you, Mr. Rahman. Your booking is confirmed.
       Your booking ID is BK250313-4821. A confirmation
       will be sent to your WhatsApp. Is there anything else?"
```

### WhatsApp
```
User: Hi
AI:   Welcome to *Grand Palace Hotel*! 🏨
      I'm Aisha, your AI receptionist...

User: Do you have rooms for 20-22 March?
AI:   *Available rooms for March 20-22 (2 nights):*
      🏠 Single: BDT 3,500/night
      🛏️ Double: BDT 5,500/night
      ⭐ Deluxe: BDT 8,500/night
      ...
```

---

## 🐍 Python Examples

### Making a Booking via API
```python
import httpx

async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://localhost:8000/bookings",
        json={
            "guest_name": "Ahmed Khan",
            "guest_phone": "+880123456789",
            "guest_email": "ahmed@example.com",
            "room_type": "deluxe",
            "check_in_date": "2026-03-15",
            "check_out_date": "2026-03-17",
            "num_guests": 2
        }
    )
    booking = response.json()
    print(f"Booking ID: {booking['data']['booking_id']}")
```

### Checking Room Availability
```python
from datetime import date
import httpx

async with httpx.AsyncClient() as client:
    response = await client.get(
        "http://localhost:8000/bookings/availability",
        params={
            "check_in_date": str(date(2026, 3, 15)),
            "check_out_date": str(date(2026, 3, 17)),
            "room_type": "deluxe"
        }
    )
    available_rooms = response.json()
    print(available_rooms)
```

### Testing Voice Call Locally
```python
# Save as test_voice_call.py
import httpx
from twilio.twiml.voice_response import VoiceResponse

async def test_incoming_call():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/voice/incoming",
            data={
                "CallSid": "CA1234567890",
                "From": "+880123456789",
                "To": "+1-555-555-5555"
            }
        )
        print(response.text)
        # Should return TwiML with initial greeting

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_incoming_call())
```

---

## 🔒 Production Checklist
- [ ] Enable Twilio webhook signature validation (set `VERIFY_TWILIO_SIGNATURE=true`)
- [ ] Add authentication middleware to `/admin/*` routes
- [ ] Use MongoDB Atlas with strong credentials & IP whitelist
- [ ] Set `APP_ENV=production`
- [ ] Configure proper TTS voice (ElevenLabs for better quality)
- [ ] Apply for WhatsApp Business API (not sandbox)
- [ ] Set up SSL certificate for your domain (HTTPS required for Twilio)
- [ ] Configure MongoDB backups
- [ ] Set up proper logging with rotation
- [ ] Load test with concurrent calls
- [ ] Implement rate limiting on API endpoints
- [ ] Set up monitoring & alerting
- [ ] Create admin dashboard for booking management

---

## 🐛 Troubleshooting

### Issue: "Connection to LLM Provider failed"
```python
# Check if LM Studio is running locally
# Or verify API keys in .env for OpenAI/Gemini

# Test LLM connection
python -c "from ai.llm_provider import get_llm_provider; print(get_llm_provider().health_check())"
```

### Issue: "Twilio webhook signature validation failed"
```bash
# Ensure TWILIO_AUTH_TOKEN is correctly set in .env
# Twilio may be calling from a different IP — check ngrok logs
# Temporarily set VERIFY_TWILIO_SIGNATURE=false for testing
```

### Issue: "MongoDB connection timeout"
```bash
# Check MongoDB is running and accessible
# Verify MONGODB_URI format: mongodb+srv://user:pass@cluster.mongodb.net/dbname
# Or use local: mongodb://localhost:27017/hotel_ai
```

### Issue: "Audio playback sounds robotic"
```bash
# Switch TTS_PROVIDER to elevenlabs (paid but high quality)
# Or use google (free but lower quality)
# Adjust speech rate: TTS_SPEECH_RATE in config.py
```

---

## 📚 Key Files & Their Purpose

| File | Purpose |
|------|---------|
| `main.py` | FastAPI application entry point & route mounting |
| `config.py` | Centralized settings via Pydantic BaseSettings |
| `ai/llm_provider.py` | LLM abstraction (OpenAI/Gemini/LM Studio) |
| `ai/agent.py` | Conversation state machine & multi-turn logic |
| `ai/tools.py` | Booking tools (availability check, create booking) |
| `voice/twilio_handler.py` | Phone call webhook handlers & TwiML generation |
| `voice/stt_tts.py` | Speech-to-text & Text-to-speech providers |
| `whatsapp/handler.py` | WhatsApp message handler |
| `routers/api.py` | REST API endpoints (/bookings, /rooms, /admin) |
| `database/mongodb.py` | MongoDB async connection pool |
| `database/models.py` | Pydantic data models |

---

## 📖 Environment Variables

Create `.env` file with:
```bash
# ─── Core ───────────────────────────────────────────
DEBUG=true
APP_ENV=development
HOTEL_NAME="Grand Palace Hotel"

# ─── Database ───────────────────────────────────────
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/hotel_ai
# OR for local: mongodb://localhost:27017/hotel_ai

# ─── LLM Provider ────────────────────────────────────
LLM_PROVIDER=openai          # Options: openai, gemini, lm_studio
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
LM_STUDIO_BASE_URL=http://localhost:1234/v1

# ─── STT Provider ────────────────────────────────────
STT_PROVIDER=openai_whisper  # Options: openai_whisper, deepgram, google
DEEPGRAM_API_KEY=...
GOOGLE_CLOUD_CREDENTIALS=...

# ─── TTS Provider ────────────────────────────────────
TTS_PROVIDER=elevenlabs      # Options: openai, elevenlabs, google
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM

# ─── Twilio ─────────────────────────────────────────
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+1555555555
TWILIO_WHATSAPP_NUMBER=+1555555555
VERIFY_TWILIO_SIGNATURE=false

# ─── Webhooks ───────────────────────────────────────
WEBHOOK_BASE_URL=https://your-ngrok.io
WEBHOOK_TIMEOUT_SECONDS=30

# ─── Admin ──────────────────────────────────────────
ADMIN_SECRET_KEY=your-super-secret-key
```

---

## 🧪 Testing & Quality Assurance

### Quick Start Testing (বাংলা Guide)
```bash
# 1. Activate venv
venv\Scripts\activate

# 2. Start MongoDB
mongod

# 3. Start server (Terminal 2)
uvicorn main:app --reload

# 4. Run all tests (Terminal 3)
python test_all.py
```

**Expected:** All 17+ tests ✅ PASSING

### Testing Options

| Type | Command | Time | Coverage |
|------|---------|------|----------|
| **All Tests** | `python test_all.py` | 5-10s | Complete |
| **Unit Tests** | `pytest -v` | <1s | Code logic |
| **API Tests** | `curl http://localhost:8000/rooms` | <1s | Endpoints |
| **WhatsApp Sim** | `curl -X POST .../api/whatsapp/incoming` | <1s | Messaging |
| **Voice Sim** | `curl -X POST .../api/voice/incoming` | <1s | Calls |

### Test Coverage

✅ **17+ Unit Tests**
- Agent initialization & message processing
- LLM provider singleton & interfaces
- WhatsApp & Voice handler logic
- Booking operations
- Guest profile management
- Database models validation

✅ **Mock Fixtures** (No external dependencies needed)
- MockLLMProvider - canned responses
- MockDatabase - in-memory MongoDB
- MockSettings - test configuration

✅ **Integration Tests**
- API endpoints
- WhatsApp webhooks
- Voice call handlers
- Booking flow (end-to-end)

✅ **Documentation**
- QUICK_START_TESTING.md (বাংলা)
- TESTING_GUIDE.md (Detailed)
- TESTING_COMPLETE.md (Summary)
- Test examples in code

### Documentation Files

```
📄 QUICK_START_TESTING.md    ← Start here (বাংলা guide)
📄 TESTING_GUIDE.md          ← Detailed testing manual
📄 TESTING_COMPLETE.md       ← Test summary
📄 DOCUMENTATION_INDEX.md    ← Navigation guide
📄 PROJECT_STRUCTURE.md      ← Code organization
📄 CONFIG_FIX.md             ← Configuration help
```

---