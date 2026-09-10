from typing import Annotated, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class IncidentState(TypedDict):
    """
    LangGraph state for a single emergency call session.

    This state accumulates across multiple conversation turns.
    Each node reads from and writes to specific fields.
    """

    # ── Chat History ──────────────────────────────────────────────
    messages: Annotated[list[BaseMessage], add_messages]

    # ── Extracted Incident Fields (accumulated across turns) ─────
    emergency_type: Optional[str]       # Fire, Medical, Police, Traffic, Natural Disaster, Civil, Other
    location: Optional[str]             # Address, landmark, or area
    details: Optional[str]              # What is happening
    priority: Optional[int]             # 1 (critical) → 5 (low)
    caller_name: Optional[str]
    caller_age: Optional[int]           # Age of the caller
    caller_phone: Optional[str]         # Phone number
    casualties: Optional[int]           # Injured / trapped count
    estimated_arrival: Optional[str]    # ETA if caller mentions

    # ── RAG & Advanced Routing ──────────────────────────────────
    dispatch_plan: Optional[list[dict]]      # [{service, priority, reason}]
    retrieved_context: Optional[str]         # Protocols retrieved from ChromaDB

    # ── Dispatcher-facing fields ─────────────────────────────────
    summary: Optional[str]              # 1-2 sentence briefing
    routed_service: Optional[str]       # Fire Dept, Ambulance, Police, etc.
    sop_steps: Optional[list[str]]      # Standard Operating Procedure steps
    dispatcher_notes: Optional[str]     # Extra context for dispatcher
    priority_score: Optional[int]       # Severity score from scoring module
    priority_label: Optional[str]       # Score label (e.g., CRITICAL)

    # ── Real-time Guidance (sent to caller before officials arrive) ──
    guidance: Optional[str]             # Safety instructions for the caller

    # ── Fake Call Detection ────────────────────────────────────────
    fake_probability: Optional[float]   # 0.0–1.0 probability of being fake
    fake_label: Optional[str]           # GENUINE | SUSPICIOUS | LIKELY_FAKE
    fake_signals: Optional[list[str]]   # Reasons for the score
    _llm_fake_score: Optional[float]    # Analyst LLM's raw fake score (internal)

    # ── Conversation control ─────────────────────────────────────
    missing_info: list[str]             # Fields still needed
    current_question: Optional[str]     # AI's follow-up question → TTS route
    status: str                         # "gathering_info" | "ready_to_dispatch"
    turn_count: int                     # Number of caller messages processed
