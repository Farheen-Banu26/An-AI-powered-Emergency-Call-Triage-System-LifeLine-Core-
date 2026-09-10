# Lifeline-Core Backend

AI-powered real-time emergency call triage and dispatch system.

## Architecture

```
Caller Audio ──► WebSocket /api/stream/audio
                   │
                   ├─ VAD (Voice Activity Detection)
                   ├─ STT (Sarvam AI / Deepgram fallback)
                   ├─ Severity Scoring (rule-based)
                   │
                   ▼
              LangGraph AI Workflow
              ┌─────────────┐
              │   Analyst    │  ← Extracts structured data
              │      ▼       │
              │ Completeness │  ← Enough info to dispatch?
              │      ▼       │
              │  Summarizer  │  ← Generates dispatcher briefing
              │    /    \    │
              │   ▼      ▼   │
              │ Question Router│ ← Follow-up OR service routing
              └─────────────┘
                   │
                   ├──► Dispatcher Dashboard (WebSocket)
                   └──► TTS → Caller (Sarvam AI)
```

## Prerequisites

- **Python 3.11+**
- **Ollama** running locally with a model (default: `qwen3`)
- **Sarvam AI** API key (for STT/TTS)
- Optional: **Deepgram** API key (fallback STT)

## Quick Start

```bash
# 1. Start Ollama
ollama serve
ollama pull qwen3:8b

# 2. Set up environment
cd backend
python -m venv venv
venv\Scripts\activate     # Windows
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env with your API keys

# 4. Ingest protocols into ChromaDB (first time only)
python ingest_knowledge.py

# 5. Run the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check with diagnostics |
| `POST` | `/api/call/message` | Send caller transcript text |
| `GET` | `/api/call/question/{session_id}` | Get AI follow-up question |
| `GET` | `/api/call/question/{session_id}/audio?lang=hi` | Stream TTS audio |
| `GET` | `/api/call/status/{session_id}` | Get full incident state |
| `GET` | `/api/call/sessions` | List active sessions |
| `DELETE` | `/api/call/{session_id}` | End a session |
| `WS` | `/api/stream/audio?session_id=X` | Real-time audio ingestion |
| `WS` | `/api/dispatcher/ws` | Live dispatcher updates |

### Example: Send a message

```bash
curl -X POST http://localhost:8000/api/call/message \
  -H "Content-Type: application/json" \
  -d '{"session_id": "call_123", "message": "There is a fire at the main market!"}'
```

### Example: Get status

```bash
curl http://localhost:8000/api/call/status/call_123
```

## Testing

```bash
cd backend
pytest tests/ -v
```

## Docker

```bash
cd backend
docker build -t lifeline-core .
docker run -p 8000:8000 --env-file .env lifeline-core
```
