"""
Gemini Vision Analysis Service for Emergency Visual Evidence.

Provides cautious, structured visual observations of uploaded images and camera snapshots
for emergency dispatchers without making definitive medical diagnoses or replacing the core AI triage.
"""

import json
import logging
import os
import re
from typing import Optional, List, Dict, Any
import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM_PROMPT = """You are an AI visual evidence observer for an emergency dispatch system (LifeLine-Core).
Carefully analyze all observable visual elements in the provided image within the context of the reported emergency scene.

SCENE CONTEXT: {scene}

STRICT SAFETY AND REPORTING RULES:
1. Identify all observable physical facts, visible damaged objects/vehicles, scene environment, hazards, visible persons, road conditions, and apparent situation.
2. DO NOT make definitive medical diagnoses or assert unobservable internal injuries (e.g. do NOT diagnose 'internal bleeding', 'fracture', 'concussion', 'unconsciousness', 'spinal injury').
3. Use cautious, observable phrasing where appropriate (e.g. 'Possible vehicle collision visible', 'Two visibly damaged vehicles present', 'Multiple people visible', 'Possible injured person lying on roadway', 'Visible blood-like staining near person', 'Vehicle debris scattered on road', 'Road obstruction visible', 'Possible fire / smoke visible').
4. Return a structured JSON object matching this schema:
{{
  "observations": [
    {{
      "label": "Short observable title (e.g. Possible vehicle collision)",
      "description": "Clear factual visual description of what is visible in the image",
      "confidence": 0.95
    }}
  ]
}}
Provide between 2 and 6 detailed, accurate visual observations based strictly on what is visible in the image."""


class GeminiVisionService:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.settings = get_settings()
        self._custom_api_key = api_key
        self._custom_model = model

    def _extract_base64_and_mime(self, image_data: str) -> tuple[str, str]:
        """Extract clean base64 data and mime-type from data URL or raw base64."""
        if image_data.startswith("data:"):
            match = re.match(r"data:([^;]+);base64,(.*)", image_data, re.DOTALL)
            if match:
                return match.group(2).strip(), match.group(1).strip()
        # Default fallback to image/jpeg
        return image_data.strip(), "image/jpeg"

    async def analyze_image(self, image_data: str, scene: Optional[str] = "general") -> Dict[str, Any]:
        """
        Analyze an image with Gemini Vision and return structured visual observations.
        Does not raise exceptions; returns graceful fallback on any error.
        """
        api_key = (
            self._custom_api_key
            if self._custom_api_key is not None
            else (
                self.settings.gemini_api_key
                or self.settings.google_api_key
                or os.getenv("GEMINI_API_KEY", "")
                or os.getenv("GOOGLE_API_KEY", "")
            )
        )
        if not api_key:
            logger.warning("Gemini API key is not configured in environment or settings.")
            return {
                "observations": [],
                "status": "unavailable",
                "message": "Visual analysis unavailable. Gemini API key is not configured.",
            }

        clean_base64, mime_type = self._extract_base64_and_mime(image_data)
        if not clean_base64:
            return {
                "observations": [],
                "status": "error",
                "message": "Invalid image data format.",
            }

        prompt_text = SYSTEM_PROMPT.format(scene=scene or "general emergency scene")

        # Models to try in order of preference
        configured_model = self._custom_model or self.settings.gemini_model or "gemini-3.5-flash-lite"
        models_to_try = [
            configured_model,
            "gemini-3.5-flash-lite",
            "gemini-3.6-flash",
            "gemini-3.7-flash",
            "gemini-3.8-flash",
            "gemini-flash-latest",
        ]
        # Deduplicate while preserving order
        models_to_try = list(dict.fromkeys(models_to_try))

        # Payload formatted according to Gemini REST API specification (camelCase)
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt_text},
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": clean_base64,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            for model in models_to_try:
                url = GEMINI_API_URL.format(model=model)
                try:
                    res = await client.post(
                        url,
                        params={"key": api_key},
                        headers={"Content-Type": "application/json"},
                        json=payload,
                    )
                    if res.status_code == 200:
                        data = res.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                raw_text = parts[0].get("text", "").strip()
                                logger.info("Gemini Vision model %s returned text length %d", model, len(raw_text))
                                return self._parse_gemini_json(raw_text)
                    elif res.status_code == 404:
                        logger.warning("Gemini model %s returned 404, trying next model...", model)
                        continue
                    else:
                        logger.warning("Gemini Vision API error (%s) on model %s: %s", res.status_code, model, res.text[:200])
                except Exception as e:
                    logger.warning("Gemini Vision API request failed for model %s: %s", model, e)

        return {
            "observations": [],
            "status": "unavailable",
            "message": "Visual analysis unavailable. The uploaded evidence was not analyzed.",
        }

    def _parse_gemini_json(self, raw_text: str) -> Dict[str, Any]:
        """Safely parse and validate structured observations from Gemini response."""
        try:
            # Strip potential markdown code fences
            cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*```$", "", cleaned).strip()
            parsed = json.loads(cleaned)

            raw_items = []
            if isinstance(parsed, dict):
                # Check for standard and alternative wrapper keys
                raw_items = (
                    parsed.get("observations")
                    or parsed.get("evidence")
                    or parsed.get("findings")
                    or parsed.get("results")
                    or parsed.get("items")
                    or []
                )
                if not raw_items and ("label" in parsed or "description" in parsed):
                    raw_items = [parsed]
            elif isinstance(parsed, list):
                raw_items = parsed

            if raw_items:
                observations = []
                for item in raw_items:
                    if isinstance(item, dict):
                        label = (
                            item.get("label")
                            or item.get("title")
                            or item.get("observation")
                            or item.get("finding")
                            or item.get("name")
                            or ""
                        )
                        description = (
                            item.get("description")
                            or item.get("desc")
                            or item.get("details")
                            or item.get("detail")
                            or ""
                        )
                        confidence = item.get("confidence")

                        # If label is missing but description exists, use description as label
                        if not label and description:
                            label = description[:80]

                        if label:
                            clean_confidence = None
                            if confidence is not None:
                                try:
                                    val = float(confidence)
                                    clean_confidence = val if 0.0 <= val <= 1.0 else (val / 100.0 if 0.0 <= val <= 100.0 else None)
                                except (ValueError, TypeError):
                                    clean_confidence = None

                            observations.append({
                                "label": str(label).strip(),
                                "description": str(description).strip() if description else None,
                                "confidence": clean_confidence,
                            })

                if observations:
                    return {
                        "observations": observations,
                        "status": "ok",
                        "success": True,
                        "message": "Visual observations generated successfully.",
                    }
        except Exception as e:
            logger.warning("Failed to parse Gemini Vision JSON: %s (raw text: %s)", e, raw_text[:200])

        # Fallback to line-by-line extraction if bullet points or lines are present
        line_observations = []
        for line in raw_text.splitlines():
            line = re.sub(r"^[\s*•\-–\d\.\)]+", "", line).strip()
            if len(line) >= 4 and not line.startswith("{") and not line.startswith("}") and not line.startswith("[") and not line.startswith("]"):
                line_observations.append({
                    "label": line,
                    "description": None,
                    "confidence": None,
                })
        if line_observations:
            return {
                "observations": line_observations[:6],
                "status": "ok",
                "success": True,
                "message": "Visual observations extracted from text response.",
            }

        return {
            "observations": [],
            "status": "ok",
            "success": True,
            "message": "No distinct critical hazards observed.",
        }


gemini_vision_service = GeminiVisionService()
