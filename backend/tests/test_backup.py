"""Backup verification covers the collaboration schema."""

from pathlib import Path

from scripts.backup_db import verify_database


def test_backup_verification_includes_collaboration_tables(client):
    # Opening the TestClient ensures the application and test database are ready.
    response = client.get("/api/v1/ready")
    assert response.status_code == 200

    result = verify_database(Path("test-kanban.db"))
    assert result["alembicRevision"] == "20260806_0003"
    assert "card_comments" in result["rowCounts"]
    assert "card_checklist_items" in result["rowCounts"]
    assert "board_members" in result["rowCounts"]
    assert "notifications" in result["rowCounts"]
