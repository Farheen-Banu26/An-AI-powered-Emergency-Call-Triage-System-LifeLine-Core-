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

logger = logging.getLogger(__name__)


def _empty_state() -> IncidentState:
    """Create a blank incident state."""
    return IncidentState(
        messages=[],
        emergency_type=None,
        location=None,
        details=None,
        priority=None,
        caller_name=None,
        caller_age=None,
        caller_phone=None,
        casualties=None,
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
        missing_info=[],
        current_question=None,
        status="gathering_info",
        turn_count=0,
    )


class SessionStore:
    """
    Thread-safe in-memory session store for active emergency call sessions.

    Each session maps to a LangGraph IncidentState that accumulates data
    across multiple conversation turns.
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

    # ── AI pipeline ─────────────────────────────────────────────

    async def process_message(self, session_id: str, message: str) -> None:
        """Process a new caller message through the LangGraph pipeline (async)."""
        self.get_or_create(session_id)

        with self._lock:
            state = self._sessions[session_id]

        # Severity scoring (deterministic keyword analysis)
        severity = SeverityService()
        scoring = severity.evaluate(message)

        # Build input (append new message + severity scores)
        input_state = dict(state)
        input_state["messages"] = list(state["messages"]) + [
            HumanMessage(content=message)
        ]
        input_state["priority_score"] = max(
            state.get("priority_score") or 0, scoring["priority_score"]
        )
        input_state["priority_label"] = scoring["priority_label"]

        # Run the LangGraph workflow asynchronously (non-blocking)
        result = await emergency_workflow.ainvoke(input_state)

        with self._lock:
            self._sessions[session_id] = result

        logger.info(
            "Session %s | turn %d | status=%s",
            session_id,
            result.get("turn_count", 0),
            result.get("status"),
        )

        # Persist to MongoDB
        await self._persist_to_mongo(session_id, result)

    async def _persist_to_mongo(self, session_id: str, state: dict) -> None:
        """Persist session state to MongoDB."""
        try:
            from app.services.mongo_service import save_session
            await save_session(session_id, state)
        except Exception as e:
            logger.warning("MongoDB persist failed for %s: %s", session_id, e)

    # ── read helpers ────────────────────────────────────────────

    def get_state(self, session_id: str) -> Optional[IncidentState]:
        """Return the raw state dict (or None)."""
        return self._sessions.get(session_id)

    def get_question(self, session_id: str) -> Optional[str]:
        """Get the AI's current follow-up question for TTS."""
        state = self._sessions.get(session_id)
        return state.get("current_question") if state else None

    def get_incident_data(self, session_id: str) -> Optional[IncidentData]:
        """Get the current structured incident data."""
        state = self._sessions.get(session_id)
        if state is None:
            return None

        return IncidentData(
            emergency_type=state.get("emergency_type"),
            location=state.get("location"),
            details=state.get("details"),
            priority=state.get("priority"),
            caller_name=state.get("caller_name"),
            caller_age=state.get("caller_age"),
            caller_phone=state.get("caller_phone"),
            casualties=state.get("casualties"),
            estimated_arrival=state.get("estimated_arrival"),
            summary=state.get("summary"),
            guidance=state.get("guidance"),
            missing_info=state.get("missing_info", []),
            status=state.get("status", "gathering_info"),
            question=state.get("current_question"),
            dispatch_plan=state.get("dispatch_plan", []),
            retrieved_context=state.get("retrieved_context"),
            routed_service=state.get("routed_service"),
            priority_score=state.get("priority_score"),
            priority_label=state.get("priority_label"),
            fake_probability=state.get("fake_probability"),
            fake_label=state.get("fake_label"),
            fake_signals=state.get("fake_signals", []),
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


# Global singleton
session_store = SessionStore()
