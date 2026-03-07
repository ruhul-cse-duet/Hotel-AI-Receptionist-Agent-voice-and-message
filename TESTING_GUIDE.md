# Hotel AI Receptionist — Complete Testing Guide

আপনার প্রজেক্ট test করার সম্পূর্ণ গাইড (WhatsApp, Voice Calls, API)

## 📋 Testing Strategy

```
┌─────────────────────────────────────┐
│     COMPLETE TESTING FLOW           │
├─────────────────────────────────────┤
│  1. Unit Tests (pytest) — Local     │
│  2. API Tests (curl/Postman)        │
│  3. WhatsApp Simulation             │
│  4. Voice Call Simulation           │
│  5. End-to-End Integration          │
└─────────────────────────────────────┘
```

---

## 🏗️ Step 1: Local Development Setup

### Prerequisites
```bash
# Ensure you have:
- Python 3.11+ ✓
- MongoDB running locally or Atlas
- Twilio Account (for sandbox testing)
- ngrok (for webhook tunneling)
- Postman or curl (for API testing)
```

### Setup Commands (Windows cmd.exe)

```cmd
# 1. Activate venv
cd "C:\Users\ruhul\Desktop\project\AI-powered hotel receptionist with calling and messaging"
venv\Scripts\activate

# 2. Install all dependencies
pip install -r requirements.txt

# 3. Start local MongoDB (if using local)
mongod

# 4. Seed test data
python -m utils.seed_rooms

# 5. Start FastAPI server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Server will be running at: `http://localhost:8000`

---

## 🧪 Step 2: Unit & Integration Tests

### Run All Tests
```bash
# Activate venv first
venv\Scripts\activate

# Run all tests
pytest -v

# Run specific test file
pytest tests/test_llm_provider.py -v

# Run specific test
pytest tests/test_agent.py::TestHotelAgent::test_voice_agent_initialization -v

# Run with coverage
pytest --cov=ai --cov=database --cov=voice --cov=whatsapp -v
```

### Test Files Available
```
tests/
├── test_agent.py              # Agent logic tests
├── test_llm_provider.py       # LLM provider tests
└── test_handlers.py           # API handler tests
```

---

## 📡 Step 3: API Testing (Postman / curl)

### Test Data
```json
{
  "guest_name": "Ahmed Khan",
  "guest_phone": "+880123456789",
  "guest_email": "ahmed@example.com",
  "room_type": "deluxe",
  "check_in_date": "2026-03-15",
  "check_out_date": "2026-03-17",
  "adults": 2,
  "children": 0
}
```

### A. Check Availability

**curl:**
```bash
curl -X GET "http://localhost:8000/bookings/availability?check_in_date=2026-03-15&check_out_date=2026-03-17&room_type=deluxe" \
  -H "Content-Type: application/json"
```

**Expected Response:**
```json
{
  "status": "success",
  "data": {
    "available": true,
    "rooms": [
      {
        "room_id": "xxx",
        "room_number": "201",
        "room_type": "deluxe",
        "price_per_night": 8500,
        "total_price": 17850,
        "amenities": {...}
      }
    ]
  }
}
```

### B. List All Rooms

```bash
curl -X GET "http://localhost:8000/rooms" \
  -H "Content-Type: application/json"
```

### C. Create a Booking

```bash
curl -X POST "http://localhost:8000/bookings" \
  -H "Content-Type: application/json" \
  -d '{
    "guest_name": "Ahmed Khan",
    "guest_phone": "+880123456789",
    "guest_email": "ahmed@example.com",
    "room_type": "deluxe",
    "check_in_date": "2026-03-15",
    "check_out_date": "2026-03-17",
    "adults": 2,
    "children": 0,
    "special_requests": "Need extra pillows"
  }'
```

**Expected Response:**
```json
{
  "status": "success",
  "data": {
    "booking_id": "HTLXX1234",
    "guest_name": "Ahmed Khan",
    "room_number": "201",
    "check_in_date": "2026-03-15",
    "check_out_date": "2026-03-17",
    "total_amount": 17850,
    "status": "confirmed"
  }
}
```

### D. Get Booking Details

```bash
curl -X GET "http://localhost:8000/bookings/HTLXX1234" \
  -H "Content-Type: application/json"
```

### E. Cancel Booking

```bash
curl -X DELETE "http://localhost:8000/bookings/HTLXX1234" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Change of plans"}'
```

### F. Admin Dashboard

```bash
curl -X GET "http://localhost:8000/admin/dashboard" \
  -H "Content-Type: application/json"
```

---

## 💬 Step 4: WhatsApp Testing (Twilio Sandbox)

### Setup Twilio WhatsApp Sandbox

1. Go to: https://console.twilio.com/us/account/messaging/try-it-out/whatsapp
2. Follow join instructions
3. Note your sandbox number

### Option A: Real WhatsApp Messages

1. Join sandbox by replying to Twilio message
2. Send message to sandbox number
3. Your app will receive on `POST /api/whatsapp/incoming`
4. Watch logs in your console

**Message Examples to Send:**
```
Hi
Hello
Do you have rooms for 15-17 March?
I want to book a deluxe room
My name is Ahmed Khan
My phone is +880123456789
```

### Option B: Simulate WhatsApp (curl)

```bash
# Simulate incoming WhatsApp message
curl -X POST "http://localhost:8000/api/whatsapp/incoming" \
  -d "From=whatsapp%3A%2B880123456789" \
  -d "To=whatsapp%3A%2B14155238886" \
  -d "Body=Hi%2C+do+you+have+rooms+for+15-17+March%3F" \
  -d "NumMedia=0" \
  -d "ProfileName=Test+User"
```

### Webhook URL Setup

1. Update `.env`: `WEBHOOK_BASE_URL=https://your-ngrok-url.io`
2. In Twilio Console:
   - Messaging → Try it out → WhatsApp Sandbox
   - Webhook URL: `https://your-ngrok-url.io/api/whatsapp/incoming`
   - HTTP Method: POST

---

## 📞 Step 5: Voice Call Testing (Twilio)

### Setup Twilio Voice (Prod Numbers)

1. Buy a Twilio phone number
2. Configure voice webhook:
   - Phone Numbers → Manage → Active Numbers
   - Voice → Webhook URL: `https://your-ngrok-url.io/api/voice/incoming`
   - HTTP Method: POST

### Testing Voice Calls

**Option A: Real Call**
```bash
# Call your Twilio number from any phone
# You'll hear greeting, speak into phone
# AI receptionist will respond via TTS
```

**Option B: Simulate Call (curl)**
```bash
# Simulate incoming call
curl -X POST "http://localhost:8000/api/voice/incoming" \
  -d "CallSid=CA1234567890abcdef" \
  -d "From=%2B880123456789" \
  -d "To=%2B1555555555" \
  -d "Direction=inbound"
```

**What Happens:**
1. TwiML response sent (greeting audio)
2. WebSocket media stream established
3. Audio chunks sent to app
4. STT converts speech → text
5. LLM processes & generates response
6. TTS converts response → audio
7. Audio sent back to caller

---

## 🔧 Step 6: ngrok Tunneling (for Webhooks)

### Windows cmd.exe

```cmd
# Download ngrok from https://ngrok.com/download
# Extract and add to PATH

# Run ngrok
ngrok http 8000

# Output:
# Forwarding https://abc123.ngrok.io -> http://localhost:8000

# Update .env
WEBHOOK_BASE_URL=https://abc123.ngrok.io
```

### Important
- ngrok URL changes each restart
- Keep ngrok running while testing
- Update Twilio webhooks if URL changes

---

## 📊 Step 7: Full End-to-End Test Scenario

### Complete Booking Flow Test

```bash
# Terminal 1: Start MongoDB
mongod

# Terminal 2: Start FastAPI
venv\Scripts\activate
uvicorn main:app --reload

# Terminal 3: Start ngrok
ngrok http 8000

# Terminal 4: Test Booking API
# 1. Check availability
curl -X GET "http://localhost:8000/bookings/availability?check_in_date=2026-03-15&check_out_date=2026-03-17"

# 2. Create booking
curl -X POST "http://localhost:8000/bookings" \
  -H "Content-Type: application/json" \
  -d '{
    "guest_name": "Fatima Rahman",
    "guest_phone": "+880987654321",
    "room_type": "deluxe",
    "check_in_date": "2026-03-15",
    "check_out_date": "2026-03-17",
    "adults": 1,
    "children": 0
  }'

# 3. Send WhatsApp confirmation
# (Simulated or real)
curl -X POST "http://localhost:8000/api/whatsapp/incoming" \
  -d "From=whatsapp%3A%2B880987654321" \
  -d "Body=Hello%2C+can+I+get+my+booking+details%3F" \
  -d "NumMedia=0"

# 4. Check booking status
curl -X GET "http://localhost:8000/bookings?guest_phone=%2B880987654321"
```

---

## 🧩 Step 8: Postman Collection

Create a Postman collection:

```json
{
  "info": {
    "name": "Hotel AI Receptionist API",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": [
    {
      "name": "Check Availability",
      "request": {
        "method": "GET",
        "url": "{{base_url}}/bookings/availability?check_in_date=2026-03-15&check_out_date=2026-03-17"
      }
    },
    {
      "name": "Create Booking",
      "request": {
        "method": "POST",
        "url": "{{base_url}}/bookings",
        "body": {
          "mode": "raw",
          "raw": "{...booking data...}"
        }
      }
    },
    {
      "name": "Get Bookings",
      "request": {
        "method": "GET",
        "url": "{{base_url}}/bookings"
      }
    },
    {
      "name": "Cancel Booking",
      "request": {
        "method": "DELETE",
        "url": "{{base_url}}/bookings/HTLXX1234"
      }
    }
  ],
  "variable": [
    {
      "key": "base_url",
      "value": "http://localhost:8000"
    }
  ]
}
```

---

## 🐛 Debugging & Logs

### Check Logs

```bash
# In your terminal running FastAPI:
# Look for:
# - 📱 WhatsApp from +880123456789...
# - 📞 Incoming call: CA1234...
# - ✅ Booking created: HTLXX1234...
# - 🔧 Tool: check_room_availability(...)
```

### Enable Debug Logs

In `.env`:
```
DEBUG=true
LOG_LEVEL=DEBUG
APP_ENV=development
```

### Check MongoDB

```bash
# Connect to MongoDB
mongosh

# List databases
show dbs

# Use hotel db
use hotel_ai_dev

# Check collections
show collections

# View bookings
db.bookings.find().pretty()

# View conversations
db.conversations.find().pretty()
```

---

## ✅ Testing Checklist

- [ ] Unit tests pass (`pytest`)
- [ ] API endpoints respond (`curl` tests)
- [ ] WhatsApp messages received and replied
- [ ] Voice calls connected via ngrok
- [ ] Bookings created in MongoDB
- [ ] Conversation history saved
- [ ] LLM responses generated
- [ ] Logs show expected events
- [ ] Admin dashboard displays data

---

## 🚀 Next: Production Testing

When ready for production:
```bash
# Set environment
APP_ENV=production

# Enable webhook validation
VERIFY_TWILIO_SIGNATURE=true

# Use MongoDB Atlas
MONGODB_URI=mongodb+srv://...

# Deploy to cloud (Heroku, Railway, etc.)
git push heroku main
```

---

## 📞 Common Issues & Fixes

| Issue | Solution |
|-------|----------|
| "Cannot connect to MongoDB" | Ensure `mongod` is running or update `MONGODB_URI` |
| "Twilio webhook timeout" | Keep ngrok running, check tunnel URL in Twilio console |
| "API returns 404" | Check base URL, ensure routes mounted in `main.py` |
| "WhatsApp not receiving" | Verify sandbox join, check webhook URL in Twilio |
| "Voice call drops" | Check WebSocket connection, ensure TTS/STT configured |
| "LLM returns empty" | Check API key, verify LLM provider in `.env` |

---

## 📚 Additional Resources

- [Twilio WhatsApp Docs](https://www.twilio.com/docs/whatsapp)
- [Twilio Voice Docs](https://www.twilio.com/docs/voice)
- [ngrok Docs](https://ngrok.com/docs)
- [Postman Docs](https://learning.postman.com)
- [MongoDB Compass](https://www.mongodb.com/products/compass) - GUI for MongoDB

---

## 🎯 Summary

Your testing workflow:
1. **Local Unit Tests** → `pytest`
2. **API Tests** → `curl` or Postman
3. **WhatsApp** → Real or simulated messages
4. **Voice** → Twilio sandbox or real calls
5. **Integration** → Full end-to-end flow
6. **Production** → Deploy & monitor

You now have complete testing capability! 🎉
