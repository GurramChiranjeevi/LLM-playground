from typing import Iterator

from fastapi import Request

from app.database.connection import Database
from app.database.repository import TodoRepository
from app.services.todo_service import TodoService


def get_database(request: Request) -> Database:
    return request.app.state.database


def get_todo_service(request: Request) -> Iterator[TodoService]:
    """Build a service with a connection scoped to the current request."""
    database: Database = request.app.state.database
    with database.connect() as connection:
        yield TodoService(TodoRepository(connection))
