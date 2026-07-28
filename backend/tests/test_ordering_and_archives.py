"""Ordering, cross-column movement, archive restore and idempotency guards."""

from uuid import uuid4


def get_snapshot(client, board_id, headers, include_archived=False):
    response = client.get(
        f"/api/v1/boards/{board_id}/snapshot",
        headers=headers,
        params={"include_archived": str(include_archived).lower()},
    )
    assert response.status_code == 200, response.text
    return response.json()


def create_card(client, board_id, column_id, headers, title):
    response = client.post(
        f"/api/v1/boards/{board_id}/cards",
        headers=headers,
        json={
            "column_id": column_id,
            "title": title,
            "client_request_id": str(uuid4()),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_card_positions_remain_dense_after_moves(client, board, owner_headers):
    initial = get_snapshot(client, board["id"], owner_headers)
    source, target = initial["columns"][:2]
    first = create_card(client, board["id"], source["id"], owner_headers, "Первая")
    second = create_card(client, board["id"], source["id"], owner_headers, "Вторая")
    third = create_card(client, board["id"], source["id"], owner_headers, "Третья")

    moved_inside = client.post(
        f"/api/v1/cards/{third['id']}/move",
        headers=owner_headers,
        json={
            "target_column_id": source["id"],
            "target_index": 0,
            "expected_version": third["version"],
            "client_request_id": str(uuid4()),
        },
    )
    assert moved_inside.status_code == 200, moved_inside.text

    after_inside = get_snapshot(client, board["id"], owner_headers)
    second_current = next(item for item in after_inside["cards"] if item["id"] == second["id"])
    moved_across = client.post(
        f"/api/v1/cards/{second['id']}/move",
        headers=owner_headers,
        json={
            "target_column_id": target["id"],
            "target_index": 0,
            "expected_version": second_current["version"],
            "client_request_id": str(uuid4()),
        },
    )
    assert moved_across.status_code == 200, moved_across.text

    final = get_snapshot(client, board["id"], owner_headers)
    source_cards = sorted(
        (item for item in final["cards"] if item["column_id"] == source["id"]),
        key=lambda item: item["position"],
    )
    target_cards = sorted(
        (item for item in final["cards"] if item["column_id"] == target["id"]),
        key=lambda item: item["position"],
    )
    assert [item["id"] for item in source_cards] == [third["id"], first["id"]]
    assert [item["position"] for item in source_cards] == [0, 1]
    assert [item["id"] for item in target_cards] == [second["id"]]
    assert [item["position"] for item in target_cards] == [0]


def test_archive_and_restore_card(client, board, owner_headers):
    initial = get_snapshot(client, board["id"], owner_headers)
    first_column, restore_column = initial["columns"][:2]
    card = create_card(
        client,
        board["id"],
        first_column["id"],
        owner_headers,
        "Архивируемая",
    )
    archived = client.request(
        "DELETE",
        f"/api/v1/cards/{card['id']}",
        headers=owner_headers,
        json={
            "expected_version": card["version"],
            "client_request_id": str(uuid4()),
        },
    )
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None

    active = get_snapshot(client, board["id"], owner_headers)
    assert card["id"] not in {item["id"] for item in active["cards"]}
    with_archive = get_snapshot(client, board["id"], owner_headers, True)
    assert card["id"] in {item["id"] for item in with_archive["cards"]}

    restored = client.post(
        f"/api/v1/cards/{card['id']}/restore",
        headers=owner_headers,
        json={
            "target_column_id": restore_column["id"],
            "expected_version": archived.json()["version"],
            "client_request_id": str(uuid4()),
        },
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["archived_at"] is None
    assert restored.json()["column_id"] == restore_column["id"]


def test_client_request_id_cannot_be_reused_for_another_action(
    client, board, owner_headers
):
    request_id = str(uuid4())
    created = client.post(
        f"/api/v1/boards/{board['id']}/columns",
        headers=owner_headers,
        json={
            "title": "Временная",
            "client_request_id": request_id,
        },
    )
    assert created.status_code == 201
    reused = client.post(
        f"/api/v1/boards/{board['id']}/cards",
        headers=owner_headers,
        json={
            "column_id": created.json()["id"],
            "title": "Не должна создаться",
            "client_request_id": request_id,
        },
    )
    assert reused.status_code == 409
    assert reused.json()["error"]["code"] == "CLIENT_REQUEST_ID_REUSED"


def test_nonempty_column_can_move_cards_before_delete(
    client, board, owner_headers
):
    initial = get_snapshot(client, board["id"], owner_headers)
    source, target = initial["columns"][:2]
    card = create_card(client, board["id"], source["id"], owner_headers, "Переносимая")
    deleted = client.request(
        "DELETE",
        f"/api/v1/columns/{source['id']}",
        headers=owner_headers,
        json={
            "expected_version": source["version"],
            "card_action": "move",
            "target_column_id": target["id"],
            "client_request_id": str(uuid4()),
        },
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["archived_at"] is not None
    final = get_snapshot(client, board["id"], owner_headers)
    moved = next(item for item in final["cards"] if item["id"] == card["id"])
    assert moved["column_id"] == target["id"]
    assert [item["position"] for item in final["columns"]] == list(
        range(len(final["columns"]))
    )
