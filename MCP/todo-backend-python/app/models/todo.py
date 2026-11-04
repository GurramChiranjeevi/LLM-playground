from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Todo:
    """Domain entity representing a single todo item."""

    id: int
    title: str
    description: Optional[str]
    completed: bool
    created_at: datetime
    updated_at: datetime
