import os
import io
import logging
import tempfile
from typing import Optional, Dict, Any

from groq import Groq
from sarvamai import SarvamAI

from app.config import get_settings

logger = logging.getLogger(__name__)


class STTService:
    """
    Multi-layer STT Service.
    Primary:  Groq Whisper (whisper-large-v3-turbo) — fast & highly accurate
    Fallback: Sarvam AI (saaras:v2.5) — for Indian languages
    """

    def __init__(self):
        settings = get_settings()
        self.groq_api_key = settings.groq_api_key
        self.sarvam_api_key = settings.sarvam_api_key
        self.stt_provider = getattr(settings, "stt_provider", "groq")

        # Groq client (primary)
        self.groq_client: Optional[Groq] = None
        if self.groq_api_key:
            self.groq_client = Groq(api_key=self.groq_api_key)
        else:
            logger.warning("GROQ_API_KEY missing — Groq Whisper STT unavailable.")

        # Sarvam client (fallback / Indian languages)
        self.sarvam_client = None
        if self.sarvam_api_key:
            self.sarvam_client = SarvamAI(api_subscription_key=self.sarvam_api_key)
        else:
            logger.warning("SARVAM_API_KEY missing — Sarvam STT unavailable.")

    async def transcribe(self, audio_data: bytes, language: str = "ta") -> Dict[str, Any]:
        """
        Transcribe raw 16 kHz mono PCM audio.
        Tries Groq Whisper first, falls back to Sarvam AI.
        """
        result: Dict[str, Any] = {
            "transcript": "",
            "confidence": 0.0,
            "language": language,
            "provider": "",
        }

        provider = self.stt_provider

        # ── Primary: Groq Whisper ────────────────────────────────
        if provider == "groq" and self.groq_client:
            try:
                transcript = await self._transcribe_groq(audio_data, language)
                if transcript:
                    result.update({
                        "transcript": transcript,
                        "confidence": 0.95,
                        "provider": "groq-whisper",
                    })
                    return result
                logger.info("Groq Whisper returned empty — trying Sarvam fallback.")
            except Exception as e:
                logger.error("Groq Whisper STT failed: %s", e)

        # ── Fallback: Sarvam AI ──────────────────────────────────
        if self.sarvam_client:
            try:
                transcript = self._transcribe_sarvam(audio_data)
                if transcript:
                    result.update({
                        "transcript": transcript,
                        "confidence": 0.8,
                        "provider": "sarvam",
                    })
                    return result
            except Exception as e:
                logger.error("Sarvam STT fallback failed: %s", e)

        # ── If provider is sarvam-first, try Groq as fallback ───
        if provider == "sarvam" and self.groq_client:
            try:
                transcript = await self._transcribe_groq(audio_data, language)
                if transcript:
                    result.update({
                        "transcript": transcript,
                        "confidence": 0.95,
                        "provider": "groq-whisper",
                    })
                    return result
            except Exception as e:
                logger.error("Groq Whisper fallback failed: %s", e)

        return result

    async def _transcribe_groq(self, audio_data: bytes, language: str = "en") -> str:
        """
        Transcribe using Groq's Whisper large-v3-turbo.
        Converts raw PCM → WAV in-memory, then sends to Groq API.
        """
        import wave
        import asyncio

        # Wrap raw PCM bytes in a proper WAV container
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(1)         # mono
            wf.setsampwidth(2)         # 16-bit
            wf.setframerate(16000)     # 16 kHz
            wf.writeframes(audio_data)
        wav_buffer.seek(0)

        # Groq SDK is synchronous — run in thread pool
        def _call():
            return self.groq_client.audio.transcriptions.create(
                file=("audio.wav", wav_buffer.read()),
                model="whisper-large-v3-turbo",
                language=language.split("-")[0],      # "en-IN" → "en"
                response_format="text",
                temperature=0.0,
            )

        wav_buffer.seek(0)
        response = await asyncio.get_event_loop().run_in_executor(None, _call)

        # response is a string when response_format="text"
        transcript = str(response).strip() if response else ""
        if transcript:
            logger.info("Groq Whisper: %s", transcript[:80])
        return transcript

    def _transcribe_sarvam(self, audio_data: bytes) -> str:
        """Transcribe using Sarvam AI saaras model."""
        response = self.sarvam_client.speech_to_text.generate(
            file=audio_data,
            model="saaras:v2.5",
            language_code="unknown",
            with_timestamps=False,
        )
        transcript = getattr(response, "transcript", "")
        if transcript:
            logger.info("Sarvam STT: %s", transcript[:80])
        return transcript
