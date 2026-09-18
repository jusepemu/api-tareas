import os
from datetime import timedelta

import jwt
from sqlmodel import Session, select

from app.features.auth.service import hash_refresh_token, utc_now
from app.models import UserSession

REGISTER_ENDPOINT = "/api/v1/auth/register"
TOKEN_ENDPOINT = "/api/v1/auth/token"


def register_and_login(client, email: str, password: str) -> dict:
    client.post(REGISTER_ENDPOINT, json={"email": email, "password": password})
    response = client.post(
        TOKEN_ENDPOINT, data={"username": email, "password": password}
    )
    return response.json()


def get_session_by_refresh(session: Session, refresh_token: str) -> UserSession | None:
    return session.exec(
        select(UserSession).where(
            UserSession.refresh_token_hash == hash_refresh_token(refresh_token)
        )
    ).first()


def make_expired_access_token(user_id: str) -> str:
    return jwt.encode(
        {"sub": user_id, "exp": utc_now() - timedelta(minutes=5)},
        os.getenv("SECRET_KEY"),
        algorithm=os.getenv("ALGORITHM"),
    )
