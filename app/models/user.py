from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import Field, SQLModel


class UserBase(SQLModel):
    email: str = Field(max_length=255)


class User(UserBase, table=True):
    id: str | None = Field(default_factory=lambda: str(uuid4()), primary_key=True, max_length=36)
    password_hash: str = Field(max_length=255)
    created_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC))


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=255)


class UserPublic(UserBase):
    id: str
    created_at: datetime | None = None
