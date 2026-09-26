"""
Translation Service for LifeLine-Core Bidirectional Multilingual Triage.

Supports:
- Sarvam AI (mayura:v1) text translation API
- Groq LLM fast fallback translation
- Sub-millisecond in-memory cache for emergency phrases
"""

import asyncio
import logging
import os
from typing import Optional
import httpx
from groq import Groq
from sarvamai import SarvamAI

from app.config import get_settings

logger = logging.getLogger(__name__)

SARVAM_LANG_MAP = {
    "en": "en-IN",
    "en-IN": "en-IN",
    "ta": "ta-IN",
    "ta-IN": "ta-IN",
    "hi": "hi-IN",
    "hi-IN": "hi-IN",
    "te": "te-IN",
    "kn": "kn-IN",
    "bn": "bn-IN",
    "mr": "mr-IN",
    "gu": "gu-IN",
    "ml": "ml-IN",
    "pa": "pa-IN",
    "od": "od-IN",
}

LANG_NAMES = {
    "en": "English",
    "ta": "Tamil",
    "hi": "Hindi",
    "te": "Telugu",
    "kn": "Kannada",
    "bn": "Bengali",
    "mr": "Marathi",
    "gu": "Gujarati",
    "ml": "Malayalam",
    "pa": "Punjabi",
    "od": "Odia",
}


class TranslationService:
    def __init__(self):
        settings = get_settings()
        self.sarvam_api_key = settings.sarvam_api_key
        self.groq_api_key = settings.groq_api_key
        self._cache: dict[str, str] = {}

        self.sarvam_client = None
        if self.sarvam_api_key:
            try:
                self.sarvam_client = SarvamAI(api_subscription_key=self.sarvam_api_key)
            except Exception as e:
                logger.warning("TranslationService: Failed to init Sarvam client: %s", e)

        self.groq_client = None
        if self.groq_api_key:
            try:
                self.groq_client = Groq(api_key=self.groq_api_key)
            except Exception as e:
                logger.warning("TranslationService: Failed to init Groq client: %s", e)

    def _normalize_lang(self, lang: Optional[str]) -> str:
        if not lang:
            return "en"
        clean = lang.lower().strip()
        if clean.startswith("ta"):
            return "ta"
        if clean.startswith("hi"):
            return "hi"
        if clean.startswith("te"):
            return "te"
        if clean.startswith("kn"):
            return "kn"
        if clean.startswith("ml"):
            return "ml"
        if clean.startswith("en"):
            return "en"
        return clean.split("-")[0]

    def detect_language(self, text: str, fallback_lang: str = "en") -> str:
        """
        Detect language of caller transcript from script / character ranges.
        Preserves code-mixed speech without false overrides.
        """
        if not text:
            return self._normalize_lang(fallback_lang)
        # Check Indic Unicode blocks
        if any('\u0B80' <= ch <= '\u0BFF' for ch in text):
            return "ta"
        if any('\u0900' <= ch <= '\u097F' for ch in text):
            return "hi"
        if any('\u0C00' <= ch <= '\u0C7F' for ch in text):
            return "te"
        if any('\u0C80' <= ch <= '\u0CFF' for ch in text):
            return "kn"
        if any('\u0D00' <= ch <= '\u0D7F' for ch in text):
            return "ml"
        return self._normalize_lang(fallback_lang)

    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """
        Translate text from source_lang to target_lang.
        If source_lang == target_lang or text is empty, returns original text immediately.
        """
        if not text or not text.strip():
            return text

        src = self._normalize_lang(source_lang)
        tgt = self._normalize_lang(target_lang)

        if src == tgt:
            return text

        cache_key = f"{src}->{tgt}:{text.strip()}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 1. Primary: Sarvam AI Translate API
        if self.sarvam_client and src in SARVAM_LANG_MAP and tgt in SARVAM_LANG_MAP:
            try:
                translated = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        self._translate_sarvam,
                        text,
                        SARVAM_LANG_MAP[src],
                        SARVAM_LANG_MAP[tgt],
                    ),
                    timeout=4.0,
                )
                if translated and translated.strip():
                    clean_res = translated.strip()
                    self._cache[cache_key] = clean_res
                    return clean_res
            except Exception as e:
                logger.warning("Sarvam translation (%s->%s) error: %s — trying Groq fallback", src, tgt, e)

        # 2. Fallback: Groq LLM Fast Translation
        if self.groq_client:
            try:
                translated = await asyncio.wait_for(
                    self._translate_groq(text, src, tgt),
                    timeout=3.0,
                )
                if translated and translated.strip():
                    clean_res = translated.strip()
                    self._cache[cache_key] = clean_res
                    return clean_res
            except Exception as e:
                logger.error("Groq translation fallback (%s->%s) error: %s", src, tgt, e)

        # If all fail, return original text safely
        return text

    def _translate_sarvam(self, text: str, src_code: str, tgt_code: str) -> str:
        res = self.sarvam_client.text.translate(
            input=text,
            source_language_code=src_code,
            target_language_code=tgt_code,
            model="mayura:v1",
        )
        return getattr(res, "translated_text", "") or ""

    async def _translate_groq(self, text: str, src: str, tgt: str) -> str:
        src_name = LANG_NAMES.get(src, src)
        tgt_name = LANG_NAMES.get(tgt, tgt)
        prompt = (
            f"You are a professional emergency translation assistant. "
            f"Translate the following emergency message from {src_name} to {tgt_name}. "
            f"Preserve all critical emergency facts, numbers, medical conditions, and names accurately. "
            f"Output ONLY the translated sentence with no commentary, no markdown, and no quotes:\n\n{text}"
        )
        resp = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self.groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=256,
            ),
        )
        return resp.choices[0].message.content.strip()


# Global singleton
translation_service = TranslationService()
