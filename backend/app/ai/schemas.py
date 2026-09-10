from pydantic import BaseModel, Field
from typing import Optional


class IncidentData(BaseModel):
    """Structured incident data extracted by the AI from the conversation."""

    emergency_type: Optional[str] = Field(
        None,
        description="Type of emergency: Fire, Medical, Police, Traffic, Natural Disaster, Civil, Other",
    )
    location: Optional[str] = Field(None, description="Location of the incident")
    details: Optional[str] = Field(None, description="Details of what is happening")
    priority: Optional[int] = Field(
        None, description="Priority level 1 (critical) to 5 (low)", ge=1, le=5
    )
    caller_name: Optional[str] = Field(None, description="Name of the caller")
    caller_age: Optional[int] = Field(None, description="Age of the caller")
    caller_phone: Optional[str] = Field(None, description="Phone number of the caller")
    casualties: Optional[int] = Field(
        None, description="Number of injured/trapped people"
    )
    estimated_arrival: Optional[str] = Field(
        None, description="ETA if mentioned by the caller"
    )
    summary: Optional[str] = Field(
        None, description="Concise dispatcher briefing (1-2 sentences)"
    )
    guidance: Optional[str] = Field(
        None, description="Real-time safety guidance for the caller"
    )
    missing_info: list[str] = Field(
        default_factory=list, description="List of critical fields still missing"
    )
    status: str = Field(
        "gathering_info",
        description="gathering_info or ready_to_dispatch",
    )
    
    # ── RAG / Parallel Dispatch ────────────────────────────────
    dispatch_plan: list[dict] = Field(
        default_factory=list,
        description="Parallel dispatch actions: [{service, priority, reason}]"
    )
    retrieved_context: Optional[str] = Field(
        None, description="Protocols used for decision making"
    )
    question: Optional[str] = Field(
        None, description="Next follow-up question for the caller"
    )
    routed_service: Optional[str] = Field(
        None, description="Primary emergency service dispatched"
    )
    priority_score: Optional[int] = Field(
        None, description="Severity score 0-10 from keyword analysis"
    )
    priority_label: Optional[str] = Field(
        None, description="Severity label: CRITICAL, EMERGENCY, URGENT, ROUTINE"
    )
    fake_probability: Optional[float] = Field(
        None, description="Probability the call is fake (0.0–1.0)"
    )
    fake_label: Optional[str] = Field(
        None, description="Fake call label: GENUINE, SUSPICIOUS, LIKELY_FAKE"
    )
    fake_signals: list[str] = Field(
        default_factory=list, description="Signals that contributed to fake score"
    )


class MessageInput(BaseModel):
    """Input body for the /api/call/message endpoint."""

    session_id: str = Field(..., description="Unique identifier for this call session")
    message: str = Field(..., description="Transcribed caller sentence")


class MessageResponse(BaseModel):
    """Response from the /api/call/message endpoint."""

    success: bool
    session_id: str


class QuestionResponse(BaseModel):
    """Response from the /api/call/question endpoint."""

    session_id: str
    question: Optional[str] = None
    guidance: Optional[str] = None


class QuestionAudioResponse(BaseModel):
    """Response metadata for the text+audio subtitle endpoint."""

    session_id: str
    question: Optional[str] = None
    guidance: Optional[str] = None
    audio_url: Optional[str] = None


class StatusResponse(BaseModel):
    """Response from the /api/call/status endpoint — full incident data."""

    session_id: str
    incident: IncidentData
    conversation_turns: int = 0


class SummaryResponse(BaseModel):
    """Full session summary for the frontend dashboard."""

    session_id: str
    emergency_type: Optional[str] = None
    location: Optional[str] = None
    details: Optional[str] = None
    priority: Optional[int] = None
    caller_name: Optional[str] = None
    caller_age: Optional[int] = None
    caller_phone: Optional[str] = None
    casualties: Optional[int] = None
    summary: Optional[str] = None
    guidance: Optional[str] = None
    routed_service: Optional[str] = None
    sop_steps: Optional[list[str]] = None
    dispatcher_notes: Optional[str] = None
    dispatch_plan: list[dict] = Field(default_factory=list)
    status: str = "gathering_info"
    turn_count: int = 0
    messages: list[dict] = Field(default_factory=list)
