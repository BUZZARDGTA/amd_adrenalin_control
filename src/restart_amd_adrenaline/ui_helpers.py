"""UI-specific runtime type validation helpers."""

from PyQt6.QtWidgets import QHeaderView


class InvalidTypeError(TypeError):
    """Raised when a value is not the expected runtime type."""

    def __init__(self, field_name: str, expected_type: str, actual_type: str) -> None:
        """Build a consistent type-validation error message."""
        message = f"{field_name} must be {expected_type}, got {actual_type}"
        super().__init__(message)


def require_str(value: object, field_name: str) -> str:
    """Return value as a string, or raise if it is not a string."""
    if not isinstance(value, str):
        raise InvalidTypeError(field_name, "str", type(value).__name__)
    return value


def require_qheader_view(value: object, field_name: str) -> QHeaderView:
    """Return value as a QHeaderView, or raise if it is missing or invalid."""
    if not isinstance(value, QHeaderView):
        raise InvalidTypeError(field_name, "QHeaderView", type(value).__name__)
    return value
