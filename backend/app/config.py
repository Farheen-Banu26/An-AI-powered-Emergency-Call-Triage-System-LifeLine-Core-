from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings

_BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    # ── Server ───────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    debug: bool = False

    # ── LLM Provider Switch ─────────────────────────────────────
    # Set to "ollama" or "groq"
    llm_provider: str = "groq"

    # ── Ollama (local) ──────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3"
    ollama_num_gpu: int = 99  # layers offloaded to GPU (99 = all)

    # ── Groq (cloud) ────────────────────────────────────────────
    groq_api_key: str = ""
    groq_model: str = "qwen/qwen3.8-27b"

    # ── MongoDB ──────────────────────────────────────────────────
    mongodb_uri: str = ""
    mongodb_db_name: str = "lifeline"

    # ── CORS ─────────────────────────────────────────────────────
    frontend_url: str = "http://localhost:5173"
    allowed_origins: str = ""  # comma-separated extra origins

    # ── External APIs ────────────────────────────────────────────
    sarvam_api_key: str = ""
    deepgram_api_key: str = ""
    gemini_api_key: str = ""
    google_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"

    # ── RAG / ChromaDB ───────────────────────────────────────────
    chroma_persist_dir: str = str(_BASE_DIR / "chroma_db_v2")
    chroma_collection: str = "emergency_protocols"
    embedding_model: str = "mxbai-embed-large"

    # ── STT Provider ─────────────────────────────────────────────
    stt_provider: str = "sarvam"  # "sarvam" (saaras:v4 / translate) with Groq Whisper fallback

    # ── VAD ──────────────────────────────────────────────────────
    vad_aggressiveness: int = 3
    vad_frame_duration_ms: int = 30
    vad_padding_duration_ms: int = 300
    vad_min_speech_ms: int = 300          # min speech duration to accept (ms)
    vad_silence_hangover_ms: int = 600    # silence duration before concluding utterance (ms)
    vad_energy_threshold: int = 300       # RMS energy floor (rejects background noise)

    @property
    def cors_origins(self) -> list[str]:
        """Compute the full list of allowed CORS origins."""
        origins = [self.frontend_url]
        if self.allowed_origins:
            origins.extend([o.strip() for o in self.allowed_origins.split(",") if o.strip()])
        return origins

    @property
    def resolved_chroma_persist_dir(self) -> str:
        """Ensure ChromaDB path is absolute relative to _BASE_DIR."""
        p = Path(self.chroma_persist_dir)
        if not p.is_absolute():
            return str((_BASE_DIR / p).resolve())
        return str(p.resolve())

    @property
    def resolved_groq_model(self) -> str:
        """Auto-resolve Groq model name."""
        if self.groq_model in ["llama-3.3-70b-versatile", "llama-3.1-70b-versatile"]:
            return "qwen/qwen3.8-27b"
        return self.groq_model

    @property
    def active_model_name(self) -> str:
        """Return the model name for the active provider."""
        if self.llm_provider == "groq":
            return self.resolved_groq_model
        return self.ollama_model

    model_config = {
        "env_file": [str(_BASE_DIR / ".env"), ".env", "backend/.env"],
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
