from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import SessionDep, get_active_current_user
from app.features.tasks import service
from app.models import TaskCreate, TaskPublic, TaskUpdate, UserPublic

router = APIRouter(prefix="/api/v1/task", tags=["tasks"])

TASK_NOT_FOUND_EXCEPTION = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Task not found",
)


@router.get("")
def get_tasks(
    session: SessionDep,
    user: Annotated[UserPublic, Depends(get_active_current_user)],
    limit: int = 50,
    offset: int = 0,
):
    tasks_query, count = service.list_tasks(session, user.id, limit, offset)
    tasks = [TaskPublic.model_validate(task) for task in tasks_query]
    has_more = count > offset + len(tasks)

    return {"ok": True, "count": count, "results": tasks, "has_more": has_more}


@router.get("/{task_id}")
def get_task(
    task_id: str,
    user: Annotated[UserPublic, Depends(get_active_current_user)],
    session: SessionDep,
):
    task = service.get_owned_task(session, task_id, user.id)

    if task is not None:
        return {"ok": True, "task": TaskPublic.model_validate(task)}

    raise TASK_NOT_FOUND_EXCEPTION


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(
    item: TaskCreate,
    session: SessionDep,
    user: Annotated[UserPublic, Depends(get_active_current_user)],
):
    db_task = service.create_task(session, item, user.id)
    return {"ok": True, "task": TaskPublic.model_validate(db_task)}


@router.put("/{task_id}", status_code=status.HTTP_200_OK)
def update_task(
    task_id: str,
    item: TaskUpdate,
    session: SessionDep,
    user: Annotated[UserPublic, Depends(get_active_current_user)],
):
    task = service.update_task(session, task_id, item, user.id)

    if task is None:
        raise TASK_NOT_FOUND_EXCEPTION

    return {"ok": True, "task": TaskPublic.model_validate(task)}


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: str,
    session: SessionDep,
    user: Annotated[UserPublic, Depends(get_active_current_user)],
):
    task = service.delete_task(session, task_id, user.id)

    if task is None:
        raise TASK_NOT_FOUND_EXCEPTION
