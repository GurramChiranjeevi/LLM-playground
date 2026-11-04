class TodoNotFoundError(Exception):
    """Raised when a todo cannot be found."""

    def __init__(self, todo_id: int) -> None:
        self.todo_id = todo_id
        super().__init__("Todo {0} was not found".format(todo_id))


class InvalidTodoError(Exception):
    """Raised when todo input violates a business rule."""
