import asyncio
import pytest
from app.services.session_service import session_store
from app.services.tts_service import TTSService


# ── 1. Medical Emergency (Non-cardiac) ───────────────────────────
def test_scenario_medical_emergency():
    """Test dynamic triage and questioning for general medical emergency."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "en")

    # Turn 1: Caller reports diabetic collapse
    asyncio.run(session_store.process_message(
        session_id,
        "My diabetic sister has collapsed and is dizzy at 45 MG Road, Chennai.",
        language="en"
    ))

    state = session_store.get_state(session_id)
    assert state is not None
    assert state["emergency_type"] == "Medical"
    assert state["priority"] <= 3
    assert state["selected_language"] == "en"

    q1 = state.get("current_question") or ""
    assert len(q1) > 0

    # Turn 2: User answers follow-up
    asyncio.run(session_store.process_message(
        session_id,
        "She is awake and breathing, but very weak.",
        language="en"
    ))

    state2 = session_store.get_state(session_id)
    assert state2["known_facts"].get("consciousness") is True
    assert state2["known_facts"].get("breathing") is True


# ── 2. Cardiac Symptoms ──────────────────────────────────────────
def test_scenario_cardiac_symptoms():
    """Test cardiac emergency triggers critical priority and life-saving guidance."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "en")

    asyncio.run(session_store.process_message(
        session_id,
        "My father is clutching his chest with severe pain and cannot breathe.",
        language="en"
    ))

    state = session_store.get_state(session_id)
    assert state["priority"] == 1
    assert "cpr" in state["guidance"].lower() or "chest" in state["guidance"].lower() or "airway" in state["guidance"].lower()


# ── 3. Structure Fire ────────────────────────────────────────────
def test_scenario_fire_incident():
    """Test fire emergency extracts fire type, traps, and fire guidance."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "en")

    asyncio.run(session_store.process_message(
        session_id,
        "There is heavy smoke and fire on the 3rd floor at Skyline Apartments.",
        language="en"
    ))

    state = session_store.get_state(session_id)
    assert state["emergency_type"] == "Fire"
    assert state["priority"] == 1
    assert "evacuate" in state["guidance"].lower() or "smoke" in state["guidance"].lower() or "fire" in state["guidance"].lower()

    # Turn 2: Confirm nobody trapped
    asyncio.run(session_store.process_message(
        session_id,
        "Everyone is evacuating, no one is trapped inside.",
        language="en"
    ))

    state2 = session_store.get_state(session_id)
    assert state2["known_facts"].get("trapped_people") == 0


# ── 4. Road Traffic Accident ─────────────────────────────────────
def test_scenario_road_accident():
    """Test road crash triage with vehicle involvement and injuries."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "en")

    asyncio.run(session_store.process_message(
        session_id,
        "A car collided with a truck on Highway 44 near Toll Gate. Two people are injured.",
        language="en"
    ))

    state = session_store.get_state(session_id)
    assert state["emergency_type"] in ("Traffic", "Medical")
    assert state["casualties"] == 2
    assert "Highway 44" in (state["location"] or "") or "Toll Gate" in (state["location"] or "")


# ── 5. Severe Arterial Bleeding ──────────────────────────────────
def test_scenario_severe_bleeding():
    """Test severe bleeding triggers direct pressure safety guidance."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "en")

    asyncio.run(session_store.process_message(
        session_id,
        "Worker has severe arterial bleeding from a deep machinery cut on his arm at Industrial Estate.",
        language="en"
    ))

    state = session_store.get_state(session_id)
    assert state["priority"] == 1
    assert "pressure" in state["guidance"].lower() or "bleeding" in state["guidance"].lower() or "cloth" in state["guidance"].lower()


# ── 6. Security / Weapon Threat ──────────────────────────────────
def test_scenario_security_threat():
    """Test police tactical response for armed threat and safe room instruction."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "en")

    asyncio.run(session_store.process_message(
        session_id,
        "Active shooter with a rifle seen outside City Mall entrance.",
        language="en"
    ))

    state = session_store.get_state(session_id)
    assert state["emergency_type"] == "Police"
    assert state["priority"] == 1
    assert "lock" in state["guidance"].lower() or "secure" in state["guidance"].lower() or "silent" in state["guidance"].lower() or "room" in state["guidance"].lower()


# ── 7. Hazardous Material / Poisoning ────────────────────────────
def test_scenario_poisoning_hazmat():
    """Test chemical / poisoning protocol activation and context retrieval."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "en")

    asyncio.run(session_store.process_message(
        session_id,
        "Strong chemical smell in the basement and workers are experiencing severe dizziness and vomiting.",
        language="en"
    ))

    state = session_store.get_state(session_id)
    assert state["priority"] <= 2
    assert state["known_facts"].get("hazards") is not None or "chemical" in (state.get("details") or "").lower()


# ── 8. Drowning Incident ─────────────────────────────────────────
def test_scenario_drowning():
    """Test drowning rescue protocol and CPR/drain airway guidance."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "en")

    asyncio.run(session_store.process_message(
        session_id,
        "A child was pulled from the swimming pool and is unresponsive.",
        language="en"
    ))

    state = session_store.get_state(session_id)
    assert state["priority"] == 1
    assert "cpr" in state["guidance"].lower() or "airway" in state["guidance"].lower() or "chest" in state["guidance"].lower()


# ── 9. Multilingual Dynamic Generation (Tamil) ───────────────────
def test_multilingual_tamil_dynamic():
    """Test Tamil language generation for fire emergency."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "ta")

    asyncio.run(session_store.process_message(
        session_id,
        "எங்கள் வீட்டில் தீப்பிடித்துள்ளது, புகை அதிகமாக வருகிறது.",
        language="ta"
    ))

    state = session_store.get_state(session_id)
    assert state["selected_language"] == "ta"
    assert state["emergency_type"] == "Fire"
    question = state.get("current_question") or ""
    guidance = state.get("guidance") or ""

    assert any('\u0B80' <= ch <= '\u0BFF' for ch in question) or any('\u0B80' <= ch <= '\u0BFF' for ch in guidance)


# ── 10. Multilingual Dynamic Generation (Hindi) ──────────────────
def test_multilingual_hindi_dynamic():
    """Test Hindi language generation for road accident."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "hi")

    asyncio.run(session_store.process_message(
        session_id,
        "सड़क पर दो कारों की भीषण टक्कर हो गई है, तुरंत एम्बुलेंस भेजिए।",
        language="hi"
    ))

    state = session_store.get_state(session_id)
    assert state["selected_language"] == "hi"
    question = state.get("current_question") or ""
    guidance = state.get("guidance") or ""

    assert any('\u0900' <= ch <= '\u097F' for ch in question) or any('\u0900' <= ch <= '\u097F' for ch in guidance)


# ── 11. TTS Integration Language Verification ────────────────────
def test_tts_service_language_mapping():
    """Test TTS Service handles all configured BCP-47 language codes."""
    tts = TTSService()
    assert tts.LANGUAGE_MAP.get("ta") == "ta-IN"
    assert tts.LANGUAGE_MAP.get("hi") == "hi-IN"
    assert tts.LANGUAGE_MAP.get("en") == "en-IN"
    assert tts.LANGUAGE_MAP.get("te") == "te-IN"
    assert tts.LANGUAGE_MAP.get("kn") == "kn-IN"


# ── 12. Multi-turn Dynamic Progression (No stuck static guidance) ─
@pytest.mark.anyio
async def test_multiturn_dynamic_progression_no_static_stuck_response():
    """Test that turns 1 through 5 generate dynamic responses and do not get stuck on generic static text."""
    sid = "test_multiturn_5turns"
    session_store.get_or_create(sid)
    session_store.set_language(sid, "en")

    # Turn 1
    await session_store.process_message(sid, "I have severe stomach pain.", language="en")
    st1 = session_store.get_state(sid)
    r1 = st1.get("current_question") or st1.get("guidance") or ""
    assert r1 != "Emergency assistance is on the way. Please remain calm."
    assert len(r1) > 5

    # Turn 2
    await session_store.process_message(sid, "The pain has suddenly become much worse.", language="en")
    st2 = session_store.get_state(sid)
    r2 = st2.get("current_question") or st2.get("guidance") or ""
    assert r2 != "Emergency assistance is on the way. Please remain calm."
    assert r2 != r1

    # Turn 3
    await session_store.process_message(sid, "I am also feeling dizzy.", language="en")
    st3 = session_store.get_state(sid)
    r3 = st3.get("current_question") or st3.get("guidance") or ""
    assert r3 != "Emergency assistance is on the way. Please remain calm."
    assert r3 != r2

    # Turn 4
    await session_store.process_message(sid, "I am having trouble breathing.", language="en")
    st4 = session_store.get_state(sid)
    r4 = st4.get("current_question") or st4.get("guidance") or ""
    assert r4 != "Emergency assistance is on the way. Please remain calm."
    assert r4 != r3

    # Turn 5
    await session_store.process_message(sid, "I think I may faint.", language="en")
    st5 = session_store.get_state(sid)
    r5 = st5.get("current_question") or st5.get("guidance") or ""
    assert r5 != "Emergency assistance is on the way. Please remain calm."
    assert r5 != r4

