import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage
from starlette.websockets import WebSocketState

from app.ai.workflow import emergency_workflow
from app.routes.dispatcher import broadcast_emergency_update
from app.services.session_service import session_store
from app.services.severity_service import SeverityService
from app.services.stt_service import STTService
from app.services.vad_service import VADService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/audio")
async def stream_audio(
    websocket: WebSocket,
    session_id: str = Query(...),
    lang: str = Query("en"),
):
    """
    Main WebSocket endpoint for real-time audio ingestion.
    Orchestrates: VAD → STT → AI Workflow → Dispatcher broadcast.
    """
    await websocket.accept()
    logger.info("Audio stream connected: %s", session_id)

    # Per-connection services
    vad = VADService()
    stt = STTService()
    severity = SeverityService()

    # Ensure session exists
    session_store.get_or_create(session_id)

    async def _safe_send(msg: dict):
        """Send JSON to the caller, silently ignoring if disconnected."""
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json(msg)
        except Exception:
            pass

    async def _run_ai_pipeline(transcript: str):
        """Run the full AI pipeline (can be slow with Ollama). Runs as background task."""

        # Send "processing" indicator so frontend knows we're working
        await _safe_send({
            "type": "processing",
            "text": "Processing your message...",
            "session_id": session_id,
        })

        # Severity scoring (fast, local)
        scoring = severity.evaluate(transcript)

        # Get current state, append message, run workflow
        state = session_store.get_state(session_id)
        if state is None:
            return

        input_state = dict(state)
        input_state["messages"] = list(state["messages"]) + [HumanMessage(content=transcript)]
        input_state["priority_score"] = max(
            state.get("priority_score") or 0, scoring["priority_score"]
        )
        input_state["priority_label"] = scoring["priority_label"]

        try:
            result = await emergency_workflow.ainvoke(input_state)
            # Update the session store thread-safely
            with session_store._lock:
                session_store._sessions[session_id] = result
        except Exception as e:
            logger.error("AI Workflow error [%s]: %s", session_id, e, exc_info=True)
            return

        # Broadcast to dispatcher dashboard(s)
        await broadcast_emergency_update({
            "session_id": session_id,
            "transcript": transcript,
            "severity": result.get("priority_label"),
            "score": result.get("priority_score"),
            "summary": result.get("summary"),
            "status": result.get("status"),
            "emergency_type": result.get("emergency_type"),
            "location": result.get("location"),
            "caller_name": result.get("caller_name"),
            "caller_age": result.get("caller_age"),
            "caller_phone": result.get("caller_phone"),
            "guidance": result.get("guidance"),
            "sop_steps": result.get("sop_steps"),
            "dispatch_plan": result.get("dispatch_plan", []),
            "routed_service": result.get("routed_service"),
            "fake_probability": result.get("fake_probability"),
            "fake_label": result.get("fake_label"),
            "fake_signals": result.get("fake_signals", []),
        })

        # Send AI response back to caller
        status = result.get("status", "gathering_info")
        current_q = result.get("current_question")
        guidance = result.get("guidance")
        p_score = result.get("priority_score")
        p_label = result.get("priority_label")

        logger.info(
            "Pipeline result [%s]: status=%s, priority_score=%s, priority_label=%s",
            session_id, status, p_score, p_label,
        )

        response_text = current_q or guidance
        if response_text:
            await _safe_send({
                "type": "question",
                "text": response_text,
                "guidance": guidance,
                "session_id": session_id,
                "status": status,
                "priority_score": p_score,
                "priority_label": p_label,
                "fake_probability": result.get("fake_probability"),
                "fake_label": result.get("fake_label"),
                "fake_signals": result.get("fake_signals", []),
            })

    async def handle_speech(chunk: bytes):
        """Process a single VAD-detected speech segment."""
        if not chunk:
            return

        logger.info("Speech segment: %d bytes", len(chunk))

        # 1. Transcribe (fast — Sarvam API ~500ms)
        stt_result = await stt.transcribe(chunk, language=lang)
        transcript = stt_result.get("transcript")
        if not transcript:
            return

        logger.info("Transcript [%s]: %s", session_id, transcript)

        # 2. Send transcript back to caller immediately (subtitles)
        await _safe_send({
            "type": "transcript",
            "text": transcript,
            "session_id": session_id,
        })

        # 3. Run the AI pipeline as a background task so the receive loop
        #    continues handling audio frames and keeping the WebSocket alive
        asyncio.create_task(_run_ai_pipeline(transcript))

    # Track background AI tasks so we can wait/cancel on disconnect
    pending_tasks: list[asyncio.Task] = []

    # Monkey-patch handle_speech to collect tasks
    _original_handle_speech = handle_speech

    async def handle_speech_tracked(chunk: bytes):
        """Wrapper that keeps references to spawned background tasks."""
        before = set(asyncio.all_tasks())
        await _original_handle_speech(chunk)
        after = set(asyncio.all_tasks())
        new_tasks = after - before
        pending_tasks.extend(new_tasks)

    try:
        while True:
            # Use a timeout so the loop can check connection state periodically
            try:
                data = await asyncio.wait_for(
                    websocket.receive_bytes(), timeout=60.0
                )
            except asyncio.TimeoutError:
                # No audio received for 60s — send a keep-alive ping
                if websocket.client_state == WebSocketState.CONNECTED:
                    await _safe_send({"type": "ping"})
                    continue
                else:
                    break

            for speech_chunk in vad.get_speech_chunks(data):
                await handle_speech_tracked(speech_chunk)

    except WebSocketDisconnect:
        logger.info("Caller disconnected: %s", session_id)
        final_chunk = vad.close()
        if final_chunk:
            await handle_speech_tracked(final_chunk)
    except Exception as e:
        logger.error("Stream error [%s]: %s", session_id, e, exc_info=True)
    finally:
        # Clean up: cancel any still-running AI pipeline tasks
        for t in pending_tasks:
            if not t.done():
                t.cancel()
        # Close WebSocket gracefully if still open
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close()
        except Exception:
            pass
