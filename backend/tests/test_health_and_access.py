"""Health contract, validation, request IDs and disabled-account access."""

from uuid import UUID

from app.database import SessionLocal
from app.users.service import set_user_active


def test_health_uses_versioned_public_contract(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["appVersion"] == "1.3.0"
    assert response.json()["apiVersion"] == "v1"
    assert "app_version" not in response.json()
    UUID(response.headers["X-Request-ID"])
    assert response.headers["X-Server-Time"].endswith("Z")


def test_ready_requires_collaboration_schema(client):
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["alembicRevision"] == "20260806_0003"
    assert "card_comments" in payload["requiredTables"]
    assert "card_checklist_items" in payload["requiredTables"]
    assert "user_invitations" in payload["requiredTables"]
    assert "board_members" in payload["requiredTables"]
    assert "notifications" in payload["requiredTables"]


def test_validation_error_is_safe_and_structured(client, owner_headers):
    response = client.post(
        "/api/v1/boards",
        headers=owner_headers,
        json={"title": "   ", "unexpected": "not accepted"},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["requestId"] == response.headers["X-Request-ID"]
    assert "fields" in error["details"]


def test_disabled_user_loses_access_immediately(client, users, colleague_headers):
    before = client.get("/api/v1/boards", headers=colleague_headers)
    assert before.status_code == 200
    with SessionLocal() as db:
        set_user_active(db, users["colleague"]["username"], False)
    after = client.get("/api/v1/boards", headers=colleague_headers)
    assert after.status_code == 403
    assert after.json()["error"]["code"] == "USER_DISABLED"
