@echo off
echo Starting Lifeline-Core Backend ...
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
