import os
from datetime import timedelta

import jwt
from sqlmodel import Session, select

from app.features.auth.service import create_access_token, utc_now
from app.models.user import User

ME_ENDPOINT = "/api/v1/auth/me"


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def make_user(session: Session, email: str) -> User:
    user = User(email=email, password_hash="hashed_secret_not_used_here")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def make_expired_token(user_id: str) -> str:
    expire = utc_now() - timedelta(minutes=5)
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        os.getenv("SECRET_KEY"),
        algorithm=os.getenv("ALGORITHM"),
    )


def test_me_returns_user_when_valid_token(client, session):
    user = make_user(session, "valid@example.com")
    token = create_access_token({"sub": user.id})

    response = client.get(ME_ENDPOINT, headers=auth_headers(token))

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["user"]["id"] == user.id
    assert data["user"]["email"] == user.email


def test_me_returns_401_when_no_token_sent(client):
    response = client.get(ME_ENDPOINT)

    assert response.status_code == 401


def test_me_returns_401_when_expired_token(client, session):
    user = make_user(session, "expired@example.com")

    assert user.id is not None, "User ID should not be None"

    token = make_expired_token(user.id)

    response = client.get(ME_ENDPOINT, headers=auth_headers(token))

    assert response.status_code == 401


def test_me_does_not_leak_password_hash_when_valid_token(client, session):
    user = make_user(session, "noleak@example.com")
    token = create_access_token({"sub": user.id})

    response = client.get(ME_ENDPOINT, headers=auth_headers(token))

    assert response.status_code == 200
    assert "password_hash" not in response.json()["user"]
    stored = session.exec(select(User).where(User.id == user.id)).first()
    assert stored.password_hash is not None
