"""Authentication and user lifecycle tests."""

from app.auth.security import hash_password, verify_password
from app.database import SessionLocal
from app.models import User


def test_argon2id_hash_and_verify():
    encoded = hash_password("LongEnough-Password")
    assert encoded.startswith("$argon2id$")
    assert verify_password("LongEnough-Password", encoded)
    assert not verify_password("wrong-password", encoded)


def test_login_refresh_rotation_and_logout(client, users):
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "StrongPass-01"},
    )
    assert login.status_code == 200
    first = login.json()
    assert first["expires_in"] == 12 * 60 * 60
    assert first["refresh_expires_in"] == 30 * 24 * 60 * 60

    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {first['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["username"] == "owner"

    rotated = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first["refresh_token"]},
    )
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != first["refresh_token"]

    replay = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first["refresh_token"]},
    )
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "REFRESH_REVOKED"

    logout = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {rotated.json()['access_token']}"},
        json={"refresh_token": rotated.json()["refresh_token"]},
    )
    assert logout.status_code == 204


def test_password_is_not_stored_in_plain_text(users):
    with SessionLocal() as db:
        user = db.get(User, users["owner"]["id"])
        assert user.password_hash != users["owner"]["password"]
        assert user.password_hash.startswith("$argon2id$")


def test_password_change_revokes_refresh_and_accepts_new_password(client, users):
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "StrongPass-01"},
    )
    pair = login.json()
    changed = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {pair['access_token']}"},
        json={
            "current_password": "StrongPass-01",
            "new_password": "NewStrongPass-03",
        },
    )
    assert changed.status_code == 200

    old_refresh = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": pair["refresh_token"]},
    )
    assert old_refresh.status_code == 401
    old_login = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "StrongPass-01"},
    )
    assert old_login.status_code == 401
    new_login = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "NewStrongPass-03"},
    )
    assert new_login.status_code == 200
