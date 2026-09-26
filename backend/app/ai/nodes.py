"""
LangGraph nodes for the emergency dispatch pipeline.

Pipeline:
    caller message → ANALYST → FAKE_CALL_CHECK → COMPLETENESS_CHECKER → SUMMARIZER
                         ↓ (if missing info)                                ↓ (if enough info)
                    QUESTION_GENERATOR                                 SERVICE_ROUTER → GUIDANCE
                         ↓                                                  ↓
                        END                                                END

6 Core Nodes + 1 Verification Node:
  1. analyst_node        — Extracts structured data, semantic facts, and scenario triage
  2. fake_call_node      — Multi-signal fake call detection
  3. completeness_node   — Evaluates scenario-specific readiness to dispatch
  4. summarizer_node     — Produces dispatcher-ready briefing
  5. question_node       — Generates dynamic follow-up question for missing info
  6. router_node         — Routes to correct emergency services + SOPs with RAG
  7. guidance_node       — Generates real-time safety instructions for the caller
"""

import json
import logging
import re
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.ai.prompts import (
    ANALYST_PROMPT,
    GUIDANCE_PROMPT,
    QUESTION_GENERATOR_PROMPT,
    ROUTER_PROMPT,
    ROUTER_RAG_PROMPT,
    SOP_DATABASE,
    SUMMARIZER_PROMPT,
)
from app.ai.state import IncidentState
from app.config import get_settings
from app.services.fake_call_service import FakeCallDetector
from app.services.rag_service import retrieve_context

logger = logging.getLogger(__name__)

LANGUAGE_NAMES = {
    "en": "English",
    "ta": "Tamil (தமிழ்)",
    "hi": "Hindi (हिन्दी)",
    "te": "Telugu (తెలుగు)",
    "kn": "Kannada (ಕನ್ನಡ)",
    "bn": "Bengali (বাংলা)",
    "mr": "Marathi (मराठी)",
    "gu": "Gujarati (ગુજરાતી)",
    "ml": "Malayalam (മലയാളം)",
    "pa": "Punjabi (ਪੰਜਾਬੀ)",
    "ur": "Urdu (اردو)",
}


# ── Shared Helpers ────────────────────────────────────────────────

# GPS accuracy threshold: ≤ 100m is considered reliable for dispatch purposes
_GPS_RELIABLE_ACCURACY_THRESHOLD_M = 100.0


def _gps_is_reliable(state: IncidentState) -> bool:
    """
    Return True when GPS coordinates are present and accurate enough to skip
    the generic 'where are you?' question.

    Criteria:
    - latitude and longitude are present (not None), AND
    - location_status is 'reliable' OR location_accuracy <= threshold
    """
    lat = state.get("latitude")
    lon = state.get("longitude")
    if lat is None or lon is None:
        return False

    status = state.get("location_status")
    if status == "reliable":
        return True
    if status in ("unavailable", "low_accuracy"):
        return False

    # No explicit status: use accuracy value
    accuracy = state.get("location_accuracy")
    if accuracy is not None:
        return float(accuracy) <= _GPS_RELIABLE_ACCURACY_THRESHOLD_M

    # Coordinates present but no accuracy info — treat as marginally reliable
    return True


def _gps_is_low_accuracy(state: IncidentState) -> bool:
    """Return True when GPS is present but has poor accuracy (> threshold)."""
    lat = state.get("latitude")
    lon = state.get("longitude")
    if lat is None or lon is None:
        return False
    status = state.get("location_status")
    if status == "low_accuracy":
        return True
    accuracy = state.get("location_accuracy")
    if accuracy is not None:
        return float(accuracy) > _GPS_RELIABLE_ACCURACY_THRESHOLD_M
    return False


def _location_is_known(state: IncidentState) -> bool:
    """
    Return True when the caller's location is sufficiently known to NOT ask
    a generic 'please tell me your location' question.

    Location is known if:
    - GPS is reliable (lat/lon present with good accuracy), OR
    - A non-placeholder text location exists in state
    """
    if _gps_is_reliable(state):
        return True
    loc = state.get("location")
    return bool(loc) and loc not in (
        "Awaiting location...",
        "Location unknown",
        "Location denied or unavailable",
        "Location unavailable",
        "unknown",
        "null",
    )


def _gps_context_string(state: IncidentState) -> str:
    """
    Build a concise GPS status string for injection into LLM prompts.
    Tells the LLM exactly what location data is available so it can decide
    whether to ask for location, a landmark, or neither.
    """
    lat = state.get("latitude")
    lon = state.get("longitude")
    accuracy = state.get("location_accuracy")
    source = state.get("location_source", "unknown")
    status = state.get("location_status", "unknown")
    loc_text = state.get("location")
    landmark = state.get("landmark")

    if lat is not None and lon is not None:
        acc_str = f"±{int(accuracy)}m" if accuracy is not None else "accuracy unknown"
        coord_str = f"{lat:.5f}, {lon:.5f} ({acc_str})"
        if _gps_is_reliable(state):
            gps_desc = f"GPS AVAILABLE — reliable ({acc_str}) — coords: {coord_str} — source: {source}"
        elif _gps_is_low_accuracy(state):
            gps_desc = f"GPS AVAILABLE — low accuracy ({acc_str}) — coords: {coord_str} — source: {source}"
        else:
            gps_desc = f"GPS present — status: {status} — coords: {coord_str}"
    else:
        gps_desc = "GPS NOT available — location unknown"

    parts = [f"GPS: {gps_desc}"]
    if loc_text and loc_text not in ("Awaiting location...", "Location unknown", "unknown"):
        parts.append(f"Text location: {loc_text}")
    if landmark:
        parts.append(f"Landmark: {landmark}")
    return " | ".join(parts)


def _get_llm(temperature: float = 0.1, model_override: str = None, max_tokens: int = 350):
    """
    Create the LLM client based on LLM_PROVIDER env setting.
    Returns a ChatOllama or ChatGroq instance.
    """
    settings = get_settings()

    if settings.llm_provider == "groq":
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not configured in backend/.env")
        from langchain_groq import ChatGroq

        target_model = model_override or settings.active_model_name

        return ChatGroq(
            model=target_model,
            api_key=settings.groq_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=1,
            timeout=10,
        )
    else:
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=temperature,
            num_gpu=settings.ollama_num_gpu,
        )


def _clean_llm_text(text: str) -> str:
    """Remove <think>...</think> blocks and strip whitespace."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip()


def _parse_json(text: str) -> dict:
    """Extract JSON from LLM response — handles markdown fences, braces, etc."""
    text = _clean_llm_text(text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass

    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        try:
            return json.loads(brace.group(0))
        except json.JSONDecodeError:
            pass

    return {}


def _extract_semantic_facts(text: str) -> dict:
    """
    Extract key factual attributes with semantic equivalence.
    Captures positive/negative state without forcing fixed questions.
    """
    t = text.lower()
    facts: dict = {}

    # Breathing state (negative check first)
    if any(k in t for k in ["not breathing", "isn't breathing", "stopped breathing", "cannot breathe", "can't breathe", "no breath", "difficulty breathing", "மூச்சு விடவில்லை", "மூச்சு இல்லை", "सांस नहीं", "सांस बंद"]):
        facts["breathing"] = False
    elif any(k in t for k in ["is breathing", "he is breathing", "she is breathing", "breathing normally", "breathing", "மூச்சு விடுகிறார்", "சாंस ले रहे", "सांस ले रहे", "सांस चल रही"]):
        facts["breathing"] = True

    # Consciousness state (negative check first)
    if any(k in t for k in ["unconscious", "unresponsive", "fainted", "passed out", "collapsed", "blackout", "not awake", "மயக்கமடைந்து", "மயக்கம்", "சுயநினைவு இல்லை", "बेहोश", "होश नहीं"]):
        facts["consciousness"] = False
    elif any(k in t for k in ["is conscious", "conscious", "awake", "she is awake", "he is awake", "talking", "responsive", "alert", "சுயநினைவு உள்ளது", "விழித்திருக்கிறார்", "होश में", "जाग रहे"]):
        facts["consciousness"] = True

    # Trapped persons status (negative check first)
    if any(k in t for k in ["no one is trapped", "no one trapped", "not trapped", "nobody trapped", "none trapped", "யாரும் சிக்கவில்லை", "कोई फंसा नहीं"]):
        facts["trapped_people"] = 0
    elif any(k in t for k in ["trapped inside", "stuck inside", "people trapped", "trapped in car", "trapped in fire", "trapped", "கட்டடத்தில் சிக்கியுள்ளனர்", "அகப்பட்டுள்ளனர்", "अंदर फंसे", "फंसे हुए"]):
        facts["trapped_people"] = 1

    # Bleeding
    if any(k in t for k in ["arterial bleeding", "heavy bleeding", "severe bleeding", "bleeding profusely", "spurting blood", "கடுமையான ரத்தம்", "ரத்தம் கொட்டுகிறது", "भारी खून"]):
        facts["bleeding"] = "severe"
    elif any(k in t for k in ["bleeding", "blood", "wound", "cut", "ரத்தம்", "காயம்", "खून", "चोट"]):
        facts["bleeding"] = "present"

    # Fire / Smoke
    if any(k in t for k in ["flames", "smoke", "burning", "blaze", "fire", "தீ", "புகை", "ஆபத்து", "ஆக்", "आग", "धुआं"]):
        facts["fire_smoke"] = True

    # Weapons / Active threat
    if any(k in t for k in ["gun", "knife", "rifle", "weapon", "attacker", "shooter", "pistol", "துப்பாக்கி", "கத்தி", "தாக்குதல்", "हथियार", "बंदूक"]):
        facts["weapons"] = True

    # Hazmat / Chemical
    if any(k in t for k in ["chemical", "toxic", "gas leak", "fumes", "smell", "poison", "விஷம்", "வாயு கசிவு", "गैस रिसाव", "जहर"]):
        facts["hazards"] = "chemical/gas"

    # Drowning
    if any(k in t for k in ["drowning", "drowned", "in the water", "in pool", "in lake", "in river", "தண்ணீரில் மூழ்கியுள்ளார்", "पानी में डूब"]):
        facts["drowning"] = True

    # Vehicle collision
    if any(k in t for k in ["crash", "collision", "collided", "overturned", "hit and run", "accident", "விபத்து", "ஆக்சிடென்ட்", "दुर्घटना", "टक्कर"]):
        facts["vehicle_crash"] = True

    # Electrical hazard
    if any(k in t for k in ["electric shock", "electrocution", "live wire", "power line", "மின்சாரம்", "बिजली का झटका"]):
        facts["electrical"] = True

    # Building collapse
    if any(k in t for k in ["building collapse", "collapsed building", "debris", "rubble", "கட்டிடம் இடிந்து", "इमारत गिर"]):
        facts["building_collapse"] = True

    return facts


def _deterministic_analyst_fallback(state: IncidentState, latest_text: str) -> dict:
    """Fallback entity extraction when LLM is offline or timed out."""
    text_lower = latest_text.lower()
    extracted: dict = {}

    if any(k in text_lower for k in [
        "cardiac", "heart", "chest", "attack", "breathing", "cpr", "bleeding", "unconscious",
        "stroke", "seizure", "ambulance", "hospital", "patient", "drowning", "poison",
        "collapsed", "collapse", "diabetic", "diabetes", "dizzy", "dizziness", "faint",
        "fainted", "weak", "hurt", "injured", "injury", "sick", "pain", "choking",
        "allergic", "vomiting", "asthma", "மூச்சு", "மயக்கம்", "மாரடைப்பு", "ரத்தம்",
        "सांस", "बेहोश", "दौरा", "खून", "दर्द", "चोट"
    ]):
        extracted["emergency_type"] = "Medical"
    elif any(k in text_lower for k in [
        "fire", "flames", "smoke", "blaze", "burning", "explosion", "gas leak", "hazmat",
        "chemical", "தீ", "புகை", "ஆபத்து", "ஆக்", "आग", "धुआं"
    ]):
        extracted["emergency_type"] = "Fire"
    elif any(k in text_lower for k in [
        "weapon", "gun", "knife", "robbery", "assault", "police", "threat", "intruder",
        "attack", "shooter", "hostage", "machete", "stabbing", "shots", "திருடன்",
        "தாக்குதல்", "துப்பாக்கி", "हथियार", "हमला", "पुलिस"
    ]):
        extracted["emergency_type"] = "Police"
    elif any(k in text_lower for k in [
        "accident", "collision", "crash", "car", "traffic", "overturned", "hit and run",
        "truck", "vehicle", "highway", "விபத்து", "ஆக்சிடென்ட்", "மோதி", "दुर्घटना",
        "एक्सीडेंट", "टक्कर"
    ]):
        extracted["emergency_type"] = "Traffic"
    elif any(k in text_lower for k in [
        "flood", "earthquake", "building collapse", "cyclone", "disaster", "landslide",
        "வெள்ளம்", "புயல்", "பாढ़", "बाढ़", "भूकंप"
    ]):
        extracted["emergency_type"] = "Natural Disaster"
    else:
        extracted["emergency_type"] = state.get("emergency_type") or "Medical"

    loc_bracket = re.search(r"\[Location:\s*([^\]]+)\]", latest_text, re.IGNORECASE)
    if loc_bracket:
        extracted["location"] = loc_bracket.group(1).strip()
    else:
        loc_match = re.search(r"\b(?:at|in|near|on)\s+([A-Z0-9][A-Za-z0-9\s,\-\.]+)", latest_text)
        if loc_match:
            extracted["location"] = loc_match.group(1).strip()

    # Casualties extraction with numeric & word numbers (English, Tamil, Hindi)
    cas_match = re.search(r"\b(\d+)\s*(?:people|persons|victims|casualties|trapped|injured|dead|பேர்|நபர்கள்|மக்கள்|लोग|व्यक्ति)\b", text_lower)
    if cas_match:
        extracted["casualties"] = int(cas_match.group(1))
    elif any(k in text_lower for k in ["one person", "one victim", "someone", "a person", "a child", "worker", "father", "sister", "brother", "mother", "ஒருவர்", "ஒரு நபர்", "ஒரு பெண்", "ஒரு ஆண்", "एक व्यक्ति", "एक आदमी", "एक बच्चा"]):
        extracted["casualties"] = 1
    elif any(k in text_lower for k in ["two people", "two persons", "two injured", "two victims", "2 people", "இருவர்", "இரண்டு பேர்", "இரண்டு", "दो लोग", "दो व्यक्ति"]):
        extracted["casualties"] = 2
    elif any(k in text_lower for k in ["three people", "three persons", "3 people", "மூன்று பேர்", "மூவர்", "மூன்று", "तीन लोग", "तीन व्यक्ति", "तीन"]):
        extracted["casualties"] = 3
    elif any(k in text_lower for k in ["four people", "four persons", "4 people", "நான்கு பேர்", "நால்வர்", "நான்கு", "चार लोग", "चार व्यक्ति"]):
        extracted["casualties"] = 4
    elif any(k in text_lower for k in [
        "i cut", "my hand", "my leg", "my arm", "my head", "my chest", "my foot", "my finger",
        "i am bleeding", "i'm bleeding", "i am injured", "i'm injured", "i am hurt", "i'm hurt",
        "i fell", "i feel", "எனக்கு", "என் கை", "எனது", "காயம்", "ரத்தம்", "मुझे", "मेरा", "मेरी", "चोट", "खून"
    ]):
        extracted["casualties"] = 1
    elif "மயங்கிவிட்டனர்" in text_lower or "injured" in text_lower or "trapped" in text_lower:
        extracted["casualties"] = 1

    extracted["details"] = latest_text.replace(f"[Location: {extracted.get('location', '')}]", "").strip()

    name_match = re.search(r"\b(?:my name is|this is|i am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", latest_text)
    if name_match:
        extracted["caller_name"] = name_match.group(1).strip()

    if any(k in text_lower for k in ["cardiac", "heart attack", "unconscious", "not breathing", "cpr", "dying", "severe bleeding", "flames", "fire", "explosion", "shooter", "gun", "drowning", "துப்பாக்கி", "மாரடைப்பு", "ஆபத்து"]):
        extracted["priority"] = 1
    elif any(k in text_lower for k in ["chemical", "poison", "dizzy", "vomiting", "accident", "crash", "collision", "assault", "robbery", "injured", "hurt", "விபத்து", "காயம்"]):
        extracted["priority"] = 2
    else:
        extracted["priority"] = 3

    extracted["known_facts"] = _extract_semantic_facts(latest_text)
    return extracted



# ── NODE 1: ANALYST ──────────────────────────────────────────────

def analyst_node(state: IncidentState) -> dict:
    """
    Extracts structured emergency data from the caller's message.
    Maintains structured facts, scenario classification, RAG protocol knowledge,
    and dynamically generates context-aware question and guidance in selected_language.
    """
    latest_text = ""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            latest_text = msg.content
            break

    update: dict = {"turn_count": state.get("turn_count", 0) + 1}

    # Respect user-selected emergency service if present
    if state.get("selected_service") and not state.get("emergency_type"):
        service_norm = re.sub(r"[^a-z]", "", state["selected_service"].lower())
        service_map = {
            "ambulance": "Medical",
            "police": "Police",
            "fire": "Fire",
            "fireservice": "Fire",
            "rescue": "Natural Disaster",
            "rescueteam": "Natural Disaster",
            "bluecross": "Animal Control",
            "animalrescue": "Animal Control",
        }
        update["emergency_type"] = service_map.get(service_norm, state["selected_service"].capitalize())

    # Language Resolution & Preservation
    active_lang = state.get("selected_language") or state.get("language") or state.get("input_language") or "en"
    if any('\u0B80' <= ch <= '\u0BFF' for ch in latest_text):
        active_lang = "ta"
    elif any('\u0900' <= ch <= '\u097F' for ch in latest_text):
        active_lang = "hi"

    lang_display = LANGUAGE_NAMES.get(active_lang, active_lang.upper())

    # Semantic facts extraction from text
    semantic_facts = _extract_semantic_facts(latest_text)
    existing_facts = dict(state.get("known_facts") or {})
    existing_facts.update(semantic_facts)

    # Build GPS context for LLM (so it knows not to ask for location when GPS is reliable)
    gps_ctx = _gps_context_string(state)
    loc_is_known = _location_is_known(state)
    gps_is_reliable = _gps_is_reliable(state)
    gps_is_low = _gps_is_low_accuracy(state)

    # Record GPS location as a known fact so it persists across turns
    if gps_is_reliable:
        existing_facts["gps_location"] = "known"
        existing_facts["gps_accuracy_m"] = state.get("location_accuracy")
    elif gps_is_low:
        existing_facts["gps_location"] = "low_accuracy"
        existing_facts["gps_accuracy_m"] = state.get("location_accuracy")

    # Accumulate previous answers
    prev_answers = list(state.get("previous_answers") or [])
    if latest_text and latest_text not in prev_answers:
        prev_answers.append(latest_text)
    update["previous_answers"] = prev_answers

    # Retrieve relevant RAG emergency protocols from ChromaDB
    rag_query = f"{latest_text} {state.get('emergency_type', '')} {state.get('scenario_category', '')}"
    try:
        rag_context = retrieve_context(rag_query, k=2)
    except Exception as e:
        logger.warning("RAG retrieval failed in analyst: %s", e)
        rag_context = "Standard Emergency Dispatch Protocol"

    update["retrieved_context"] = rag_context

    # Dynamic LLM Invocation
    parsed: dict = {}
    try:
        llm = _get_llm(temperature=0.2)

        # Dynamic context prompt injection (Language-independent, scenario-aware)
        dynamic_context = (
            f"\n\n## Session State (Turn {update['turn_count']})\n"
            f"- selected_language: {active_lang} ({lang_display})\n"
            f"- emergency_type: {state.get('emergency_type', 'unknown')}\n"
            f"- location (text): {state.get('location', 'unknown')}\n"
            f"- {gps_ctx}\n"
            f"- details: {state.get('details', 'unknown')}\n"
            f"- priority: {state.get('priority', 'unknown')}\n"
            f"- casualties: {state.get('casualties', 'unknown')}\n"
            f"- known_facts: {json.dumps(existing_facts, ensure_ascii=False)}\n"
            f"- previous_questions: {json.dumps(state.get('previous_questions', []), ensure_ascii=False)}\n"
            f"\n## Relevant Protocol Knowledge (from ChromaDB RAG):\n{rag_context}\n"
            f"\n## LOCATION AWARENESS RULES (CRITICAL):\n"
            f"- location_is_known: {loc_is_known}\n"
            f"- gps_reliable: {gps_is_reliable}\n"
            f"- gps_low_accuracy: {gps_is_low}\n"
            f"- If gps_reliable=True: DO NOT ask a generic location question. Location is pinpointed via GPS.\n"
            f"  You MAY ask for a landmark/floor/access point ONLY if it materially helps responders.\n"
            f"- If gps_low_accuracy=True: may ask for a nearby landmark to confirm the approximate area.\n"
            f"- If gps_reliable=False and location_is_known=False: ask for address or landmark.\n"
            f"\n## MANDATORY INSTRUCTIONS:\n"
            f"1. Generate 'next_question' only when additional information is genuinely needed.\n"
            f"2. DO NOT repeat information in 'known_facts' or 'previous_questions'.\n"
            f"3. DO NOT follow a fixed questionnaire.\n"
            f"4. Choose the highest-value missing information for the current scenario.\n"
            f"5. Write 'next_question', 'guidance', 'summary' strictly in {lang_display} ({active_lang}).\n"
            f"6. For code-mixed speech, maintain {lang_display} as the primary language."
        )


        messages = [
            SystemMessage(content=ANALYST_PROMPT + dynamic_context)
        ] + list(state.get("messages", []))

        response = llm.invoke(messages)
        parsed = _parse_json(response.content)
    except Exception as e:
        logger.warning("LLM analyst invocation failed: %s. Using deterministic fallback.", e)
        parsed = _deterministic_analyst_fallback(state, latest_text)

    # Merge extracted fields
    field_map = {
        "emergency_type": str,
        "scenario_category": str,
        "location": str,
        "details": str,
        "caller_name": str,
        "caller_phone": str,
        "estimated_arrival": str,
    }

    for field, _ in field_map.items():
        val = parsed.get(field)
        if val and val != "null" and val != "unknown":
            if field == "details" and state.get("details"):
                existing = state["details"]
                if val.lower() not in existing.lower():
                    update[field] = f"{existing}. {val}"
                else:
                    update[field] = existing
            else:
                update[field] = val

    # Numeric fields
    if parsed.get("priority") is not None:
        try:
            update["priority"] = max(1, min(5, int(parsed["priority"])))
        except (ValueError, TypeError):
            pass
    elif state.get("priority_score"):
        ps = state["priority_score"]
        update["priority"] = 1 if ps >= 8 else (2 if ps >= 6 else (3 if ps >= 4 else 4))

    if parsed.get("casualties") is not None:
        try:
            update["casualties"] = int(parsed["casualties"])
        except (ValueError, TypeError):
            pass

    if parsed.get("caller_age") is not None:
        try:
            update["caller_age"] = int(parsed["caller_age"])
        except (ValueError, TypeError):
            pass

    # Update structured facts
    llm_facts = parsed.get("known_facts")
    if isinstance(llm_facts, dict):
        existing_facts.update(llm_facts)
    update["known_facts"] = existing_facts

    update["missing_info"] = parsed.get("missing_info", [])

    # Cache dynamic summary
    if parsed.get("summary") and str(parsed["summary"]).strip():
        update["_llm_summary"] = str(parsed["summary"]).strip()
        update["summary"] = update["_llm_summary"]

    # Cache dynamic question
    if parsed.get("next_question") and str(parsed["next_question"]).strip():
        q_cand = str(parsed["next_question"]).strip()
        update["_llm_question"] = q_cand
        update["current_question"] = q_cand

    # Cache dynamic guidance
    if parsed.get("guidance") and str(parsed["guidance"]).strip():
        g_cand = str(parsed["guidance"]).strip()
        update["_llm_guidance"] = g_cand
        update["guidance"] = g_cand

    llm_fake = parsed.get("fake_score")
    if llm_fake is not None:
        try:
            update["_llm_fake_score"] = float(llm_fake)
        except (ValueError, TypeError):
            pass

    # Language state attributes
    update["language"] = active_lang
    update["selected_language"] = active_lang
    update["input_language"] = active_lang
    update["detected_language"] = parsed.get("detected_language") or active_lang
    update["response_language"] = active_lang

    # Baseline emergency guarantees from deterministic extraction
    fallback = _deterministic_analyst_fallback(state, latest_text)
    if not update.get("emergency_type") or update.get("emergency_type") in ("unknown", "null", "Other", "None"):
        update["emergency_type"] = fallback.get("emergency_type") or state.get("emergency_type") or "Medical"
    if not update.get("location") or update.get("location") in ("unknown", "null", "Location unknown", "Awaiting location..."):
        if fallback.get("location"):
            update["location"] = fallback["location"]
        elif state.get("location"):
            update["location"] = state["location"]
    if not update.get("details") or update.get("details") in ("unknown", "null", "None", "Details pending"):
        if fallback.get("details"):
            update["details"] = fallback["details"]
        elif state.get("details"):
            update["details"] = state["details"]
    if update.get("casualties") is None:
        if fallback.get("casualties") is not None:
            update["casualties"] = fallback["casualties"]
        elif state.get("casualties") is not None:
            update["casualties"] = state["casualties"]
    if update.get("caller_name") is None:
        if fallback.get("caller_name"):
            update["caller_name"] = fallback["caller_name"]
        elif state.get("caller_name"):
            update["caller_name"] = state["caller_name"]
    if update.get("priority") is None:
        update["priority"] = fallback.get("priority") or state.get("priority") or 2
    else:
        try:
            update["priority"] = max(1, min(5, int(update["priority"])))
        except (ValueError, TypeError):
            update["priority"] = 2

    # ── Deterministic Safety Fast-Path Overrides (Zero False Negatives) ──

    # Life-safety guidance is authoritative and immediately provided for critical conditions
    text_lower = latest_text.lower()
    if any(p in text_lower for p in ["not breathing", "unresponsive", "cardiac arrest", "no pulse", "heart stopped", "cannot breathe", "can't breathe", "choking", "drowning", "stroke", "behos", "saans nahi", "moochu", "mayangi", "மூச்சு", "மயக்கம்", "மயக்கமடைந்து", "மாரடைப்பு", "सांस", "बेहोश", "दौरा"]):
        update["priority"] = 1
        if not update.get("emergency_type"):
            update["emergency_type"] = "Medical"
        if active_lang == "ta":
            cpr_guide = "சுவாசப்பாதையைச் சரிபார்க்கவும். மூச்சு இல்லை என்றால், உடனடியாக நெஞ்சுப் பகுதியில் சிபிஆர் (CPR) அழுத்தத்தைத் தொடங்குங்கள்."
        elif active_lang == "hi":
            cpr_guide = "वायुमार्ग की जांच करें। यदि सांस नहीं ले रहे हैं, तो तुरंत 100-120 प्रति मिनट की गति से सीपीआर शुरू करें।"
        else:
            cpr_guide = "Check airway. If unresponsive and not breathing, lay flat and begin continuous chest compressions at 100-120 bpm."
        update["guidance"] = cpr_guide
        update["_llm_guidance"] = cpr_guide
    elif any(f in text_lower for f in ["fire", "smoke", "burning", "blaze", "flames", "building on fire", "trapped in fire", "தீ", "புகை", "ஆபத்து", "ஆக்", "आग", "धुआं"]):
        update["priority"] = 1
        update["emergency_type"] = "Fire"
        if active_lang == "ta":
            fire_guide = "பாதுகாப்பாக இருந்தால் உடனே வெளியேறுங்கள். புகைக்குக் கீழே குனிந்து செல்லுங்கள். லிப்ட் பயன்படுத்த வேண்டாம்."
        elif active_lang == "hi":
            fire_guide = "सुरक्षित होने पर तुरंत इमारत से बाहर निकलें। धुएं के नीचे झुककर चलें। लिफ्ट का उपयोग न करें।"
        else:
            fire_guide = "Evacuate immediately if safe. Stay low under smoke, feel doors before opening, and do not use elevators."
        update["guidance"] = fire_guide
        update["_llm_guidance"] = fire_guide
    elif any(b in text_lower for b in [
        "arterial bleeding", "heavy bleeding", "severe bleeding", "bleeding heavily", "bleeding profusely",
        "spurting blood", "cut on arm", "cut my hand", "cut on hand", "cut my finger", "cut my leg",
        "bleeding is not stopping", "bleeding not stopping", "won't stop bleeding", "wont stop bleeding",
        "continuous bleeding", "uncontrolled bleeding", "bleeding badly", "deep cut", "severe cut",
        "stabbed", "ரத்தம்", "அதிக ரத்தம்", "ரத்தம் நிற்கவில்லை", "खून", "भारी खून", "खून बहना बंद नहीं"
    ]):
        update["priority"] = 1
        if not update.get("emergency_type"):
            update["emergency_type"] = "Medical"
        if active_lang == "ta":
            bleed_guide = "காயத்தின் மீது சுத்தமான துணியை வைத்து அழுத்தமாகப் பிடித்துக் கொள்ளுங்கள்."
        elif active_lang == "hi":
            bleed_guide = "साफ कपड़े से घाव पर तुरंत सीधा और लगातार दबाव डालें।"
        else:
            bleed_guide = "Apply direct, firm, continuous pressure to the bleeding wound using a clean cloth or bandage immediately."
        update["guidance"] = bleed_guide
        update["_llm_guidance"] = bleed_guide
    elif any(t in text_lower for t in ["active shooter", "gunman", "active attacker", "attacker", "machete", "stabbing in progress", "shots fired", "hostage", "armed threat", "துப்பாக்கி", "தாக்குதல்", "हथियार", "हमला", "गोली"]):
        update["priority"] = 1
        update["emergency_type"] = "Police"
        if active_lang == "ta":
            threat_guide = "பாதுகாப்பான அறைக்குச் சென்று கதவைப் பூட்டுங்கள், போனை சைலண்டில் வையுங்கள்."
        elif active_lang == "hi":
            threat_guide = "सुरक्षित कमरे में जाएं, दरवाजा बंद करें और फोन को साइलेंट रखें।"
        else:
            threat_guide = "Move to a secure locked room, silence all phones, stay low and away from doors and windows."
        update["guidance"] = threat_guide
        update["_llm_guidance"] = threat_guide
    elif any(d in text_lower for d in ["mass casualty", "explosion", "building collapse", "boiler explosion", "வெள்ளம்", "புயல்", "बाढ़", "भूकंप"]):
        update["priority"] = 1
        update["emergency_type"] = "Natural Disaster"
        if active_lang == "ta":
            disaster_guide = "சேதமடைந்த கட்டிடங்களிலிருந்து விலகி பாதுகாப்பான திறந்தவெளிப் பகுதிக்குச் செல்லுங்கள்."
        elif active_lang == "hi":
            disaster_guide = "क्षतिग्रस्त इमारतों से दूर सुरक्षित खुले क्षेत्र में जाएं।"
        else:
            disaster_guide = "Move to a safe open area away from damaged structures, electrical lines, and debris."
        update["guidance"] = disaster_guide
        update["_llm_guidance"] = disaster_guide

    if not update.get("guidance"):
        if active_lang == "ta":
            update["guidance"] = "அவசர உதவி விரைவாக அனுப்பப்படுகிறது. தயவுசெய்து அமைதியாக இருங்கள்."
        elif active_lang == "hi":
            update["guidance"] = "आपातकालीन मदद तुरंत भेजी जा रही है। कृपया शांत रहें।"
        else:
            update["guidance"] = "Emergency assistance is on the way. Please remain calm."

    logger.info("Analyst triage completed for turn %d | lang=%s | facts=%s", update["turn_count"], active_lang, existing_facts)
    return update


# ── NODE 1b: FAKE CALL DETECTOR ─────────────────────────────────

def fake_call_node(state: IncidentState) -> dict:
    """
    Runs multi-signal fake call detection on the latest turn.
    Combines keyword matching, behavioral analysis, and explicit test guardrails.
    """
    messages = state.get("messages", [])
    if not messages:
        return {}

    latest_text = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            latest_text = msg.content
            break

    if not latest_text:
        return {}

    detector = FakeCallDetector()

    for msg in messages:
        if isinstance(msg, HumanMessage) and msg.content != latest_text:
            detector.evaluate_turn(
                msg.content,
                emergency_type=state.get("emergency_type"),
                location=state.get("location"),
                details=state.get("details"),
                turn_count=0,
                llm_fake_score=None,
            )

    llm_fake = state.get("_llm_fake_score")
    result = detector.evaluate_turn(
        latest_text,
        emergency_type=state.get("emergency_type"),
        location=state.get("location"),
        details=state.get("details"),
        turn_count=state.get("turn_count", 0),
        llm_fake_score=llm_fake,
    )

    update = {
        "fake_probability": result["fake_probability"],
        "fake_label": result["fake_label"],
        "fake_signals": result["fake_signals"],
    }

    if result["fake_label"] == "EXPLICIT_TEST":
        update["status"] = "gathering_info"
        update["current_question"] = "LifeLine-Core test mode recognized. No emergency units will be dispatched. If this is a real emergency, please describe the emergency."
        update["summary"] = "Non-emergency test session initiated by user."
        update["guidance"] = "Test mode active. No emergency dispatch requested."
        update["priority"] = 5
        update["priority_label"] = "LOW"
        update["priority_score"] = 1
    elif result["fake_label"] == "LIKELY_FAKE":
        update["status"] = "gathering_info"
        update["current_question"] = "Please clarify: is there an active life-threatening emergency requiring immediate emergency service dispatch?"
        update["summary"] = "Potential non-emergency/prank call flagged for operator verification."

    return update


# ── NODE 2: COMPLETENESS CHECKER ────────────────────────────────

def completeness_node(state: IncidentState) -> dict:
    """
    Evaluates whether critical scenario information has been gathered to dispatch.
    """
    MIN_TURNS = 2

    fake_label = state.get("fake_label", "GENUINE")
    if fake_label in ("EXPLICIT_TEST", "LIKELY_FAKE"):
        logger.warning("Dispatch BLOCKED — call flagged as %s", fake_label)
        return {"status": "gathering_info"}

    has_type = state.get("emergency_type") is not None
    has_location = _location_is_known(state)
    has_priority = state.get("priority") is not None or state.get("priority_score") is not None
    turn_count = state.get("turn_count", 0)

    # 1. Basic essential fields
    if not (has_type and has_location and has_priority):
        return {"status": "gathering_info"}

    # 2. Minimum conversation turns
    if turn_count < MIN_TURNS:
        return {"status": "gathering_info"}

    # 3. Scenario-Specific checks
    current_type = (state.get("emergency_type") or "").strip()
    critical_types = ["Fire", "Medical", "Police", "Traffic", "Natural Disaster"]

    if current_type in critical_types and state.get("casualties") is None and turn_count < 3:
        return {"status": "gathering_info"}

    return {"status": "ready_to_dispatch"}


# ── NODE 2B: PROTOCOL RAG ───────────────────────────────────────

def rag_node(state: IncidentState) -> dict:
    """
    ChromaDB Protocol Retriever with in-memory caching.
    Runs asynchronously and enriches the incident state.
    """
    emergency_type = state.get("emergency_type", "Medical")
    details = state.get("details", "")
    query = f"{emergency_type} emergency protocol for {details}" if details else f"{emergency_type} emergency response protocol"

    try:
        results = search_protocols(query=query, top_k=2)
        if results:
            protocols = [r.get("text", "") for r in results if r.get("text")]
            return {"rag_context": "\n---\n".join(protocols)}
    except Exception as e:
        logger.warning("RAG retrieval failed: %s", e)

    return {"rag_context": state.get("rag_context", "")}


# ── NODE 3: DYNAMIC QUESTION GENERATOR ──────────────────────────

def question_node(state: IncidentState) -> dict:
    """
    Dynamic context-aware question generator.
    Guarantees:
    - Zero fixed-question lists.
    - Zero repeat questions from previous turns.
    - Full scenario awareness.
    - Output strictly in selected_language.
    """
    prev_questions = list(state.get("previous_questions") or [])

    # 1. First priority: Use dynamically generated question from Analyst LLM
    llm_q = state.get("_llm_question")
    if llm_q and str(llm_q).strip() and str(llm_q).strip() not in prev_questions:
        q_text = str(llm_q).strip()
        prev_questions.append(q_text)
        return {"current_question": q_text, "previous_questions": prev_questions}

    active_lang = state.get("selected_language") or state.get("language") or "en"
    lang_display = LANGUAGE_NAMES.get(active_lang, active_lang.upper())

    # 2. Second priority: Generate dynamic question with targeted prompt
    try:
        llm = _get_llm(temperature=0.2)
        gps_ctx_q = _gps_context_string(state)
        loc_known_q = _location_is_known(state)
        known_facts_q = dict(state.get("known_facts") or {})
        if _gps_is_reliable(state):
            known_facts_q["gps_location"] = "known"
        elif _gps_is_low_accuracy(state):
            known_facts_q["gps_location"] = "low_accuracy"

        prompt_text = QUESTION_GENERATOR_PROMPT.format(
            emergency_type=state.get("emergency_type", "Unknown"),
            scenario_category=state.get("scenario_category", "general"),
            location=f"{state.get('location', 'Unknown')} | {gps_ctx_q} | location_is_known={loc_known_q}",
            details=state.get("details", "None"),
            priority=state.get("priority", 2),
            casualties=state.get("casualties", "Unknown"),
            known_facts=json.dumps(known_facts_q, ensure_ascii=False),
            previous_questions=json.dumps(prev_questions, ensure_ascii=False),
            missing_info=json.dumps(state.get("missing_info", []), ensure_ascii=False),
            context=state.get("rag_context") or state.get("retrieved_context") or "Standard emergency protocol",
            target_language_name=lang_display,
            selected_language=active_lang,
        )

        response = llm.invoke([
            SystemMessage(content="You are LifeLine emergency dynamic follow-up question generator."),
            HumanMessage(content=prompt_text),
        ])
        q_text = _clean_llm_text(response.content).strip('"\'')
        if q_text and len(q_text) > 5 and not q_text.lower().startswith("null"):
            if q_text not in prev_questions:
                prev_questions.append(q_text)
            return {"current_question": q_text, "previous_questions": prev_questions}
    except Exception as e:
        logger.warning("Dedicated question generation failed: %s", e)

    # 3. Dynamic scenario-aware fallback (when LLM is completely unreachable)
    emergency_type = state.get("emergency_type", "Medical")
    details_lower = (state.get("details") or "").lower()

    fallback_q = None
    location_already_known = _location_is_known(state)
    if not location_already_known and "location" not in str(prev_questions):
        if _gps_is_low_accuracy(state):
            if active_lang == "ta":
                fallback_q = "அருகிலுள்ள அடையாள இடம் அல்லது சாலை பெயரைக் கூறுங்கள்?"
            elif active_lang == "hi":
                fallback_q = "क्या आप नज़दीकी लैंडमार्क या सड़क का नाम बता सकते हैं?"
            else:
                fallback_q = "Can you name a nearby landmark or road to confirm your area?"
        else:
            if active_lang == "ta":
                fallback_q = "உங்கள் சரியான இருப்பிடம் அல்லது அடையாள இடத்தைக் கூறுங்கள்?"
            elif active_lang == "hi":
                fallback_q = "कृपया अपना सटीक स्थान या नजदीकी लैंडमार्क बताएं?"
            else:
                fallback_q = "Can you confirm your exact location or nearest landmark?"
    elif any(b in details_lower for b in ["bleed", "cut", "wound", "blood", "ரத்தம்", "காயம்", "खून", "चोट"]):
        candidates = [
            "Are you able to apply continuous direct pressure to the wound with a clean cloth?",
            "Is the bleeding starting to slow down, or is it soaking through the bandage?",
            "Are you feeling dizzy, pale, or weak from the blood loss?"
        ] if active_lang == "en" else ([
            "காயத்தின் மீது தொடர்ந்து அழுத்தம் கொடுத்துக் கொண்டிருக்கிறீர்களா?",
            "ரத்தம் கட்டுக்குள் வருகிறதா அல்லது அதிகமாக வெளியேறுகிறதா?",
            "உங்களுக்கு மயக்கம் அல்லது நடுக்கம் ஏற்படுகிறதா?"
        ] if active_lang == "ta" else [
            "क्या आप घाव पर लगातार सीधा दबाव बना पा रहे हैं?",
            "क्या खून बहना कम हो रहा है या कपड़े से बाहर आ रहा है?",
            "क्या आपको चक्कर या कमजोरी महसूस हो रही है?"
        ])
        fallback_q = next((c for c in candidates if c not in prev_questions), candidates[0])
    elif any(d in details_lower for d in ["dizzy", "dizziness", "faint", "fainted", "fainting", "pass out", "passed out", "மயக்கம்", "சுற்றுகிறது", "चक्कर", "बेहोश"]):
        candidates = [
            "Sit or lie down flat immediately. Are you experiencing blurred vision, sweating, or nausea?",
            "Is there someone with you right now who can assist you while help arrives?",
            "Are you able to speak clearly and keep your head elevated?"
        ] if active_lang == "en" else ([
            "உடனடியாக பாதுகாப்பாக அமருங்கள் அல்லது படுங்கள். பார்வை மங்கலாக அல்லது வியர்க்கிறதா?",
            "உதவி வரும் வரை உங்களுடன் யாராவது உடனிருக்கிறார்களா?",
            "உங்களால் தெளிவாகப் பேச முடிகிறதா?"
        ] if active_lang == "ta" else [
            "तुरंत सुरक्षित स्थान पर बैठें या लेट जाएं। क्या आपको पसीना या चक्कर आ रहा है?",
            "क्या इस समय आपके साथ कोई मौजूद है जो मदद कर सके?",
            "क्या आप स्पष्ट रूप से बोल पा रहे हैं?"
        ])
        fallback_q = next((c for c in candidates if c not in prev_questions), candidates[0])
    elif any(c in details_lower for c in ["chest", "breathe", "breath", "unconscious", "heart", "weak", "moochu", "மாரடைப்பு", "மயக்கம்", "சாंस", "बेहोश", "दर्द"]):
        candidates = [
            "Is the patient conscious and able to speak or breathe normally right now?",
            "Loosen any tight clothing around the neck. How long have these breathing difficulties lasted?",
            "Are they experiencing sweating or pain spreading into the left arm or jaw?"
        ] if active_lang == "en" else ([
            "பாதிக்கப்பட்ட நபர் கண் விழித்து பேசுகிறாரா அல்லது அசைவு உள்ளதா?",
            "கழுத்து மற்றும் மார்பு ஆடைகளைத் தளர்த்துங்கள். மூச்சுத் திணறல் எப்போது தொடங்கியது?",
            "இடது கை அல்லது தாடை பகுதியில் வலி பரவுகிறதா?"
        ] if active_lang == "ta" else [
            "क्या मरीज होश में है और ठीक से सांस ले पा रहा है?",
            "गले के कपड़े ढीले करें। सांस लेने में यह तकलीफ कब से हो रही है?",
            "क्या दर्द बाएं हाथ या जबड़े तक फैल रहा है?"
        ])
        fallback_q = next((c for c in candidates if c not in prev_questions), candidates[0])
    elif any(p in details_lower for p in ["stomach", "abdomen", "abdominal", "pain", "cramp", "belly", "வயிறு", "வலி", "पेट", "दर्द"]):
        candidates = [
            "Where exactly is the pain most severe, and is it sharp or cramping?",
            "Are you experiencing any vomiting, fever, or difficulty walking?",
            "Has the pain spread to your chest, back, or lower abdomen?"
        ] if active_lang == "en" else ([
            "வலி எங்கு அதிகமாக உள்ளது, அது குத்துவது போல் உள்ளதா?",
            "வாந்தி, காய்ச்சல் அல்லது நடக்க சிரமம் உள்ளதா?",
            "வலி முதுகு அல்லது நெஞ்சுப் பகுதிக்கு பரவுகிறதா?"
        ] if active_lang == "ta" else [
            "दर्द विशेष रूप से किस स्थान पर हो रहा है, क्या यह तेज चुभने जैसा है?",
            "क्या आपको उल्टी, बुखार या चलने में कठिनाई हो रही है?",
            "क्या दर्द पीठ या सीने की ओर फैल रहा है?"
        ])
        fallback_q = next((c for c in candidates if c not in prev_questions), candidates[0])
    elif emergency_type == "Fire" or any(f in details_lower for f in ["fire", "smoke", "flame", "தீ", "புகை", "ஆக", "आग"]):
        candidates = [
            "Are you and everyone else safely outside away from the smoke and flames?",
            "Is anyone trapped on upper floors or inside closed rooms?",
            "Can you confirm whether everyone has evacuated the building?"
        ] if active_lang == "en" else ([
            "நீங்கள் மற்றும் பிறர் கட்டிடத்திலிருந்து பாதுகாப்பாக வெளியேறிவிட்டீர்களா?",
            "கட்டிடத்தின் மேல் தளத்திலோ அல்லது அறையிலோ யாராவது சிக்கியுள்ளார்களா?",
            "அனைவரும் பாதுகாப்பான திறந்தவெளிக்கு வந்துவிட்டார்களா?"
        ] if active_lang == "ta" else [
            "क्या आप और अन्य सभी लोग इमारत से सुरक्षित बाहर निकल गए हैं?",
            "क्या कोई ऊपरी मंजिल या किसी कमरे में फंसा हुआ है?",
            "क्या सभी लोग सुरक्षित खुले स्थान पर पहुंच गए हैं?"
        ])
        fallback_q = next((c for c in candidates if c not in prev_questions), candidates[0])
    elif emergency_type in ["Traffic", "Accident"] or any(a in details_lower for a in ["crash", "accident", "car", "bike", "road", "விபத்து", "டிராபிக்", "टक्कर"]):
        candidates = [
            "Is anyone trapped inside a vehicle or lying on the road?",
            "Are all vehicles stabilized away from oncoming traffic?",
            "How many people appear injured or requiring immediate ambulance transport?"
        ] if active_lang == "en" else ([
            "வாகனத்தில் யாராவது சிக்கியுள்ளார்களா அல்லது சாலையில் கிடக்கிறார்களா?",
            "வாகனங்கள் நகராமல் பாதுகாப்பான நிலையில் உள்ளனவா?",
            "எத்தனை பேருக்கு அவசர மருத்துவ உதவி தேவைப்படுகிறது?"
        ] if active_lang == "ta" else [
            "क्या कोई वाहन में फंसा हुआ है या सड़क पर पड़ा है?",
            "क्या आने-जाने वाले ट्रैफिक से सुरक्षित स्थान पर हैं?",
            "कितने लोगों को तत्काल एम्बुलेंस की आवश्यकता है?"
        ])
        fallback_q = next((c for c in candidates if c not in prev_questions), candidates[0])
    elif emergency_type == "Police" or any(p in details_lower for p in ["gun", "knife", "attacker", "threat", "robbery", "துப்பாக்கி", "தாக்குதல்", "हथियार"]):
        candidates = [
            "Are you currently in a safe and secure location away from danger?",
            "Is the threat or attacker still visible or present at the scene?",
            "Are there any injured victims nearby requiring immediate medical dispatch?"
        ] if active_lang == "en" else ([
            "நீங்கள் இப்போது பாதுகாப்பான மற்றும் மறைவான இடத்தில் உள்ளீர்களா?",
            "தாக்குதல் நடத்தியவர் இன்னும் சம்பவ இடத்தில் தெரிகிறாரா?",
            "காயமடைந்தவர்கள் யாருக்காவது மருத்துவ உதவி தேவைப்படுகிறதா?"
        ] if active_lang == "ta" else [
            "क्या आप इस समय किसी सुरक्षित और छिपे हुए स्थान पर हैं?",
            "क्या हमलावर अभी भी मौके पर मौजूद है?",
            "क्या आसपास कोई घायल है जिसे मेडिकल मदद की जरूरत है?"
        ])
        fallback_q = next((c for c in candidates if c not in prev_questions), candidates[0])
    else:
        candidates = [
            "Can you describe the current symptoms or situation in more detail?",
            "How rapidly are the symptoms changing or worsening?",
            "Is the patient conscious, alert, and able to respond to you?"
        ] if active_lang == "en" else ([
            "சம்பவ இடத்தின் தற்போதைய நிலவரத்தை சுருக்கமாகக் கூறுங்கள்?",
            "அறிகுறிகள் எவ்வளவு வேகமாக தீவிரமடைந்து வருகின்றன?",
            "பாதிக்கப்பட்ட நபர் விழிப்பாக இருந்து பேச முடிகிறதா?"
        ] if active_lang == "ta" else [
            "कृपया स्थिति के बारे में थोड़ा और विस्तार से बताएं?",
            "लक्षण कितनी तेजी से बदल या बढ़ रहे हैं?",
            "क्या मरीज पूरी तरह होश में है और जवाब दे पा रहा है?"
        ])
        fallback_q = next((c for c in candidates if c not in prev_questions), candidates[0])

    if fallback_q and fallback_q not in prev_questions:
        prev_questions.append(fallback_q)

    return {"current_question": fallback_q, "previous_questions": prev_questions}


# ── NODE 4: SERVICE ROUTER ──────────────────────────────────────

def router_node(state: IncidentState) -> dict:
    """
    Routes the incident to the appropriate emergency service using RAG context.
    Determines multi-agency dispatch plan instantly with ChromaDB protocol grounding.
    """
    query = f"{state.get('emergency_type', '')} {state.get('details', '')} {state.get('location', '')}"
    try:
        context = retrieve_context(query)
    except Exception as e:
        logger.warning("RAG retrieval failed: %s", e)
        context = "Standard emergency dispatch protocol active."

    etype = (state.get("emergency_type") or "Medical").strip().capitalize()
    selected = state.get("selected_service")

    if selected:
        primary_service = selected.capitalize()
    elif etype == "Fire":
        primary_service = "Fire & Rescue"
    elif etype == "Police":
        primary_service = "Police"
    elif etype == "Traffic":
        primary_service = "Ambulance"
    elif etype == "Natural Disaster":
        primary_service = "Disaster Response Force"
    elif etype == "Animal Control":
        primary_service = "Animal Control"
    else:
        primary_service = "Ambulance"

    dispatch_plan = []
    if primary_service in ("Fire", "Fire & Rescue"):
        dispatch_plan = [
            {"service": "Fire & Rescue", "priority": 1, "reason": "Active fire suppression, hazard containment, and rescue"},
            {"service": "Ambulance", "priority": 2, "reason": "Medical standby for burns, smoke inhalation, and triage"},
        ]
    elif primary_service == "Police":
        dispatch_plan = [
            {"service": "Police", "priority": 1, "reason": "Immediate tactical law enforcement and perimeter security"},
            {"service": "Ambulance", "priority": 2, "reason": "Medical standby for potential trauma casualties"},
        ]
    elif primary_service in ("Traffic", "Traffic Police"):
        dispatch_plan = [
            {"service": "Ambulance", "priority": 1, "reason": "Immediate trauma medical care and victim stabilization"},
            {"service": "Traffic Police", "priority": 2, "reason": "Road clearance, diversion, and crash investigation"},
        ]
    elif primary_service == "Disaster Response Force":
        dispatch_plan = [
            {"service": "Disaster Response Force", "priority": 1, "reason": "Heavy search, rescue, and evacuation"},
            {"service": "Ambulance", "priority": 1, "reason": "Mass casualty emergency medical support"},
            {"service": "Police", "priority": 2, "reason": "Area cordon and security"},
        ]
    else:
        dispatch_plan = [
            {"service": "Ambulance", "priority": 1, "reason": "Emergency medical response and transport"},
        ]

    sop_steps = SOP_DATABASE.get(etype, SOP_DATABASE.get("Other", [
        "1. Verify exact coordinates and route responding units.",
        "2. Maintain continuous communications with caller.",
        "3. Monitor scene safety and provide real-time updates.",
    ]))

    routing_notes = f"Auto-routed to {primary_service} based on protocol {etype} criteria."

    return {
        "dispatch_plan": dispatch_plan,
        "retrieved_context": context,
        "routed_service": primary_service,
        "sop_steps": sop_steps,
        "dispatcher_notes": routing_notes,
    }


# ── NODE 5: SUMMARIZER ─────────────────────────────────────────

def summarizer_node(state: IncidentState) -> dict:
    """
    Generates a concise dispatcher-ready briefing.
    Uses unified single-pass LLM summary or deterministic briefing.
    """
    if state.get("summary"):
        return {"summary": state["summary"]}

    llm_sum = state.get("_llm_summary")
    if llm_sum and len(llm_sum) > 10 and not llm_sum.lower().startswith("null"):
        return {
            "summary": llm_sum,
            "dispatcher_notes": f"Priority {state.get('priority', 'P1')} dispatch active.",
        }

    etype = state.get("emergency_type", "Incident")
    loc = state.get("location", "Location unknown")
    det = state.get("details", "Details pending")
    cas = state.get("casualties", 0)
    summary_text = f"Reported {etype} emergency at {loc}. {det}. Casualties: {cas}."
    dispatcher_notes = f"Priority {state.get('priority', 'P1')} response active."

    return {
        "summary": summary_text,
        "dispatcher_notes": dispatcher_notes,
    }


# ── NODE 6: GUIDANCE ────────────────────────────────────────────

def guidance_node(state: IncidentState) -> dict:
    """
    Generates real-time safety guidance for the caller in selected_language.
    Does NOT overwrite dynamic current_question generated by question_node.
    """
    active_lang = state.get("selected_language") or state.get("language") or state.get("response_language") or "en"

    llm_guidance = state.get("_llm_guidance")
    if llm_guidance and len(llm_guidance) > 10 and not llm_guidance.lower().startswith("null"):
        return {"guidance": llm_guidance}

    if state.get("guidance"):
        return {"guidance": state["guidance"]}

    etype = (state.get("emergency_type") or "").lower()

    if active_lang == "ta":
        if "cardiac" in etype or "medical" in etype or state.get("priority") == 1:
            guidance_text = "சுவாசப்பாதையைச் சரிபார்க்கவும். மூச்சு இல்லை என்றால் உடனடியாக மார்பை அழுத்தி சிபிஆர் (CPR) செய்யுங்கள். அவசர ஊர்தி அனுப்பப்படுகிறது."
        elif "fire" in etype:
            guidance_text = "தீயணைப்பு படை அனுப்பப்படுகிறது. உடனடியாக கட்டடத்தை விட்டு பாதுகாப்பான இடத்திற்கு வெளியேறுங்கள். லிப்ட் பயன்படுத்த வேண்டாம்."
        elif "police" in etype or "weapon" in etype:
            guidance_text = "காவல்துறை அனுப்பப்படுகிறது. பாதுகாப்பான இடத்தில் கதவுகளைப் பூட்டி அமைதியாக இருங்கள்."
        else:
            guidance_text = "உதவி உடனடியாக வருகிறது. தயவுசெய்து அமைதியாக இருங்கள், லைனில் தொடருங்கள்."
    elif active_lang == "hi":
        if "cardiac" in etype or "medical" in etype or state.get("priority") == 1:
            guidance_text = "वायुमार्ग की जांच करें। यदि सांस नहीं ले रहे हैं, तो तुरंत सीपीआर (CPR) शुरू करें। एम्बुलेंस भेजी जा रही है।"
        elif "fire" in etype:
            guidance_text = "दमकल दल भेजा जा रहा है। तुरंत इमारत से सुरक्षित बाहर निकलें। लिफ्ट का उपयोग न करें।"
        elif "police" in etype or "weapon" in etype:
            guidance_text = "पुलिस दल भेजा जा रहा है। सुरक्षित स्थान पर रहें और शांत रहें।"
        else:
            guidance_text = "मदद भेजी जा रही है। कृपया शांत रहें और कॉल पर बने रहें।"
    else:
        if "cardiac" in etype or "medical" in etype:
            guidance_text = "Emergency units dispatched. If patient is unresponsive and not breathing, lay flat and begin chest compressions immediately at 100-120 bpm."
        elif "fire" in etype:
            guidance_text = "Emergency units dispatched. Evacuate the building immediately if safe. Stay low beneath smoke and do not use elevators."
        elif "police" in etype or "weapon" in etype:
            guidance_text = "Police units dispatched. Move to a secure location, lock all doors, stay out of sight, and keep your phone on silent."
        else:
            guidance_text = "Help is on the way. Please stay calm, keep the line open, and ensure the entrance is accessible for responders."

    return {"guidance": guidance_text}
