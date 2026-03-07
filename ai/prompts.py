"""
AI prompts and templates used across the agent, voice and WhatsApp handlers.
Provides:
- get_system_prompt(channel, hotel_name, ...)
- VOICE_BREVITY_REMINDER
- GREETING_WHATSAPP
- BOOKING_CONFIRMATION_WHATSAPP
"""
from typing import Optional

VOICE_BREVITY_REMINDER = (
    "When replying to the guest over voice, be brief and natural. "
    "Use 2-3 short sentences, avoid lists, and speak like a polite receptionist."
)

GREETING_WHATSAPP = (
    "Hello {hotel_name}! 👋\n"
    "I'm your AI receptionist. How can I assist you today?"
)

BOOKING_CONFIRMATION_WHATSAPP = (
    "*Booking Confirmed!*\n"
    "Booking ID: {booking_id}\n"
    "Guest: {guest_name}\n"
    "Room: {room_type} {room_number}\n"
    "Check-in: {check_in_date} • Check-out: {check_out_date}\n"
    "Total: {currency} {total_amount}\n\n"
    "Thank you for choosing {hotel_address} — we look forward to welcoming you!"
)


GREETING_VOICE = (
    "Good day! Thank you for calling {hotel_name}. "
    "This is your AI receptionist. How may I help you today?"
)


def get_system_prompt(
    channel: str,
    hotel_name: str,
    hotel_address: str,
    checkin_time: str,
    checkout_time: str,
    currency: str,
) -> str:
    """Return a system prompt tailored to the channel (voice|whatsapp).

    This prompt guides the LLM's behavior for booking, availability, and confirmations.
    Keep it concise but informative.
    """
    base = (
        f"You are an AI receptionist for {hotel_name} located at {hotel_address}. "
        "You help guests check availability, book rooms, and answer simple hotel questions. "
        f"Always confirm check-in time is {checkin_time} and checkout time is {checkout_time}. "
        f"Prices are in {currency}."
    )

    if channel == "voice":
        base += " When speaking, be concise, polite, and use natural spoken language. "
        base += "If asked to provide pricing, give clear totals and ask for confirmation."
    else:
        # whatsapp / text channel
        base += " Use friendly, helpful messaging suitable for WhatsApp. "
        base += "You may include short lists and emojis where appropriate."

    # Safety and privacy guidance
    base += (
        " Do not ask for sensitive payment card data in chat; for payments, instruct the user to contact the front desk or follow secure payment links. "
        "When a booking is confirmed, prepare a JSON-friendly tool call to create the booking record."
    )

    return base
