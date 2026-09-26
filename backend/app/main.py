import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings


# ── Lifespan (startup / shutdown) ────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    settings = get_settings()
    logger = logging.getLogger("lifeline")

    # Validate critical config
    warnings: list[str] = []
    if not settings.sarvam_api_key:
        warnings.append("SARVAM_API_KEY not set — STT/TTS will fail")
    if not settings.deepgram_api_key:
        warnings.append("DEEPGRAM_API_KEY not set — fallback STT unavailable")
    if settings.llm_provider == "groq" and not settings.groq_api_key:
        warnings.append("GROQ_API_KEY not set — Groq LLM calls will fail")

    for w in warnings:
        logger.warning(w)

    # Initialize MongoDB connection
    if settings.mongodb_uri:
        try:
            from app.services.mongo_service import get_db
            get_db()
            logger.info("MongoDB connected: %s", settings.mongodb_db_name)
        except Exception as e:
            logger.error("MongoDB connection failed: %s", e)
    else:
        logger.warning("MONGODB_URI not set — sessions will NOT be persisted")

    # Warm up ChromaDB Vector Store so first query has zero cold latency
    try:
        from app.services.rag_service import retrieve_context
        retrieve_context("emergency medical ambulance protocol")
        logger.info("ChromaDB vector store warmed up successfully.")
    except Exception as e:
        logger.warning("ChromaDB warmup note: %s", e)

    logger.info(
        "Lifeline-Core started | provider=%s | model=%s | ollama=%s | chroma=%s",
        settings.llm_provider,
        settings.active_model_name,
        settings.ollama_base_url,
        settings.chroma_persist_dir,
    )

    yield  # ← app is running

    # Shutdown: close MongoDB
    try:
        from app.services.mongo_service import close_db
        await close_db()
    except Exception:
        pass

    logger.info("Lifeline-Core shutting down.")


# ── Logging ──────────────────────────────────────────────────────
settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)

# ── App ──────────────────────────────────────────────────────────
from app.routes import health, calls, stream, dispatcher  # noqa: E402

app = FastAPI(
    title="Lifeline-Core Emergency Dispatch AI",
    description="AI-powered real-time emergency call triage and routing system",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ───────────────────────────────────────────────────────
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(calls.router, prefix="/api/call", tags=["calls"])
app.include_router(stream.router, prefix="/api/stream", tags=["streaming"])
app.include_router(dispatcher.router, prefix="/api/dispatcher", tags=["dispatcher"])
