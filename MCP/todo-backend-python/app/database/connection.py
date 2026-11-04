import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class Database:
    """Owns the SQLite file and provides short-lived connections."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._schema_path = Path(__file__).with_name("schema.sql")

    @property
    def path(self) -> Path:
        return self._path

    def initialize(self) -> None:
        """Create the database file and apply the schema if needed."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(self._schema_path.read_text(encoding="utf-8"))

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a request-scoped connection that commits or rolls back."""
        connection = sqlite3.connect(str(self._path), check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
