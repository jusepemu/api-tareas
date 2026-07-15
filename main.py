import uuid
from fastapi import FastAPI, status
from pydantic import BaseModel


class TaskCreated(BaseModel):
    task: str


app = FastAPI()

tasks = []


@app.get("/")
def root():
    return {"ok": True, "message": "Hello World"}


@app.get("/task")
def get_tasks():
    return {"ok": True, "count": len(tasks), "results": tasks}


@app.post("/task", status_code=status.HTTP_201_CREATED)
def create_task(item: TaskCreated):
    uid = uuid.uuid4()
    new_task = {"id": str(uid), "task": item.task}
    tasks.append(new_task)
    return {"ok": True, "task": new_task}
