from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 1000


class TodoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_TITLE_LENGTH)
    description: Optional[str] = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)


class TodoUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=MAX_TITLE_LENGTH)
    description: Optional[str] = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    completed: Optional[bool] = None


class TodoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str]
    completed: bool
    created_at: datetime
    updated_at: datetime
