import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.ai.schemas import (
    MessageInput,
    MessageResponse,
    QuestionResponse,
    StatusResponse,
    SummaryResponse,
)
from app.services.session_service import session_store
from app.services.tts_service import TTSService

logger = logging.getLogger(__name__)
router = APIRouter()
tts_service = TTSService()


@router.post("/message", response_model=MessageResponse)
async def receive_message(body: MessageInput):
    """
    Receive a caller sentence and process it through the AI pipeline.
    """
    try:
        session_store.get_or_create(body.session_id)
        await session_store.process_message(body.session_id, body.message)
        return MessageResponse(success=True, session_id=body.session_id)
    except Exception as e:
        logger.error("Pipeline error for session %s: %s", body.session_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


@router.get("/question/{session_id}", response_model=QuestionResponse)
async def get_question(session_id: str):
    """
    Get the AI's current follow-up question and guidance for this session.
    """
    if session_store.get_state(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")

    state = session_store.get_state(session_id)
    return QuestionResponse(
        session_id=session_id,
        question=state.get("current_question") if state else None,
        guidance=state.get("guidance") if state else None,
    )


@router.get("/question/{session_id}/audio")
async def get_question_audio(session_id: str, lang: str = "ta"):
    """
    Stream the current AI question as audio (TTS) AND return the raw text
    as a header for subtitle display.
    """
    if session_store.get_state(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")

    question = session_store.get_question(session_id)
    if not question:
        raise HTTPException(status_code=404, detail="No question available to synthesize")

    try:
        return StreamingResponse(
            tts_service.stream_speech(question, language_code=lang),
            media_type="audio/wav",
            headers={
                "X-Question-Text": question.replace("\n", " "),
                "Access-Control-Expose-Headers": "X-Question-Text",
            },
        )
    except Exception as e:
        logger.error("TTS error for session %s: %s", session_id, e)
        raise HTTPException(status_code=500, detail=f"TTS error: {str(e)}")


@router.get("/question/{session_id}/full")
async def get_question_with_text(session_id: str, lang: str = "hi"):
    """
    Return both the raw text (for subtitles) and the audio URL for the
    current AI question. The frontend can display the text immediately
    while streaming the audio.
    """
    state = session_store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    question = state.get("current_question")
    guidance = state.get("guidance")

    return JSONResponse({
        "session_id": session_id,
        "question": question,
        "guidance": guidance,
        "audio_url": f"/api/call/question/{session_id}/audio?lang={lang}" if question else None,
    })


@router.get("/status/{session_id}", response_model=StatusResponse)
async def get_status(session_id: str):
    """
    Get the full structured incident data for this session.
    """
    incident = session_store.get_incident_data(session_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return StatusResponse(
        session_id=session_id,
        incident=incident,
        conversation_turns=session_store.get_turn_count(session_id),
    )


@router.get("/summary/{session_id}", response_model=SummaryResponse)
async def get_summary(session_id: str):
    """
    Get a full session summary from agent state and LLM memory.
    Combines in-memory state with MongoDB persisted data.
    """
    # Try in-memory first
    state = session_store.get_state(session_id)

    if state is None:
        # Fallback to MongoDB
        try:
            from app.services.mongo_service import get_session_summary
            doc = await get_session_summary(session_id)
            if doc:
                return SummaryResponse(
                    session_id=session_id,
                    emergency_type=doc.get("emergency_type"),
                    location=doc.get("location"),
                    details=doc.get("details"),
                    priority=doc.get("priority"),
                    caller_name=doc.get("caller_name"),
                    caller_age=doc.get("caller_age"),
                    caller_phone=doc.get("caller_phone"),
                    casualties=doc.get("casualties"),
                    summary=doc.get("summary"),
                    guidance=doc.get("guidance"),
                    routed_service=doc.get("routed_service"),
                    sop_steps=doc.get("sop_steps"),
                    dispatcher_notes=doc.get("dispatcher_notes"),
                    dispatch_plan=doc.get("dispatch_plan", []),
                    status=doc.get("status", "gathering_info"),
                    turn_count=doc.get("turn_count", 0),
                    messages=doc.get("messages", []),
                )
        except Exception as e:
            logger.warning("MongoDB lookup failed for %s: %s", session_id, e)

        raise HTTPException(status_code=404, detail="Session not found")

    # Build from in-memory state
    from app.services.mongo_service import _serialize_messages
    return SummaryResponse(
        session_id=session_id,
        emergency_type=state.get("emergency_type"),
        location=state.get("location"),
        details=state.get("details"),
        priority=state.get("priority"),
        caller_name=state.get("caller_name"),
        caller_age=state.get("caller_age"),
        caller_phone=state.get("caller_phone"),
        casualties=state.get("casualties"),
        summary=state.get("summary"),
        guidance=state.get("guidance"),
        routed_service=state.get("routed_service"),
        sop_steps=state.get("sop_steps"),
        dispatcher_notes=state.get("dispatcher_notes"),
        dispatch_plan=state.get("dispatch_plan", []),
        status=state.get("status", "gathering_info"),
        turn_count=state.get("turn_count", 0),
        messages=_serialize_messages(state.get("messages", [])),
    )


@router.get("/sessions")
async def list_sessions():
    """List all active session IDs (in-memory + MongoDB)."""
    in_memory = session_store.list_sessions()
    try:
        from app.services.mongo_service import list_all_sessions
        db_sessions = await list_all_sessions()
        return {"in_memory": in_memory, "persisted": db_sessions}
    except Exception:
        return {"in_memory": in_memory, "persisted": []}


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """Delete (end) an active call session from memory and database."""
    deleted_memory = session_store.delete(session_id)
    deleted_db = False
    try:
        from app.services.mongo_service import delete_session_db
        deleted_db = await delete_session_db(session_id)
    except Exception as e:
        logger.warning("MongoDB delete failed for %s: %s", session_id, e)

    if not deleted_memory and not deleted_db:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": session_id, "from_memory": deleted_memory, "from_db": deleted_db}
