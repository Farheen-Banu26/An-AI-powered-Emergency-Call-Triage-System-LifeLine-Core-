import asyncio
import io
import logging
import os
import tempfile
import time
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

    def __init__(self, provider: Optional[str] = None):
        settings = get_settings()
        self.groq_api_key = settings.groq_api_key
        self.sarvam_api_key = settings.sarvam_api_key
        self.stt_provider = provider or getattr(settings, "stt_provider", "sarvam") or "sarvam"

        # Groq client (fallback / alternative)
        self.groq_client: Optional[Groq] = None
        if self.groq_api_key:
            self.groq_client = Groq(api_key=self.groq_api_key)
        else:
            logger.warning("GROQ_API_KEY missing — Groq Whisper STT unavailable.")

        # Sarvam client (primary for Indian languages & English)
        self.sarvam_client = None
        if self.sarvam_api_key:
            self.sarvam_client = SarvamAI(api_subscription_key=self.sarvam_api_key)
        else:
            logger.warning("SARVAM_API_KEY missing — Sarvam STT unavailable.")

    async def transcribe(
        self,
        audio_data: bytes,
        language: str = "ta",
        mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Transcribe raw 16 kHz mono PCM audio.
        Primary:  Sarvam AI (saaras:v4 / translate) — high accuracy for Indian languages & English
        Fallback: Groq Whisper (whisper-large-v3-turbo)
        """
        result: Dict[str, Any] = {
            "transcript": "",
            "confidence": 0.0,
            "language": language,
            "provider": "",
        }

        provider = self.stt_provider

        # ── Primary: Sarvam AI ──────────────────────────────────
        if provider == "sarvam" and self.sarvam_client:
            try:
                t0 = time.time()
                logger.info("[VOICE] language=%s event=stt_request_started session_id=%s provider=sarvam", language, getattr(self, "_active_session", "unknown"))

                # Transcribe in speaker's native language to preserve original transcript
                if mode == "translate" and hasattr(self.sarvam_client.speech_to_text, "translate"):
                    transcript = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(None, self._translate_sarvam, audio_data),
                        timeout=5.0
                    )
                else:
                    transcript = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(None, self._transcribe_sarvam, audio_data, language),
                        timeout=5.0
                    )

                latency_ms = (time.time() - t0) * 1000
                logger.info("[VOICE] language=%s event=stt_request_finished provider=sarvam latency_ms=%.1f transcript=%r", language, latency_ms, transcript[:60] if transcript else "")

                # If Sarvam executed successfully, return its result.
                # If transcript is empty, Sarvam correctly identified silence — DO NOT fall back to Groq!
                result.update({
                    "transcript": transcript or "",
                    "confidence": 0.98 if transcript else 0.0,
                    "provider": "sarvam",
                })
                return result

            except asyncio.TimeoutError:
                logger.warning("[VOICE] Sarvam STT timed out after 5.0s — trying Groq fallback")
            except Exception as e:
                logger.error("Sarvam STT failed: %s — trying Groq fallback", e)

        # ── Fallback: Groq Whisper (Only reached if Sarvam threw an unhandled Exception/Timeout) ──
        if self.groq_client:
            try:
                t0 = time.time()
                logger.info("[VOICE] language=%s event=stt_request_started session_id=%s provider=groq-whisper-fallback", language, getattr(self, "_active_session", "unknown"))
                transcript = await asyncio.wait_for(self._transcribe_groq(audio_data, language), timeout=5.0)
                latency_ms = (time.time() - t0) * 1000
                logger.info("[VOICE] language=%s event=stt_request_finished provider=groq-whisper-fallback latency_ms=%.1f transcript=%r", language, latency_ms, transcript[:60] if transcript else "")
                if transcript:
                    result.update({
                        "transcript": transcript,
                        "confidence": 0.85,
                        "provider": "groq-whisper",
                    })
                    return result
            except asyncio.TimeoutError:
                logger.warning("[VOICE] Groq Whisper STT timed out after 5.0s")
            except Exception as e:
                logger.error("Groq Whisper STT failed: %s", e)

        # ── Fallback if provider was configured as groq-first ───
        if provider == "groq" and self.sarvam_client:
            try:
                t0 = time.time()
                transcript = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, self._transcribe_sarvam, audio_data, language),
                    timeout=5.0
                )
                if transcript:
                    result.update({
                        "transcript": transcript,
                        "confidence": 0.95,
                        "provider": "sarvam",
                    })
                    return result
            except Exception as e:
                logger.error("Sarvam fallback failed: %s", e)

        return result

    def _translate_sarvam(self, audio_data: bytes, model: str = "saaras:v2.5") -> str:
        """Translate Indic / code-mixed speech directly into English using Sarvam AI."""
        import wave
        if not audio_data.startswith(b"RIFF"):
            wav_buf = io.BytesIO()
            with wave.open(wav_buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(audio_data)
            audio_payload = wav_buf.getvalue()
        else:
            audio_payload = audio_data

        try:
            response = self.sarvam_client.speech_to_text.translate(
                file=("audio.wav", audio_payload, "audio/wav"),
                model=model,
            )
            transcript = getattr(response, "transcript", "")
            return transcript.strip() if transcript else ""
        except Exception as e:
            logger.warning("Sarvam translate call error: %s — falling back to transcribe", e)
            return self._transcribe_sarvam(audio_data, language="en")

    def _transcribe_sarvam(self, audio_data: bytes, language: str = "en") -> str:
        """Transcribe using Sarvam AI Saaras v4 (with saaras:v3 fallback)."""
        import wave
        if not audio_data.startswith(b"RIFF"):
            wav_buf = io.BytesIO()
            with wave.open(wav_buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(audio_data)
            audio_payload = wav_buf.getvalue()
        else:
            audio_payload = audio_data

        target_lang = "unknown"
        if language in ("hi", "hi-IN"):
            target_lang = "hi-IN"
        elif language in ("ta", "ta-IN"):
            target_lang = "ta-IN"
        elif language in ("en", "en-IN"):
            target_lang = "en-IN"

        # Try saaras:v4 first
        try:
            response = self.sarvam_client.speech_to_text.transcribe(
                file=("audio.wav", audio_payload, "audio/wav"),
                model="saaras:v4",
                language_code=target_lang,
            )
            transcript = getattr(response, "transcript", "")
            if transcript:
                return transcript.strip()
        except Exception as e:
            logger.warning("Sarvam saaras:v4 failed (%s), trying saaras:v3", e)

        # Fallback to saaras:v3
        try:
            response = self.sarvam_client.speech_to_text.transcribe(
                file=("audio.wav", audio_payload, "audio/wav"),
                model="saaras:v3",
                language_code=target_lang,
            )
            transcript = getattr(response, "transcript", "")
            return transcript.strip() if transcript else ""
        except Exception as e:
            logger.error("Sarvam saaras:v3 also failed: %s", e)
            raise e

    async def _transcribe_groq(self, audio_data: bytes, language: str = "en") -> str:
        """
        Transcribe using Groq's Whisper large-v3-turbo with hallucination filtering.
        """
        import wave
        import asyncio

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(1)         # mono
            wf.setsampwidth(2)         # 16-bit
            wf.setframerate(16000)     # 16 kHz
            wf.writeframes(audio_data)
        wav_buffer.seek(0)

        def _call():
            # whisper-large-v3-turbo is significantly faster with lower latency
            return self.groq_client.audio.transcriptions.create(
                file=("audio.wav", wav_buffer.read()),
                model="whisper-large-v3-turbo",
                language=language.split("-")[0],
                response_format="text",
                temperature=0.0,
            )

        wav_buffer.seek(0)
        response = await asyncio.get_event_loop().run_in_executor(None, _call)

        transcript = str(response).strip() if response else ""

        # Hallucination filter for Whisper
        hallucination_phrases = [
            "thank you for watching", "thanks for watching", "subscribe to my channel",
            "i'm going to go back to my room", "and i could tell you what the other thing is",
            "i'm not a man of a hero", "yes, i am the one", "i'm going to go", "god. god. god",
            "i'll get it", "i'm going to get him", "i need to go", "that... that...",
            "நான் பார்த்துக்கொள்ளுங்கள்", "நான் வருக்கிறேன்", "you", "bye", "bye bye"
        ]
        t_low = transcript.lower().strip()
        if any(h in t_low for h in hallucination_phrases) or t_low in ["yeah", "yes", "all right", "what?", "god", "you"]:
            logger.warning("[GROQ WHISPER] Discarded known hallucination: %r", transcript)
            return ""

        if transcript:
            logger.info("Groq Whisper: %s", transcript[:80])
        return transcript
