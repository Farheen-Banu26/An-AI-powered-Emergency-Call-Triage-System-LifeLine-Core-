import json
import logging
from typing import List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()

# Active dispatcher WebSocket connections
_dispatcher_connections: List[WebSocket] = []


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
