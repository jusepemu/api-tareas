import os
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Annotated, Any

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pwdlib import PasswordHash
from sqlmodel import Session, SQLModel, func, select

import models
from db import engine, get_session


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(bind=engine)
    yield


password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("dummypassword")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


app = FastAPI(lifespan=lifespan)
SessionDep = Annotated[Session, Depends(get_session)]


# Exceptions
TASK_NOT_FOUND_EXCEPTION = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Task not found",
)
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


# Utilities
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
        models.UserSession(
            refresh_token_hash=hashed_refresh_token,
            user_id=user_id,
            expires_at=expires,
            device=device,
        )
    )
    session.commit()

    return {"access_token": access_token, "refresh_token": refresh_token}


def get_active_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], session: SessionDep
) -> models.UserPublic:
    decode_token = decode_access_token(token)
    user_id = decode_token.get("sub")
    if not user_id:
        raise INVALID_TOKEN_ERROR
    user = session.get(models.User, user_id)
    if not user:
        raise INVALID_TOKEN_ERROR
    return models.UserPublic.model_validate(user)


# API Routes
@app.get("/")
def root():
    return {"ok": True, "message": "Hello World"}


@app.post("/api/v1/auth/token")
def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    response: Response,
    session: SessionDep,
):
    user_query = session.exec(
        select(models.User).where(models.User.email == form_data.username)
    ).first()
    if not user_query:
        _ = verify_password(form_data.password, DUMMY_HASH)
        raise INVALID_CREDENTIALS_ERROR
    if not verify_password(form_data.password, user_query.password_hash):
        raise INVALID_CREDENTIALS_ERROR

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


@app.post("/api/v1/auth/register")
def register(form_data: models.UserCreate, session: SessionDep):
    hashed_password = get_password_hash(form_data.password)
    user_query = session.exec(
        select(models.User).where(models.User.email == form_data.email)
    ).first()
    if user_query:
        raise HTTPException(
            status_code=409, detail="Problems to register user, verify your credentials"
        )
    user = models.User(email=form_data.email, password_hash=hashed_password)
    session.add(user)
    session.commit()

    return {"ok": True, "message": "User registered successfully"}


@app.get("/api/v1/auth/me")
def get_current_user(
    user: Annotated[models.UserPublic, Depends(get_active_current_user)],
):
    return {"ok": True, "user": user}


@app.post("/api/v1/auth/refresh")
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

    hashed_token = hash_refresh_token(refresh_token)
    user_session = session.exec(
        select(models.UserSession).where(
            models.UserSession.refresh_token_hash == hashed_token
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

    tokens = generate_tokens_pair(
        device=device[:255], user_id=user_session.user_id, session=session
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


@app.post("/api/v1/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
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

    hashed = hash_refresh_token(refresh_token)
    user_session = session.exec(
        select(models.UserSession).where(
            models.UserSession.refresh_token_hash == hashed,
            models.UserSession.user_id == sub,
        )
    ).one_or_none()

    if user_session and not user_session.revoked_at:
        user_session.revoked_at = utc_now()
        user_session.last_used_at = utc_now()
        session.add(user_session)
        session.commit()

    response.delete_cookie(
        "refresh_token",
        path="/",
        samesite="lax",
    )
    response.status_code = 204


@app.get("/api/v1/task")
def get_tasks(
    session: SessionDep,
    user: Annotated[models.UserPublic, Depends(get_active_current_user)],
    limit: int = 50,
    offset: int = 0,
):
    tasks_query = session.exec(
        select(models.Task)
        .where(models.Task.user_id == user.id)
        .offset(offset)
        .limit(limit)
    ).all()
    tasks = [models.TaskPublic.model_validate(task) for task in tasks_query]
    count = session.exec(select(func.count()).select_from(models.Task)).one()
    has_more = count > offset + len(tasks)

    return {"ok": True, "count": count, "results": tasks, "has_more": has_more}


@app.get("/api/v1/task/{task_id}")
def get_task(
    task_id: str,
    user: Annotated[models.UserPublic, Depends(get_active_current_user)],
    session: SessionDep,
):
    task = session.get(models.Task, task_id)

    if task is not None and task.user_id == user.id:
        return {"ok": True, "task": models.TaskPublic.model_validate(task)}

    raise TASK_NOT_FOUND_EXCEPTION


@app.post("/api/v1/task", status_code=status.HTTP_201_CREATED)
def create_task(
    item: models.TaskCreate,
    session: SessionDep,
    user: Annotated[models.UserPublic, Depends(get_active_current_user)],
):
    db_task = models.Task.model_validate(item)
    db_task.user_id = user.id
    session.add(db_task)
    session.commit()
    session.refresh(db_task)

    return {"ok": True, "task": models.TaskPublic.model_validate(db_task)}


@app.put("/api/v1/task/{task_id}", status_code=status.HTTP_200_OK)
def update_task(
    task_id: str,
    item: models.TaskUpdate,
    session: SessionDep,
    user: Annotated[models.UserPublic, Depends(get_active_current_user)],
):
    task = session.exec(
        select(models.Task).where(
            models.Task.id == task_id,
            models.Task.user_id == user.id,
        )
    ).one_or_none()

    if task is None:
        raise TASK_NOT_FOUND_EXCEPTION

    _ = task.sqlmodel_update(item.model_dump(exclude_unset=True))
    session.add(task)
    session.commit()
    session.refresh(task)

    return {"ok": True, "task": models.TaskPublic.model_validate(task)}


@app.delete("/api/v1/task/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: str,
    session: SessionDep,
    user: Annotated[models.UserPublic, Depends(get_active_current_user)],
):
    task = session.exec(
        select(models.Task).where(
            models.Task.id == task_id,
            models.Task.user_id == user.id,
        )
    ).one_or_none()

    if task is None:
        raise TASK_NOT_FOUND_EXCEPTION

    session.delete(task)
    session.commit()
