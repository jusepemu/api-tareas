from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel


class StatusEnum(str, Enum):
    TODO = "todo"
    PENDING = "pending"
    COMPLETED = "completed"


class TaskBase(SQLModel):
    title: str = Field(max_length=255)
    description: str | None = Field(default=None, max_length=255)
    completed: bool = False
    status: StatusEnum = Field(
        default=StatusEnum.TODO,
        sa_column=Column(
            SAEnum(
                StatusEnum,
                values_callable=lambda x: [e.value for e in x],
                name="statusenum",
            ),
            default=StatusEnum.TODO,
            nullable=False,
        ),
    )
    start_date: datetime | None = None
    end_date: datetime | None = None


class Task(TaskBase, table=True):
    id: str | None = Field(default_factory=lambda: str(uuid4()), primary_key=True, max_length=36)
    created_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC))

    user_id: str | None = Field(foreign_key="user.id")


class TaskCreate(TaskBase):
    pass


class TaskUpdate(SQLModel):
    title: str | None = None
    description: str | None = None
    completed: bool | None = None
    status: StatusEnum | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None


class TaskPublic(TaskBase):
    id: str
    created_at: datetime | None = None


# Users
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


class UserSession(SQLModel, table=True):
    id: str | None = Field(default_factory=lambda: str(uuid4()), primary_key=True, max_length=36)
    user_id: str = Field(foreign_key="user.id", index=True)
    device: str = Field(max_length=255)
    refresh_token_hash: str = Field(max_length=255, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
    revoked_at: datetime | None = Field(default=None)
    last_used_at: datetime | None = Field(default=None)
