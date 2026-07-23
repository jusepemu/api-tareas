import uuid
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from db import connection


class TaskCreated(BaseModel):
    task: str


class Task(BaseModel):
    id: str
    task: str


class TaskUpdate(BaseModel):
    task: str


app = FastAPI()

tasks = []


def find_task_index(task_id: str) -> int | None:
    return next((i for i, t in enumerate(tasks) if t.get("id") == task_id), None)


TASK_NOT_FOUND_EXCEPTION = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Task not found",
)


@app.get("/")
def root():
    return {"ok": True, "message": "Hello World"}


@app.get("/db-health")
def validate_connection():
    cursor = connection.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()

    if result is not None:
        return {"ok": True, "message": "Database is healthy"}

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database is not healthy",
    )


@app.get("/task")
def get_tasks():
    return {"ok": True, "count": len(tasks), "results": tasks}


@app.get("/task/{task_id}")
def get_task(task_id: str):
    index = find_task_index(task_id)

    if index is not None:
        return {"ok": True, "task": tasks[index]}

    raise TASK_NOT_FOUND_EXCEPTION


@app.post("/task", status_code=status.HTTP_201_CREATED)
def create_task(item: TaskCreated):
    uid = uuid.uuid4()
    new_task = {"id": str(uid), "task": item.task}
    tasks.append(new_task)

    return {"ok": True, "task": new_task}


@app.put("/task/{task_id}", status_code=status.HTTP_202_ACCEPTED)
def update_task(task_id: str, item: TaskUpdate):
    index = find_task_index(task_id)

    if index is None:
        raise TASK_NOT_FOUND_EXCEPTION

    tasks[index] = {"id": task_id, **item.model_dump()}

    return {"ok": True, "task": tasks[index]}


@app.delete("/task/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str):
    index = find_task_index(task_id)

    if index is None:
        raise TASK_NOT_FOUND_EXCEPTION

    tasks.pop(index)
