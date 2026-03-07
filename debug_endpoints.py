#!/usr/bin/env python
"""
Debug script to check FastAPI routing
"""

import sys
import requests

BASE_URL = "http://localhost:8000"

def test_endpoint(method, path, name):
    try:
        url = f"{BASE_URL}{path}"
        if method == "GET":
            response = requests.get(url)
        else:
            response = requests.post(url, json={})
        
        status = "✅" if response.status_code != 404 else "❌"
        print(f"{status} {method:6} {path:40} → {response.status_code}")
        return response.status_code != 404
    except Exception as e:
        print(f"❌ {method:6} {path:40} → ERROR: {e}")
        return False

print("Testing FastAPI Endpoints\n")

# Test basic health
print("=== BASIC HEALTH ===")
test_endpoint("GET", "/", "root")
test_endpoint("GET", "/health", "health")
test_endpoint("GET", "/docs", "docs")

# Test API endpoints
print("\n=== API ENDPOINTS ===")
test_endpoint("GET", "/rooms", "list_rooms")
test_endpoint("POST", "/rooms", "create_room")
test_endpoint("GET", "/bookings", "list_bookings")
test_endpoint("POST", "/bookings", "create_booking")
test_endpoint("GET", "/bookings/availability", "check_availability")
test_endpoint("GET", "/admin/dashboard", "admin_dashboard")

# Test WhatsApp & Voice
print("\n=== WEBHOOKS ===")
test_endpoint("POST", "/api/whatsapp/incoming", "whatsapp_incoming")
test_endpoint("POST", "/api/voice/incoming", "voice_incoming")

print("\n✅ Debug complete. Check which endpoints are returning 404")
