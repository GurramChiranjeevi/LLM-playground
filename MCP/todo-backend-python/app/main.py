from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.routes import health, todos
from app.config import Settings
from app.database.connection import Database


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    resolved_settings = settings or Settings.from_environment()
    database = Database(resolved_settings.database_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database.initialize()
        yield

    app = FastAPI(
        title="Todo API",
        version="1.0.0",
        description="A layered Todo API built with FastAPI and SQLite.",
        lifespan=lifespan,
    )
    app.state.database = database

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(todos.router, prefix="/api/v1")

    return app


app = create_app()
