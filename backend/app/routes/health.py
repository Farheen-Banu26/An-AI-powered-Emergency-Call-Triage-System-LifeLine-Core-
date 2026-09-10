from fastapi import APIRouter

from app.config import get_settings
from app.services.session_service import session_store

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint with basic diagnostics."""
    settings = get_settings()
    return {
        "status": "ok",
        "version": "1.0.0",
        "llm_provider": settings.llm_provider,
        "model": settings.active_model_name,
        "active_sessions": len(session_store.list_sessions()),
    }
