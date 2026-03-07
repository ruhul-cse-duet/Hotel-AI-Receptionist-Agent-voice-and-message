"""
Complete Manual Testing Script for Hotel AI Receptionist
Run this script to test all features:
- Unit tests (pytest)
- API endpoints (curl)
- WhatsApp simulation
- Voice call simulation

Usage:
    python test_all.py
"""

import subprocess
import sys
import json
import requests
from datetime import date, timedelta
from time import sleep

# Color codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"

BASE_URL = "http://localhost:8000"


def print_header(text):
    print(f"\n{CYAN}{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}{RESET}\n")


def print_success(text):
    print(f"{GREEN}✓ {text}{RESET}")


def print_error(text):
    print(f"{RED}✗ {text}{RESET}")


def print_info(text):
    print(f"{YELLOW}» {text}{RESET}")


def print_json(data):
    print(json.dumps(data, indent=2, default=str))


# ─────────────────────────────────────────────────────────
# 1. UNIT TESTS
# ─────────────────────────────────────────────────────────

def run_unit_tests():
    print_header("RUNNING UNIT TESTS (pytest)")
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-v", "--tb=short"],
            cwd=".",
            capture_output=False
        )
        
        if result.returncode == 0:
            print_success("All unit tests passed!")
            return True
        else:
            print_error("Some unit tests failed")
            return False
    except Exception as e:
        print_error(f"Failed to run tests: {e}")
        return False


# ─────────────────────────────────────────────────────────
# 2. API TESTS
# ─────────────────────────────────────────────────────────

def test_api_health():
    """Test if API is running"""
    print_header("TESTING API HEALTH")
    
    try:
        response = requests.get(f"{BASE_URL}/docs")
        if response.status_code == 200:
            print_success("API is running at http://localhost:8000")
            return True
        else:
            print_error("API returned unexpected status code")
            return False
    except requests.exceptions.ConnectionError:
        print_error("Cannot connect to API. Is it running on port 8000?")
        print_info("Start the server: uvicorn main:app --reload")
        return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


def test_list_rooms():
    """Test GET /rooms"""
    print_header("TEST: List All Rooms")
    
    try:
        response = requests.get(f"{BASE_URL}/rooms")
        data = response.json()
        
        if response.status_code == 200:
            print_success(f"Retrieved {len(data.get('data', []))} rooms")
            if data.get('data'):
                print_info("Sample room:")
                print_json(data['data'][0])
            return True
        else:
            print_error(f"API error: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


def test_check_availability():
    """Test GET /bookings/availability"""
    print_header("TEST: Check Room Availability")
    
    try:
        check_in = (date.today() + timedelta(days=5)).isoformat()
        check_out = (date.today() + timedelta(days=7)).isoformat()
        
        print_info(f"Checking for {check_in} to {check_out}")
        
        response = requests.get(
            f"{BASE_URL}/bookings/availability",
            params={
                "check_in_date": check_in,
                "check_out_date": check_out,
                "room_type": "deluxe"
            }
        )
        data = response.json()
        
        if response.status_code == 200:
            available_count = len(data.get('data', {}).get('rooms', []))
            print_success(f"Found {available_count} available deluxe rooms")
            if available_count > 0:
                print_info("Available rooms:")
                for room in data['data']['rooms'][:2]:
                    print(f"  - Room {room['room_number']}: BDT {room['price_per_night']}/night")
            return True
        else:
            print_error(f"API error: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


def test_create_booking():
    """Test POST /bookings"""
    print_header("TEST: Create Booking")
    
    try:
        check_in = (date.today() + timedelta(days=5)).isoformat()
        check_out = (date.today() + timedelta(days=7)).isoformat()
        
        booking_data = {
            "guest_name": "Test User",
            "guest_phone": "+880123456789",
            "guest_email": "test@example.com",
            "room_id": "room_dlx_001",  # Using a standard room ID
            "check_in_date": check_in,
            "check_out_date": check_out,
            "adults": 2,
            "children": 0,
            "special_requests": "High floor preferred"
        }
        
        print_info("Creating booking with data:")
        print_json(booking_data)
        
        response = requests.post(
            f"{BASE_URL}/bookings",
            json=booking_data
        )
        data = response.json()
        
        if response.status_code == 200:
            booking_id = data.get('data', {}).get('booking_id')
            print_success(f"Booking created! ID: {booking_id}")
            print_json(data['data'])
            return True, booking_id
        else:
            print_error(f"Failed to create booking: {response.status_code}")
            print_json(data)
            return False, None
    except Exception as e:
        print_error(f"Error: {e}")
        return False, None


def test_get_booking(booking_id=None):
    """Test GET /bookings/{booking_id}"""
    print_header("TEST: Get Booking Details")
    
    if not booking_id:
        print_error("No booking ID provided")
        return False
    
    try:
        response = requests.get(f"{BASE_URL}/bookings/{booking_id}")
        data = response.json()
        
        if response.status_code == 200:
            print_success(f"Retrieved booking {booking_id}")
            print_json(data['data'])
            return True
        else:
            print_error(f"Failed to retrieve booking: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


def test_list_bookings():
    """Test GET /bookings"""
    print_header("TEST: List All Bookings")
    
    try:
        response = requests.get(f"{BASE_URL}/bookings")
        data = response.json()
        
        if response.status_code == 200:
            count = len(data.get('data', []))
            print_success(f"Retrieved {count} bookings")
            if count > 0:
                print_info("Latest booking:")
                print_json(data['data'][0])
            return True
        else:
            print_error(f"Failed to list bookings: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


# ─────────────────────────────────────────────────────────
# 3. WHATSAPP SIMULATION
# ─────────────────────────────────────────────────────────

def test_whatsapp_incoming():
    """Simulate incoming WhatsApp message"""
    print_header("TEST: WhatsApp Incoming Message")
    
    try:
        print_info("Simulating WhatsApp message...")
        
        response = requests.post(
            f"{BASE_URL}/api/whatsapp/incoming",
            data={
                "From": "whatsapp:+880987654321",
                "To": "whatsapp:+14155238886",
                "Body": "Hi, do you have rooms available for next week?",
                "NumMedia": "0",
                "ProfileName": "Test User"
            }
        )
        
        if response.status_code in [200, 204]:
            print_success("WhatsApp message processed")
            return True
        else:
            print_error(f"Failed to process message: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


# ─────────────────────────────────────────────────────────
# 4. VOICE CALL SIMULATION
# ─────────────────────────────────────────────────────────

def test_voice_incoming():
    """Simulate incoming voice call"""
    print_header("TEST: Voice Call Incoming")
    
    try:
        print_info("Simulating incoming call...")
        
        response = requests.post(
            f"{BASE_URL}/api/voice/incoming",
            data={
                "CallSid": "CA1234567890abcdef",
                "From": "+880123456789",
                "To": "+1555555555",
                "Direction": "inbound",
                "CallStatus": "ringing"
            }
        )
        
        if response.status_code == 200:
            print_success("Voice call webhook processed")
            print_info("Expected response: TwiML with media stream setup")
            return True
        else:
            print_error(f"Failed to process call: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False


# ─────────────────────────────────────────────────────────
# 5. MAIN TEST RUNNER
# ─────────────────────────────────────────────────────────

def main():
    print(f"\n{CYAN}🏨 Hotel AI Receptionist - Complete Test Suite{RESET}\n")
    
    # Track results
    results = {
        "unit_tests": False,
        "api_health": False,
        "list_rooms": False,
        "check_availability": False,
        "create_booking": False,
        "get_booking": False,
        "list_bookings": False,
        "whatsapp": False,
        "voice": False,
    }
    
    # Run tests
    print_info("Starting comprehensive tests...\n")
    
    # 1. Unit Tests
    results["unit_tests"] = run_unit_tests()
    
    # 2. API Tests
    if not test_api_health():
        print_error("API is not running. Skipping remaining tests.")
        print_info("Start the server: uvicorn main:app --reload")
        print_summary(results)
        return 1
    
    results["api_health"] = True
    results["list_rooms"] = test_list_rooms()
    results["check_availability"] = test_check_availability()
    
    success, booking_id = test_create_booking()
    results["create_booking"] = success
    
    if booking_id:
        results["get_booking"] = test_get_booking(booking_id)
    
    results["list_bookings"] = test_list_bookings()
    
    # 3. WhatsApp Test
    results["whatsapp"] = test_whatsapp_incoming()
    
    # 4. Voice Test
    results["voice"] = test_voice_incoming()
    
    # Summary
    print_summary(results)
    
    # Return exit code
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    if passed == total:
        print_success(f"All {total} tests passed! ✓")
        return 0
    else:
        print_error(f"{passed}/{total} tests passed")
        return 1


def print_summary(results):
    print_header("TEST SUMMARY")
    
    for test_name, passed in results.items():
        status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        test_display = test_name.replace("_", " ").title()
        print(f"  {test_display}: {status}")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    percentage = (passed / total * 100) if total > 0 else 0
    
    print(f"\n  Overall: {passed}/{total} ({percentage:.0f}%) tests passed\n")


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
