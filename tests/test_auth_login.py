import os

import jwt
import pytest
from sqlmodel import Session, select

from app.features.auth.service import hash_refresh_token
from app.models import User, UserSession

REGISTER_ENDPOINT = "/api/v1/auth/register"
TOKEN_ENDPOINT = "/api/v1/auth/token"

EMAIL = "login@example.com"
PASSWORD = "correct-password-123"


def test_token_returns_tokens_and_creates_session_when_credentials_are_valid(
    client, session: Session
):
    # Arrange — usuario real con hash real
    client.post(REGISTER_ENDPOINT, json={"email": EMAIL, "password": PASSWORD})
    user = session.exec(select(User).where(User.email == EMAIL)).first()
    assert user is not None

    # Act — formulario (no JSON), como espera OAuth2PasswordRequestForm
    response = client.post(
        TOKEN_ENDPOINT,
        data={"username": EMAIL, "password": PASSWORD},
    )

    # Assert
    # 1. Lo que ve el cliente
    assert response.status_code == 200

    body = response.json()
    access_token = body["access_token"]
    refresh_token = body["refresh_token"]

    # 2. El access es un JWT y su sub es el id del usuario
    payload = jwt.decode(
        access_token,
        os.getenv("SECRET_KEY"),
        algorithms=[os.getenv("ALGORITHM")],
    )
    assert payload["sub"] == user.id

    # 3. El refresh es opaco: no se decodifica como JWT
    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(
            refresh_token,
            os.getenv("SECRET_KEY"),
            algorithms=[os.getenv("ALGORITHM")],
        )

    # 4. Dual-channel: la cookie y el body llevan el mismo refresh
    assert response.cookies.get("refresh_token") == refresh_token

    # 5. Estado en la DB: una sesión activa con el hash del refresh devuelto
    sessions = session.exec(
        select(UserSession).where(UserSession.user_id == user.id)
    ).all()
    assert len(sessions) == 1
    stored = sessions[0]
    assert stored.refresh_token_hash == hash_refresh_token(refresh_token)
    assert stored.refresh_token_hash != refresh_token
    assert stored.revoked_at is None
