from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session

from app.features.auth.service import create_access_token
from app.models import Task, User

TASKS_ENDPOINT = "/api/v1/task"


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def make_user(session: Session, email: str) -> User:
    user = User(email=email, password_hash="hashed_secret_not_used_here")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def make_task(session: Session, user: User, title: str) -> Task:
    task = Task(title=title, user_id=user.id)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@pytest.fixture
def two_users(session: Session):
    user_a = make_user(session, "user_a@example.com")
    user_b = make_user(session, "user_b@example.com")
    return {
        "user_a": user_a,
        "user_b": user_b,
        "token_a": create_access_token({"sub": user_a.id}),
        "token_b": create_access_token({"sub": user_b.id}),
        "tasks_a": [make_task(session, user_a, f"A{i}") for i in range(1, 4)],
        "tasks_b": [make_task(session, user_b, f"B{i}") for i in range(1, 4)],
    }


# --- Autenticación ---
def test_get_tasks_returns_401_when_no_token(client):
    response = client.get(TASKS_ENDPOINT)

    assert response.status_code == 401


def test_get_task_returns_401_when_no_token(client):
    response = client.get(f"{TASKS_ENDPOINT}/some-task-id")

    assert response.status_code == 401


def test_create_task_returns_401_when_no_token(client):
    response = client.post(TASKS_ENDPOINT, json={"title": "Nueva"})

    assert response.status_code == 401


def test_update_task_returns_401_when_no_token(client):
    response = client.put(f"{TASKS_ENDPOINT}/some-task-id", json={"title": "Nueva"})

    assert response.status_code == 401


def test_delete_task_returns_401_when_no_token(client):
    response = client.delete(f"{TASKS_ENDPOINT}/some-task-id")

    assert response.status_code == 401


# --- Listado y ownership ---
def test_list_tasks_returns_only_own_tasks_when_user_a(client, two_users):
    response = client.get(TASKS_ENDPOINT, headers=auth_headers(two_users["token_a"]))

    assert response.status_code == 200
    titles = {task["title"] for task in response.json()["results"]}
    assert titles == {"A1", "A2", "A3"}


def test_list_tasks_returns_only_own_tasks_when_user_b(client, two_users):
    response = client.get(TASKS_ENDPOINT, headers=auth_headers(two_users["token_b"]))

    assert response.status_code == 200
    titles = {task["title"] for task in response.json()["results"]}
    assert titles == {"B1", "B2", "B3"}


def test_list_tasks_excludes_other_user_ids_when_user_a(client, two_users):
    response = client.get(TASKS_ENDPOINT, headers=auth_headers(two_users["token_a"]))

    returned_ids = {task["id"] for task in response.json()["results"]}
    other_ids = {task.id for task in two_users["tasks_b"]}
    assert returned_ids.isdisjoint(other_ids)


def test_list_tasks_excludes_other_user_ids_when_user_b(client, two_users):
    response = client.get(TASKS_ENDPOINT, headers=auth_headers(two_users["token_b"]))

    returned_ids = {task["id"] for task in response.json()["results"]}
    other_ids = {task.id for task in two_users["tasks_a"]}
    assert returned_ids.isdisjoint(other_ids)


def test_list_tasks_counts_only_own_tasks_when_user_a(client, two_users):
    response = client.get(TASKS_ENDPOINT, headers=auth_headers(two_users["token_a"]))

    assert response.json()["count"] == 3


def test_list_tasks_counts_only_own_tasks_when_user_b(client, two_users):
    response = client.get(TASKS_ENDPOINT, headers=auth_headers(two_users["token_b"]))

    assert response.json()["count"] == 3


# --- Orden determinista ---
def test_list_tasks_orders_by_created_at_when_inserted_out_of_order(
    client, session, two_users
):
    base = datetime(2024, 1, 1, tzinfo=UTC)
    session.add_all(
        [
            Task(
                title="late",
                user_id=two_users["user_a"].id,
                created_at=base + timedelta(days=2),
            ),
            Task(title="early", user_id=two_users["user_a"].id, created_at=base),
            Task(
                title="mid",
                user_id=two_users["user_a"].id,
                created_at=base + timedelta(days=1),
            ),
        ]
    )
    session.commit()

    response = client.get(TASKS_ENDPOINT, headers=auth_headers(two_users["token_a"]))

    titles = [task["title"] for task in response.json()["results"]]
    assert titles.index("early") < titles.index("mid") < titles.index("late")


def test_list_tasks_orders_by_id_when_created_at_ties(client, session, two_users):
    base = datetime(2024, 1, 1, tzinfo=UTC)
    session.add_all(
        [
            Task(
                id="zzzz",
                title="tie-b",
                user_id=two_users["user_a"].id,
                created_at=base,
            ),
            Task(
                id="aaaa",
                title="tie-a",
                user_id=two_users["user_a"].id,
                created_at=base,
            ),
        ]
    )
    session.commit()

    response = client.get(TASKS_ENDPOINT, headers=auth_headers(two_users["token_a"]))

    tied_ids = [
        task["id"]
        for task in response.json()["results"]
        if task["title"].startswith("tie-")
    ]
    assert tied_ids == ["aaaa", "zzzz"]


# --- Paginación ---
def test_list_tasks_returns_first_page_when_limit_2_offset_0(client, two_users):
    response = client.get(
        f"{TASKS_ENDPOINT}?limit=2&offset=0",
        headers=auth_headers(two_users["token_b"]),
    )

    body = response.json()
    assert len(body["results"]) == 2
    assert body["count"] == 3
    assert body["has_more"] is True


def test_list_tasks_returns_last_page_when_limit_2_offset_2(client, two_users):
    response = client.get(
        f"{TASKS_ENDPOINT}?limit=2&offset=2",
        headers=auth_headers(two_users["token_b"]),
    )

    body = response.json()
    assert len(body["results"]) == 1
    assert body["count"] == 3
    assert body["has_more"] is False


def test_list_tasks_returns_empty_page_when_offset_beyond_count(client, two_users):
    response = client.get(
        f"{TASKS_ENDPOINT}?limit=2&offset=3",
        headers=auth_headers(two_users["token_b"]),
    )

    body = response.json()
    assert body["results"] == []
    assert body["count"] == 3
    assert body["has_more"] is False


def test_list_tasks_has_no_duplicates_when_paginated(client, two_users):
    headers = auth_headers(two_users["token_b"])
    first_page = client.get(f"{TASKS_ENDPOINT}?limit=2&offset=0", headers=headers)
    second_page = client.get(f"{TASKS_ENDPOINT}?limit=2&offset=2", headers=headers)

    first_ids = {task["id"] for task in first_page.json()["results"]}
    second_ids = {task["id"] for task in second_page.json()["results"]}
    assert first_ids.isdisjoint(second_ids)


def test_list_tasks_pages_union_contains_all_when_paginated(client, two_users):
    headers = auth_headers(two_users["token_b"])
    first_page = client.get(f"{TASKS_ENDPOINT}?limit=2&offset=0", headers=headers)
    second_page = client.get(f"{TASKS_ENDPOINT}?limit=2&offset=2", headers=headers)

    union = {task["id"] for task in first_page.json()["results"]}
    union |= {task["id"] for task in second_page.json()["results"]}
    assert union == {task.id for task in two_users["tasks_b"]}


# --- Validación de paginación ---
def test_list_tasks_returns_422_when_limit_0(client, two_users):
    response = client.get(
        f"{TASKS_ENDPOINT}?limit=0",
        headers=auth_headers(two_users["token_b"]),
    )

    assert response.status_code == 422


def test_list_tasks_returns_422_when_offset_negative(client, two_users):
    response = client.get(
        f"{TASKS_ENDPOINT}?offset=-1",
        headers=auth_headers(two_users["token_b"]),
    )

    assert response.status_code == 422


def test_list_tasks_returns_422_when_limit_above_max(client, two_users):
    response = client.get(
        f"{TASKS_ENDPOINT}?limit=101",
        headers=auth_headers(two_users["token_b"]),
    )

    assert response.status_code == 422


def test_list_tasks_returns_200_when_limit_at_max(client, two_users):
    response = client.get(
        f"{TASKS_ENDPOINT}?limit=100",
        headers=auth_headers(two_users["token_b"]),
    )

    assert response.status_code == 200


# --- Validación de actualización ---
def test_update_task_returns_422_when_title_is_null(client, two_users):
    task = two_users["tasks_a"][0]

    response = client.put(
        f"{TASKS_ENDPOINT}/{task.id}",
        json={"title": None},
        headers=auth_headers(two_users["token_a"]),
    )

    assert response.status_code == 422


def test_update_task_returns_200_when_body_is_empty(client, two_users):
    task = two_users["tasks_a"][0]

    response = client.put(
        f"{TASKS_ENDPOINT}/{task.id}",
        json={},
        headers=auth_headers(two_users["token_a"]),
    )

    assert response.status_code == 200


# --- Lectura individual ---
def test_get_task_returns_task_when_owned(client, two_users):
    task = two_users["tasks_a"][0]

    response = client.get(
        f"{TASKS_ENDPOINT}/{task.id}",
        headers=auth_headers(two_users["token_a"]),
    )

    assert response.status_code == 200
    assert response.json()["task"]["id"] == task.id


def test_get_task_returns_404_when_owned_by_other_user_a_requests_b(client, two_users):
    task = two_users["tasks_b"][0]

    response = client.get(
        f"{TASKS_ENDPOINT}/{task.id}",
        headers=auth_headers(two_users["token_a"]),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


def test_get_task_returns_404_when_owned_by_other_user_b_requests_a(client, two_users):
    task = two_users["tasks_a"][0]

    response = client.get(
        f"{TASKS_ENDPOINT}/{task.id}",
        headers=auth_headers(two_users["token_b"]),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


def test_get_task_returns_404_when_not_exists(client, two_users):
    response = client.get(
        f"{TASKS_ENDPOINT}/missing-task-id",
        headers=auth_headers(two_users["token_a"]),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


# --- Creación ---
def test_create_task_returns_201_when_valid(client, two_users):
    response = client.post(
        TASKS_ENDPOINT,
        json={"title": "Nueva tarea"},
        headers=auth_headers(two_users["token_a"]),
    )

    assert response.status_code == 201
    assert response.json()["task"]["title"] == "Nueva tarea"


def test_create_task_persists_owner_when_created(client, session, two_users):
    response = client.post(
        TASKS_ENDPOINT,
        json={"title": "Nueva tarea"},
        headers=auth_headers(two_users["token_a"]),
    )

    db_task = session.get(Task, response.json()["task"]["id"])
    assert db_task is not None
    assert db_task.user_id == two_users["user_a"].id


def test_create_task_is_not_readable_when_other_user(client, two_users):
    created = client.post(
        TASKS_ENDPOINT,
        json={"title": "Nueva tarea"},
        headers=auth_headers(two_users["token_a"]),
    ).json()["task"]

    response = client.get(
        f"{TASKS_ENDPOINT}/{created['id']}",
        headers=auth_headers(two_users["token_b"]),
    )

    assert response.status_code == 404


def test_create_task_is_not_listed_when_other_user(client, two_users):
    created = client.post(
        TASKS_ENDPOINT,
        json={"title": "Nueva tarea"},
        headers=auth_headers(two_users["token_a"]),
    ).json()["task"]

    listed_ids = {
        task["id"]
        for task in client.get(
            TASKS_ENDPOINT, headers=auth_headers(two_users["token_b"])
        ).json()["results"]
    }
    assert created["id"] not in listed_ids


def test_create_task_ignores_user_id_when_provided_in_body(client, session, two_users):
    response = client.post(
        TASKS_ENDPOINT,
        json={"title": "Nueva tarea", "user_id": two_users["user_b"].id},
        headers=auth_headers(two_users["token_a"]),
    )

    assert response.status_code == 201
    db_task = session.get(Task, response.json()["task"]["id"])
    assert db_task.user_id == two_users["user_a"].id


def test_create_task_ignores_id_when_provided_in_body(client, two_users):
    response = client.post(
        TASKS_ENDPOINT,
        json={"title": "Nueva tarea", "id": "attacker-chosen-id"},
        headers=auth_headers(two_users["token_a"]),
    )

    assert response.status_code == 201
    assert response.json()["task"]["id"] != "attacker-chosen-id"


# --- Actualización ---
def test_update_task_returns_200_and_persists_when_owned(client, session, two_users):
    task = two_users["tasks_a"][0]

    response = client.put(
        f"{TASKS_ENDPOINT}/{task.id}",
        json={"title": "Actualizada"},
        headers=auth_headers(two_users["token_a"]),
    )

    assert response.status_code == 200
    session.expire_all()
    assert session.get(Task, task.id).title == "Actualizada"


def test_update_task_keeps_id_when_id_in_body(client, two_users):
    task = two_users["tasks_a"][0]

    response = client.put(
        f"{TASKS_ENDPOINT}/{task.id}",
        json={"id": "attacker-chosen-id", "title": "Actualizada"},
        headers=auth_headers(two_users["token_a"]),
    )

    assert response.status_code == 200
    assert response.json()["task"]["id"] == task.id


def test_update_task_keeps_owner_when_user_id_in_body(client, session, two_users):
    task = two_users["tasks_a"][0]

    response = client.put(
        f"{TASKS_ENDPOINT}/{task.id}",
        json={"user_id": two_users["user_b"].id},
        headers=auth_headers(two_users["token_a"]),
    )

    assert response.status_code == 200
    session.expire_all()
    assert session.get(Task, task.id).user_id == two_users["user_a"].id


def test_update_task_returns_404_when_owned_by_other_user(client, two_users):
    task = two_users["tasks_a"][0]

    response = client.put(
        f"{TASKS_ENDPOINT}/{task.id}",
        json={"title": "Hackeada"},
        headers=auth_headers(two_users["token_b"]),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


def test_update_task_does_not_change_when_attempted_by_other_user(
    client, session, two_users
):
    task = two_users["tasks_a"][0]
    original_title = task.title

    client.put(
        f"{TASKS_ENDPOINT}/{task.id}",
        json={"title": "Hackeada"},
        headers=auth_headers(two_users["token_b"]),
    )

    session.expire_all()
    assert session.get(Task, task.id).title == original_title


# --- Eliminación ---
def test_delete_task_returns_204_when_owned(client, two_users):
    task = two_users["tasks_a"][0]

    response = client.delete(
        f"{TASKS_ENDPOINT}/{task.id}",
        headers=auth_headers(two_users["token_a"]),
    )

    assert response.status_code == 204


def test_delete_task_returns_empty_body_when_owned(client, two_users):
    task = two_users["tasks_a"][0]

    response = client.delete(
        f"{TASKS_ENDPOINT}/{task.id}",
        headers=auth_headers(two_users["token_a"]),
    )

    assert response.content == b""


def test_delete_task_removes_from_db_when_owned(client, session, two_users):
    task = two_users["tasks_a"][0]

    client.delete(
        f"{TASKS_ENDPOINT}/{task.id}",
        headers=auth_headers(two_users["token_a"]),
    )

    session.expire_all()
    assert session.get(Task, task.id) is None


def test_delete_task_returns_404_when_owned_by_other_user(client, two_users):
    task = two_users["tasks_a"][0]

    response = client.delete(
        f"{TASKS_ENDPOINT}/{task.id}",
        headers=auth_headers(two_users["token_b"]),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


def test_delete_task_does_not_remove_when_attempted_by_other_user(
    client, session, two_users
):
    task = two_users["tasks_a"][0]

    client.delete(
        f"{TASKS_ENDPOINT}/{task.id}",
        headers=auth_headers(two_users["token_b"]),
    )

    session.expire_all()
    assert session.get(Task, task.id) is not None


def test_delete_task_returns_404_when_already_deleted(client, two_users):
    task = two_users["tasks_a"][0]
    headers = auth_headers(two_users["token_a"])

    client.delete(f"{TASKS_ENDPOINT}/{task.id}", headers=headers)
    response = client.delete(f"{TASKS_ENDPOINT}/{task.id}", headers=headers)

    assert response.status_code == 404
