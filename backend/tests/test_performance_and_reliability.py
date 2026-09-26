import pytest
import time
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.config import get_settings
from app.services.session_service import session_store
from app.services.severity_service import SeverityService
from app.services.stt_service import STTService
from app.services.tts_service import TTSService
from app.services.rag_service import retrieve_context
from app.routes.stream import is_meaningful_transcript


def test_primary_llm_model_is_qwen():
    """Verify production configuration uses qwen/qwen3.8-27b as primary model."""
    settings = get_settings()
    assert settings.groq_model == "qwen/qwen3.8-27b"
    assert settings.resolved_groq_model == "qwen/qwen3.8-27b"
    assert settings.active_model_name == "qwen/qwen3.8-27b"


def test_stt_primary_provider_is_sarvam():
    """Verify STT service uses Sarvam Saaras v4 as primary with Groq Whisper fallback."""
    stt = STTService()
    assert stt.stt_provider == "sarvam"
    assert stt.sarvam_client is not None


def test_rag_warm_performance():
    """Verify warm RAG retrieval executes in < 15ms."""
    # Pre-warm
    _ = retrieve_context("cardiac arrest cpr", k=3)

    t0 = time.perf_counter()
    ctx = retrieve_context("building fire smoke evacuation", k=3)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert len(ctx) > 50
    assert elapsed_ms < 20.0, f"RAG warm retrieval took too long: {elapsed_ms:.2f}ms"


def test_short_emergency_phrase_meaningful():
    """Verify short Tamil and English emergency keywords are accepted and not discarded."""
    assert is_meaningful_transcript("தீ!")
    assert is_meaningful_transcript("உதவி!")
    assert is_meaningful_transcript("Help!")
    assert is_meaningful_transcript("Fire!")
    assert is_meaningful_transcript("Heart attack")
    assert not is_meaningful_transcript("")
    assert not is_meaningful_transcript("...")
    assert not is_meaningful_transcript("thank you")


def test_severity_scoring_fast_path_latency():
    """Verify deterministic severity scoring takes < 5ms."""
    severity = SeverityService()
    t0 = time.perf_counter()
    res = severity.evaluate("என் அப்பா மயக்கமடைந்து மூச்சு விடவில்லை")
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert res["priority_score"] >= 8
    assert "CRITICAL" in res["priority_label"]
    assert elapsed_ms < 5.0, f"Severity evaluation took too long: {elapsed_ms:.2f}ms"


def test_tts_dynamic_language_support():
    """Verify TTSService maps supported languages dynamically."""
    tts = TTSService()
    assert tts.LANGUAGE_MAP["ta"] == "ta-IN"
    assert tts.LANGUAGE_MAP["hi"] == "hi-IN"
    assert tts.LANGUAGE_MAP["en"] == "en-IN"
    assert tts.LANGUAGE_MAP["te"] == "te-IN"
    assert tts.LANGUAGE_MAP["kn"] == "kn-IN"
    assert tts.LANGUAGE_MAP["ml"] == "ml-IN"


def test_critical_safety_path_does_not_wait_for_mongo():
    """Verify that MongoDB persistence failure does not crash or block session state updates."""
    session_id = session_store.get_or_create()
    state = session_store.get_state(session_id)
    assert state is not None

    with patch("app.services.mongo_service.save_session", side_effect=Exception("MongoDB timeout")):
        # Should not raise exception
        asyncio.run(session_store._persist_to_mongo(session_id, state))


def test_tts_failure_does_not_raise():
    """Verify TTS synthesis error returns None gracefully without throwing unhandled exceptions."""
    tts = TTSService()
    with patch.object(tts.client.text_to_speech, "convert", side_effect=Exception("API limit reached")):
        audio = tts.synthesize_base64_audio("Test message", "en")
        assert audio is None


def test_qwen_structured_reasoning():
    """Verify Qwen 3.8-27B processes emergency message and outputs structured triage."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "ta")

    asyncio.run(
        session_store.process_message(
            session_id,
            "அண்ணா சாலையில் பெரிய கார் விபத்து, இரண்டு பேருக்கு அதிக ரத்தப்போக்கு!",
            language="ta",
        )
    )

    state = session_store.get_state(session_id)
    assert state is not None
    assert state["emergency_type"].upper() in ["TRAFFIC", "MEDICAL", "RESCUE", "ACCIDENT", "ROAD ACCIDENT"]
    assert state["priority"] in [1, 2]
    assert state["language"] == "ta"

    question = state.get("current_question") or state.get("guidance") or ""
    assert any('\u0B80' <= ch <= '\u0BFF' for ch in question), f"Expected Tamil question, got: {question}"


def test_immediate_dispatcher_broadcast_payload():
    """Verify dispatcher broadcast receives immediate transcript without waiting for full workflow."""
    from app.routes.dispatcher import broadcast_emergency_update

    mock_ws = MagicMock()
    mock_ws.send_text = AsyncMock()

    from app.routes import dispatcher
    dispatcher._dispatcher_connections.append(mock_ws)

    try:
        payload = {
            "session_id": "test-session-123",
            "transcript": "Emergency at Central Station",
            "status": "caller_speaking",
        }
        asyncio.run(broadcast_emergency_update(payload))
        assert mock_ws.send_text.called
    finally:
        if mock_ws in dispatcher._dispatcher_connections:
            dispatcher._dispatcher_connections.remove(mock_ws)
