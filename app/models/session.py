from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import Field, SQLModel


class UserSession(SQLModel, table=True):
    id: str | None = Field(default_factory=lambda: str(uuid4()), primary_key=True, max_length=36)
    user_id: str = Field(foreign_key="user.id", index=True, max_length=36)
    device: str = Field(max_length=255)
    refresh_token_hash: str = Field(max_length=255, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
    revoked_at: datetime | None = Field(default=None)
    last_used_at: datetime | None = Field(default=None)
