"""API endpoint tests."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_root():
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_health():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_create_story_from_json():
    """Test creating story from JSON."""
    story_data = {
        "title": "테스트 스토리",
        "genre": "드라마",
        "protagonist": {
            "name": "홍길동",
            "age": 30,
            "gender": "남",
            "occupation": "작가",
            "personality": "열정적"
        },
        "scenes": [
            {
                "scene_number": 1,
                "title": "시작",
                "narration": "이것은 테스트 나레이션입니다." * 100
            }
        ]
    }

    response = client.post(
        "/api/v1/story/from-json",
        json={"story_data": story_data}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "테스트 스토리"
    assert data["status"] == "completed"
