"""Standalone 30-user smoke/load scenario for a running deployment."""

import argparse
import asyncio
import getpass
import os
import sys
from uuid import uuid4

import httpx


async def login(client: httpx.AsyncClient, username: str, password: str) -> str:
    response = await client.post("/auth/login", json={"username": username, "password": password})
    response.raise_for_status()
    return response.json()["access_token"]


async def read_loop(client: httpx.AsyncClient, token: str, board_id: str, iterations: int) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    for index in range(iterations):
        response = await client.get(f"/boards/{board_id}/revision", headers=headers)
        response.raise_for_status()
        if index % 4 == 0:
            snapshot = await client.get(f"/boards/{board_id}/snapshot", headers=headers)
            snapshot.raise_for_status()
        await asyncio.sleep(0.2)


async def mutation_loop(
    client: httpx.AsyncClient,
    token: str,
    board_id: str,
    source_column_id: str,
    target_column_id: str,
    index: int,
    run_id: str,
) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    create = await client.post(
        f"/boards/{board_id}/cards",
        headers=headers,
        json={
            "column_id": source_column_id,
            "title": f"Нагрузочная карточка {run_id}-{index}",
            "description": "Временная карточка нагрузочного сценария",
            "priority": "normal",
            "client_request_id": str(uuid4()),
        },
    )
    create.raise_for_status()
    card = create.json()
    update = await client.patch(
        f"/cards/{card['id']}",
        headers=headers,
        json={
            "priority": "high",
            "expected_version": card["version"],
            "client_request_id": str(uuid4()),
        },
    )
    update.raise_for_status()
    updated = update.json()
    move = await client.post(
        f"/cards/{card['id']}/move",
        headers=headers,
        json={
            "target_column_id": target_column_id,
            "target_index": index - 1,
            "expected_version": updated["version"],
            "client_request_id": str(uuid4()),
        },
    )
    move.raise_for_status()
    return card["id"]


async def run(args: argparse.Namespace) -> None:
    timeout = httpx.Timeout(20)
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/") + "/api/v1",
        timeout=timeout,
    ) as client:
        credentials = [
            (f"{args.username_prefix}{number:02d}", args.password)
            for number in range(1, args.users + 1)
        ]
        tokens = await asyncio.gather(
            *(login(client, username, password) for username, password in credentials)
        )
        headers = {"Authorization": f"Bearer {tokens[0]}"}
        snapshot = await client.get(f"/boards/{args.board_id}/snapshot", headers=headers)
        snapshot.raise_for_status()
        columns = snapshot.json()["columns"]
        if not columns:
            raise RuntimeError("На доске нет активных колонок")
        if len(columns) < 2:
            raise RuntimeError("Для нагрузочного сценария нужны минимум две активные колонки")
        source_column_id = columns[0]["id"]
        target_column_id = columns[1]["id"]
        run_id = uuid4().hex[:8]
        readers = [read_loop(client, token, args.board_id, args.iterations) for token in tokens]
        writers = [
            mutation_loop(
                client,
                tokens[index],
                args.board_id,
                source_column_id,
                target_column_id,
                index + 1,
                run_id,
            )
            for index in range(min(args.writers, len(tokens)))
        ]
        _reader_results, created_ids = await asyncio.gather(
            asyncio.gather(*readers),
            asyncio.gather(*writers),
        )
        final_snapshot_response = await client.get(
            f"/boards/{args.board_id}/snapshot",
            headers=headers,
        )
        final_snapshot_response.raise_for_status()
        final_snapshot = final_snapshot_response.json()
        actual_ids = {card["id"] for card in final_snapshot["cards"]}
        missing = sorted(set(created_ids) - actual_ids)
        if missing:
            raise RuntimeError(f"После нагрузки отсутствуют созданные карточки: {missing}")
        for column in final_snapshot["columns"]:
            positions = sorted(
                card["position"]
                for card in final_snapshot["cards"]
                if not card["archived_at"] and card["column_id"] == column["id"]
            )
            if positions != list(range(len(positions))):
                raise RuntimeError(f"Нарушены позиции в колонке {column['id']}: {positions}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True, help="Например http://127.0.0.1:8000")
    parser.add_argument("--board-id", required=True)
    parser.add_argument("--username-prefix", default="user")
    parser.add_argument(
        "--password",
        help=(
            "Не рекомендуется: пароль будет виден в command line. "
            "Без параметра используется безопасный prompt."
        ),
    )
    parser.add_argument("--users", type=int, default=30)
    parser.add_argument("--writers", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args()
    if args.users < 1:
        parser.error("--users должен быть не меньше 1")
    if args.writers < 1:
        parser.error("--writers должен быть не меньше 1")
    args.password = (
        args.password
        or os.environ.get("KANBAN_LOAD_TEST_PASSWORD")
        or getpass.getpass("Пароль тестовых пользователей: ")
    )
    if not args.password:
        parser.error("Пароль не может быть пустым")
    try:
        asyncio.run(run(args))
        print("Нагрузочный сценарий завершён без HTTP-ошибок")
        return 0
    except Exception as exc:
        print(f"Нагрузочный сценарий завершился ошибкой: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
