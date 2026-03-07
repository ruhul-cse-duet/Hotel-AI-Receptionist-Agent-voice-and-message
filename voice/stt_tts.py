"""
Speech-to-Text (STT) and Text-to-Speech (TTS) Services
STT: OpenAI Whisper | Deepgram (low-latency)
TTS: OpenAI TTS | ElevenLabs (most natural)
"""

import io
import base64
import logging
import asyncio
import tempfile
import os
from abc import ABC, abstractmethod
from typing import Optional, AsyncIterator

from config import settings, STTProvider, TTSProvider

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# STT — Speech to Text
# ─────────────────────────────────────────────

class BaseSTT(ABC):
    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> str:
        pass


class OpenAIWhisperSTT(BaseSTT):
    """OpenAI Whisper - best accuracy, slightly slower"""

    def __init__(self):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        logger.info("🎙 STT: OpenAI Whisper")

    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> str:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        try:
            with open(tmp_path, "rb") as audio_file:
                transcript = await self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language,
                    response_format="text",
                )
            return transcript.strip()
        finally:
            os.unlink(tmp_path)


class DeepgramSTT(BaseSTT):
    """Deepgram - ultra-low latency (~300ms), best for real-time"""

    def __init__(self):
        from deepgram import DeepgramClient
        self.client = DeepgramClient(settings.DEEPGRAM_API_KEY)
        logger.info("🎙 STT: Deepgram (real-time)")

    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> str:
        from deepgram import PrerecordedOptions, FileSource

        payload: FileSource = {"buffer": audio_bytes}
        options = PrerecordedOptions(
            model="nova-2",
            language=language,
            smart_format=True,
            punctuate=True,
            filler_words=False,
        )
        response = await asyncio.to_thread(
            self.client.listen.prerecorded.v("1").transcribe_file,
            payload,
            options,
        )
        return response.results.channels[0].alternatives[0].transcript


class LocalWhisperSTT(BaseSTT):
    """Local Whisper via faster-whisper — works offline with LM Studio"""

    def __init__(self):
        from faster_whisper import WhisperModel
        self.model = WhisperModel("base", device="cpu", compute_type="int8")
        logger.info("🎙 STT: Local Whisper (faster-whisper)")

    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> str:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        try:
            segments, _ = await asyncio.to_thread(
                self.model.transcribe, tmp_path, language=language
            )
            return " ".join(seg.text.strip() for seg in segments)
        finally:
            os.unlink(tmp_path)


# ─────────────────────────────────────────────
# TTS — Text to Speech
# ─────────────────────────────────────────────

class BaseTTS(ABC):
    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Returns raw audio bytes (MP3 or WAV)"""
        pass

    @abstractmethod
    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Streams audio chunks for lower latency"""
        pass


class OpenAITTS(BaseTTS):
    """OpenAI TTS - good quality, fast"""

    def __init__(self):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.voice = settings.OPENAI_TTS_VOICE
        logger.info(f"🔊 TTS: OpenAI ({self.voice})")

    async def synthesize(self, text: str) -> bytes:
        response = await self.client.audio.speech.create(
            model="tts-1",
            voice=self.voice,
            input=text,
            response_format="mp3",
        )
        return response.content

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        async with self.client.audio.speech.with_streaming_response.create(
            model="tts-1",
            voice=self.voice,
            input=text,
            response_format="mp3",
        ) as response:
            async for chunk in response.iter_bytes(chunk_size=4096):
                yield chunk


class ElevenLabsTTS(BaseTTS):
    """ElevenLabs - most natural human-like voice"""

    def __init__(self):
        from elevenlabs import AsyncElevenLabs
        self.client = AsyncElevenLabs(api_key=settings.ELEVENLABS_API_KEY)
        self.voice_id = settings.ELEVENLABS_VOICE_ID
        logger.info(f"🔊 TTS: ElevenLabs (voice: {self.voice_id})")

    async def synthesize(self, text: str) -> bytes:
        audio = await self.client.generate(
            text=text,
            voice=self.voice_id,
            model="eleven_turbo_v2",
            output_format="mp3_22050_32",
        )
        chunks = []
        async for chunk in audio:
            chunks.append(chunk)
        return b"".join(chunks)

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        async for chunk in await self.client.generate(
            text=text,
            voice=self.voice_id,
            model="eleven_turbo_v2",
            output_format="mp3_22050_32",
            stream=True,
        ):
            yield chunk


class GTTSLocal(BaseTTS):
    """Google TTS (gTTS) - free, works offline for local dev"""

    def __init__(self):
        logger.info("🔊 TTS: gTTS (free local)")

    async def synthesize(self, text: str) -> bytes:
        from gtts import gTTS
        fp = io.BytesIO()
        tts = gTTS(text=text, lang="en", slow=False)
        await asyncio.to_thread(tts.write_to_fp, fp)
        return fp.getvalue()

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        audio = await self.synthesize(text)
        chunk_size = 4096
        for i in range(0, len(audio), chunk_size):
            yield audio[i:i + chunk_size]


# ─────────────────────────────────────────────
# Factories
# ─────────────────────────────────────────────

_stt_instance: Optional[BaseSTT] = None
_tts_instance: Optional[BaseTTS] = None


def get_stt() -> BaseSTT:
    global _stt_instance
    if not _stt_instance:
        provider = settings.STT_PROVIDER
        if provider == STTProvider.DEEPGRAM and settings.DEEPGRAM_API_KEY:
            _stt_instance = DeepgramSTT()
        elif provider == STTProvider.OPENAI_WHISPER and settings.OPENAI_API_KEY:
            _stt_instance = OpenAIWhisperSTT()
        else:
            # Local fallback
            try:
                _stt_instance = LocalWhisperSTT()
            except ImportError:
                raise RuntimeError("No STT configured. Set OPENAI_API_KEY or DEEPGRAM_API_KEY")
    return _stt_instance


def get_tts() -> BaseTTS:
    global _tts_instance
    if not _tts_instance:
        provider = settings.TTS_PROVIDER
        if provider == TTSProvider.ELEVENLABS and settings.ELEVENLABS_API_KEY:
            _tts_instance = ElevenLabsTTS()
        elif provider == TTSProvider.OPENAI and settings.OPENAI_API_KEY:
            _tts_instance = OpenAITTS()
        else:
            _tts_instance = GTTSLocal()
    return _tts_instance
