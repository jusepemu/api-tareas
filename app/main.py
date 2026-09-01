from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlmodel import SQLModel

from app import db, models  # noqa
from app.features.auth.router import router as auth_router
from app.features.tasks.router import router as tasks_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(bind=db.engine)
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(auth_router)
app.include_router(tasks_router)


@app.get("/")
def root():
    return {"ok": True, "message": "Hello World"}
