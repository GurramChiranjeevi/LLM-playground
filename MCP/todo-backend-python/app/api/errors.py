from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.services.exceptions import InvalidTodoError, TodoNotFoundError


def register_exception_handlers(app: FastAPI) -> None:
    """Translate service-layer errors into HTTP responses."""

    @app.exception_handler(TodoNotFoundError)
    async def handle_todo_not_found(
        request: Request, exc: TodoNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)},
        )

    @app.exception_handler(InvalidTodoError)
    async def handle_invalid_todo(
        request: Request, exc: InvalidTodoError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": str(exc)},
        )
