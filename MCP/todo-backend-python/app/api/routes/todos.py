from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.dependencies import get_todo_service
from app.schemas.todo import TodoCreate, TodoResponse, TodoUpdate
from app.services.todo_service import TodoService

router = APIRouter(prefix="/todos", tags=["todos"])


@router.post("", response_model=TodoResponse, status_code=status.HTTP_201_CREATED)
def create_todo(
    payload: TodoCreate,
    service: TodoService = Depends(get_todo_service),
) -> TodoResponse:
    todo = service.create_todo(title=payload.title, description=payload.description)
    return TodoResponse.model_validate(todo)


@router.get("", response_model=List[TodoResponse])
def list_todos(
    completed: Optional[bool] = Query(default=None),
    service: TodoService = Depends(get_todo_service),
) -> List[TodoResponse]:
    return [
        TodoResponse.model_validate(todo)
        for todo in service.list_todos(completed=completed)
    ]


@router.get("/{todo_id}", response_model=TodoResponse)
def get_todo(
    todo_id: int,
    service: TodoService = Depends(get_todo_service),
) -> TodoResponse:
    return TodoResponse.model_validate(service.get_todo(todo_id))


@router.patch("/{todo_id}", response_model=TodoResponse)
def update_todo(
    todo_id: int,
    payload: TodoUpdate,
    service: TodoService = Depends(get_todo_service),
) -> TodoResponse:
    changes = payload.model_dump(exclude_unset=True)
    todo = service.update_todo(todo_id, **changes)
    return TodoResponse.model_validate(todo)


@router.delete("/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_todo(
    todo_id: int,
    service: TodoService = Depends(get_todo_service),
) -> Response:
    service.delete_todo(todo_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
