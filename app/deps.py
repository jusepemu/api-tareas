from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session

from app.db import get_session
from app.features.auth.service import INVALID_TOKEN_ERROR, decode_access_token
from app.models import User, UserPublic

SessionDep = Annotated[Session, Depends(get_session)]
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def get_active_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], session: SessionDep
) -> UserPublic:
    decode_token = decode_access_token(token)
    user_id = decode_token.get("sub")
    if not user_id:
        raise INVALID_TOKEN_ERROR
    user = session.get(User, user_id)
    if not user:
        raise INVALID_TOKEN_ERROR
    return UserPublic.model_validate(user)
