import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

API_PREFIX = "/api/v1"


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(database_path=tmp_path / "todos.db"))
    with TestClient(app) as test_client:
        yield test_client


def create_todo(client, title="Write tests", description="Cover the CRUD flow"):
    return client.post(
        "{0}/todos".format(API_PREFIX),
        json={"title": title, "description": description},
    )


def test_create_and_fetch_todo(client):
    response = create_todo(client)

    assert response.status_code == 201
    created = response.json()
    assert created["id"] > 0
    assert created["title"] == "Write tests"
    assert created["description"] == "Cover the CRUD flow"
    assert created["completed"] is False
    assert created["created_at"] == created["updated_at"]

    fetched = client.get("{0}/todos/{1}".format(API_PREFIX, created["id"]))

    assert fetched.status_code == 200
    assert fetched.json() == created


def test_create_normalizes_whitespace(client):
    response = create_todo(client, title="  Ship it  ", description="   ")

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Ship it"
    assert body["description"] is None


def test_create_rejects_blank_title(client):
    response = create_todo(client, title="   ")

    assert response.status_code == 422
    assert response.json() == {"detail": "title must not be blank"}


def test_list_todos_is_newest_first_and_filters_completed(client):
    first = create_todo(client, title="First").json()
    second = create_todo(client, title="Second").json()
    client.patch("{0}/todos/{1}".format(API_PREFIX, first["id"]), json={"completed": True})

    all_todos = client.get("{0}/todos".format(API_PREFIX)).json()
    completed = client.get("{0}/todos?completed=true".format(API_PREFIX)).json()
    pending = client.get("{0}/todos?completed=false".format(API_PREFIX)).json()

    assert [todo["id"] for todo in all_todos] == [second["id"], first["id"]]
    assert [todo["title"] for todo in completed] == ["First"]
    assert [todo["title"] for todo in pending] == ["Second"]


def test_update_changes_only_provided_fields(client):
    created = create_todo(client).json()

    response = client.patch(
        "{0}/todos/{1}".format(API_PREFIX, created["id"]),
        json={"completed": True},
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["completed"] is True
    assert updated["title"] == created["title"]
    assert updated["description"] == created["description"]
    assert updated["updated_at"] >= created["updated_at"]


def test_update_can_clear_description(client):
    created = create_todo(client).json()

    response = client.patch(
        "{0}/todos/{1}".format(API_PREFIX, created["id"]),
        json={"description": None},
    )

    assert response.status_code == 200
    assert response.json()["description"] is None


def test_update_rejects_null_title(client):
    created = create_todo(client).json()

    response = client.patch(
        "{0}/todos/{1}".format(API_PREFIX, created["id"]),
        json={"title": None},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "title must be a string"}


def test_update_missing_todo_returns_404(client):
    response = client.patch("{0}/todos/999".format(API_PREFIX), json={"completed": True})

    assert response.status_code == 404
    assert response.json() == {"detail": "Todo 999 was not found"}


def test_delete_todo(client):
    created = create_todo(client).json()

    response = client.delete("{0}/todos/{1}".format(API_PREFIX, created["id"]))

    assert response.status_code == 204
    assert response.content == b""
    assert client.get("{0}/todos/{1}".format(API_PREFIX, created["id"])).status_code == 404


def test_delete_missing_todo_returns_404(client):
    response = client.delete("{0}/todos/999".format(API_PREFIX))

    assert response.status_code == 404


def test_health_check(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
