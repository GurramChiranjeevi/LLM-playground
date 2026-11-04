# Todo Backend (Python)

A clean, layered REST API for managing todos, built with **FastAPI** and **SQLite**. The project is backend-only and deliberately separates HTTP handling, business rules, and persistence so each layer can evolve and be tested independently.

## Highlights

- Layered architecture: **network -> service -> database**
- SQLite persistence with parameterized SQL and no ORM
- Pydantic request/response validation
- Domain-focused service layer with explicit error types
- Request-scoped database connections (safe connection lifecycle)
- Interactive OpenAPI docs at `/docs` and `/redoc`
- Test suite covering the full CRUD flow

## Requirements

- Python 3.9+
- `pip`

## Project structure

```text
todo-backend-python/
├── app/
│   ├── main.py                     # App factory, lifespan, router wiring
│   ├── config.py                   # Environment-based settings
│   ├── api/                        # NETWORK LAYER (HTTP)
│   │   ├── dependencies.py         # Dependency injection / wiring
│   │   ├── errors.py               # Service errors -> HTTP responses
│   │   └── routes/
│   │       ├── health.py
│   │       └── todos.py            # Todo endpoints
│   ├── services/                   # SERVICE LAYER (business rules)
│   │   ├── exceptions.py
│   │   └── todo_service.py
│   ├── database/                   # DATABASE LAYER (persistence)
│   │   ├── connection.py           # Connection lifecycle
│   │   ├── repository.py           # SQL queries only
│   │   └── schema.sql
│   ├── models/
│   │   └── todo.py                 # Domain entity
│   └── schemas/
│       └── todo.py                 # Request/response contracts
├── tests/
│   └── test_todos.py
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
└── README.md
```

### Request flow

```text
HTTP request
    |
    v
API route (app/api)              validates input, maps HTTP <-> service calls
    |
    v
TodoService (app/services)       enforces business rules, raises domain errors
    |
    v
TodoRepository (app/database)    executes SQL against SQLite
    |
    v
SQLite database file
```

Each layer only depends inward:

- Routes know about services; they do not write SQL.
- The service knows about the repository contract; it does not know HTTP.
- The repository knows about SQLite and domain entities; it does not know HTTP or business rules.

## Setup

```bash
cd todo-backend-python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the server

```bash
uvicorn app.main:app --reload
```

The API is served at `http://127.0.0.1:8000`.

Useful URLs:

- `GET /health` - health check
- `GET /docs` - Swagger UI
- `GET /redoc` - ReDoc
- `GET /openapi.json` - OpenAPI schema

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `TODO_DB_PATH` | `todo.db` | Path to the SQLite database file |

Example:

```bash
TODO_DB_PATH=./data/todos.db uvicorn app.main:app --reload
```

The database file and schema are created automatically on startup.

## API

Base path: `/api/v1`

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/todos` | Create a todo |
| `GET` | `/todos` | List todos (newest first) |
| `GET` | `/todos/{todo_id}` | Get a single todo |
| `PATCH` | `/todos/{todo_id}` | Partially update a todo |
| `DELETE` | `/todos/{todo_id}` | Delete a todo |

### Todo resource

```json
{
  "id": 1,
  "title": "Write documentation",
  "description": "Document every endpoint and layer",
  "completed": false,
  "created_at": "2026-11-04T10:00:00+00:00",
  "updated_at": "2026-11-04T10:00:00+00:00"
}
```

### Create a todo

```bash
curl -X POST http://127.0.0.1:8000/api/v1/todos \
  -H "Content-Type: application/json" \
  -d '{"title": "Write documentation", "description": "Document every endpoint"}'
```

`title` is required (1-200 characters after trimming). `description` is optional (up to 1000 characters).

### List todos

```bash
# All todos
curl http://127.0.0.1:8000/api/v1/todos

# Only completed todos
curl "http://127.0.0.1:8000/api/v1/todos?completed=true"

# Only pending todos
curl "http://127.0.0.1:8000/api/v1/todos?completed=false"
```

### Get a todo

```bash
curl http://127.0.0.1:8000/api/v1/todos/1
```

### Update a todo

Send only the fields you want to change. Omitted fields are left untouched. Sending `"description": null` clears the description.

```bash
curl -X PATCH http://127.0.0.1:8000/api/v1/todos/1 \
  -H "Content-Type: application/json" \
  -d '{"completed": true}'
```

### Delete a todo

```bash
curl -X DELETE http://127.0.0.1:8000/api/v1/todos/1
```

Returns `204 No Content` on success.

### Error format

Errors are returned as JSON:

```json
{ "detail": "Todo 999 was not found" }
```

| Status | Meaning |
| --- | --- |
| `400` | Reserved for malformed requests |
| `404` | Todo does not exist |
| `422` | Request validation or business rule failure |

## Tests

Install development dependencies and run the suite:

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests use a temporary SQLite database per test, so they do not touch your development database.

## Design notes

- **No ORM.** The repository uses explicit SQL with bound parameters to keep queries visible and safe from injection.
- **Domain entity vs. API schema.** `Todo` is a transport-agnostic dataclass; Pydantic schemas model only what the HTTP API accepts and returns.
- **Explicit service errors.** `TodoNotFoundError` and `InvalidTodoError` keep the service independent of HTTP status codes. The API layer maps them to responses.
- **Connection per request.** Each request gets a fresh connection that commits on success, rolls back on failure, and always closes.
- **Partial updates.** A sentinel value inside the service distinguishes "field omitted" from "explicit null", which is why `PATCH {"description": null}` clears the field while `PATCH {}` leaves it unchanged.
