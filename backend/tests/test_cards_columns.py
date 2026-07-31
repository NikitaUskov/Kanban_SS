"""Card movement, WIP, conflicts and activity integration tests."""

from uuid import uuid4


def snapshot(client, board_id, headers):
    response = client.get(f"/api/v1/boards/{board_id}/snapshot", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def create_card(client, board_id, column_id, headers, title, request_id=None):
    return client.post(
        f"/api/v1/boards/{board_id}/cards",
        headers=headers,
        json={
            "column_id": column_id,
            "title": title,
            "priority": "normal",
            "client_request_id": request_id or str(uuid4()),
        },
    )


def test_card_conflict_revision_and_activity(client, board, owner_headers):
    first_snapshot = snapshot(client, board["id"], owner_headers)
    column = first_snapshot["columns"][0]
    created = create_card(client, board["id"], column["id"], owner_headers, "Первая карточка")
    assert created.status_code == 201, created.text
    card = created.json()

    updated = client.patch(
        f"/api/v1/cards/{card['id']}",
        headers=owner_headers,
        json={
            "title": "Изменённая карточка",
            "expected_version": card["version"],
            "client_request_id": str(uuid4()),
        },
    )
    assert updated.status_code == 200

    stale = client.patch(
        f"/api/v1/cards/{card['id']}",
        headers=owner_headers,
        json={
            "title": "Устаревшая запись",
            "expected_version": card["version"],
            "client_request_id": str(uuid4()),
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "CARD_VERSION_CONFLICT"

    revision = client.get(f"/api/v1/boards/{board['id']}/revision", headers=owner_headers).json()
    assert revision["revision"] > first_snapshot["board"]["revision"]
    activity = client.get(f"/api/v1/boards/{board['id']}/activity", headers=owner_headers).json()
    actions = {item["action"] for item in activity["items"]}
    assert {"board.created", "card.created", "card.updated"}.issubset(actions)


def test_wip_limit_blocks_cross_column_move(client, board, owner_headers):
    current = snapshot(client, board["id"], owner_headers)
    source, target = current["columns"][:2]
    limited = client.patch(
        f"/api/v1/columns/{target['id']}",
        headers=owner_headers,
        json={
            "wip_limit": 1,
            "expected_version": target["version"],
            "client_request_id": str(uuid4()),
        },
    )
    assert limited.status_code == 200

    target_card = create_card(client, board["id"], target["id"], owner_headers, "Занимает WIP")
    source_card = create_card(client, board["id"], source["id"], owner_headers, "Нельзя перенести")
    assert target_card.status_code == 201
    assert source_card.status_code == 201

    move = client.post(
        f"/api/v1/cards/{source_card.json()['id']}/move",
        headers=owner_headers,
        json={
            "target_column_id": target["id"],
            "target_index": 1,
            "expected_version": source_card.json()["version"],
            "client_request_id": str(uuid4()),
        },
    )
    assert move.status_code == 409
    assert move.json()["error"]["code"] == "WIP_LIMIT_EXCEEDED"


def test_card_create_idempotency_and_nonempty_column_guard(client, board, owner_headers):
    current = snapshot(client, board["id"], owner_headers)
    column = current["columns"][0]
    request_id = str(uuid4())
    first = create_card(
        client,
        board["id"],
        column["id"],
        owner_headers,
        "Одна карточка",
        request_id,
    )
    repeated = create_card(
        client,
        board["id"],
        column["id"],
        owner_headers,
        "Одна карточка",
        request_id,
    )
    assert first.status_code == 201
    assert repeated.status_code == 201
    assert first.json()["id"] == repeated.json()["id"]

    refreshed = snapshot(client, board["id"], owner_headers)
    current_column = next(item for item in refreshed["columns"] if item["id"] == column["id"])
    deletion = client.request(
        "DELETE",
        f"/api/v1/columns/{column['id']}",
        headers=owner_headers,
        json={
            "expected_version": current_column["version"],
            "client_request_id": str(uuid4()),
        },
    )
    assert deletion.status_code == 409
    assert deletion.json()["error"]["code"] == "COLUMN_NOT_EMPTY"
