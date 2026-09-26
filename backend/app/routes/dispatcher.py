import json
import logging
from typing import List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel, Field

from app.services.session_service import session_store
from app.services.translation_service import translation_service
from app.services.tts_service import TTSService

logger = logging.getLogger(__name__)
router = APIRouter()
tts_service = TTSService()

# Active dispatcher WebSocket connections
_dispatcher_connections: List[WebSocket] = []


class DispatcherVoiceMessageInput(BaseModel):
    session_id: str = Field(..., description="Target active caller session ID")
    message: str = Field(..., description="Dispatcher spoken question or instruction")
    target_language: Optional[str] = Field("en", description="Target language code (en, ta, hi)")


@router.websocket("/ws")
async def dispatcher_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for the dispatcher dashboard to receive live updates.
    """
    await websocket.accept()
    _dispatcher_connections.append(websocket)
    logger.info("Dispatcher connected. Total: %d", len(_dispatcher_connections))

    try:
        while True:
            # Keep connection alive — clients may send pings/heartbeats
            await websocket.receive_text()
    except WebSocketDisconnect:
        _safe_remove(websocket)
        logger.info("Dispatcher disconnected. Total: %d", len(_dispatcher_connections))
    except Exception:
        _safe_remove(websocket)


def _safe_remove(ws: WebSocket):
    try:
        _dispatcher_connections.remove(ws)
    except ValueError:
        pass


async def broadcast_emergency_update(data: dict):
    """
    Broadcast emergency data to all connected dispatcher dashboards.
    Automatically cleans up broken connections.
    """
    if not _dispatcher_connections:
        return

    payload = json.dumps(data, default=str)
    broken: list[WebSocket] = []

    for conn in _dispatcher_connections:
        try:
            await conn.send_text(payload)
        except Exception:
            broken.append(conn)

    for b in broken:
        _safe_remove(b)
        logger.warning("Removed broken dispatcher connection.")


@router.post("/speak")
async def dispatcher_speak(body: DispatcherVoiceMessageInput):
    """
    Dispatcher-to-Caller Two-Way Voice:
    Translates dispatcher instruction into the caller's language and synthesizes TTS.
    """
    state = session_store.get_state(body.session_id)
    caller_lang = (state.get("detected_language") if state else None) or body.target_language or "en"
    dispatcher_lang = (state.get("selected_language") if state else None) or "en"

    # Translate dispatcher message into caller's spoken language
    caller_message = await translation_service.translate(
        body.message, source_lang=dispatcher_lang, target_lang=caller_lang
    )

    # Synthesize audio in caller's native language
    audio_base64 = tts_service.synthesize_base64_audio(caller_message, caller_lang)

    # Broadcast update to connected dashboard
    await broadcast_emergency_update({
        "session_id": body.session_id,
        "dispatcher_instruction": body.message,
        "caller_instruction": caller_message,
        "language": dispatcher_lang,
        "caller_language": caller_lang,
        "has_audio": bool(audio_base64),
    })

    return {
        "success": True,
        "session_id": body.session_id,
        "message": body.message,
        "caller_message": caller_message,
        "target_language": caller_lang,
        "audio_base64": audio_base64,
    }
