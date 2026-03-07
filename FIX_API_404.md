# 🔧 API 404 Errors - How to Fix

আপনার API endpoints 404 return করছে। এটি fix করার জন্য follow করুন:

---

## Step 1: Restart FastAPI Server

আপনার FastAPI server restart করুন যাতে updated code load হয়:

```bash
# If running in PyCharm, click "Run" → "Restart App"
# Or stop the server (Ctrl+C) and restart:
uvicorn main:app --reload
```

**Important:** Server আবার start হলে আপনি logs দেখবেন যেমন:
```
✅ Voice router imported
✅ WhatsApp router imported
✅ API routers imported
📞 Voice router registered
💬 WhatsApp router registered
📋 Bookings router registered
🏨 Rooms router registered
👨‍💼 Admin router registered
```

---

## Step 2: Check MongoDB is Running

Database চলছে কিনা verify করুন:

```bash
# Terminal খুলুন এবং চালান:
mongosh

# যদি connected হয়, write করুন:
use hotel_ai_dev
db.rooms.countDocuments()

# Output হবে room count
```

যদি না চলে, mongod শুরু করুন

---

## Step 3: Seed Database

```bash
python -m utils.seed_rooms
```

**Output:**
```
✅ Seeded XX rooms
```

---

## Step 4: Test Endpoints Now

```bash
# সব routes check করুন:
python debug_endpoints.py
```

যদি এখনও 404 পান, output দেখুন যেখানে routers failed

---

## Common Issues & Fixes

### ❌ Import Error in API Routers

**Log দেখায়:**
```
❌ Failed to import API routers: ...
```

**Fix:**
- Check: `routers/__init__.py` file exists
- Check: `routers/api.py` has no syntax errors
- Check: All imports in `routers/api.py` are correct

```bash
# Verify file exists:
dir routers\api.py

# Test import:
python -c "from routers.api import bookings_router; print('✓ OK')"
```

### ❌ MongoDB Not Connected

**Log দেখায়:**
```
Database disconnected
```

**Fix:**
- Start MongoDB: `mongod`
- Or check `.env` for MONGODB_URI

### ❌ Database is Empty

**Problem:** Rooms list empty

**Fix:**
```bash
python -m utils.seed_rooms
```

---

## Quick Diagnostic Script

এই script রান করুন যা automatically check করবে সব:

```bash
python debug_endpoints.py
```

এটি দেখাবে:
- ✅ Which endpoints work
- ❌ Which return 404
- কেন fail হলো

---

## After Fixes

Once আপনি সব fix করলে:

```bash
# সব tests আবার চালান
python test_all.py
```

সবকিছু ✅ PASS হওয়া উচিত!

---

## If Still Stuck

1. **Check FastAPI console logs** - আছে কি ❌ error messages?
2. **Run debug_endpoints.py** - কোন endpoints কাজ করছে?
3. **Check .env file** - সব settings ঠিক আছে?
4. **Verify MongoDB** - চলছে কিনা mongosh দিয়ে?
5. **Read main.py logs** - কি fail হয়েছে import?

---

**Next:** Server restart করুন এবং `python test_all.py` আবার চালান!

✅ সবকিছু work করবে!
