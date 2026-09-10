import logging
import base64
from typing import Generator, Optional
from sarvamai import SarvamAI
from app.config import get_settings

logger = logging.getLogger(__name__)

class TTSService:
    """
    Sarvam AI Text-to-Speech service.
    Converts AI question text into streaming audio bytes.
    """
    
    # Language code mapping — ISO 639-1 → BCP-47 (Sarvam format).
    LANGUAGE_MAP = {
        "en": "en-IN",  # English (Indian accent)
        "ta": "ta-IN",  # Tamil
        "hi": "hi-IN",  # Hindi
    }

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.sarvam_api_key
        if not self.api_key:
            logger.warning("SARVAM_API_KEY not found in environment.")
        
        self.client = None
        if self.api_key:
            try:
                self.client = SarvamAI(api_subscription_key=self.api_key)
                logger.info("Sarvam AI TTS client initialized.")
            except Exception as e:
                logger.error(f"Failed to initialize Sarvam AI client: {e}")

        self.stream_chunk_size = 4096  # 4 KB

    def stream_speech(self, text: str, language_code: str = "hi") -> Generator[bytes, None, None]:
        """
        Synthesizes text to speech and yields audio bytes in chunks.
        """
        if not self.client:
            logger.error("TTS Client not initialized. Cannot stream speech.")
            return

        target_lang = self.LANGUAGE_MAP.get(language_code, "en-IN")
        
        try:
            response = self.client.text_to_speech.convert(
                text=text,
                target_language_code=target_lang,
                model="bulbul:v2",
                speech_sample_rate=16000
            )
            
            audios = getattr(response, "audios", None)
            if not audios:
                logger.error("Sarvam TTS returned no audio data.")
                return

            for b64_audio in audios:
                try:
                    raw_bytes = base64.b64decode(b64_audio)
                    # Yield in fixed-size chunks for progressive streaming
                    offset = 0
                    while offset < len(raw_bytes):
                        yield raw_bytes[offset : offset + self.stream_chunk_size]
                        offset += self.stream_chunk_size
                except Exception as e:
                    logger.error(f"Failed to decode or yield audio chunk: {e}")
                    
        except Exception as e:
            logger.error(f"Sarvam TTS streaming error: {e}")
