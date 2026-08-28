import os
import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

import jwt
from fastapi import HTTPException, status
from pwdlib import PasswordHash
from sqlmodel import Session, select

from app.models import User, UserCreate, UserSession

password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("dummypassword")

INVALID_TOKEN_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid token",
    headers={"WWW-Authenticate": "Bearer"},
)
INVALID_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def create_access_token(data: dict[str, Any]) -> str:
    to_encode = data.copy()
    expires_in = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES") or 30)
    expire = utc_now() + timedelta(minutes=expires_in)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, os.getenv("SECRET_KEY"), algorithm=os.getenv("ALGORITHM")
    )
    return encoded_jwt


def create_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(refresh_token: str) -> str:
    return sha256(refresh_token.encode()).hexdigest()


def decode_access_token(
    access_token: str,
    *,
    verify_expiration: bool = True,
) -> dict[str, Any]:
    algorithm = os.getenv("ALGORITHM")
    if not algorithm:
        raise HTTPException(status_code=500, detail="Server configuration error")
    try:
        return jwt.decode(
            access_token,
            os.getenv("SECRET_KEY"),
            algorithms=[algorithm],
            options={"verify_exp": verify_expiration},
        )
    except jwt.InvalidTokenError:
        raise INVALID_TOKEN_ERROR


def ensure_access_matches_user(access_token: str, user_id: str) -> None:
    payload = decode_access_token(access_token, verify_expiration=False)
    sub = payload.get("sub")
    if not sub or sub != user_id:
        raise INVALID_TOKEN_ERROR


def generate_tokens_pair(device: str, user_id: str, session: Session) -> dict[str, str]:
    access_token = create_access_token({"sub": user_id})
    refresh_token = create_refresh_token()
    hashed_refresh_token = hash_refresh_token(refresh_token)
    expires = utc_now() + timedelta(
        days=int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS") or 1)
    )

    session.add(
        UserSession(
            refresh_token_hash=hashed_refresh_token,
            user_id=user_id,
            expires_at=expires,
            device=device,
        )
    )
    session.commit()

    return {"access_token": access_token, "refresh_token": refresh_token}


def authenticate(session: Session, email: str, password: str) -> User:
    user_query = session.exec(select(User).where(User.email == email)).first()
    if not user_query:
        _ = verify_password(password, DUMMY_HASH)
        raise INVALID_CREDENTIALS_ERROR
    if not verify_password(password, user_query.password_hash):
        raise INVALID_CREDENTIALS_ERROR
    return user_query


def register_user(session: Session, form_data: UserCreate) -> None:
    hashed_password = get_password_hash(form_data.password)
    user_query = session.exec(
        select(User).where(User.email == form_data.email)
    ).first()
    if user_query:
        raise HTTPException(
            status_code=409, detail="Problems to register user, verify your credentials"
        )
    user = User(email=form_data.email, password_hash=hashed_password)
    session.add(user)
    session.commit()


def refresh_tokens(
    session: Session, refresh_token: str, access_token: str, device: str
) -> dict[str, str]:
    hashed_token = hash_refresh_token(refresh_token)
    user_session = session.exec(
        select(UserSession).where(
            UserSession.refresh_token_hash == hashed_token
        )
    ).one_or_none()

    if not user_session:
        raise INVALID_TOKEN_ERROR

    if user_session.revoked_at or user_session.expires_at < utc_now():
        user_session.revoked_at = utc_now()
        session.commit()
        raise INVALID_TOKEN_ERROR

    ensure_access_matches_user(access_token, user_session.user_id)

    user_session.last_used_at = utc_now()
    user_session.revoked_at = utc_now()
    session.add(user_session)
    session.commit()

    return generate_tokens_pair(
        device=device, user_id=user_session.user_id, session=session
    )


def revoke_session(session: Session, refresh_token: str, user_id: str) -> None:
    hashed = hash_refresh_token(refresh_token)
    user_session = session.exec(
        select(UserSession).where(
            UserSession.refresh_token_hash == hashed,
            UserSession.user_id == user_id,
        )
    ).one_or_none()

    if user_session and not user_session.revoked_at:
        user_session.revoked_at = utc_now()
        user_session.last_used_at = utc_now()
        session.add(user_session)
        session.commit()
