import base64
import datetime
import logging
import urllib.parse
from typing import Optional

from fastapi import APIRouter, HTTPException, Body, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.ai.schemas import (
    MessageInput,
    MessageResponse,
    QuestionResponse,
    StatusResponse,
    SummaryResponse,
    VideoEvidenceInput,
)
from app.routes.dispatcher import broadcast_emergency_update
from app.services.session_service import session_store
from app.services.tts_service import TTSService
from app.services.gemini_vision_service import GeminiVisionService

logger = logging.getLogger(__name__)
router = APIRouter()
tts_service = TTSService()
gemini_vision_service = GeminiVisionService()


# ── Payload Schemas for Media / Sensor Data ───────────────────────

class ImageFrameInput(BaseModel):
    session_id: str
    image_data: str = Field(..., description="Base64 encoded JPEG/PNG/WEBP image frame")
    label: Optional[str] = "Live Evidence Frame"
    source: Optional[str] = Field("camera", description="'upload' | 'camera' | 'snapshot'")
    scene: Optional[str] = Field("general", description="Selected emergency scene (road_accident, fire, medical, public_safety, general)")


class SensorDataInput(BaseModel):
    session_id: str
    heart_rate: Optional[int] = None
    spo2: Optional[int] = None
    device_name: Optional[str] = "Bluetooth Sensor"
    status: Optional[str] = "Connected"
    notes: Optional[str] = None


class ServiceSelectInput(BaseModel):
    session_id: str
    service: str = Field(..., description="Selected service: ambulance, police, fire, rescue, bluecross")


class LocationUpdateInput(BaseModel):
    """
    GPS / map / manual location data sent from the frontend.
    Covers both browser GPS and manual-correction scenarios.
    """
    session_id: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = Field(None, description="Accuracy radius in metres")
    source: Optional[str] = Field("Browser GPS", description="'Browser GPS' | 'Manual Entry' | 'IP Fallback'")
    address: Optional[str] = None
    landmark: Optional[str] = None
    display_string: Optional[str] = None
    is_low_accuracy: Optional[bool] = None
    timestamp: Optional[str] = None


# ── Message / Dialogue ───────────────────────────────────────────

@router.post("/message", response_model=MessageResponse)
async def receive_message(body: MessageInput):
    """
    Receive a caller sentence and process it through the AI pipeline.
    """
    try:
        session_store.get_or_create(body.session_id)

        await session_store.process_message(body.session_id, body.message, language=body.language)

        # Broadcast real-time incident update to connected Dispatcher Dashboards
        state = session_store.get_state(body.session_id) or {}
        await broadcast_emergency_update({
            "session_id": body.session_id,
            "transcript": state.get("translated_transcript") or body.message,
            "original_transcript": state.get("original_transcript") or body.message,
            "caller_language": state.get("detected_language") or body.language,
            "language": state.get("selected_language") or "en",
            "severity": state.get("priority_label"),
            "score": state.get("priority_score"),
            "summary": state.get("summary"),
            "status": state.get("status", "gathering_info"),
            "emergency_type": state.get("emergency_type"),
            "location": state.get("location"),
            "caller_name": state.get("caller_name"),
            "caller_age": state.get("caller_age"),
            "caller_phone": state.get("caller_phone"),
            "casualties": state.get("casualties"),
            "guidance": state.get("guidance"),
            "current_question": state.get("current_question"),
            "missing_info": state.get("missing_info", []),
            "sop_steps": state.get("sop_steps"),
            "dispatch_plan": state.get("dispatch_plan", []),
            "routed_service": state.get("routed_service"),
            "fake_probability": state.get("fake_probability"),
            "fake_label": state.get("fake_label"),
            "fake_signals": state.get("fake_signals", []),
            "selected_service": state.get("selected_service"),
            "sensor_telemetry": state.get("sensor_telemetry"),
            "captured_images": state.get("captured_images", []),
            "turn_count": state.get("turn_count", 0),
            "known_facts": state.get("known_facts", {}),
            # GPS / location telemetry
            "latitude": state.get("latitude"),
            "longitude": state.get("longitude"),
            "location_accuracy": state.get("location_accuracy"),
            "location_source": state.get("location_source"),
            "location_status": state.get("location_status"),
            "location_display": state.get("location_display"),
        })

        return MessageResponse(success=True, session_id=body.session_id)
    except Exception as e:
        logger.error("Pipeline error for session %s: %s", body.session_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


# ── Emergency Service Selection ───────────────────────────────────

@router.post("/service")
async def select_service(body: ServiceSelectInput):
    """
    Record user-selected emergency service and broadcast update to dispatchers.
    """
    session_store.set_selected_service(body.session_id, body.service)
    state = session_store.get_state(body.session_id) or {}
    await broadcast_emergency_update({
        "session_id": body.session_id,
        "selected_service": body.service,
        "emergency_type": state.get("emergency_type") or body.service.capitalize(),
        "status": state.get("status", "gathering_info"),
    })
    return {"success": True, "session_id": body.session_id, "selected_service": body.service}


# ── GPS / Location Update ─────────────────────────────────────────

@router.post("/location")
async def update_location(body: LocationUpdateInput):
    """
    Receive GPS or manual-correction location from the caller's device.

    This endpoint persists live GPS coordinates (latitude, longitude, accuracy,
    source) directly into the active IncidentState so the LangGraph AI pipeline
    has access to the location before — and between — every caller message.

    The AI question generator uses this state to skip the generic 'Where are you?'
    question when reliable GPS is already available.
    """
    location_data = {
        "latitude": body.latitude,
        "longitude": body.longitude,
        "accuracy": body.accuracy,
        "source": body.source or "Browser GPS",
        "address": body.address,
        "landmark": body.landmark,
        "display_string": body.display_string,
        "is_low_accuracy": body.is_low_accuracy,
        "timestamp": body.timestamp,
    }

    updated_state = await session_store.update_location(body.session_id, location_data)

    # Broadcast updated location to dispatcher dashboard in real-time
    await broadcast_emergency_update({
        "session_id": body.session_id,
        "latitude": updated_state.get("latitude"),
        "longitude": updated_state.get("longitude"),
        "location_accuracy": updated_state.get("location_accuracy"),
        "location_source": updated_state.get("location_source"),
        "location_status": updated_state.get("location_status"),
        "location_display": updated_state.get("location_display"),
        "location": updated_state.get("location"),
    })

    logger.info(
        "Location updated for session %s: source=%s lat=%.5f lon=%.5f acc=%.1fm status=%s",
        body.session_id,
        updated_state.get("location_source"),
        updated_state.get("latitude") or 0,
        updated_state.get("longitude") or 0,
        updated_state.get("location_accuracy") or 0,
        updated_state.get("location_status"),
    )
    return {
        "success": True,
        "session_id": body.session_id,
        "location_status": updated_state.get("location_status"),
        "location_display": updated_state.get("location_display"),
    }


# ── Camera / Image Evidence Upload ───────────────────────────────

@router.post("/image")
async def upload_image_frame(body: ImageFrameInput):
    """
    Receive, analyze with Gemini Vision, and store visual evidence from caller device.
    Associates the frame with the emergency session and notifies dispatchers in real-time.
    """
    if not body.image_data:
        raise HTTPException(status_code=400, detail="Missing image data")

    # Validate image data format (Data URL or base64)
    if not (body.image_data.startswith("data:image/") or len(body.image_data) > 50):
        raise HTTPException(status_code=400, detail="Invalid image payload format")

    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Analyze with Gemini Vision (returns structured observations or graceful fallback)
    analysis_result = await gemini_vision_service.analyze_image(
        body.image_data, scene=body.scene or "general"
    )
    observations = analysis_result.get("observations", [])

    frame_record = {
        "timestamp": timestamp,
        "label": body.label or ("Uploaded Evidence" if body.source == "upload" else "Emergency Evidence"),
        "image_data": body.image_data,
        "source": body.source or "camera",
        "scene": body.scene or "general",
        "observations": observations,
    }

    await session_store.add_captured_image(body.session_id, frame_record)

    # Broadcast frame notice to dispatcher dashboard
    await broadcast_emergency_update({
        "session_id": body.session_id,
        "new_evidence_frame": {
            "timestamp": timestamp,
            "label": frame_record["label"],
            "has_image": True,
            "source": frame_record["source"],
            "scene": frame_record["scene"],
            "observations": observations,
        },
    })

    logger.info(
        "Visual evidence received for session %s (source=%s, scene=%s, %d observations)",
        body.session_id, frame_record["source"], frame_record["scene"], len(observations)
    )
    return {
        "status": analysis_result.get("status", "ok"),
        "success": analysis_result.get("success", True),
        "session_id": body.session_id,
        "timestamp": timestamp,
        "source": frame_record["source"],
        "scene": frame_record["scene"],
        "observations": observations,
        "message": analysis_result.get("message", "Visual evidence received and analyzed"),
    }


# ── Video Evidence Upload ─────────────────────────────────────────

@router.post("/evidence/video")
async def upload_video_evidence(body: VideoEvidenceInput):
    """
    Receive and store emergency video + audio evidence recording metadata.
    Associates the evidence with the emergency session and broadcasts to dispatchers.
    """
    timestamp = body.timestamp or datetime.datetime.now(datetime.timezone.utc).isoformat()
    video_record = {
        "timestamp": timestamp,
        "category": body.category or "general",
        "duration_seconds": body.duration_seconds or 0.0,
        "video_data": body.video_data,
        "location": body.location,
        "notes": body.notes,
    }

    await session_store.add_video_evidence(body.session_id, video_record)

    # Broadcast video evidence alert to dispatcher dashboard
    await broadcast_emergency_update({
        "session_id": body.session_id,
        "new_video_evidence": {
            "timestamp": timestamp,
            "category": video_record["category"],
            "duration_seconds": video_record["duration_seconds"],
            "has_video": bool(video_record["video_data"]),
            "location": video_record["location"],
        },
    })

    logger.info(
        "Video evidence received for session %s (category: %s, duration: %ss)",
        body.session_id, body.category, body.duration_seconds
    )
    return {
        "success": True,
        "session_id": body.session_id,
        "timestamp": timestamp,
        "category": body.category,
        "message": "Video evidence successfully recorded and linked to session",
    }


# ── Bluetooth / Sensor Telemetry Upload ───────────────────────────

@router.post("/sensor-data")
async def receive_sensor_data(body: SensorDataInput):
    """
    Receive real-time biometric telemetry (e.g. Heart Rate, SpO2) from Web Bluetooth.
    Injects vital signs into the emergency session state and broadcasts to dispatchers.
    """
    telemetry = {
        "heart_rate": body.heart_rate,
        "spo2": body.spo2,
        "device_name": body.device_name,
        "status": body.status,
        "notes": body.notes,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    await session_store.update_sensor_telemetry(body.session_id, telemetry)

    # Broadcast vital signs update to dispatcher dashboard
    await broadcast_emergency_update({
        "session_id": body.session_id,
        "sensor_telemetry": telemetry,
    })

    logger.info("Sensor telemetry received for session %s: HR=%s", body.session_id, body.heart_rate)
    return {
        "success": True,
        "session_id": body.session_id,
        "telemetry": telemetry,
    }


# ── Questions & Audio (TTS) ──────────────────────────────────────

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
        question=state.get("caller_question") or state.get("current_question") if state else None,
        guidance=state.get("caller_guidance") or state.get("guidance") if state else None,
    )


@router.get("/question/{session_id}/audio")
async def get_question_audio(session_id: str, lang: Optional[str] = None, text: Optional[str] = None):
    """
    Synthesize and stream the exact requested message text or current AI question/guidance as valid WAV audio (TTS) in the caller's language.
    """
    state = session_store.get_state(session_id)
    if state is None:
        # Create or fetch session gracefully
        session_store.get_or_create(session_id)
        state = session_store.get_state(session_id)

    # Priority: explicit caller language requested -> detected caller language -> session selected language -> fallback en
    caller_lang = lang or (state.get("detected_language") if state else None) or (state.get("selected_language") if state else None) or "en"

    # Use explicit message text if provided (message-bound TTS), otherwise fallback to caller question
    question = (text.strip() if text and text.strip() else None) or (state.get("caller_question") if state else None) or (state.get("caller_guidance") if state else None) or session_store.get_question(session_id, lang=caller_lang) or (state.get("guidance") if state else None)

    if not question:
        if caller_lang == "ta":
            question = "அவசர சேவை செயல்படுகிறது. என்ன நடந்தது என்பதை விவரிக்கவும்."
        elif caller_lang == "hi":
            question = "आपातकालीन सेवा सक्रिय है। कृपया बताएं क्या हुआ है।"
        else:
            question = "Emergency service active. Please describe what happened."

    try:
        b64_audio = tts_service.synthesize_base64_audio(question, language_code=caller_lang)
        if not b64_audio:
            raise HTTPException(status_code=502, detail="TTS service returned no audio data")

        audio_bytes = base64.b64decode(b64_audio)
        safe_header_text = urllib.parse.quote(question.replace("\n", " ")[:200])

        return Response(
            content=audio_bytes,
            media_type="audio/wav",
            headers={
                "Content-Type": "audio/wav",
                "Content-Length": str(len(audio_bytes)),
                "X-Question-Text": safe_header_text,
                "Access-Control-Expose-Headers": "X-Question-Text",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("TTS error for session %s: %s", session_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"TTS error: {str(e)}")


@router.get("/question/{session_id}/full")
async def get_question_with_text(session_id: str, lang: Optional[str] = None):
    """
    Return both the raw text (for subtitles) and the audio URL for the
    current AI question in caller language.
    """
    state = session_store.get_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    caller_lang = lang or state.get("detected_language") or state.get("selected_language") or "en"
    question = state.get("caller_question") or state.get("current_question")
    guidance = state.get("caller_guidance") or state.get("guidance")

    return JSONResponse({
        "session_id": session_id,
        "question": question,
        "guidance": guidance,
        "audio_url": f"/api/call/question/{session_id}/audio?lang={caller_lang}" if question else None,
    })



# ── Status & Summary ─────────────────────────────────────────────

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
                    caller_guidance=doc.get("caller_guidance"),
                    current_question=doc.get("current_question"),
                    caller_question=doc.get("caller_question"),
                    routed_service=doc.get("routed_service"),
                    sop_steps=doc.get("sop_steps"),
                    dispatcher_notes=doc.get("dispatcher_notes"),
                    dispatch_plan=doc.get("dispatch_plan", []),
                    status=doc.get("status", "gathering_info"),
                    turn_count=doc.get("turn_count", 0),
                    messages=doc.get("messages", []),
                    captured_images=doc.get("captured_images", []),
                    video_evidence=doc.get("video_evidence", []),
                    sensor_telemetry=doc.get("sensor_telemetry"),
                    selected_service=doc.get("selected_service"),
                    selected_language=doc.get("selected_language"),
                    detected_language=doc.get("detected_language"),
                    original_transcript=doc.get("original_transcript"),
                    translated_transcript=doc.get("translated_transcript"),
                )
        except Exception as e:
            logger.warning("MongoDB lookup failed for %s: %s", session_id, e)

        raise HTTPException(status_code=404, detail="Session not found")

    from app.services.mongo_service import _serialize_messages
    return SummaryResponse(
        session_id=session_id,
        emergency_type=state.get("emergency_type"),
        location=state.get("location"),
        landmark=state.get("landmark"),
        latitude=state.get("latitude"),
        longitude=state.get("longitude"),
        location_accuracy=state.get("location_accuracy"),
        location_source=state.get("location_source"),
        location_status=state.get("location_status"),
        location_display=state.get("location_display"),
        details=state.get("details"),
        priority=state.get("priority"),
        priority_score=state.get("priority_score"),
        priority_label=state.get("priority_label"),
        caller_name=state.get("caller_name"),
        caller_age=state.get("caller_age"),
        caller_phone=state.get("caller_phone"),
        casualties=state.get("casualties"),
        summary=state.get("summary"),
        guidance=state.get("guidance"),
        caller_guidance=state.get("caller_guidance"),
        current_question=state.get("current_question"),
        caller_question=state.get("caller_question"),
        missing_info=state.get("missing_info", []),
        routed_service=state.get("routed_service"),
        sop_steps=state.get("sop_steps"),
        dispatcher_notes=state.get("dispatcher_notes"),
        dispatch_plan=state.get("dispatch_plan", []),
        fake_probability=state.get("fake_probability"),
        fake_label=state.get("fake_label"),
        fake_signals=state.get("fake_signals", []),
        status=state.get("status", "gathering_info"),
        turn_count=state.get("turn_count", 0),
        messages=_serialize_messages(state.get("messages", [])),
        captured_images=state.get("captured_images", []),
        video_evidence=state.get("video_evidence", []),
        sensor_telemetry=state.get("sensor_telemetry"),
        selected_service=state.get("selected_service"),
        selected_language=state.get("selected_language") or state.get("language"),
        detected_language=state.get("detected_language"),
        original_transcript=state.get("original_transcript"),
        translated_transcript=state.get("translated_transcript"),
        known_facts=state.get("known_facts", {}),
        previous_questions=state.get("previous_questions", []),
    )


# ── Session Management ───────────────────────────────────────────

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
