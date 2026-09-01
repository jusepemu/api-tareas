from sqlmodel import Session, select

from app.models.user import User

REGISTER_ENDPOINT = "/api/v1/auth/register"


def test_register_returns_200_when_valid_data(client):
    email = "test@example.com"
    password = "secret123"

    response = client.post(
        REGISTER_ENDPOINT,
        json={"email": email, "password": password},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "registered successfully" in data["message"]


def test_register_creates_user_in_db_when_valid_data(client, session):
    email = "dbtest@example.com"
    password = "secret123"

    client.post(
        REGISTER_ENDPOINT,
        json={"email": email, "password": password},
    )

    user = session.exec(select(User).where(User.email == email)).first()
    assert user is not None
    assert user.email == email
    assert user.password_hash != password
    assert user.id is not None


def test_register_returns_409_when_email_already_registered(client, session: Session):
    user = User(email="test@example.com", password_hash="secret123")
    session.add(user)
    session.commit()

    response = client.post(
        REGISTER_ENDPOINT,
        json={"email": "test@example.com", "password": "secret123"},
    )

    assert response.status_code == 409


def test_register_returns_422_when_password_too_short(client):
    response = client.post(
        REGISTER_ENDPOINT, json={"email": "test@example.com", "password": "short"}
    )

    assert response.status_code == 422


def test_register_returns_422_when_password_is_blank(client):
    response = client.post(
        REGISTER_ENDPOINT, json={"email": "test@example.com", "password": ""}
    )

    assert response.status_code == 422


def test_register_returns_422_when_email_is_blank(client):
    response = client.post(
        REGISTER_ENDPOINT, json={"email": "", "password": "secret123"}
    )

    assert response.status_code == 422


def test_register_returns_422_when_email_is_invalid(client):
    response = client.post(
        REGISTER_ENDPOINT, json={"email": "invalid-email", "password": "secret123"}
    )

    assert response.status_code == 422


def test_register_returns_422_when_password_is_whitespace_only(client, session):
    email = "whitespace@example.com"
    password = "        "

    response = client.post(
        REGISTER_ENDPOINT,
        json={"email": email, "password": password},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(error["loc"][-1] == "password" for error in detail)

    user = session.exec(select(User).where(User.email == email)).first()
    assert user is None
