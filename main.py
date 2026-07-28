from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from sqlmodel import Session, SQLModel, func, select

import models
from db import engine, get_session


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(bind=engine)
    yield


app = FastAPI(lifespan=lifespan)
SessionDep = Annotated[Session, Depends(get_session)]


TASK_NOT_FOUND_EXCEPTION = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Task not found",
)


@app.get("/")
def root():
    return {"ok": True, "message": "Hello World"}


@app.get("/task")
def get_tasks(session: SessionDep, limit: int = 50, offset: int = 0):
    tasks_query = session.exec(select(models.Task).offset(offset).limit(limit)).all()
    tasks = [models.TaskPublic.model_validate(task) for task in tasks_query]
    count = session.exec(select(func.count()).select_from(models.Task)).one()
    has_more = count > offset + len(tasks)

    return {"ok": True, "count": count, "results": tasks, "has_more": has_more}


@app.get("/task/{task_id}")
def get_task(task_id: str, session: SessionDep):
    task = session.get(models.Task, task_id)

    if task is not None:
        return {"ok": True, "task": models.TaskPublic.model_validate(task)}

    raise TASK_NOT_FOUND_EXCEPTION


@app.post("/task", status_code=status.HTTP_201_CREATED)
def create_task(item: models.TaskCreate, session: SessionDep):
    db_task = models.Task.model_validate(item)
    session.add(db_task)
    session.commit()
    session.refresh(db_task)

    return {"ok": True, "task": models.TaskPublic.model_validate(db_task)}


@app.put("/task/{task_id}", status_code=status.HTTP_202_ACCEPTED)
def update_task(task_id: str, item: models.TaskUpdate, session: SessionDep):
    task = session.get(models.Task, task_id)

    if task is None:
        raise TASK_NOT_FOUND_EXCEPTION

    task_data = item.model_dump(exclude_unset=True)
    task.sqlmodel_update(task_data)
    session.add(task)
    session.commit()
    session.refresh(task)

    return {"ok": True, "task": models.TaskPublic.model_validate(task)}


@app.delete("/task/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str, session: SessionDep):
    task = session.get(models.Task, task_id)

    if task is None:
        raise TASK_NOT_FOUND_EXCEPTION

    session.delete(task)
    session.commit()
