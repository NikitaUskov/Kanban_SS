"""Version 1.3 invitation, board access, subtasks and notification tests."""

from urllib.parse import parse_qs, urlparse
from uuid import uuid4


def token_from_url(url: str, key: str) -> str:
    values = parse_qs(urlparse(url).query).get(key)
    assert values
    return values[0]


def grant(client, board_id, user_id, headers, role="editor"):
    response = client.put(
        f"/api/v1/boards/{board_id}/members/{user_id}",
        headers=headers,
        json={"role": role},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_invitation_acceptance_and_login_by_email(client, board, owner_headers):
    created = client.post(
        "/api/v1/admin/invitations",
        headers=owner_headers,
        json={
            "email": "new.member@example.com",
            "display_name": "Новый участник",
            "system_role": "member",
            "board_access": [{"board_id": board["id"], "role": "editor"}],
            "send_email": False,
        },
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["email_status"] == "created"
    assert payload["invite_url"]
    token = token_from_url(payload["invite_url"], "invite")

    preview = client.get(f"/api/v1/auth/invitations/{token}")
    assert preview.status_code == 200, preview.text
    assert preview.json()["email"] == "new.member@example.com"

    accepted = client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "token": token,
            "username": "new.member",
            "display_name": "Новый участник",
            "password": "StrongPass-13",
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["user"]["email_verified_at"] is not None

    reused = client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "token": token,
            "username": "another.member",
            "password": "StrongPass-14",
        },
    )
    assert reused.status_code == 410

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "new.member@example.com", "password": "StrongPass-13"},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    boards = client.get("/api/v1/boards", headers=headers)
    assert boards.status_code == 200
    assert boards.json()["items"][0]["id"] == board["id"]
    assert boards.json()["items"][0]["current_user_role"] == "editor"


def test_viewer_cannot_mutate_and_member_cannot_create_board(
    client, board, users, owner_headers, colleague_headers
):
    grant(client, board["id"], users["colleague"]["id"], owner_headers, "viewer")
    snapshot = client.get(f"/api/v1/boards/{board['id']}/snapshot", headers=colleague_headers)
    assert snapshot.status_code == 200
    column_id = snapshot.json()["columns"][0]["id"]
    forbidden = client.post(
        f"/api/v1/boards/{board['id']}/cards",
        headers=colleague_headers,
        json={
            "column_id": column_id,
            "title": "Нельзя создать",
            "client_request_id": str(uuid4()),
        },
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "BOARD_ROLE_INSUFFICIENT"

    create_board = client.post(
        "/api/v1/boards",
        headers=colleague_headers,
        json={"title": "Лишняя доска", "create_default_columns": False},
    )
    assert create_board.status_code == 403
    assert create_board.json()["error"]["code"] == "ADMIN_REQUIRED"


def test_subtasks_are_one_level_and_update_parent_progress(client, board, owner_headers):
    snapshot = client.get(f"/api/v1/boards/{board['id']}/snapshot", headers=owner_headers).json()
    column_id = snapshot["columns"][0]["id"]
    parent = client.post(
        f"/api/v1/boards/{board['id']}/cards",
        headers=owner_headers,
        json={
            "column_id": column_id,
            "title": "Основная задача",
            "client_request_id": str(uuid4()),
        },
    )
    assert parent.status_code == 201, parent.text
    parent = parent.json()
    subtask = client.post(
        f"/api/v1/boards/{board['id']}/cards",
        headers=owner_headers,
        json={
            "column_id": column_id,
            "parent_card_id": parent["id"],
            "title": "Подзадача",
            "client_request_id": str(uuid4()),
        },
    )
    assert subtask.status_code == 201, subtask.text
    subtask = subtask.json()

    current = client.get(f"/api/v1/boards/{board['id']}/snapshot", headers=owner_headers).json()
    assert {item["id"] for item in current["cards"]} == {parent["id"]}
    parent_summary = current["cards"][0]
    assert parent_summary["subtask_total"] == 1
    assert parent_summary["subtask_completed"] == 0

    detail = client.get(f"/api/v1/cards/{parent['id']}", headers=owner_headers)
    assert detail.status_code == 200
    assert detail.json()["subtasks"][0]["id"] == subtask["id"]

    nested = client.post(
        f"/api/v1/boards/{board['id']}/cards",
        headers=owner_headers,
        json={
            "column_id": column_id,
            "parent_card_id": subtask["id"],
            "title": "Слишком глубокая",
            "client_request_id": str(uuid4()),
        },
    )
    assert nested.status_code == 400
    assert nested.json()["error"]["code"] == "SUBTASK_DEPTH_LIMIT"

    completed = client.patch(
        f"/api/v1/cards/{subtask['id']}",
        headers=owner_headers,
        json={
            "completed": True,
            "expected_version": subtask["version"],
            "client_request_id": str(uuid4()),
        },
    )
    assert completed.status_code == 200, completed.text
    refreshed = client.get(f"/api/v1/cards/{parent['id']}", headers=owner_headers)
    assert refreshed.json()["subtask_completed"] == 1


def test_assignment_and_mentions_create_notifications(
    client, board, users, owner_headers, colleague_headers
):
    grant(client, board["id"], users["colleague"]["id"], owner_headers, "editor")
    snapshot = client.get(f"/api/v1/boards/{board['id']}/snapshot", headers=owner_headers).json()
    created = client.post(
        f"/api/v1/boards/{board['id']}/cards",
        headers=owner_headers,
        json={
            "column_id": snapshot["columns"][0]["id"],
            "title": "Задача с уведомлениями",
            "assignee_user_id": users["colleague"]["id"],
            "client_request_id": str(uuid4()),
        },
    )
    assert created.status_code == 201, created.text
    card = created.json()
    comment = client.post(
        f"/api/v1/cards/{card['id']}/comments",
        headers=owner_headers,
        json={
            "body": "@colleague, проверьте задачу",
            "client_request_id": str(uuid4()),
        },
    )
    assert comment.status_code == 201, comment.text

    notifications = client.get("/api/v1/notifications?limit=20", headers=colleague_headers)
    assert notifications.status_code == 200
    types = {item["type"] for item in notifications.json()["items"]}
    assert {"assignment", "mention"}.issubset(types)
    assert notifications.json()["unread_count"] >= 2

    marked = client.post("/api/v1/notifications/read-all", headers=colleague_headers)
    assert marked.status_code == 204
    count = client.get("/api/v1/notifications/unread-count", headers=colleague_headers)
    assert count.json()["unread_count"] == 0


def test_manual_password_reset_link_revokes_old_password(client, users, owner_headers):
    created = client.post(
        f"/api/v1/admin/users/{users['colleague']['id']}/password-reset-link",
        headers=owner_headers,
    )
    assert created.status_code == 200, created.text
    token = token_from_url(created.json()["reset_url"], "reset-password")
    confirmed = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "ResetStrongPass-13"},
    )
    assert confirmed.status_code == 200, confirmed.text
    old = client.post(
        "/api/v1/auth/login",
        json={"username": "colleague", "password": "StrongPass-02"},
    )
    assert old.status_code == 401
    new = client.post(
        "/api/v1/auth/login",
        json={"username": "colleague", "password": "ResetStrongPass-13"},
    )
    assert new.status_code == 200
