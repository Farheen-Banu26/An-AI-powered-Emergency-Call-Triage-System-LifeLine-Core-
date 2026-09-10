"""Tests for the API routes using FastAPI TestClient."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "active_sessions" in data


def test_session_not_found(client):
    resp = client.get("/api/call/status/nonexistent-session")
    assert resp.status_code == 404


def test_question_session_not_found(client):
    resp = client.get("/api/call/question/nonexistent-session")
    assert resp.status_code == 404


def test_delete_session_not_found(client):
    resp = client.delete("/api/call/nonexistent-session")
    assert resp.status_code == 404


def test_list_sessions(client):
    resp = client.get("/api/call/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert "in_memory" in data
    assert "persisted" in data
