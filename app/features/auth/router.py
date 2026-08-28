from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from app.deps import SessionDep, get_active_current_user, oauth2_scheme
from app.features.auth.service import (
    INVALID_TOKEN_ERROR,
    authenticate,
    decode_access_token,
    generate_tokens_pair,
    refresh_tokens,
    register_user,
    revoke_session,
)
from app.models import UserCreate, UserPublic

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/token")
def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    response: Response,
    session: SessionDep,
):
    user_query = authenticate(session, form_data.username, form_data.password)

    assert user_query.id is not None, "user is not reachable"

    device = request.headers.get("user-agent", "web")
    tokens = generate_tokens_pair(
        device=device[:255], user_id=user_query.id, session=session
    )

    response.set_cookie(
        "refresh_token",
        tokens["refresh_token"],
        httponly=True,
        samesite="lax",
    )

    return {
        "ok": True,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "token_type": "bearer",
    }


@router.post("/register")
def register(form_data: UserCreate, session: SessionDep):
    register_user(session, form_data)
    return {"ok": True, "message": "User registered successfully"}


@router.get("/me")
def get_current_user(
    user: Annotated[UserPublic, Depends(get_active_current_user)],
):
    return {"ok": True, "user": user}


@router.post("/refresh")
def refresh_token(
    request: Request, tokens: dict[str, str], response: Response, session: SessionDep
):
    refresh_from_cookie = request.cookies.get("refresh_token")
    refresh_token = (
        refresh_from_cookie if refresh_from_cookie else tokens.get("refresh_token")
    )
    access_token = tokens.get("access_token")
    device = request.headers.get("user-agent", "web")

    if not refresh_token:
        raise INVALID_TOKEN_ERROR

    if not access_token:
        raise INVALID_TOKEN_ERROR

    tokens = refresh_tokens(
        session, refresh_token, access_token, device[:255]
    )
    response.set_cookie(
        "refresh_token",
        tokens["refresh_token"],
        httponly=True,
        samesite="lax",
    )

    return {
        "ok": True,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    access_token: Annotated[str, Depends(oauth2_scheme)],
    body: dict[str, str],
    response: Response,
    session: SessionDep,
):
    refresh_token = request.cookies.get("refresh_token") or (
        body.get("refresh_token") if body else None
    )
    payload = decode_access_token(access_token, verify_expiration=False)
    sub = payload.get("sub")

    if not sub:
        raise INVALID_TOKEN_ERROR

    if not refresh_token:
        raise INVALID_TOKEN_ERROR

    revoke_session(session, refresh_token, sub)

    response.delete_cookie(
        "refresh_token",
        path="/",
        samesite="lax",
    )
    response.status_code = 204
