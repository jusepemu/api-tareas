import os
from datetime import timedelta
from typing import Any

import jwt
import pytest
from fastapi import HTTPException
from sqlmodel import Session

from app.deps import get_active_current_user
from app.features.auth.service import create_access_token, decode_access_token, utc_now
from app.models.user import User

SECRET = "SECRET_KEY"
ALG = "ALGORITHM"


def encode(payload: dict[str, Any], secret: str | None = None) -> str:
    return jwt.encode(payload, secret or os.getenv(SECRET), algorithm=os.getenv(ALG))


def make_user(session: Session, email: str) -> User:
    user = User(email=email, password_hash="hashed_secret_not_used_here")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


# --- decode_access_token ---
def test_decode_access_token_raises_invalid_when_expired():
    token = encode({"sub": "u1", "exp": utc_now() - timedelta(minutes=5)})

    with pytest.raises(HTTPException) as exc:
        decode_access_token(token)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid token"


def test_decode_access_token_raises_invalid_when_tampered():
    token = create_access_token({"sub": "u1"})
    tampered = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")

    with pytest.raises(HTTPException) as exc:
        decode_access_token(tampered)

    assert exc.value.status_code == 401


def test_decode_access_token_raises_invalid_when_wrong_secret():
    token = encode(
        {"sub": "u1", "exp": utc_now() + timedelta(minutes=5)},
        "attacker_key_that_is_long_enough_to_be_valid",
    )

    with pytest.raises(HTTPException) as exc:
        decode_access_token(token)

    assert exc.value.status_code == 401


def test_decode_access_token_raises_invalid_when_not_a_jwt():
    with pytest.raises(HTTPException) as exc:
        decode_access_token("esto-no-es-un-jwt")

    assert exc.value.status_code == 401


# --- get_active_current_user ---
def test_get_active_current_user_returns_user_when_valid_token(session):
    user = make_user(session, "fn@example.com")
    token = create_access_token({"sub": user.id})

    result = get_active_current_user(token, session)

    assert result.id == user.id
    assert result.email == user.email


def test_get_active_current_user_raises_invalid_when_token_without_sub(session):
    token = encode({"exp": utc_now() + timedelta(minutes=5)})

    with pytest.raises(HTTPException) as exc:
        get_active_current_user(token, session)

    assert exc.value.status_code == 401


def test_get_active_current_user_raises_invalid_when_user_not_exists(session):
    token = create_access_token({"sub": "no-existe-uuid"})

    with pytest.raises(HTTPException) as exc:
        get_active_current_user(token, session)

    assert exc.value.status_code == 401
