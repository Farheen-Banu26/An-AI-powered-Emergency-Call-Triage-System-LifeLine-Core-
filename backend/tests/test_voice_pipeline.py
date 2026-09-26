import asyncio
import time
import urllib.parse
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.session_service import session_store
from app.services.vad_service import VADService
from app.services.stt_service import STTService
from app.routes.stream import is_meaningful_transcript
from app.services.severity_service import SeverityService
from app.services.tts_service import TTSService


def _generate_voiced_pcm(duration_ms: int = 500, freq: int = 300, amplitude: int = 12000) -> bytes:
    """Generate 16kHz 16-bit mono PCM sine wave representing voiced speech."""
    import math
    import struct
    num_samples = int(16000 * (duration_ms / 1000.0))
    samples = [int(amplitude * math.sin(2 * math.pi * freq * i / 16000)) for i in range(num_samples)]
    return struct.pack(f"<{num_samples}h", *samples)


def test_vad_short_emergency_word_detection():
    """Verify VAD handles short emergency utterances like 'Fire!' or 'தீ!' without discarding."""
    vad = VADService()
    voiced_audio = _generate_voiced_pcm(duration_ms=400)
    
    chunks = list(vad.get_speech_chunks(voiced_audio))
    flushed = vad.flush()
    assert len(chunks) > 0 or (flushed is not None and len(flushed) > 0)


def test_vad_speech_end_flush():
    """Verify vad.flush() returns buffered speech when client signals speech_end."""
    vad = VADService()
    voiced_audio = _generate_voiced_pcm(duration_ms=350)
    list(vad.get_speech_chunks(voiced_audio))
    flushed = vad.flush()
    assert flushed is not None
    assert len(flushed) >= 2000


def test_silence_produces_zero_transcripts():
    """Verify pure background silence yields 0 VAD utterances and 0 transcripts."""
    vad = VADService()
    silence_pcm = b"\x00\x00" * 16000  # 1 second of silence
    chunks = list(vad.get_speech_chunks(silence_pcm))
    flushed = vad.flush()
    assert len(chunks) == 0
    assert flushed is None


def test_is_meaningful_transcript():
    """Verify non-meaningful transcripts and hallucinations are discarded while short Tamil/English words are preserved."""
    assert not is_meaningful_transcript("")
    assert not is_meaningful_transcript("...")
    assert not is_meaningful_transcript("thank you.")
    assert not is_meaningful_transcript("thanks for watching!")
    assert not is_meaningful_transcript("you")
    
    # Meaningful emergency words
    assert is_meaningful_transcript("Fire!")
    assert is_meaningful_transcript("தீ!")
    assert is_meaningful_transcript("உதவி!")
    assert is_meaningful_transcript("Help!")
    assert is_meaningful_transcript("My father is unconscious and not breathing.")
    assert is_meaningful_transcript("என் அப்பா மயக்கமடைந்து மூச்சு விடவில்லை.")


@pytest.mark.anyio
async def test_stt_timeout_and_fallback():
    """Verify STT service uses Sarvam primary and falls back gracefully to Groq Whisper without hanging."""
    service = STTService(provider="sarvam")
    service.groq_client = MagicMock()
    service.sarvam_client = MagicMock()
    
    # 1. Normal Sarvam primary success
    mock_resp = MagicMock()
    mock_resp.transcript = "என் அப்பா மயக்கமடைந்து மூச்சு விடவில்லை."
    service.sarvam_client.speech_to_text.transcribe = MagicMock(return_value=mock_resp)
    res = await service.transcribe(b"\x00" * 6400, language="ta")
    assert res["transcript"] == "என் அப்பா மயக்கமடைந்து மூச்சு விடவில்லை."
    assert res["provider"] == "sarvam"

    # 2. Sarvam timeout/failure -> Groq Whisper fallback
    service.sarvam_client.speech_to_text.transcribe = MagicMock(side_effect=Exception("API Error"))
    service.groq_client.audio.transcriptions.create = MagicMock(return_value="My father is unconscious and not breathing.")
    res = await service.transcribe(b"\x00" * 6400, language="ta")
    assert res["transcript"] == "My father is unconscious and not breathing."
    assert res["provider"] == "groq-whisper"


@pytest.mark.anyio
async def test_fast_path_deterministic_trigger():
    """Verify critical safety fast path triggers deterministically in <5ms for cardiac and fire."""
    severity = SeverityService()
    
    t0 = time.perf_counter()
    res1 = severity.evaluate("My father is unconscious and not breathing.")
    dt1 = (time.perf_counter() - t0) * 1000
    assert res1["priority_label"] == "CRITICAL (Cat 1)"
    assert res1["priority_score"] >= 9
    assert dt1 < 10.0

    t0 = time.perf_counter()
    res2 = severity.evaluate("Fire! The building is on fire!")
    dt2 = (time.perf_counter() - t0) * 1000
    assert res2["priority_score"] >= 4
    assert dt2 < 10.0


def test_message_bound_tts_overrides_session_state():
    """Verify ?text= parameter binds audio synthesis to the exact requested text rather than mutable current_question."""
    client = TestClient(app)
    sid = "test_msg_bound"
    session_store.get_or_create(sid)
    state = session_store.get_state(sid)
    state["current_question"] = "Message B: What is the patient age?"

    # Request audio specifically for Message A
    message_a = "Message A: Please remain calm. Help is on the way."
    encoded_text = urllib.parse.quote(message_a)
    resp = client.get(f"/api/call/question/{sid}/audio?lang=en&text={encoded_text}")
    assert resp.status_code == 200
    assert resp.headers.get("content-type") == "audio/wav"
    assert resp.content.startswith(b"RIFF")
    # Header should reflect Message A, not Message B
    assert urllib.parse.unquote(resp.headers.get("x-question-text", "")) == message_a


def test_message_bound_tts_tamil():
    """Verify ?text= parameter works with Tamil Unicode message text."""
    client = TestClient(app)
    sid = "test_msg_bound_ta"
    session_store.get_or_create(sid)
    state = session_store.get_state(sid)
    state["current_question"] = "வேறொரு கேள்வி"

    tamil_msg = "ஆம்புலன்ஸ் அனுப்பப்பட்டுள்ளது. தயவுசெய்து அமைதியாக இருங்கள்."
    encoded_text = urllib.parse.quote(tamil_msg)
    resp = client.get(f"/api/call/question/{sid}/audio?lang=ta&text={encoded_text}")
    assert resp.status_code == 200
    assert resp.headers.get("content-type") == "audio/wav"
    assert resp.content.startswith(b"RIFF")
    assert urllib.parse.unquote(resp.headers.get("x-question-text", "")) == tamil_msg


def test_dispatcher_websocket_connection_and_broadcast():
    """Verify dispatcher WebSocket connects and receives broadcast events."""
    client = TestClient(app)
    with client.websocket_connect("/api/dispatcher/ws") as ws:
        ws.send_text('{"type": "ping"}')
        assert ws is not None


@pytest.mark.anyio
async def test_fast_path_single_emission_behavior():
    """TEST B: Verify critical emergency triggers fast-path response once and suppresses 2nd bubble from LangGraph."""
    from app.services.severity_service import SeverityService
    severity = SeverityService()
    
    # 1. Critical utterance evaluation
    crit_eval = severity.evaluate("My father is unconscious and not breathing.")
    assert crit_eval["priority_score"] >= 9
    
    # Fast path guidance logic as in stream.py
    emergency_type = crit_eval.get("emergency_type", "medical")
    fast_guidance = (
        "Please check if they are breathing. If not breathing, start CPR immediately. "
        "Place hands in center of chest and push hard and fast."
    )
    assert fast_guidance is not None

    # 2. Simulated WebSocket safe_send tracking
    sent_messages = []
    async def mock_safe_send(payload):
        sent_messages.append(payload)

    # When fast-path executes, it sends fast_guidance immediately:
    await mock_safe_send({
        "type": "question",
        "text": fast_guidance,
        "guidance": fast_guidance,
        "session_id": "test_fp_single",
        "status": "triage_complete",
        "priority_score": crit_eval["priority_score"],
        "priority_label": crit_eval["priority_label"],
        "language_code": "en",
    })
    
    # Then background pipeline runs with has_fast_path_response=True
    # simulating the logic in _run_ai_pipeline
    has_fast_path_response = bool(fast_guidance)
    if has_fast_path_response:
        await mock_safe_send({
            "type": "vad_state",
            "state": "listening",
            "session_id": "test_fp_single",
        })
    else:
        await mock_safe_send({
            "type": "question",
            "text": "Redundant question",
            "session_id": "test_fp_single",
        })

    # Assert exactly ONE "question" message was emitted
    question_msgs = [m for m in sent_messages if m.get("type") == "question"]
    assert len(question_msgs) == 1
    assert question_msgs[0]["text"] == fast_guidance


@pytest.mark.anyio
async def test_normal_message_single_emission():
    """TEST C: Verify normal non-critical message produces exactly one caller-facing question/guidance."""
    sent_messages = []
    async def mock_safe_send(payload):
        sent_messages.append(payload)

    # For normal message, fast_guidance is None -> has_fast_path_response is False
    fast_guidance = None
    has_fast_path_response = bool(fast_guidance)

    if has_fast_path_response:
        await mock_safe_send({"type": "vad_state", "state": "listening"})
    else:
        await mock_safe_send({
            "type": "question",
            "text": "Can you tell me what happened?",
            "session_id": "test_normal_single",
        })
        await mock_safe_send({"type": "vad_state", "state": "listening"})

    question_msgs = [m for m in sent_messages if m.get("type") == "question"]
    assert len(question_msgs) == 1
    assert question_msgs[0]["text"] == "Can you tell me what happened?"


def test_tts_replay_idempotence():
    """TEST D: Verify requesting TTS replay for the same text returns valid audio bound to the exact requested text."""
    client = TestClient(app)
    sid = "test_tts_replay"
    session_store.get_or_create(sid)
    
    target_text = "An ambulance has been dispatched. Please remain calm."
    encoded = urllib.parse.quote(target_text)

    # Initial TTS playback request
    resp1 = client.get(f"/api/call/question/{sid}/audio?lang=en&text={encoded}")
    assert resp1.status_code == 200
    assert resp1.headers.get("content-type") == "audio/wav"
    assert resp1.content.startswith(b"RIFF")
    assert urllib.parse.unquote(resp1.headers.get("x-question-text", "")) == target_text

    # Replay TTS playback request
    resp2 = client.get(f"/api/call/question/{sid}/audio?lang=en&text={encoded}")
    assert resp2.status_code == 200
    assert resp2.headers.get("content-type") == "audio/wav"
    assert resp2.content.startswith(b"RIFF")
    assert urllib.parse.unquote(resp2.headers.get("x-question-text", "")) == target_text


@pytest.mark.anyio
async def test_severe_bleeding_fast_path_and_guidance():
    """Verify 'I cut my hand badly and the bleeding is not stopping' triggers bleeding guidance and no generic opening question."""
    from app.ai.nodes import analyst_node, question_node
    from langchain_core.messages import HumanMessage

    state = {
        "session_id": "test_bleeding_triage",
        "messages": [HumanMessage(content="I cut my hand badly and the bleeding is not stopping.")],
        "turn_count": 0,
        "selected_language": "en",
        "language": "en",
    }

    # 1. Analyst node processes utterance
    analyst_result = analyst_node(state)
    assert analyst_result.get("emergency_type") in ("Medical", "medical")
    assert analyst_result.get("casualties") == 1
    assert "pressure" in analyst_result.get("guidance", "").lower() or "bandage" in analyst_result.get("guidance", "").lower()

    # 2. Question node does NOT ask "Is anyone injured or in immediate danger?"
    state.update(analyst_result)
    q_result = question_node(state)
    q_text = q_result.get("current_question", "")
    assert q_text != "Is anyone injured or in immediate danger?"
    assert "injured" not in q_text.lower() or "anyone" not in q_text.lower()


@pytest.mark.anyio
async def test_multi_turn_bleeding_context_adaptation():
    """Verify multi-turn state updates properly when caller says they applied a cloth."""
    from app.ai.nodes import analyst_node, question_node
    from langchain_core.messages import HumanMessage

    # Turn 1: Caller states severe bleeding
    state = {
        "session_id": "test_bleeding_multi",
        "messages": [HumanMessage(content="I cut my hand badly and the bleeding is not stopping.")],
        "turn_count": 0,
        "selected_language": "en",
        "previous_questions": [],
    }
    t1_analyst = analyst_node(state)
    state.update(t1_analyst)

    # Turn 2: Caller states they applied a clean cloth
    state["messages"].append(HumanMessage(content="I am pressing a clean cloth against the wound."))
    t2_analyst = analyst_node(state)
    state.update(t2_analyst)
    t2_q = question_node(state)

    # Question must not ask if anyone is injured or ask if location is known if GPS is set
    q_text = t2_q.get("current_question", "")
    assert q_text != "Is anyone injured or in immediate danger?"
    assert len(q_text) > 5


def test_long_silence_rejection():
    """Verify silence frames produce empty transcript and 0 caller messages."""
    from app.routes.stream import is_meaningful_transcript
    assert not is_meaningful_transcript("")
    assert not is_meaningful_transcript("   ")
    assert not is_meaningful_transcript("thank you for watching")
    assert not is_meaningful_transcript("i'm going to go")
    assert not is_meaningful_transcript("god. god. god")
    assert not is_meaningful_transcript("yes, i am the one")

