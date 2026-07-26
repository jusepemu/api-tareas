from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from sqlmodel import Field, SQLModel


class StatusEnum(str, Enum):
    TODO = "todo"
    PENDING = "pending"
    COMPLETED = "completed"



class TaskBase(SQLModel):
    title: str = Field(max_length=255)
    description: str | None = Field(default=None, max_length=255)
    completed: bool = False
    status: StatusEnum = Field(default=StatusEnum.TODO)
    start_date: datetime | None = None
    end_date: datetime | None = None


class Task(TaskBase, table=True):
    id: str | None = Field(default=lambda: str(uuid4()), primary_key=True, max_length=36)
    created_at: datetime | None = Field(default=lambda: datetime.now(UTC))


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
