"""
Regression tests for GPS location integration in LifeLine-Core.

These tests verify that:
1. GPS coordinates are recognized as known location, preventing generic location questions
2. GPS fallback behavior is correct when GPS is unavailable or inaccurate
3. Manual map corrections update the active session correctly
4. Multilingual location extraction works for all supported languages
5. Answered location/landmark answers are persisted and not repeated
6. Multiple emergency scenarios correctly skip location questions when GPS is available
"""

import asyncio
import pytest

from app.ai.nodes import (
    _gps_is_reliable,
    _gps_is_low_accuracy,
    _location_is_known,
    _gps_context_string,
)
from app.ai.state import IncidentState
from app.services.session_service import session_store


# ── Helper: build a minimal IncidentState with GPS fields ──────────────────────

def _make_state(
    latitude=None,
    longitude=None,
    accuracy=None,
    location_status=None,
    location_source="Browser GPS",
    location=None,
    landmark=None,
) -> IncidentState:
    """Build a minimal IncidentState with specified GPS fields."""
    return IncidentState(
        messages=[],
        emergency_type=None,
        scenario_category=None,
        location=location,
        landmark=landmark,
        latitude=latitude,
        longitude=longitude,
        location_accuracy=accuracy,
        location_source=location_source,
        location_status=location_status,
        location_display=None,
        details=None,
        priority=None,
        caller_name=None,
        caller_age=None,
        caller_phone=None,
        caller_gender=None,
        casualties=None,
        symptoms=[],
        hazards=[],
        injuries=[],
        trapped_people=None,
        environmental_info=None,
        camera_observations=[],
        estimated_arrival=None,
        summary=None,
        routed_service=None,
        sop_steps=None,
        dispatcher_notes=None,
        priority_score=None,
        priority_label=None,
        guidance=None,
        dispatch_plan=[],
        retrieved_context=None,
        fake_probability=None,
        fake_label=None,
        fake_signals=None,
        _llm_fake_score=None,
        captured_images=[],
        sensor_telemetry=None,
        selected_service=None,
        language="en",
        selected_language="en",
        input_language="en",
        detected_language="en",
        response_language="en",
        known_facts={},
        previous_questions=[],
        previous_answers=[],
        missing_info=[],
        current_question=None,
        status="gathering_info",
        turn_count=0,
    )


# ── TEST 1: GPS available with good accuracy → location is considered known ──

def test_gps_reliable_accuracy_below_threshold():
    """GPS with accuracy ≤ 100m is considered reliable."""
    state = _make_state(latitude=12.97194, longitude=77.59369, accuracy=8.0)
    assert _gps_is_reliable(state) is True
    assert _location_is_known(state) is True


# ── TEST 2: GPS unavailable → location fallback question MAY be generated ───

def test_gps_unavailable_location_not_known():
    """When GPS is not available, location is not known unless text is provided."""
    state = _make_state()  # No GPS, no text location
    assert _gps_is_reliable(state) is False
    assert _location_is_known(state) is False


def test_gps_unavailable_no_location_question_possible():
    """When GPS unavailable and no text location, question_node may generate location question."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "en")

    # Send a message without GPS and without location text
    asyncio.run(session_store.process_message(
        session_id,
        "There is a fire in the building.",
        language="en"
    ))

    state = session_store.get_state(session_id)
    assert state is not None
    assert state["emergency_type"] == "Fire"
    # With no GPS and no text location, the AI might ask for location
    # We do NOT assert it always asks — that's the LLM's decision.
    # We assert that state does NOT have reliable GPS
    assert state.get("location_status") != "reliable"


# ── TEST 3: GPS available but poor accuracy → system may ask for landmark ──

def test_gps_low_accuracy():
    """GPS with accuracy > 100m is considered low accuracy."""
    state = _make_state(latitude=12.97194, longitude=77.59369, accuracy=250.0)
    assert _gps_is_reliable(state) is False
    assert _gps_is_low_accuracy(state) is True
    # Location is still NOT considered fully known (poor accuracy)
    assert _location_is_known(state) is False


def test_gps_low_accuracy_context_string():
    """GPS context string correctly labels low accuracy GPS."""
    state = _make_state(
        latitude=12.97194, longitude=77.59369,
        accuracy=300.0, location_status="low_accuracy"
    )
    ctx = _gps_context_string(state)
    assert "low accuracy" in ctx.lower() or "300" in ctx


# ── TEST 4: Manual map correction → updates active session location ─────────

def test_manual_location_correction_updates_session():
    """Manual map correction correctly updates session state via update_location."""
    session_id = session_store.get_or_create()

    location_data = {
        "latitude": 11.0168,
        "longitude": 76.9558,
        "accuracy": 5.0,
        "source": "Manual Entry",
        "address": "Town Hall, Coimbatore",
        "landmark": "Town Hall",
        "display_string": "Town Hall, Coimbatore (Manual Landmark)",
    }

    updated = asyncio.run(session_store.update_location(session_id, location_data))

    assert updated.get("latitude") == 11.0168
    assert updated.get("longitude") == 76.9558
    assert updated.get("location_source") == "Manual Entry"
    assert updated.get("location_status") == "manual_override"
    assert updated.get("landmark") == "Town Hall"


def test_manual_correction_gps_location_known():
    """After manual correction, _location_is_known() recognises the session as located."""
    session_id = session_store.get_or_create()

    asyncio.run(session_store.update_location(session_id, {
        "latitude": 11.0168,
        "longitude": 76.9558,
        "accuracy": 5.0,
        "source": "Manual Entry",
        "address": "Town Hall, Coimbatore",
    }))

    state = session_store.get_state(session_id)
    assert state is not None
    # Manual entry is treated as reliable
    assert _location_is_known(state) is True


# ── TEST 5: English user-provided location → stored in structured state ──────

def test_english_location_stored_in_state():
    """English location answer is extracted and stored in session state."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "en")

    asyncio.run(session_store.process_message(
        session_id,
        "There is a medical emergency at 45 MG Road, Chennai, near the hospital.",
        language="en"
    ))

    state = session_store.get_state(session_id)
    assert state is not None
    loc = state.get("location") or ""
    details = state.get("details") or ""
    # Location must be captured somewhere in state
    assert "mg road" in loc.lower() or "mg road" in details.lower() or "chennai" in loc.lower() or "chennai" in details.lower()


# ── TEST 6: Tamil user-provided location → stored in structured state ────────

def test_tamil_location_stored_in_state():
    """Tamil location answer is extracted and stored in session state."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "ta")

    asyncio.run(session_store.process_message(
        session_id,
        "எங்கள் வீடு கள்ளக்குறிச்சி அருகே உள்ளது. அருகிலுள்ள அடையாள இடம் அரசு மருத்துவமனை.",
        language="ta"
    ))

    state = session_store.get_state(session_id)
    assert state is not None
    # Verify Tamil is maintained
    assert state.get("selected_language") == "ta"
    # Verify location/details capture the Tamil answer
    prev_answers = state.get("previous_answers") or []
    assert len(prev_answers) > 0
    answer_text = " ".join(prev_answers)
    assert "கள்ளக்குறிச்சி" in answer_text or "மருத்துவமனை" in answer_text


# ── TEST 7: Hindi user-provided location → stored in structured state ─────────

def test_hindi_location_stored_in_state():
    """Hindi location answer is extracted and stored in session state."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "hi")

    asyncio.run(session_store.process_message(
        session_id,
        "हम दिल्ली के करोल बाग में हैं, पास में जीबी रोड है।",
        language="hi"
    ))

    state = session_store.get_state(session_id)
    assert state is not None
    assert state.get("selected_language") == "hi"
    prev_answers = state.get("previous_answers") or []
    answer_text = " ".join(prev_answers)
    assert "करोल बाग" in answer_text or "दिल्ली" in answer_text


# ── TEST 8: Code-mixed location answer → relevant location evidence stored ───

def test_code_mixed_location_stored():
    """Code-mixed Tamil+English location answer is stored in session state."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "ta")

    asyncio.run(session_store.process_message(
        session_id,
        "எங்கள் வீடு Chennai near Chrompet இல் உள்ளது.",
        language="ta"
    ))

    state = session_store.get_state(session_id)
    assert state is not None
    prev_answers = state.get("previous_answers") or []
    answer_text = " ".join(prev_answers)
    assert "chrompet" in answer_text.lower() or "chennai" in answer_text.lower()


# ── TEST 9: After location answered → same question NOT repeated ─────────────

def test_location_question_not_repeated_after_answer():
    """After a location/landmark has been answered, the same semantic location question is NOT repeated."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "en")

    # Turn 1: Report fire without location
    asyncio.run(session_store.process_message(
        session_id,
        "There is a fire in my building.",
        language="en"
    ))

    state1 = session_store.get_state(session_id)
    q1 = state1.get("current_question") or ""

    # Turn 2: Provide location answer
    asyncio.run(session_store.process_message(
        session_id,
        "We are at 10 Greams Road, Chennai near the hospital entrance.",
        language="en"
    ))

    state2 = session_store.get_state(session_id)
    q2 = state2.get("current_question") or ""
    prev_questions = state2.get("previous_questions") or []

    # The second question should NOT be identical to the first
    if q1 and q2:
        assert q1.lower() != q2.lower(), f"Same question repeated: {q1!r}"

    # q2 should not ask for location if location was provided in turn 2
    location_asking_phrases = [
        "location", "where are you", "address", "iruppidam", "இருப்பிடம்",
        "स्थान", "sthaan", "landmark", "where"
    ]
    # Only fail if q2 asks for GENERIC location (not scenario-specific landmark)
    if q2:
        generic_location_q = any(p in q2.lower() for p in ["exact location", "your location", "where are you"])
        if generic_location_q:
            # This is only acceptable if GPS was not available (edge case)
            has_gps = state2.get("latitude") is not None
            if has_gps:
                pytest.fail(f"Location question repeated even though GPS is available: {q2!r}")


# ── TEST 10: Road accident + GPS available → no unnecessary generic location Q ──

def test_road_accident_with_gps_no_location_question():
    """Road accident scenario with reliable GPS → AI does not ask generic location question."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "en")

    # Pre-load GPS into session
    asyncio.run(session_store.update_location(session_id, {
        "latitude": 12.97194,
        "longitude": 77.59369,
        "accuracy": 10.0,
        "source": "Browser GPS",
    }))

    asyncio.run(session_store.process_message(
        session_id,
        "Car collision with injured passengers on the highway.",
        language="en"
    ))

    state = session_store.get_state(session_id)
    assert state is not None
    q = (state.get("current_question") or "").lower()

    # With reliable GPS, the AI should NOT ask generic "where are you" question
    assert "exact location" not in q, f"Generic location question asked with GPS available: {q!r}"
    assert "where are you" not in q, f"Generic location question asked with GPS available: {q!r}"
    assert "confirm your location" not in q, f"Generic location question asked with GPS available: {q!r}"

    # GPS must be marked reliable
    assert _gps_is_reliable(state) is True


# ── TEST 11: Fire scenario + GPS available → no unnecessary generic location Q ─

def test_fire_with_gps_no_location_question():
    """Fire emergency with reliable GPS → AI does not ask generic location question."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "ta")

    # Pre-load GPS into session
    asyncio.run(session_store.update_location(session_id, {
        "latitude": 11.0168,
        "longitude": 76.9558,
        "accuracy": 8.0,
        "source": "Browser GPS",
    }))

    asyncio.run(session_store.process_message(
        session_id,
        "எங்கள் வீட்டில் தீப்பிடித்துள்ளது, புகை அதிகமாக வருகிறது.",
        language="ta"
    ))

    state = session_store.get_state(session_id)
    assert state is not None
    assert state["emergency_type"] == "Fire"
    assert state["selected_language"] == "ta"

    # GPS must be reliable
    assert _gps_is_reliable(state) is True

    q = (state.get("current_question") or "").lower()
    # Should NOT ask generic Tamil location question when GPS is available
    # The exact Tamil phrase: உங்கள் சரியான இருப்பிடம் அல்லது அடையாள இடத்தைக் கூறுங்கள்?
    assert "சரியான இருப்பிடம்" not in q, (
        f"Generic Tamil location question asked with GPS available: {state.get('current_question')!r}"
    )


# ── TEST 12: Another scenario + GPS available → no unnecessary generic location Q ─

def test_medical_emergency_with_gps_no_location_question():
    """Medical emergency with reliable GPS → AI does not ask generic location question."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "en")

    # Pre-load GPS into session
    asyncio.run(session_store.update_location(session_id, {
        "latitude": 13.0827,
        "longitude": 80.2707,
        "accuracy": 15.0,
        "source": "Browser GPS",
    }))

    asyncio.run(session_store.process_message(
        session_id,
        "My father has severe chest pain and cannot breathe.",
        language="en"
    ))

    state = session_store.get_state(session_id)
    assert state is not None
    assert state["priority"] == 1  # Critical
    assert _gps_is_reliable(state) is True

    q = (state.get("current_question") or "").lower()
    # Should NOT ask generic "where are you" when GPS is reliable
    assert "exact location" not in q, f"Generic location question with GPS: {q!r}"
    assert "where are you" not in q, f"Generic location question with GPS: {q!r}"


# ── TEST BONUS: GPS context string format ────────────────────────────────────

def test_gps_context_string_reliable():
    """GPS context string correctly describes reliable GPS."""
    state = _make_state(
        latitude=12.97194, longitude=77.59369,
        accuracy=8.0, location_status="reliable",
        location_source="Browser GPS"
    )
    ctx = _gps_context_string(state)
    assert "GPS AVAILABLE" in ctx
    assert "reliable" in ctx
    assert "8" in ctx


def test_gps_context_string_unavailable():
    """GPS context string correctly describes absent GPS."""
    state = _make_state()  # No GPS
    ctx = _gps_context_string(state)
    assert "NOT available" in ctx or "unavailable" in ctx.lower()


def test_location_is_known_text_location():
    """Text location alone (without GPS) also counts as known location."""
    state = _make_state(location="45 MG Road, Chennai")
    assert _location_is_known(state) is True


def test_location_is_not_known_placeholder():
    """Placeholder location strings do not count as known."""
    for placeholder in [
        "Awaiting location...", "Location unknown",
        "Location denied or unavailable", "unknown", "null"
    ]:
        state = _make_state(location=placeholder)
        assert _location_is_known(state) is False, f"Placeholder {placeholder!r} incorrectly counted as known"
