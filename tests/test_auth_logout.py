from sqlmodel import Session, select

from app.models import User
from tests.helpers import (
    get_session_by_refresh,
    make_expired_access_token,
    register_and_login,
)

LOGOUT_ENDPOINT = "/api/v1/auth/logout"

EMAIL_A = "logout-a@example.com"
EMAIL_B = "logout-b@example.com"
PASSWORD = "correct-password-123"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def get_user(session: Session, email: str) -> User:
    user = session.exec(select(User).where(User.email == email)).first()
    assert user is not None
    return user


def test_logout_returns_204_and_revokes_session_when_tokens_are_valid(
    client, session: Session
):
    # Arrange — login deja la cookie y crea la UserSession
    login = register_and_login(client, EMAIL_A, PASSWORD)

    # Act — el refresh viaja por cookie
    response = client.post(LOGOUT_ENDPOINT, headers=bearer(login["access_token"]))

    # Assert
    assert response.status_code == 204

    stored = get_session_by_refresh(session, login["refresh_token"])
    assert stored is not None
    assert stored.revoked_at is not None
    assert stored.last_used_at is not None

    # El contrato incluye borrar la cookie en el cliente
    set_cookie = response.headers["set-cookie"].lower()
    assert "refresh_token=" in set_cookie
    assert "max-age=0" in set_cookie
    assert client.cookies.get("refresh_token") is None


def test_logout_returns_401_and_keeps_session_when_refresh_is_absent(
    client, session: Session
):
    login = register_and_login(client, EMAIL_A, PASSWORD)
    client.cookies.clear()

    response = client.post(LOGOUT_ENDPOINT, headers=bearer(login["access_token"]))

    assert response.status_code == 401

    stored = get_session_by_refresh(session, login["refresh_token"])
    assert stored is not None
    assert stored.revoked_at is None
    assert stored.last_used_at is None


def test_logout_returns_204_and_keeps_session_when_refresh_is_unknown(
    client, session: Session
):
    login = register_and_login(client, EMAIL_A, PASSWORD)
    client.cookies.clear()

    response = client.post(
        LOGOUT_ENDPOINT,
        headers=bearer(login["access_token"]),
        json={"refresh_token": "not-a-real-refresh-token"},
    )

    assert response.status_code == 204

    stored = get_session_by_refresh(session, login["refresh_token"])
    assert stored is not None
    assert stored.revoked_at is None
    assert stored.last_used_at is None


def test_logout_returns_204_and_keeps_other_session_when_refresh_belongs_to_another_user(
    client, session: Session
):
    login_a = register_and_login(client, EMAIL_A, PASSWORD)
    login_b = register_and_login(client, EMAIL_B, PASSWORD)
    client.cookies.clear()

    response = client.post(
        LOGOUT_ENDPOINT,
        headers=bearer(login_b["access_token"]),
        json={"refresh_token": login_a["refresh_token"]},
    )

    assert response.status_code == 204

    session_a = get_session_by_refresh(session, login_a["refresh_token"])
    assert session_a is not None
    assert session_a.revoked_at is None
    assert session_a.last_used_at is None


def test_logout_returns_204_and_revokes_session_when_access_is_expired(
    client, session: Session
):
    login = register_and_login(client, EMAIL_A, PASSWORD)
    client.cookies.clear()
    user = get_user(session, EMAIL_A)

    response = client.post(
        LOGOUT_ENDPOINT,
        headers=bearer(make_expired_access_token(user.id)),
        json={"refresh_token": login["refresh_token"]},
    )

    assert response.status_code == 204

    stored = get_session_by_refresh(session, login["refresh_token"])
    assert stored is not None
    assert stored.revoked_at is not None
