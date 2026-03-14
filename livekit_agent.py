"""
LiveKit AI Voice Agent Worker
Runs as a separate process to join LiveKit rooms and handle real-time voice.
"""

import logging

from dotenv import load_dotenv

load_dotenv()

from config import settings  # noqa: E402
from ai.prompts import get_system_prompt  # noqa: E402

# Register plugins on the main thread once.
from livekit.plugins import openai as _openai_plugin  # noqa: E402, F401
from livekit.plugins import silero as _silero_plugin  # noqa: E402, F401

logger = logging.getLogger(__name__)


def _prewarm(_proc):
    # No-op: plugin registration must happen on the main thread.
    return None


def _build_system_prompt() -> str:
    return get_system_prompt(
        channel="voice",
        hotel_name=settings.HOTEL_NAME,
        receptionist_name=settings.RECEPTIONIST_NAME,
        hotel_address=settings.HOTEL_ADDRESS,
        checkin_time=settings.HOTEL_CHECKIN_TIME,
        checkout_time=settings.HOTEL_CHECKOUT_TIME,
        currency=settings.HOTEL_CURRENCY,
        hotel_phone=settings.HOTEL_PHONE,
    )


async def entrypoint(ctx):
    from livekit.agents import AutoSubscribe
    from livekit.agents.pipeline import VoicePipelineAgent
    from livekit.agents.llm import ChatContext

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    participant = await ctx.wait_for_participant()

    chat_ctx = ChatContext().append(text=_build_system_prompt(), role="system")

    agent = VoicePipelineAgent(
        vad=_silero_plugin.VAD.load(),
        stt=_openai_plugin.STT(model="whisper-1"),
        llm=_openai_plugin.LLM(model=settings.OPENAI_MODEL),
        tts=_openai_plugin.TTS(model=settings.OPENAI_TTS_MODEL, voice=settings.OPENAI_TTS_VOICE),
        chat_ctx=chat_ctx,
    )
    agent.start(ctx.room, participant)
    await agent.say(
        f"Hello sir, this is {settings.RECEPTIONIST_NAME} from the front desk. How may I help you today?",
        allow_interruptions=True,
    )


if __name__ == "__main__":
    from livekit.agents import cli, WorkerOptions

    if not settings.LIVEKIT_URL or not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        raise RuntimeError("LiveKit env missing: LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET")

    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=_prewarm,
            ws_url=settings.LIVEKIT_URL,
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET,
        )
    )
