"""Focused unit and integration tests for Visual Evidence Upload & Gemini Vision Analysis."""

import asyncio
import base64
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.gemini_vision_service import GeminiVisionService
from app.services.session_service import session_store


@pytest.fixture
def client():
    return TestClient(app)


# Sample 1x1 base64 images
JPG_DATA = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
PNG_DATA = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
WEBP_DATA = "data:image/webp;base64,UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoBAAEAAwA0JaQAA3AA/vuUAAA="


def test_1_valid_jpg_upload(client):
    """Test 1: Valid JPG upload to /api/call/image."""
    sid = "test_vis_jpg"
    session_store.get_or_create(sid)
    resp = client.post(
        "/api/call/image",
        json={
            "session_id": sid,
            "image_data": JPG_DATA,
            "label": "Uploaded Test JPG",
            "source": "upload",
            "scene": "road_accident",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["source"] == "upload"
    assert data["scene"] == "road_accident"
    assert "observations" in data


def test_2_valid_png_upload(client):
    """Test 2: Valid PNG upload to /api/call/image."""
    sid = "test_vis_png"
    session_store.get_or_create(sid)
    resp = client.post(
        "/api/call/image",
        json={
            "session_id": sid,
            "image_data": PNG_DATA,
            "label": "Uploaded Test PNG",
            "source": "upload",
            "scene": "fire",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["source"] == "upload"
    assert data["scene"] == "fire"


def test_3_valid_webp_upload(client):
    """Test 3: Valid WEBP upload to /api/call/image."""
    sid = "test_vis_webp"
    session_store.get_or_create(sid)
    resp = client.post(
        "/api/call/image",
        json={
            "session_id": sid,
            "image_data": WEBP_DATA,
            "label": "Uploaded Test WEBP",
            "source": "upload",
            "scene": "medical",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["source"] == "upload"
    assert data["scene"] == "medical"


def test_4_invalid_image_payload_handled(client):
    """Test 4: Missing required fields in payload is rejected by validation."""
    resp = client.post(
        "/api/call/image",
        json={
            # Missing image_data
            "session_id": "test_invalid",
            "label": "test",
        },
    )
    assert resp.status_code == 422


def test_5_source_upload_preserved(client):
    """Test 5: source='upload' is preserved in session store."""
    sid = "test_source_preserve"
    session_store.get_or_create(sid)
    resp = client.post(
        "/api/call/image",
        json={
            "session_id": sid,
            "image_data": JPG_DATA,
            "label": "Upload Evidence",
            "source": "upload",
            "scene": "public_safety",
        },
    )
    assert resp.status_code == 200
    state = session_store.get_state(sid)
    assert state is not None
    images = state.get("captured_images", [])
    assert len(images) > 0
    latest_img = images[-1]
    assert latest_img.get("source") == "upload"
    assert latest_img.get("scene") == "public_safety"


def test_6_selected_scene_preserved(client):
    """Test 6: Selected scene is preserved across all categories."""
    sid = "test_scenes"
    session_store.get_or_create(sid)
    scenes = ["road_accident", "fire", "medical", "public_safety", "general"]
    for sc in scenes:
        resp = client.post(
            "/api/call/image",
            json={
                "session_id": sid,
                "image_data": JPG_DATA,
                "label": f"Scene {sc}",
                "source": "upload",
                "scene": sc,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scene"] == sc


def test_7_gemini_road_accident_structured_parsing():
    """Test 7: Gemini Vision road accident image observation parsing."""
    async def run():
        service = GeminiVisionService(api_key="mock-test-key", model="gemini-1.5-flash")
        
        mock_gemini_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": '```json\n{\n  "observations": [\n    {"label": "Possible vehicle collision visible", "description": "Two visibly damaged vehicles are present on roadway with frontal impact damage.", "confidence": 0.95},\n    {"label": "Multiple people visible", "description": "Several people are visible standing near the collision.", "confidence": 0.94},\n    {"label": "Possible injured person lying on roadway", "description": "A person is visibly lying on the road surface.", "confidence": 0.91},\n    {"label": "Visible blood-like staining near person", "description": "Red fluid staining is visible on the asphalt.", "confidence": 0.88},\n    {"label": "Vehicle debris scattered on road", "description": "Broken vehicle fragments are visible on the traffic lane.", "confidence": 0.94}\n  ]\n}\n```'
                            }
                        ]
                    }
                }
            ]
        }
        
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_gemini_response
            mock_post.return_value = mock_resp

            result = await service.analyze_image(JPG_DATA, scene="road_accident")
            assert result["status"] == "ok"
            assert len(result["observations"]) == 5
            assert result["observations"][0]["label"] == "Possible vehicle collision visible"
            assert "frontal impact damage" in result["observations"][0]["description"]
            assert result["observations"][0]["confidence"] == 0.95
            assert result["observations"][2]["label"] == "Possible injured person lying on roadway"
            assert result["observations"][3]["label"] == "Visible blood-like staining near person"
            assert result["observations"][4]["label"] == "Vehicle debris scattered on road"

    asyncio.run(run())


def test_8_gemini_fire_scene_structured_parsing():
    """Test 8: Gemini Vision fire scene image observation parsing."""
    async def run():
        service = GeminiVisionService(api_key="mock-test-key", model="gemini-1.5-flash")
        
        mock_gemini_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": '```json\n{\n  "observations": [\n    {"label": "Possible fire/flames visible", "description": "Large active flames are visibly emerging from the structure.", "confidence": 0.96},\n    {"label": "Heavy smoke visible", "description": "Dark smoke column rising from the scene.", "confidence": 0.93},\n    {"label": "Road obstruction visible", "description": "Hazard area blocking traffic lane.", "confidence": 0.89}\n  ]\n}\n```'
                            }
                        ]
                    }
                }
            ]
        }
        
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_gemini_response
            mock_post.return_value = mock_resp

            result = await service.analyze_image(JPG_DATA, scene="fire")
            assert result["status"] == "ok"
            assert len(result["observations"]) == 3
            assert result["observations"][0]["label"] == "Possible fire/flames visible"
            assert result["observations"][1]["label"] == "Heavy smoke visible"
            assert result["observations"][2]["label"] == "Road obstruction visible"

    asyncio.run(run())


def test_9_gemini_unavailable_handled_gracefully():
    """Test 9: When Gemini API key is missing or unavailable, returns unavailable status rather than hiding it."""
    async def run():
        # Empty API key
        service_no_key = GeminiVisionService(api_key="", model="gemini-1.5-flash")
        result = await service_no_key.analyze_image(JPG_DATA, scene="medical")
        assert result["status"] == "unavailable"
        assert result["observations"] == []
        assert "Gemini API key is not configured" in result["message"]

        # Network error
        service_with_key = GeminiVisionService(api_key="mock-key", model="gemini-1.5-flash")
        with patch("httpx.AsyncClient.post", side_effect=Exception("Network connection timeout")):
            result = await service_with_key.analyze_image(JPG_DATA, scene="medical")
            assert result["status"] == "unavailable"
            assert result["observations"] == []

    asyncio.run(run())


def test_10_malformed_gemini_response_handled_gracefully():
    """Test 10: When Gemini returns plain text bulleted observations."""
    async def run():
        service = GeminiVisionService(api_key="mock-key", model="gemini-1.5-flash")

        mock_text_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": "• Possible smoke visible in building\n• Road obstruction visible"
                            }
                        ]
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_text_response
            mock_post.return_value = mock_resp

            result = await service.analyze_image(JPG_DATA, scene="fire")
            assert result["status"] == "ok"
            assert len(result["observations"]) >= 1
            labels = [obs["label"] for obs in result["observations"]]
            assert any("smoke" in l.lower() or "obstruction" in l.lower() for l in labels)

    asyncio.run(run())


def test_11_api_key_remains_backend_only(client):
    """Test 11: Gemini API key is never exposed via health or session endpoints."""
    health_resp = client.get("/api/health")
    assert health_resp.status_code == 200
    health_text = health_resp.text
    assert "AIza" not in health_text
    assert "gemini_api_key" not in health_text

    sid = "test_sec_check"
    session_store.get_or_create(sid)
    status_resp = client.get(f"/api/call/status/{sid}")
    assert status_resp.status_code == 200
    assert "gemini_api_key" not in status_resp.text


def test_12_existing_camera_and_snapshot_paths_remain_valid(client):
    """Test 12: Existing camera / snapshot sources continue to work as expected."""
    sid = "test_snapshot_compat"
    session_store.get_or_create(sid)
    
    # Snapshot source
    resp_snap = client.post(
        "/api/call/image",
        json={
            "session_id": sid,
            "image_data": JPG_DATA,
            "label": "Snapshot: road_accident",
            "source": "snapshot",
            "scene": "road_accident",
        },
    )
    assert resp_snap.status_code == 200
    data_snap = resp_snap.json()
    assert data_snap["success"] is True
    assert data_snap["source"] == "snapshot"

    # Default / camera source
    resp_cam = client.post(
        "/api/call/image",
        json={
            "session_id": sid,
            "image_data": JPG_DATA,
            "label": "Camera Frame",
        },
    )
    assert resp_cam.status_code == 200
    data_cam = resp_cam.json()
    assert data_cam["success"] is True
    assert data_cam["source"] == "camera"
