"""Version 1.2 assignee, completion, comments and checklist integration tests."""

from uuid import uuid4


def snapshot(client, board_id, headers):
    response = client.get(f"/api/v1/boards/{board_id}/snapshot", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def create_card(client, board, headers, *, assignee_user_id=None):
    current = snapshot(client, board["id"], headers)
    payload = {
        "column_id": current["columns"][0]["id"],
        "title": "Совместная задача",
        "priority": "high",
        "client_request_id": str(uuid4()),
    }
    if assignee_user_id:
        payload["assignee_user_id"] = assignee_user_id
    response = client.post(
        f"/api/v1/boards/{board['id']}/cards",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_active_user_directory_and_assignee_completion(client, board, users, owner_headers):
    membership = client.put(
        f"/api/v1/boards/{board['id']}/members/{users['colleague']['id']}",
        headers=owner_headers,
        json={"role": "editor"},
    )
    assert membership.status_code == 200, membership.text
    directory = client.get("/api/v1/users?active_only=true", headers=owner_headers)
    assert directory.status_code == 200
    assert {item["username"] for item in directory.json()["items"]} == {
        "owner",
        "colleague",
    }

    card = create_card(
        client,
        board,
        owner_headers,
        assignee_user_id=users["colleague"]["id"],
    )
    assert card["assignee"]["username"] == "colleague"
    assert card["completed_at"] is None

    completed = client.patch(
        f"/api/v1/cards/{card['id']}",
        headers=owner_headers,
        json={
            "completed": True,
            "expected_version": card["version"],
            "client_request_id": str(uuid4()),
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["completed_at"] is not None

    cleared = client.patch(
        f"/api/v1/cards/{card['id']}",
        headers=owner_headers,
        json={
            "clear_assignee": True,
            "completed": False,
            "expected_version": completed.json()["version"],
            "client_request_id": str(uuid4()),
        },
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["assignee"] is None
    assert cleared.json()["completed_at"] is None


def test_comments_are_counted_and_only_author_can_edit(
    client, board, users, owner_headers, colleague_headers
):
    membership = client.put(
        f"/api/v1/boards/{board['id']}/members/{users['colleague']['id']}",
        headers=owner_headers,
        json={"role": "editor"},
    )
    assert membership.status_code == 200, membership.text
    card = create_card(client, board, owner_headers)
    created = client.post(
        f"/api/v1/cards/{card['id']}/comments",
        headers=owner_headers,
        json={"body": "Первый комментарий", "client_request_id": str(uuid4())},
    )
    assert created.status_code == 201, created.text
    comment = created.json()

    forbidden = client.patch(
        f"/api/v1/comments/{comment['id']}",
        headers=colleague_headers,
        json={
            "body": "Чужое изменение",
            "expected_version": comment["version"],
            "client_request_id": str(uuid4()),
        },
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "COMMENT_FORBIDDEN"

    updated = client.patch(
        f"/api/v1/comments/{comment['id']}",
        headers=owner_headers,
        json={
            "body": "Уточнённый комментарий",
            "expected_version": comment["version"],
            "client_request_id": str(uuid4()),
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["edited_at"] is not None

    detail = client.get(f"/api/v1/cards/{card['id']}", headers=owner_headers)
    assert detail.status_code == 200
    assert detail.json()["comment_count"] == 1
    assert detail.json()["comments"][0]["body"] == "Уточнённый комментарий"

    delete_request_id = str(uuid4())
    delete_payload = {
        "expected_version": updated.json()["version"],
        "client_request_id": delete_request_id,
    }
    deleted = client.request(
        "DELETE",
        f"/api/v1/comments/{comment['id']}",
        headers=owner_headers,
        json=delete_payload,
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted_at"] is not None

    repeated = client.request(
        "DELETE",
        f"/api/v1/comments/{comment['id']}",
        headers=owner_headers,
        json=delete_payload,
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["id"] == comment["id"]

    refreshed = client.get(f"/api/v1/cards/{card['id']}", headers=owner_headers).json()
    assert refreshed["comment_count"] == 0
    assert refreshed["comments"] == []


def test_checklist_crud_order_and_snapshot_counters(client, board, owner_headers):
    card = create_card(client, board, owner_headers)
    first = client.post(
        f"/api/v1/cards/{card['id']}/checklist-items",
        headers=owner_headers,
        json={"text": "Первый шаг", "client_request_id": str(uuid4())},
    )
    second = client.post(
        f"/api/v1/cards/{card['id']}/checklist-items",
        headers=owner_headers,
        json={"text": "Второй шаг", "client_request_id": str(uuid4())},
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text

    completed = client.patch(
        f"/api/v1/checklist-items/{second.json()['id']}",
        headers=owner_headers,
        json={
            "is_completed": True,
            "expected_version": second.json()["version"],
            "client_request_id": str(uuid4()),
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["completed_by"] is not None

    moved = client.post(
        f"/api/v1/checklist-items/{completed.json()['id']}/move",
        headers=owner_headers,
        json={
            "target_index": 0,
            "expected_version": completed.json()["version"],
            "client_request_id": str(uuid4()),
        },
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["position"] == 0

    detail = client.get(f"/api/v1/cards/{card['id']}", headers=owner_headers).json()
    assert [item["text"] for item in detail["checklist_items"]] == [
        "Второй шаг",
        "Первый шаг",
    ]
    assert detail["checklist_total"] == 2
    assert detail["checklist_completed"] == 1

    board_snapshot = snapshot(client, board["id"], owner_headers)
    summary = next(item for item in board_snapshot["cards"] if item["id"] == card["id"])
    assert summary["checklist_total"] == 2
    assert summary["checklist_completed"] == 1

    first_after_move = detail["checklist_items"][1]
    delete_payload = {
        "expected_version": first_after_move["version"],
        "client_request_id": str(uuid4()),
    }
    deleted = client.request(
        "DELETE",
        f"/api/v1/checklist-items/{first_after_move['id']}",
        headers=owner_headers,
        json=delete_payload,
    )
    assert deleted.status_code == 204, deleted.text
    repeated = client.request(
        "DELETE",
        f"/api/v1/checklist-items/{first_after_move['id']}",
        headers=owner_headers,
        json=delete_payload,
    )
    assert repeated.status_code == 204, repeated.text
    final = client.get(f"/api/v1/cards/{card['id']}", headers=owner_headers).json()
    assert final["checklist_total"] == 1
