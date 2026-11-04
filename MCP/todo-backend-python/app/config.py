import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATABASE_PATH = Path("todo.db")


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for the application."""

    database_path: Path

    @classmethod
    def from_environment(cls) -> "Settings":
        configured_path = os.getenv("TODO_DB_PATH")
        database_path = Path(configured_path) if configured_path else DEFAULT_DATABASE_PATH
        return cls(database_path=database_path)
