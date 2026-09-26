import asyncio
import logging
import threading
import uuid
from typing import Optional

from langchain_core.messages import HumanMessage

from app.ai.schemas import IncidentData
from app.ai.state import IncidentState
from app.ai.workflow import emergency_workflow
from app.services.severity_service import SeverityService
from app.services.translation_service import translation_service

logger = logging.getLogger(__name__)


def _empty_state() -> IncidentState:
    """Create a blank incident state."""
    return IncidentState(
        messages=[],
        emergency_type=None,
        scenario_category=None,
        location=None,
        landmark=None,
        latitude=None,
        longitude=None,
        location_accuracy=None,
        location_source=None,
        location_status=None,
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
        fake_signals=[],
        _llm_fake_score=None,
        captured_images=[],
        sensor_telemetry=None,
        selected_service=None,
        language="en",
        selected_language="en",
        input_language="en",
        detected_language="en",
        response_language="en",
        original_transcript=None,
        translated_transcript=None,
        caller_question=None,
        caller_guidance=None,
        known_facts={},
        previous_questions=[],
        previous_answers=[],
        missing_info=[],
        current_question=None,
        status="gathering_info",
        turn_count=0,
    )



class SessionStore:
    """
    Thread-safe in-memory session store for active emergency call sessions.

    Each session maps to a LangGraph IncidentState that accumulates data
    across multiple conversation turns and synchronizes with MongoDB.
    """

    def __init__(self):
        self._sessions: dict[str, IncidentState] = {}
        self._lock = threading.Lock()

    # ── lifecycle ────────────────────────────────────────────────

    def get_or_create(self, session_id: Optional[str] = None) -> str:
        """Return *session_id* after ensuring the session exists."""
        if session_id is None:
            session_id = str(uuid.uuid4())
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = _empty_state()
                logger.info("Session created: %s", session_id)
        return session_id

    def delete(self, session_id: str) -> bool:
        """Delete a session. Returns True if it existed."""
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    # ── State Updates (Images, Sensors, Service selection) ───────

    async def add_captured_image(self, session_id: str, image_data: dict) -> dict:
        """Add a camera evidence frame to the session state and persist."""
        self.get_or_create(session_id)
        with self._lock:
            state = self._sessions[session_id]
            images = list(state.get("captured_images") or [])
            images.append(image_data)
            state["captured_images"] = images

        await self._persist_to_mongo(session_id, state)
        return image_data

    async def add_video_evidence(self, session_id: str, video_data: dict) -> dict:
        """Add a recorded video evidence clip to the session state and persist."""
        self.get_or_create(session_id)
        with self._lock:
            state = self._sessions[session_id]
            videos = list(state.get("video_evidence") or [])
            videos.append(video_data)
            state["video_evidence"] = videos

        await self._persist_to_mongo(session_id, state)
        return video_data

    async def update_sensor_telemetry(self, session_id: str, sensor_data: dict) -> dict:
        """Update live Bluetooth / IoT biometric sensor telemetry and persist."""
        self.get_or_create(session_id)
        with self._lock:
            state = self._sessions[session_id]
            state["sensor_telemetry"] = sensor_data

        await self._persist_to_mongo(session_id, state)
        return sensor_data

    async def update_location(self, session_id: str, location_data: dict) -> dict:
        """Update live GPS / map / manual location state and persist."""
        self.get_or_create(session_id)
        with self._lock:
            state = self._sessions[session_id]
            lat = location_data.get("latitude")
            lon = location_data.get("longitude")
            accuracy = location_data.get("accuracy") if location_data.get("accuracy") is not None else location_data.get("accuracyMeters")
            source = location_data.get("source", "Browser GPS")
            status = location_data.get("status")
            address = location_data.get("address")
            landmark = location_data.get("landmark") or location_data.get("manualLandmark")
            display = location_data.get("displayString") or location_data.get("display_string")

            if lat is not None:
                state["latitude"] = float(lat)
            if lon is not None:
                state["longitude"] = float(lon)
            if accuracy is not None:
                state["location_accuracy"] = float(accuracy)
            if source:
                state["location_source"] = source

            # Determine location reliability status
            if not status:
                if source == "Manual Entry":
                    status = "manual_override"
                elif accuracy is not None and float(accuracy) > 100:
                    status = "low_accuracy"
                elif lat is not None and lon is not None:
                    status = "reliable"
                else:
                    status = "unavailable"
            state["location_status"] = status

            if landmark:
                state["landmark"] = str(landmark).strip()

            if not display:
                if lat is not None and lon is not None:
                    acc_str = f" (±{int(state['location_accuracy'])}m)" if state.get("location_accuracy") is not None else ""
                    coord_str = f"{float(lat):.5f}, {float(lon):.5f}{acc_str}"
                    display = f"{address} [{coord_str}]" if address else coord_str
                elif landmark:
                    display = landmark
                elif address:
                    display = address

            if display:
                state["location_display"] = display
                # If current location is missing or placeholder or manual override, set location
                current_loc = state.get("location")
                if not current_loc or current_loc in ("Awaiting location...", "Location unknown", "Location denied or unavailable", "Location unavailable") or source == "Manual Entry":
                    state["location"] = display

        await self._persist_to_mongo(session_id, state)
        return state

    def set_selected_service(self, session_id: str, service: str) -> None:
        """Record user-selected emergency service."""
        self.get_or_create(session_id)
        with self._lock:
            self._sessions[session_id]["selected_service"] = service

    def set_language(self, session_id: str, language: str) -> None:
        """Lock explicit dispatcher selected language for active session."""
        self.get_or_create(session_id)
        with self._lock:
            self._sessions[session_id]["language"] = language
            self._sessions[session_id]["selected_language"] = language

    # ── AI pipeline ─────────────────────────────────────────────

    async def process_message(self, session_id: str, message: str, language: Optional[str] = None) -> None:
        """Process a new caller message through the LangGraph pipeline with bidirectional language translation."""
        self.get_or_create(session_id)

        with self._lock:
            state = self._sessions[session_id]

        # 1. Dispatcher/CAD language vs Caller language
        dispatcher_lang = state.get("selected_language") or state.get("language") or "en"
        caller_lang = translation_service.detect_language(
            message, fallback_lang=language or state.get("detected_language") or "en"
        )
        original_transcript = message

        # 2. Caller -> Dispatcher Translation (if caller language differs from selected dispatcher language)
        translated_message = await translation_service.translate(
            original_transcript, source_lang=caller_lang, target_lang=dispatcher_lang
        )

        # 3. Severity scoring (evaluate on both translated English & raw text for maximum keyword coverage)
        severity = SeverityService()
        scoring_raw = severity.evaluate(original_transcript)
        scoring_trans = severity.evaluate(translated_message)
        max_priority_score = max(scoring_raw["priority_score"], scoring_trans["priority_score"])
        priority_label = scoring_trans["priority_label"] if scoring_trans["priority_score"] >= scoring_raw["priority_score"] else scoring_raw["priority_label"]

        # 4. Build LangGraph input state in dispatcher language for deterministic emergency reasoning
        input_state = dict(state)
        input_state["messages"] = list(state["messages"]) + [
            HumanMessage(content=translated_message)
        ]
        input_state["priority_score"] = max(
            state.get("priority_score") or 0, max_priority_score
        )
        input_state["priority_label"] = priority_label
        input_state["language"] = dispatcher_lang
        input_state["selected_language"] = dispatcher_lang
        input_state["detected_language"] = caller_lang
        input_state["input_language"] = caller_lang
        input_state["response_language"] = dispatcher_lang
        input_state["original_transcript"] = original_transcript
        input_state["translated_transcript"] = translated_message

        # 5. Run LangGraph workflow asynchronously in dispatcher language
        result = await emergency_workflow.ainvoke(input_state)

        # 6. Dispatcher/AI -> Caller Translation (translate questions & guidance back into caller's spoken language)
        dispatcher_question = result.get("current_question")
        dispatcher_guidance = result.get("guidance")

        caller_question = None
        if dispatcher_question:
            caller_question = await translation_service.translate(
                dispatcher_question, source_lang=dispatcher_lang, target_lang=caller_lang
            )

        caller_guidance = None
        if dispatcher_guidance:
            caller_guidance = await translation_service.translate(
                dispatcher_guidance, source_lang=dispatcher_lang, target_lang=caller_lang
            )

        # 7. Preserve bidirectional state
        result["caller_question"] = caller_question
        result["caller_guidance"] = caller_guidance
        result["original_transcript"] = original_transcript
        result["translated_transcript"] = translated_message
        result["detected_language"] = caller_lang
        result["selected_language"] = dispatcher_lang
        result["language"] = dispatcher_lang
        result["response_language"] = dispatcher_lang

        with self._lock:
            self._sessions[session_id] = result

        logger.info(
            "Session %s | turn %d | caller_lang=%s | dispatcher_lang=%s | status=%s",
            session_id,
            result.get("turn_count", 0),
            caller_lang,
            dispatcher_lang,
            result.get("status"),
        )

        # Persist to MongoDB
        await self._persist_to_mongo(session_id, result)

    async def _persist_to_mongo(self, session_id: str, state: dict) -> None:
        """Persist session state to MongoDB."""
        try:
            from app.services.mongo_service import is_mongo_configured, save_session
            if is_mongo_configured():
                await save_session(session_id, state)
        except Exception as e:
            logger.warning("MongoDB persist failed for %s: %s", session_id, e)

    # ── read helpers ────────────────────────────────────────────

    def get_state(self, session_id: str) -> Optional[IncidentState]:
        """Return the raw state dict (or None)."""
        return self._sessions.get(session_id)

    def get_question(self, session_id: str, lang: Optional[str] = None) -> Optional[str]:
        """Get the AI's follow-up question (returns caller_question if caller language requested)."""
        state = self._sessions.get(session_id)
        if not state:
            return None
        if lang and lang == state.get("detected_language") and state.get("caller_question"):
            return state.get("caller_question")
        return state.get("caller_question") or state.get("current_question")

    def get_incident_data(self, session_id: str) -> Optional[IncidentData]:
        """Get the current structured incident data."""
        state = self._sessions.get(session_id)
        if state is None:
            return None

        return IncidentData(
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
            caller_name=state.get("caller_name"),
            caller_age=state.get("caller_age"),
            caller_phone=state.get("caller_phone"),
            casualties=state.get("casualties"),
            estimated_arrival=state.get("estimated_arrival"),
            summary=state.get("summary"),
            guidance=state.get("guidance"),
            caller_guidance=state.get("caller_guidance"),
            missing_info=state.get("missing_info", []),
            status=state.get("status", "gathering_info"),
            question=state.get("current_question"),
            caller_question=state.get("caller_question"),
            dispatch_plan=state.get("dispatch_plan", []),
            retrieved_context=state.get("retrieved_context"),
            routed_service=state.get("routed_service"),
            priority_score=state.get("priority_score"),
            priority_label=state.get("priority_label"),
            fake_probability=state.get("fake_probability"),
            fake_label=state.get("fake_label"),
            fake_signals=state.get("fake_signals") or [],
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


    def get_turn_count(self, session_id: str) -> int:
        """Count human messages in this session."""
        state = self._sessions.get(session_id)
        if state is None:
            return 0
        return len([m for m in state.get("messages", []) if isinstance(m, HumanMessage)])

    def list_sessions(self) -> list[str]:
        """List all active session IDs."""
        with self._lock:
            return list(self._sessions.keys())

    def delete(self, session_id: str) -> bool:
        """Delete an active session from memory. Returns True if existed."""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info("Session removed from memory: %s", session_id)
                return True
            return False

    def delete_session(self, session_id: str) -> bool:
        """Alias for delete."""
        return self.delete(session_id)


# Global singleton
session_store = SessionStore()
