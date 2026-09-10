"""
MongoDB service for persisting emergency call sessions.

Stores full incident state, caller details, and conversation history
in MongoDB Atlas. Each session is a document in the 'sessions' collection.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── Module-level client (lazy init) ──────────────────────────────
_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None


def get_db() -> AsyncIOMotorDatabase:
    """Return (and lazily create) the Motor async MongoDB client."""
    global _client, _db
    if _db is None:
        settings = get_settings()
        if not settings.mongodb_uri:
            raise RuntimeError("MONGODB_URI is not configured in .env")
        _client = AsyncIOMotorClient(settings.mongodb_uri)
        _db = _client[settings.mongodb_db_name]
        logger.info("MongoDB connected: %s", settings.mongodb_db_name)
    return _db


async def close_db():
    """Close the MongoDB connection (call on shutdown)."""
    global _client, _db
    if _client:
        _client.close()
        _client = None
        _db = None
        logger.info("MongoDB connection closed.")


# ── Session persistence ──────────────────────────────────────────

def _serialize_messages(messages: list) -> list[dict]:
    """Convert LangChain message objects to plain dicts for MongoDB."""
    serialized = []
    for m in messages:
        serialized.append({
            "type": m.__class__.__name__,
            "content": m.content,
        })
    return serialized


async def save_session(session_id: str, state: dict) -> None:
    """Upsert a session document in MongoDB."""
    db = get_db()
    doc = {
        "session_id": session_id,
        "emergency_type": state.get("emergency_type"),
        "location": state.get("location"),
        "details": state.get("details"),
        "priority": state.get("priority"),
        "caller_name": state.get("caller_name"),
        "caller_age": state.get("caller_age"),
        "caller_phone": state.get("caller_phone"),
        "casualties": state.get("casualties"),
        "estimated_arrival": state.get("estimated_arrival"),
        "summary": state.get("summary"),
        "routed_service": state.get("routed_service"),
        "sop_steps": state.get("sop_steps"),
        "dispatcher_notes": state.get("dispatcher_notes"),
        "priority_score": state.get("priority_score"),
        "priority_label": state.get("priority_label"),
        "guidance": state.get("guidance"),
        "dispatch_plan": state.get("dispatch_plan", []),
        "retrieved_context": state.get("retrieved_context"),
        "missing_info": state.get("missing_info", []),
        "current_question": state.get("current_question"),
        "status": state.get("status", "gathering_info"),
        "turn_count": state.get("turn_count", 0),
        "messages": _serialize_messages(state.get("messages", [])),
        "updated_at": datetime.now(timezone.utc),
    }

    await db.sessions.update_one(
        {"session_id": session_id},
        {"$set": doc, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    logger.debug("Session %s persisted to MongoDB.", session_id)


async def load_session(session_id: str) -> Optional[dict]:
    """Load a session document from MongoDB (returns raw dict or None)."""
    db = get_db()
    return await db.sessions.find_one({"session_id": session_id}, {"_id": 0})


async def list_all_sessions() -> list[dict]:
    """Return summary info for all sessions."""
    db = get_db()
    cursor = db.sessions.find(
        {},
        {
            "_id": 0,
            "session_id": 1,
            "emergency_type": 1,
            "status": 1,
            "priority": 1,
            "location": 1,
            "caller_name": 1,
            "turn_count": 1,
            "created_at": 1,
            "updated_at": 1,
        },
    ).sort("updated_at", -1)
    return await cursor.to_list(length=200)


async def get_session_summary(session_id: str) -> Optional[dict]:
    """Get a full summary document for the frontend dashboard."""
    db = get_db()
    doc = await db.sessions.find_one({"session_id": session_id}, {"_id": 0})
    return doc


async def delete_session_db(session_id: str) -> bool:
    """Delete a session from MongoDB."""
    db = get_db()
    result = await db.sessions.delete_one({"session_id": session_id})
    return result.deleted_count > 0
