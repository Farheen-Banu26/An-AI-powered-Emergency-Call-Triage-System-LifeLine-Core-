import pytest
from app.services.session_service import session_store
from app.services.severity_service import SeverityService


def test_tamil_emergency_language_preservation():
    """Test Tamil selected + Tamil emergency returns Tamil question, guidance, and critical priority."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "ta")

    # Severity scoring verification
    severity = SeverityService()
    scoring = severity.evaluate("என் அப்பா மயக்கமடைந்து மூச்சு விடவில்லை")
    assert scoring["priority_score"] >= 8
    assert "CRITICAL" in scoring["priority_label"]

    # Verify session store processing
    import asyncio
    asyncio.run(session_store.process_message(session_id, "என் அப்பா மயக்கமடைந்து மூச்சு விடவில்லை", language="ta"))

    state = session_store.get_state(session_id)
    assert state is not None
    assert state["language"] == "ta"
    assert state["priority"] == 1

    question = state.get("current_question") or ""
    guidance = state.get("guidance") or ""

    # Must contain Tamil characters (\u0B80 - \u0BFF)
    assert any('\u0B80' <= ch <= '\u0BFF' for ch in question), f"Expected Tamil question, got: {question}"
    assert any('\u0B80' <= ch <= '\u0BFF' for ch in guidance), f"Expected Tamil guidance, got: {guidance}"
    assert "Can you tell me" not in question
    assert "Is he conscious" not in question


def test_hindi_emergency_language_preservation():
    """Test Hindi selected + Hindi emergency returns Hindi question, guidance, and critical priority."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "hi")

    severity = SeverityService()
    scoring = severity.evaluate("मेरे पिताजी बेहोश हैं और सांस नहीं ले रहे हैं।")
    assert scoring["priority_score"] >= 8
    assert "CRITICAL" in scoring["priority_label"]

    import asyncio
    asyncio.run(session_store.process_message(session_id, "मेरे पिताजी बेहोश हैं और सांस नहीं ले रहे हैं।", language="hi"))

    state = session_store.get_state(session_id)
    assert state is not None
    assert state["language"] == "hi"
    assert state["priority"] == 1

    question = state.get("current_question") or ""
    guidance = state.get("guidance") or ""

    # Must contain Devanagari characters (\u0900 - \u097F)
    assert any('\u0900' <= ch <= '\u097F' for ch in question), f"Expected Hindi question, got: {question}"
    assert any('\u0900' <= ch <= '\u097F' for ch in guidance), f"Expected Hindi guidance, got: {guidance}"


def test_english_emergency_preservation():
    """Test English selected + English emergency returns English throughout."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "en")

    import asyncio
    asyncio.run(session_store.process_message(session_id, "My father is unconscious and not breathing.", language="en"))

    state = session_store.get_state(session_id)
    assert state is not None
    assert state["language"] == "en"
    assert state["priority"] == 1

    question = state.get("current_question") or ""
    guidance = state.get("guidance") or ""

    assert len(question) > 0
    assert len(guidance) > 0
    assert not any('\u0B80' <= ch <= '\u0BFF' for ch in question)
    assert not any('\u0900' <= ch <= '\u097F' for ch in question)


def test_code_mixed_tamil_english():
    """Test code-mixed speech preserves Tamil as primary language."""
    session_id = session_store.get_or_create()
    session_store.set_language(session_id, "ta")

    import asyncio
    asyncio.run(session_store.process_message(session_id, "எனக்கு chest pain இருக்கு.", language="ta"))

    state = session_store.get_state(session_id)
    assert state is not None
    assert state["language"] == "ta"

    question = state.get("current_question") or ""
    assert any('\u0B80' <= ch <= '\u0BFF' for ch in question), f"Expected Tamil question, got: {question}"


def test_dynamic_language_switching():
    """Test dynamic language switching across turns within a single session."""
    session_id = session_store.get_or_create()

    import asyncio
    # Turn 1: English
    session_store.set_language(session_id, "en")
    asyncio.run(session_store.process_message(
        session_id,
        "A chemical container fell and people feel dizzy at Warehouse 4.",
        language="en"
    ))
    s1 = session_store.get_state(session_id)
    assert s1["selected_language"] == "en"

    # Turn 2: Switch to Tamil
    session_store.set_language(session_id, "ta")
    asyncio.run(session_store.process_message(
        session_id,
        "மூன்று பேர் மயங்கிவிட்டனர், உடனே உதவி தேவை.",
        language="ta"
    ))
    s2 = session_store.get_state(session_id)
    assert s2["selected_language"] == "ta"
    assert s2["casualties"] >= 1
    q2 = s2.get("current_question") or s2.get("guidance") or ""
    assert any('\u0B80' <= ch <= '\u0BFF' for ch in q2)
