"""Shared integration test fixtures."""

import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///./test-kanban.db"
os.environ["JWT_SECRET"] = "test-secret-that-is-longer-than-thirty-two-characters"
os.environ["LOG_DIR"] = "./test-logs"
os.environ["ALLOWED_ORIGINS"] = "http://localhost:5500"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.users.service import NewUser, create_user


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def users():
    with SessionLocal() as db:
        owner = create_user(db, NewUser("owner", "Владелец", "StrongPass-01"))
        colleague = create_user(db, NewUser("colleague", "Коллега", "StrongPass-02"))
        return {
            "owner": {"id": owner.id, "username": owner.username, "password": "StrongPass-01"},
            "colleague": {
                "id": colleague.id,
                "username": colleague.username,
                "password": "StrongPass-02",
            },
        }


def login_headers(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def owner_headers(client, users):
    return login_headers(client, users["owner"]["username"], users["owner"]["password"])


@pytest.fixture
def colleague_headers(client, users):
    return login_headers(
        client,
        users["colleague"]["username"],
        users["colleague"]["password"],
    )


@pytest.fixture
def board(client, owner_headers):
    response = client.post(
        "/api/v1/boards",
        headers=owner_headers,
        json={
            "title": "Тестовая доска",
            "description": "Доска интеграционных тестов",
            "create_default_columns": True,
            "client_request_id": "dd8eb6e3-4b8d-48dc-b8d6-02bf4fb43d84",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()
