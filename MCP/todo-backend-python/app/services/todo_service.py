from datetime import datetime, timezone
from typing import List, Optional, Union

from app.database.repository import TodoRepository
from app.models.todo import Todo
from app.services.exceptions import InvalidTodoError, TodoNotFoundError

MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 1000


class _Unset:
    """Sentinel used to distinguish 'not provided' from an explicit null."""

    def __repr__(self) -> str:
        return "UNSET"


UNSET = _Unset()

OptionalText = Union[str, None, _Unset]
OptionalFlag = Union[bool, _Unset]


class TodoService:
    """Application layer containing todo business rules."""

    def __init__(self, repository: TodoRepository) -> None:
        self._repository = repository

    def create_todo(self, *, title: str, description: Optional[str] = None) -> Todo:
        return self._repository.create(
            title=self._normalize_title(title),
            description=self._normalize_description(description),
            created_at=self._now(),
        )

    def list_todos(self, *, completed: Optional[bool] = None) -> List[Todo]:
        return self._repository.find_all(completed=completed)

    def get_todo(self, todo_id: int) -> Todo:
        todo = self._repository.find_by_id(todo_id)
        if todo is None:
            raise TodoNotFoundError(todo_id)
        return todo

    def update_todo(
        self,
        todo_id: int,
        *,
        title: Union[str, _Unset] = UNSET,
        description: OptionalText = UNSET,
        completed: OptionalFlag = UNSET,
    ) -> Todo:
        current = self.get_todo(todo_id)

        resolved_title = current.title if isinstance(title, _Unset) else self._normalize_title(title)
        resolved_description = (
            current.description
            if isinstance(description, _Unset)
            else self._normalize_description(description)
        )
        resolved_completed = (
            current.completed if isinstance(completed, _Unset) else self._normalize_completed(completed)
        )

        updated = self._repository.update(
            todo_id,
            title=resolved_title,
            description=resolved_description,
            completed=resolved_completed,
            updated_at=self._now(),
        )
        if updated is None:
            raise TodoNotFoundError(todo_id)
        return updated

    def delete_todo(self, todo_id: int) -> None:
        if not self._repository.delete(todo_id):
            raise TodoNotFoundError(todo_id)

    @staticmethod
    def _normalize_title(title: str) -> str:
        if not isinstance(title, str):
            raise InvalidTodoError("title must be a string")

        normalized = title.strip()
        if not normalized:
            raise InvalidTodoError("title must not be blank")
        if len(normalized) > MAX_TITLE_LENGTH:
            raise InvalidTodoError(
                "title must be at most {0} characters".format(MAX_TITLE_LENGTH)
            )
        return normalized

    @staticmethod
    def _normalize_description(description: Optional[str]) -> Optional[str]:
        if description is None:
            return None
        if not isinstance(description, str):
            raise InvalidTodoError("description must be a string")

        normalized = description.strip()
        if not normalized:
            return None
        if len(normalized) > MAX_DESCRIPTION_LENGTH:
            raise InvalidTodoError(
                "description must be at most {0} characters".format(MAX_DESCRIPTION_LENGTH)
            )
        return normalized

    @staticmethod
    def _normalize_completed(completed: bool) -> bool:
        if not isinstance(completed, bool):
            raise InvalidTodoError("completed must be a boolean")
        return completed

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
