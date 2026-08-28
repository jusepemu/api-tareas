from sqlmodel import Session, func, select

from app.models import Task, TaskCreate, TaskUpdate


def list_tasks(
    session: Session, user_id: str, limit: int, offset: int
) -> tuple[list[Task], int]:
    rows = session.exec(
        select(Task)
        .where(Task.user_id == user_id)
        .offset(offset)
        .limit(limit)
    ).all()
    count = session.exec(select(func.count()).select_from(Task)).one()
    return list(rows), count


def get_owned_task(session: Session, task_id: str, user_id: str) -> Task | None:
    task = session.get(Task, task_id)
    if task is not None and task.user_id == user_id:
        return task
    return None


def create_task(session: Session, item: TaskCreate, user_id: str) -> Task:
    db_task = Task.model_validate(item)
    db_task.user_id = user_id
    session.add(db_task)
    session.commit()
    session.refresh(db_task)
    return db_task


def update_task(
    session: Session, task_id: str, item: TaskUpdate, user_id: str
) -> Task | None:
    task = session.exec(
        select(Task).where(
            Task.id == task_id,
            Task.user_id == user_id,
        )
    ).one_or_none()

    if task is None:
        return None

    _ = task.sqlmodel_update(item.model_dump(exclude_unset=True))
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def delete_task(session: Session, task_id: str, user_id: str) -> Task | None:
    task = session.exec(
        select(Task).where(
            Task.id == task_id,
            Task.user_id == user_id,
        )
    ).one_or_none()

    if task is None:
        return None

    session.delete(task)
    session.commit()
    return task
