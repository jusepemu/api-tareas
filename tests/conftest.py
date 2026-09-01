import os

# Configurar SQLite ANTES de importar la app
os.environ["DB_TYPE"] = "sqlite"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.db import get_session
from app.main import app
from app.models import Task, User, UserSession  # noqa: F401


@pytest.fixture
def session():
    """Patrón oficial SQLModel: StaticPool permite compartir :memory: entre threads"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def client(session):
    """Override de dependency para usar la session de test"""

    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
