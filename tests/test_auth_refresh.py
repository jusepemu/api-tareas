import os

import jwt
from sqlmodel import Session, select

from app.models import User
from tests.helpers import get_session_by_refresh, register_and_login

REFRESH_ENDPOINT = "/api/v1/auth/refresh"

EMAIL = "refresh@example.com"
PASSWORD = "correct-password-123"


def test_refresh_rotates_session_when_refresh_sent_via_cookie(client, session: Session):
    # Arrange — login deja la cookie en el jar del client
    login = register_and_login(client, EMAIL, PASSWORD)
    user = session.exec(select(User).where(User.email == EMAIL)).first()
    assert user is not None

    # Act — el refresh viaja por cookie (el access sigue yendo en el body)
    response = client.post(
        REFRESH_ENDPOINT,
        json={"access_token": login["access_token"]},
    )

    # Assert
    assert response.status_code == 200
    body = response.json()

    # El refresh viejo quedó inutilizable
    old = get_session_by_refresh(session, login["refresh_token"])
    assert old is not None
    assert old.revoked_at is not None

    # Nace una sesión nueva, activa, del mismo usuario
    new = get_session_by_refresh(session, body["refresh_token"])
    assert new is not None
    assert new.revoked_at is None
    assert new.user_id == user.id

    # El access nuevo sigue siendo del usuario
    payload = jwt.decode(
        body["access_token"],
        os.getenv("SECRET_KEY"),
        algorithms=[os.getenv("ALGORITHM")],
    )
    assert payload["sub"] == user.id

    # Respuesta dual-channel: la cookie nueva == el refresh del body
    assert response.cookies.get("refresh_token") == body["refresh_token"]


def test_refresh_rotates_session_when_refresh_sent_via_body(client, session: Session):
    # Arrange — sin cookie: forzamos el else path
    login = register_and_login(client, EMAIL, PASSWORD)
    client.cookies.clear()

    # Act
    response = client.post(
        REFRESH_ENDPOINT,
        json={
            "refresh_token": login["refresh_token"],
            "access_token": login["access_token"],
        },
    )

    # Assert
    assert response.status_code == 200
    body = response.json()

    old = get_session_by_refresh(session, login["refresh_token"])
    assert old is not None
    assert old.revoked_at is not None

    new = get_session_by_refresh(session, body["refresh_token"])
    assert new is not None
    assert new.revoked_at is None


def test_refresh_returns_401_when_old_refresh_is_reused(client):
    # Arrange
    login = register_and_login(client, EMAIL, PASSWORD)
    client.cookies.clear()

    first = client.post(
        REFRESH_ENDPOINT,
        json={
            "refresh_token": login["refresh_token"],
            "access_token": login["access_token"],
        },
    )
    assert first.status_code == 200
    new_access = first.json()["access_token"]

    # Act — reusar el refresh viejo (ya rotado)
    client.cookies.clear()
    second = client.post(
        REFRESH_ENDPOINT,
        json={
            "refresh_token": login["refresh_token"],
            "access_token": new_access,
        },
    )

    # Assert
    assert second.status_code == 401
