# 🚀 Quick Start Testing Guide (বাংলা)

আপনার Hotel AI Receptionist প্রজেক্ট testing এর জন্য step by step guide।

---

## 📋 Prerequisites

- ✅ Python 3.11+ installed
- ✅ MongoDB running (local or Atlas)
- ✅ All dependencies installed (`pip install -r requirements.txt`)
- ✅ Environment file setup (`.env`)

---

## 🎯 Step 1: Start the Server

### Terminal 1: MongoDB (যদি local ব্যবহার করছেন)
```cmd
# Windows
mongod

# অথবা যদি MongoDB Path এ আছে
cd "C:\Program Files\MongoDB\Server\7.0\bin"
mongod.exe
```

### Terminal 2: FastAPI Server

```cmd
# Project folder 
cd "C:\Users\ruhul\Desktop\project\AI-powered hotel receptionist with calling and messaging"

# Virtual environment activate 
venv\Scripts\activate

# Database seed start
python -m utils.seed_rooms

# Server start
python -m uvicorn main:app --host 0.0.0.0 --port 8002 --reload

python -m uvicorn main:app --host 127.0.0.1 --port 8002 --reload
```

**Output:**
```
INFO:     Application startup complete
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

---

## 🧪 Step 2: Run All Tests

### Option A: Python Script 

```cmd
python test_all.py
```

** automatically test :**
- ✓ Unit tests (pytest)
- ✓ API endpoints
- ✓ Room availability
- ✓ Booking creation
- ✓ WhatsApp simulation
- ✓ Voice call simulation

---

## 🧪 Step 3: Individual Testing

### A. Unit Tests 

```cmd
# all tests
pytest -v

# শুধু agent tests
pytest tests/test_agent.py -v

# শুধু handler tests
pytest tests/test_handlers.py -v

# Coverage দেখুন
pytest --cov=ai --cov=database -v
```

**Expected Output:**
```
tests/test_agent.py::TestHotelAgentInitialization::test_voice_agent_creation PASSED
tests/test_agent.py::TestHotelAgentInitialization::test_whatsapp_agent_creation PASSED
...
============ 10 passed in 0.45s ============
```

### B. API Tests (curl দিয়ে)

#### 1️⃣ Check Available Rooms

```cmd
curl -X GET "http://localhost:8000/rooms" ^
  -H "Content-Type: application/json"
```

**Response:**
```json
{
  "status": "success",
  "data": [
    {
      "room_number": "101",
      "room_type": "standard",
      "price_per_night": 3500
    }
  ]
}
```

#### 2️⃣ Check Availability 

```cmd
curl -X GET "http://localhost:8000/bookings/availability?check_in_date=2026-03-15&check_out_date=2026-03-17&room_type=deluxe" ^
  -H "Content-Type: application/json"
```

#### 3️⃣ a Booking create

```cmd
curl -X POST "http://localhost:8000/bookings" ^
  -H "Content-Type: application/json" ^
  -d "{\"guest_name\":\"Ahmed Khan\",\"guest_phone\":\"+880123456789\",\"room_type\":\"deluxe\",\"check_in_date\":\"2026-03-15\",\"check_out_date\":\"2026-03-17\",\"adults\":2,\"children\":0}"
```

**Response (Booking ID ):**
```json
{
  "status": "success",
  "data": {
    "booking_id": "HTLXY1234",
    "guest_name": "Ahmed Khan",
    "room_number": "201",
    "total_amount": 17850,
    "status": "confirmed"
  }
}
```

#### 4️⃣ Booking Details দেখুন

```cmd
curl -X GET "http://localhost:8000/bookings/HTLXY1234"
```

---

## 💬 Step 4: WhatsApp Testing

### Method 1: Twilio Sandbox (Real)

1. যান: https://console.twilio.com/us/account/messaging/try-it-out/whatsapp
2. Sandbox এ join করুন (তারা একটা message পাঠাবে)
3. আপনার project তে webhook configured করুন

### Method 2: Simulation (Quick)

```cmd
curl -X POST "http://localhost:8000/api/whatsapp/incoming" ^
  -d "From=whatsapp%%3A%%2B880123456789" ^
  -d "Body=Hi%%2C+do+you+have+rooms+available%%3F" ^
  -d "NumMedia=0" ^
  -d "ProfileName=Test+User"
```

**আপনার console এ দেখবেন:**
```
📱 WhatsApp from +880123456789 (Test User): Hi, do you have rooms available?
```

---

## 📞 Step 5: Voice Call Testing

### Method 1: Twilio Sandbox (Real)

1. Twilio Phone Number কিনুন
2. Voice webhook configure করুন: `http://localhost:8000/api/voice/incoming`
3. যেকোনো phone থেকে call করুন

### Method 2: Simulation (Quick)

```cmd
curl -X POST "http://localhost:8000/api/voice/incoming" ^
  -d "CallSid=CA1234567890" ^
  -d "From=%%2B880123456789" ^
  -d "To=%%2B1555555555"
```

**আপনার console এ দেখবেন:**
```
📞 Incoming call: CA1234567890 from +880123456789
```

---

## 📊 Step 6: MongoDB Data Check

### Terminal 3: MongoDB Check

```cmd
# MongoDB shell open 
mongosh

# Show databases
show dbs

# Uses our database
use hotel_ai_dev

# Collections see
show collections

# Bookings see
db.bookings.find().pretty()

# Conversations see
db.conversations.find().pretty()

# Rooms see
db.rooms.find().pretty()
```

---

## 🔍 Debugging Tips

### Logs দেখুন

আপনার FastAPI terminal এ:
```
[DEBUG] 📱 WhatsApp from +880123456789: ...
[DEBUG] 🔧 Tool: check_room_availability(...)
[DEBUG] ✅ Booking created: HTLXX1234
```

### Issues Fix

| সমস্যা | সমাধান |
|--------|--------|
| API এ connect হচ্ছে না | `uvicorn main:app --reload` চলছে কিনা check করুন |
| MongoDB error | `mongod` চলছে কিনা check করুন |
| Tests fail | `.env` file setup আছে কিনা check করুন |
| No rooms available | `python -m utils.seed_rooms` চালান |

---

## 📱 Complete Testing Flow

```
Terminal 1: mongod
    ↓
Terminal 2: uvicorn main:app --reload
    ↓
Terminal 3: python test_all.py
    ↓
✅ All tests passed!
```

---

## 🎉 Success Indicators

যখন সবকিছু ঠিক আছে, দেখবেন:

✓ FastAPI server চলছে (http://localhost:8000)
✓ Pytest tests passing
✓ curl commands কাজ করছে
✓ MongoDB data save হচ্ছে
✓ WhatsApp messages processing হচ্ছে
✓ Voice webhooks respond করছে

---

## 📚 Next Steps

Testing ছাড়িয়ে গেলে:

1. **Postman Collection** import করুন (TESTING_GUIDE.md তে আছে)
2. **ngrok** setup করুন real Twilio webhooks এর জন্য
3. **Twilio Phone Number** কিনুন voice calls এর জন্য
4. **Production** এ deploy করুন

---

## 🆘 Help

কোনো সমস্যা হলে:

1. **Logs check করুন** - FastAPI terminal এ error message থাকবে
2. **MongoDB check করুন** - `mongosh` দিয়ে data দেখুন
3. **curl command debug করুন** - `-v` flag যোগ করুন: `curl -v ...`
4. **TESTING_GUIDE.md** পড়ুন - বিস্তারিত troubleshooting আছে

---

## ✨ Final Checklist

আগে যাওয়ার আগে confirm করুন:

- [ ] MongoDB running
- [ ] FastAPI server running
- [ ] `.env` file updated
- [ ] `python -m utils.seed_rooms` চালানো হয়েছে
- [ ] `pytest -v` সব tests pass করছে
- [ ] API endpoints responding করছে
- [ ] WhatsApp simulation কাজ করছে
- [ ] Voice call simulation কাজ করছে

সবকিছু হলে, **আপনার প্রজেক্ট production ready! 🚀**
