"""
Hotel AI Receptionist - Central Configuration
Supports: OpenAI (prod) | Gemini (prod alt) | LM Studio (local dev)
"""

from enum import Enum
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field


class LLMProvider(str, Enum):
    OPENAI = "openai"
    GEMINI = "gemini"
    LM_STUDIO = "lm_studio"


class STTProvider(str, Enum):
    OPENAI_WHISPER = "openai_whisper"
    DEEPGRAM = "deepgram"
    GOOGLE = "google"


class TTSProvider(str, Enum):
    OPENAI = "openai"
    ELEVENLABS = "elevenlabs"
    GOOGLE = "google"


class Settings(BaseSettings):
    # ── App ────────────────────────────────────────────────
    APP_NAME: str = "Hotel AI Receptionist"
    APP_ENV: str = Field(default="development")  # development | production
    DEBUG: bool = Field(default=True)
    HOST: str = "0.0.0.0"
    PORT: int = 8002
    WEBHOOK_BASE_URL: str = Field(default="https://uncatastrophically-unrivalled-coreen.ngrok-free.dev")  # public URL for Twilio webhooks
    WEBHOOK_TIMEOUT_SECONDS: int = Field(default=30)

    # Meta WhatsApp Cloud API
    META_WA_VERIFY_TOKEN: str = Field(default="")
    META_WA_ACCESS_TOKEN: str = Field(default="")
    META_WA_PHONE_NUMBER_ID: str = Field(default="")
    META_WABA_ID: str = Field(default="")
    META_GRAPH_API_VERSION: str = Field(default="v20.0")

    # Conversation memory
    CONVERSATION_MEMORY_DAYS: int = Field(default=15)
    CONVERSATION_MEMORY_MAX_MESSAGES: int = Field(default=20)

    # ── MongoDB ────────────────────────────────────────────
    MONGODB_URI: str = Field(default="mongodb://localhost:27017")
    MONGODB_DB_NAME: str = "hotel_ai_receptionist"

    # ── LLM Provider ──────────────────────────────────────
    LLM_PROVIDER: LLMProvider = Field(default=LLMProvider.LM_STUDIO)  # switch in .env

    # OpenAI
    OPENAI_API_KEY: str = Field(default="")
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_TEMPERATURE: float = 0.7

    # Gemini
    GEMINI_API_KEY: str = Field(default="")
    GEMINI_MODEL: str = "gemini-1.5-pro"

    # LM Studio (local - OpenAI-compatible endpoint)
    LM_STUDIO_BASE_URL: str = "http://localhost:1234/v1"
    LM_STUDIO_MODEL: str = "lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF"
    LM_STUDIO_API_KEY: str = "lm-studio"  # LM Studio accepts any key

    # ── STT ────────────────────────────────────────────────
    STT_PROVIDER: STTProvider = Field(default=STTProvider.OPENAI_WHISPER)
    DEEPGRAM_API_KEY: str = Field(default="")
    GOOGLE_CLOUD_CREDENTIALS: str = Field(default="")

    # ── TTS ────────────────────────────────────────────────
    TTS_PROVIDER: TTSProvider = Field(default=TTSProvider.OPENAI)
    ELEVENLABS_API_KEY: str = Field(default="")
    ELEVENLABS_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel - natural female voice
    OPENAI_TTS_VOICE: str = "nova"  # alloy|echo|fable|onyx|nova|shimmer
    GOOGLE_TTS_LANGUAGE: str = Field(default="en-US")

    # ── Twilio ─────────────────────────────────────────────
    TWILIO_ACCOUNT_SID: str = Field(default="")
    TWILIO_AUTH_TOKEN: str = Field(default="")
    TWILIO_PHONE_NUMBER: str = Field(default="")       # +1234567890
    TWILIO_WHATSAPP_NUMBER: str = Field(default="")    # whatsapp:+14155238886
    VERIFY_TWILIO_SIGNATURE: bool = Field(default=False)
    WHATSAPP_MAX_PARTS: int = Field(default=1)  # cap replies to reduce message count/limits

    # ── Hotel Info ─────────────────────────────────────────
    HOTEL_NAME: str = "Grand Azure Hotel"
    RECEPTIONIST_NAME: str = "Aria"
    HOTEL_PHONE: str = "+8801234567890"
    HOTEL_ADDRESS: str = "123 Main Street, Dhaka, Bangladesh"
    HOTEL_CHECKIN_TIME: str = "14:00"
    HOTEL_CHECKOUT_TIME: str = "12:00"
    HOTEL_CURRENCY: str = "BDT"
    HOTEL_TIMEZONE: str = "Asia/Dhaka"

    # ── Security & Admin ───────────────────────────────────
    SECRET_KEY: str = Field(default="change-this-in-production-secret-key")
    WEBHOOK_SECRET: str = Field(default="")
    ADMIN_SECRET_KEY: str = Field(default="your-super-secret-admin-key-change-this")
    API_KEY_REQUIRED: bool = Field(default=False)

    # ── Logging ────────────────────────────────────────────
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FILE: str = Field(default="hotel_ai.log")
    LOG_MAX_SIZE_MB: int = Field(default=50)
    LOG_BACKUP_COUNT: int = Field(default=5)

    # ── Feature Flags ──────────────────────────────────────
    ENABLE_VOICE_CALLS: bool = Field(default=True)
    ENABLE_WHATSAPP: bool = Field(default=True)
    ENABLE_BOOKING_CONFIRMATION_SMS: bool = Field(default=False)
    ENABLE_CALL_RECORDING: bool = Field(default=False)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
