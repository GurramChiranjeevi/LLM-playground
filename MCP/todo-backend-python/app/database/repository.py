import sqlite3
from datetime import datetime
from typing import List, Optional

from app.models.todo import Todo

_COLUMNS = "id, title, description, completed, created_at, updated_at"


class TodoRepository:
    """Persistence gateway for todos. The only layer that speaks SQL."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(
        self,
        *,
        title: str,
        description: Optional[str],
        created_at: datetime,
    ) -> Todo:
        timestamp = created_at.isoformat()
        cursor = self._connection.execute(
            """
            INSERT INTO todos (title, description, completed, created_at, updated_at)
            VALUES (?, ?, 0, ?, ?)
            """,
            (title, description, timestamp, timestamp),
        )
        todo_id = int(cursor.lastrowid)
        todo = self.find_by_id(todo_id)
        if todo is None:
            raise RuntimeError("Created todo could not be reloaded")
        return todo

    def find_by_id(self, todo_id: int) -> Optional[Todo]:
        row = self._connection.execute(
            "SELECT {columns} FROM todos WHERE id = ?".format(columns=_COLUMNS),
            (todo_id,),
        ).fetchone()
        return self._to_model(row) if row is not None else None

    def find_all(self, *, completed: Optional[bool] = None) -> List[Todo]:
        query = "SELECT {columns} FROM todos".format(columns=_COLUMNS)
        parameters: List[object] = []

        if completed is not None:
            query += " WHERE completed = ?"
            parameters.append(int(completed))

        query += " ORDER BY id DESC"
        rows = self._connection.execute(query, parameters).fetchall()
        return [self._to_model(row) for row in rows]

    def update(
        self,
        todo_id: int,
        *,
        title: str,
        description: Optional[str],
        completed: bool,
        updated_at: datetime,
    ) -> Optional[Todo]:
        cursor = self._connection.execute(
            """
            UPDATE todos
            SET title = ?, description = ?, completed = ?, updated_at = ?
            WHERE id = ?
            """,
            (title, description, int(completed), updated_at.isoformat(), todo_id),
        )
        if cursor.rowcount == 0:
            return None
        return self.find_by_id(todo_id)

    def delete(self, todo_id: int) -> bool:
        cursor = self._connection.execute(
            "DELETE FROM todos WHERE id = ?",
            (todo_id,),
        )
        return cursor.rowcount > 0

    @staticmethod
    def _to_model(row: sqlite3.Row) -> Todo:
        return Todo(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            completed=bool(row["completed"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
