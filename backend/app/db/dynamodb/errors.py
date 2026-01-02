from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class DdbError(Exception):
    """Base error for DynamoDB operations.

    These are intended to be caught by a FastAPI exception handler and rendered
    into RFC7807 problem-details responses.
    """

    message: str
    operation: str | None = None
    table_name: str | None = None
    key: dict[str, Any] | None = None
    aws_request_id: str | None = None
    retryable: bool = False
    cause: Exception | None = None

    def __str__(self) -> str:
        return self.message


@dataclass(slots=True)
class DdbNotFound(DdbError):
    pass


@dataclass(slots=True)
class DdbConflict(DdbError):
    pass


@dataclass(slots=True)
class DdbValidation(DdbError):
    pass


@dataclass(slots=True)
class DdbThrottled(DdbError):
    pass


@dataclass(slots=True)
class DdbUnavailable(DdbError):
    pass


@dataclass(slots=True)
class DdbInternal(DdbError):
    pass




