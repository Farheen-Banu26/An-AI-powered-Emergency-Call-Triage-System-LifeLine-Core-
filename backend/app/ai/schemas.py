from pydantic import BaseModel, Field
from typing import Optional


class IncidentData(BaseModel):
    """Structured incident data extracted by the AI from the conversation."""

    emergency_type: Optional[str] = Field(
        None,
        description="Type of emergency: Fire, Medical, Police, Traffic, Natural Disaster, Civil, Other",
    )
    location: Optional[str] = Field(None, description="Location of the incident")
    landmark: Optional[str] = Field(None, description="Nearby landmark or specific access point")
    latitude: Optional[float] = Field(None, description="GPS latitude")
    longitude: Optional[float] = Field(None, description="GPS longitude")
    location_accuracy: Optional[float] = Field(None, description="GPS accuracy in meters")
    location_source: Optional[str] = Field(None, description="Location source: Browser GPS, Manual Entry, etc.")
    location_status: Optional[str] = Field(None, description="Location status: reliable, low_accuracy, unavailable, manual_override")
    location_display: Optional[str] = Field(None, description="Human readable formatted location string")
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
    captured_images: list[dict] = Field(
        default_factory=list, description="Captured camera evidence frames"
    )
    video_evidence: list[dict] = Field(
        default_factory=list, description="Captured emergency video evidence recordings"
    )
    sensor_telemetry: Optional[dict] = Field(
        None, description="Biometric/sensor telemetry (e.g. Bluetooth heart rate)"
    )
    selected_service: Optional[str] = Field(
        None, description="User-selected emergency service"
    )
    selected_language: Optional[str] = Field(
        None, description="Selected language code (e.g. ta, hi, en)"
    )
    detected_language: Optional[str] = Field(
        None, description="Detected caller language code (e.g. ta, hi, en)"
    )
    original_transcript: Optional[str] = Field(
        None, description="Original caller transcript in native language"
    )
    translated_transcript: Optional[str] = Field(
        None, description="Translated transcript in dispatcher language"
    )
    caller_question: Optional[str] = Field(
        None, description="AI question in caller native language"
    )
    caller_guidance: Optional[str] = Field(
        None, description="Guidance in caller native language"
    )
    known_facts: dict = Field(
        default_factory=dict, description="Extracted semantic incident facts"
    )
    previous_questions: list[str] = Field(
        default_factory=list, description="Questions asked so far"
    )



class VideoEvidenceInput(BaseModel):
    """Input payload for video evidence recording metadata."""
    session_id: str
    video_data: Optional[str] = Field(None, description="Base64 encoded video or video URL")
    category: Optional[str] = Field("general", description="Emergency category: road_accident, fire, medical, public_safety, general")
    duration_seconds: Optional[float] = Field(0.0, description="Duration of video in seconds")
    timestamp: Optional[str] = Field(None, description="ISO timestamp")
    location: Optional[dict] = Field(None, description="GPS location captured during recording")
    notes: Optional[str] = Field(None, description="Caller / automated notes")


class MessageInput(BaseModel):
    """Input body for the /api/call/message endpoint."""

    session_id: str = Field(..., description="Unique identifier for this call session")
    message: str = Field(..., description="Transcribed caller sentence")
    language: Optional[str] = Field("en", description="Active caller/session language code (ta, hi, en)")


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
    landmark: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_accuracy: Optional[float] = None
    location_source: Optional[str] = None
    location_status: Optional[str] = None
    location_display: Optional[str] = None
    details: Optional[str] = None
    priority: Optional[int] = None
    caller_name: Optional[str] = None
    caller_age: Optional[int] = None
    caller_phone: Optional[str] = None
    casualties: Optional[int] = None
    summary: Optional[str] = None
    guidance: Optional[str] = None
    current_question: Optional[str] = None
    caller_question: Optional[str] = None
    caller_guidance: Optional[str] = None
    missing_info: list[str] = Field(default_factory=list)
    priority_score: Optional[int] = None
    priority_label: Optional[str] = None
    fake_probability: Optional[float] = None
    fake_label: Optional[str] = None
    fake_signals: list[str] = Field(default_factory=list)
    routed_service: Optional[str] = None
    sop_steps: Optional[list[str]] = None
    dispatcher_notes: Optional[str] = None
    dispatch_plan: list[dict] = Field(default_factory=list)
    status: str = "gathering_info"
    turn_count: int = 0
    messages: list[dict] = Field(default_factory=list)
    captured_images: list[dict] = Field(default_factory=list)
    video_evidence: list[dict] = Field(default_factory=list)
    sensor_telemetry: Optional[dict] = None
    selected_service: Optional[str] = None
    selected_language: Optional[str] = None
    detected_language: Optional[str] = None
    original_transcript: Optional[str] = None
    translated_transcript: Optional[str] = None
    known_facts: dict = Field(default_factory=dict)
    previous_questions: list[str] = Field(default_factory=list)
