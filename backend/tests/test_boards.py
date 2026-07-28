"""Board visibility, revision, archive and idempotency tests."""

from uuid import uuid4


def test_all_active_users_see_the_same_board(
    client, board, owner_headers, colleague_headers
):
    owner_list = client.get("/api/v1/boards", headers=owner_headers)
    colleague_list = client.get("/api/v1/boards", headers=colleague_headers)
    assert owner_list.status_code == 200
    assert colleague_list.status_code == 200
    assert owner_list.json()["items"][0]["id"] == board["id"]
    assert colleague_list.json()["items"][0]["id"] == board["id"]
    assert owner_list.json()["items"][0]["column_count"] == 5


def test_board_create_is_idempotent(client, owner_headers):
    request_id = str(uuid4())
    payload = {
        "title": "Идемпотентная доска",
        "create_default_columns": False,
        "client_request_id": request_id,
    }
    first = client.post("/api/v1/boards", headers=owner_headers, json=payload)
    second = client.post("/api/v1/boards", headers=owner_headers, json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    listing = client.get("/api/v1/boards", headers=owner_headers).json()
    assert len(listing["items"]) == 1


def test_board_archive_and_restore(client, board, owner_headers):
    archived = client.request(
        "DELETE",
        f"/api/v1/boards/{board['id']}",
        headers=owner_headers,
        json={
            "expected_version": board["version"],
            "client_request_id": str(uuid4()),
        },
    )
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    active_list = client.get("/api/v1/boards", headers=owner_headers).json()
    assert active_list["items"] == []

    restored = client.post(
        f"/api/v1/boards/{board['id']}/restore",
        headers=owner_headers,
        json={
            "expected_version": archived.json()["version"],
            "client_request_id": str(uuid4()),
        },
    )
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None

