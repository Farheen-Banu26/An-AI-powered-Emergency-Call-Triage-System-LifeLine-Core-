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
    emergency_type: Optional[str]       # Fire, Medical, Police, Traffic, Natural Disaster, Hazmat, etc.
    scenario_category: Optional[str]    # Specific scenario (e.g., cardiac, fire, crash, hazmat, drowning, threat)
    # ── Location & GPS Telemetry ─────────────────────────────────
    location: Optional[str]             # Address, landmark, or area
    landmark: Optional[str]             # Specific landmark or access point
    latitude: Optional[float]           # Live GPS latitude
    longitude: Optional[float]          # Live GPS longitude
    location_accuracy: Optional[float]  # Accuracy in meters (e.g. 8.0)
    location_source: Optional[str]      # "Browser GPS" | "Manual Entry" | "IP Fallback"
    location_status: Optional[str]      # "reliable" | "low_accuracy" | "unavailable" | "manual_override"
    location_display: Optional[str]     # Formatted display string

    details: Optional[str]              # What is happening
    priority: Optional[int]             # 1 (critical) → 5 (low)
    caller_name: Optional[str]
    caller_age: Optional[int]           # Age of the caller / patient
    caller_phone: Optional[str]         # Phone number
    caller_gender: Optional[str]        # Gender/sex where relevant
    casualties: Optional[int]           # Injured / trapped count
    symptoms: Optional[list[str]]       # Reported symptoms
    hazards: Optional[list[str]]        # Reported hazards
    injuries: Optional[list[str]]       # Reported injuries
    trapped_people: Optional[int]       # Trapped count
    environmental_info: Optional[str]   # Weather / smoke / structural condition
    camera_observations: Optional[list[str]] # Visual evidence notes
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

    # ── Media & IoT Sensor Telemetry ─────────────────────────────
    captured_images: Optional[list[dict]]  # [{url, timestamp, thumbnail, label}]
    sensor_telemetry: Optional[dict]       # {heart_rate, spo2, device_name, status}
    selected_service: Optional[str]        # Ambulance, Police, Fire, Rescue, BlueCross

    # ── Language Tracking & Lock ───────────────────────────────────
    language: Optional[str]             # Active selected language (ta, hi, en, etc.)
    selected_language: Optional[str]    # Explicit session selected language
    input_language: Optional[str]       # Language of incoming user message
    detected_language: Optional[str]    # Detected caller speech language
    response_language: Optional[str]    # Target language for dispatcher response & TTS
    original_transcript: Optional[str]  # Preserved caller transcript in caller native language
    translated_transcript: Optional[str]# Translated transcript in dispatcher selected language
    caller_question: Optional[str]      # Translated AI question in caller native language
    caller_guidance: Optional[str]      # Translated guidance in caller native language

    # ── Dynamic Scenario Entities & Semantic Facts ─────────────────
    known_facts: Optional[dict]         # Dynamic extracted facts (e.g. {"breathing": false, "trapped_people": 0, "hazards": "smoke"})
    previous_questions: list[str]       # AI follow-up questions asked in this session
    previous_answers: list[str]         # User answers provided in this session

    # ── Conversation control ─────────────────────────────────────
    missing_info: list[str]             # Fields still needed
    current_question: Optional[str]     # AI's follow-up question in selected dispatcher language
    status: str                         # "gathering_info" | "ready_to_dispatch"
    turn_count: int                     # Number of caller messages processed
